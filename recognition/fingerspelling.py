"""Fingerspelled letters from the hand landmarks, one `Letter` event per letter.

The letters go to the autocomplete (language/autocomplete.py), which suggests the whole
word; the utterance buffer turns the accepted word into one fingerspelled sign.

- `LetterModel`: a pretrained MLP on the 21 hand landmarks ("ASL Landmark MLP" by Doruk
  Dogular, trained on the ASL-HG dataset; CC BY-NC 4.0, so non-commercial use only).
  Downloaded to `models/letters/` on first use and run with ONNX Runtime (~1 ms). It
  knows A-Z and 0-9; only the letters are used. J and Z are drawn in the air, so a still
  handshape can't show them: keep them out of demo words.
- `LetterReader`: turns per-frame guesses into letters. A letter counts once its
  handshape is held still for `letter_hold_seconds`. The same letter again needs the hand
  to move or drop first (a double letter is signed with a small slide). Spelling starts
  only when two letters come within `letter_gap_seconds` of each other, so a sign's
  starting handshape isn't read as a letter; while spelling, signs other than YES / NO /
  FINISH are ignored (the recognizer asks `spelling`). Spelling ends after
  `letter_end_seconds` without a letter, or at a control sign.

Which way the model expects the hand (as the camera sees it, or mirrored) isn't
documented, so `letter_orientation: auto` tries both and keeps the surer one; set it to
`as_is` or `mirrored` once tools/try_letters.py shows which one your hand reads as.
"""

from __future__ import annotations

import json
import logging
import string
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from recognition.gating import SigningSpace
from shared.config import Config
from shared.events import LandmarkFrame, Letter, Point

log = logging.getLogger(__name__)

MODEL_URL = "https://huggingface.co/nocontextdoruk/asl-landmark-mlp/resolve/main/"
LETTERS = tuple(string.ascii_uppercase)
ORIENTATIONS = ("as_is", "mirrored")


def normalize(hand: Sequence[Point], mirrored: bool = False) -> np.ndarray:
    """The model's input: the wrist at the origin, scaled by wrist -> middle-finger base
    (landmark 9), flattened to 63 floats. `mirrored` flips left and right."""
    points = np.asarray(hand, dtype=np.float32)[:21]
    points = points - points[0]
    if mirrored:
        points[:, 0] = -points[:, 0]
    scale = float(np.linalg.norm(points[9])) or 1.0
    return (points / scale).reshape(1, -1)


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


class LetterModel:
    """The letter MLP. `predict` returns the likeliest letter and its probability among the
    letters (digits are dropped, since they look like letters: V/2, W/6, F/9, O/0)."""

    def __init__(self, config: Config, run=None, classes: Sequence[str] | None = None) -> None:
        self.orientation = str(config.get("recognition.letter_orientation", "auto"))
        if run is None:
            from recognition.isolated import ensure_file

            folder = config.path("recognition.letter_model_dir", "models/letters")
            base = str(config.get("recognition.letter_model_url", MODEL_URL))
            model = ensure_file(folder / "mlp_asl.onnx", base + "mlp_asl.onnx")
            names = ensure_file(folder / "mlp_classes.json", base + "mlp_classes.json")
            run = onnx_runner(model)
            mapping = json.loads(Path(names).read_text())  # a list, or {"0": "0", ...}
            if isinstance(mapping, dict):
                mapping = [mapping[str(i)] for i in range(len(mapping))]
            classes = [str(c) for c in mapping]
        self.run = run
        self.classes = list(classes or [])
        self.letter_index = [i for i, c in enumerate(self.classes) if c.upper() in LETTERS]
        self.last_orientation = ""

    def predict(self, hand: Sequence[Point]) -> tuple[str, float] | None:
        if len(hand) < 21:
            return None
        tries = ORIENTATIONS if self.orientation == "auto" else (self.orientation,)
        best: tuple[str, float] | None = None
        for orientation in tries:
            logits = np.asarray(self.run(normalize(hand, orientation == "mirrored")))
            probs = softmax(logits.reshape(-1)[self.letter_index])
            i = int(probs.argmax())
            if best is None or probs[i] > best[1]:
                best = (self.classes[self.letter_index[i]].upper(), float(probs[i]))
                self.last_orientation = orientation
        return best


def onnx_runner(path: Path):
    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("Letters need ONNX Runtime: run `uv sync --extra camera`") from exc
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    name = session.get_inputs()[0].name
    return lambda x: session.run(None, {name: x})[0]


@dataclass
class _Run:
    """The same guessed letter on consecutive frames, with the hand still."""

    letter: str
    start: float
    wrist: tuple[float, float]
    confidences: list[float] = field(default_factory=list)
    counted: bool = False


class LetterReader:
    def __init__(self, config: Config, model: LetterModel) -> None:
        self.model = model
        self.threshold = float(config.get("recognition.letter_threshold", 0.6))
        self.hold = float(config.get("recognition.letter_hold_seconds", 0.25))
        self.min_frames = int(config.get("recognition.letter_min_frames", 3))
        self.still = float(config.get("recognition.letter_still", 0.25))
        self.gap = float(config.get("recognition.letter_gap_seconds", 1.5))
        self.end_after = float(config.get("recognition.letter_end_seconds", 1.5))
        self.hand = str(config.get("recognition.letter_hand", "auto"))
        self.spelling = False  # letters are being published: other signs are ignored
        self._run: _Run | None = None
        self._last: str | None = None  # the last letter counted, until the hand moves
        self._pending: Letter | None = None  # a first letter, waiting for a second one
        self._last_time = 0.0

    def end(self) -> None:
        """Spelling is over (a control sign, or the hands went down)."""
        self.spelling = False
        self._pending = None
        self._run = None
        self._last = None

    def push(self, frame: LandmarkFrame, space: SigningSpace) -> list[Letter]:
        now = frame.ts
        if self.spelling and now - self._last_time > self.end_after:
            self.end()
        if self._pending is not None and now - self._pending.ts > self.gap:
            self._pending = None
        hand = self.spelling_hand(frame, space)
        guess = self.model.predict(hand) if hand else None
        if guess is None or guess[1] < self.threshold:
            self._run = None
            if hand is None:
                self._last = None  # the hand dropped or left: the same letter may come again
            return []
        letter, confidence = guess
        wrist = (hand[0][0], hand[0][1])
        size = float(np.hypot(hand[9][0] - hand[0][0], hand[9][1] - hand[0][1])) or 1.0
        run = self._run
        if run is not None:
            moved = np.hypot(wrist[0] - run.wrist[0], wrist[1] - run.wrist[1]) / size
            if moved > self.still:
                self._last = None  # moved: a double letter, or a sign
                run = None
            elif run.letter != letter:
                run = None
        if run is None:
            run = self._run = _Run(letter, now, wrist)
        run.confidences.append(confidence)
        held = now - run.start >= self.hold and len(run.confidences) >= self.min_frames
        if not held or run.counted or letter == self._last:
            return []
        run.counted = True
        self._last = letter
        mean = sum(run.confidences) / len(run.confidences)
        return self._count(Letter(letter, round(mean, 3), ts=now))

    def _count(self, letter: Letter) -> list[Letter]:
        self._last_time = letter.ts
        if self.spelling:
            return [letter]
        if self._pending is not None:
            first, self._pending = self._pending, None
            self.spelling = True
            log.debug("fingerspelling started")
            return [first, letter]
        self._pending = letter
        return []

    def spelling_hand(self, frame: LandmarkFrame, space: SigningSpace) -> tuple[Point, ...]:
        """The hand that's spelling: one hand in the signing space (two hands up means a
        two-handed sign), or the one `letter_hand` names."""
        if self.hand in ("left", "right"):
            hand = frame.left_hand if self.hand == "left" else frame.right_hand
            return hand if space.contains(hand) else ()
        up = [h for h in (frame.right_hand, frame.left_hand) if space.contains(h)]
        return up[0] if len(up) == 1 else ()


def letter_reader(config: Config) -> LetterReader | None:
    """The camera's letter reader, or None when `recognition.letters` is off."""
    if not config.get("recognition.letters", True):
        return None
    return LetterReader(config, LetterModel(config))
