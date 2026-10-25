"""Fingerspelled letters from the hand landmarks, one `Letter` event per letter.

The letters go to the autocomplete (language/autocomplete.py), which suggests the whole
word; the utterance buffer turns the accepted word into one fingerspelled sign.

- `LetterModel`: a pretrained MLP on the 21 hand landmarks ("ASL Landmark MLP" by Doruk
  Dogular, trained on the ASL-HG dataset; CC BY-NC 4.0, so non-commercial use only).
  Downloaded to `models/letters/` on first use and run with ONNX Runtime (~1 ms). It
  knows A-Z and 0-9; only the letters are used. J and Z are drawn in the air, so a still
  handshape can't show them: keep them out of demo words. `letter_set` limits the letters
  to the ones the demo spells (the best of those wins, but only if it's also among the
  model's `letter_top_k` likeliest letters, so a handshape that's clearly another letter,
  or no letter, isn't forced into one).
- `LetterReader`: turns per-frame guesses into letters. A letter counts once its
  handshape is held still for `letter_hold_seconds`; a different letter has to last
  `letter_switch_seconds` to take over, so a flicker doesn't restart the hold, and a
  tracking blip under `letter_release_seconds` doesn't count as dropping the hand. The
  same letter again needs a different letter or the hand down in between, or with
  `letter_slide_doubles` a small slide (how fluent signers sign a double letter). With
  `letter_start_count: 2`, spelling starts only when two letters come within
  `letter_gap_seconds`, so a sign's starting handshape isn't read as a letter (1 = every
  letter counts at once, fine with a long hold). While spelling, signs other than YES /
  NO / FINISH are ignored (the recognizer asks `spelling`). Spelling ends after
  `letter_end_seconds` without a letter, or at a control sign. `holding` is the letter
  being held and how far along, for the app's progress bar.

Which way the model expects the hand (as the camera sees it, or mirrored) isn't
documented, so `letter_orientation: auto` tries both and follows the one that has been
surer so far (switching every frame would break up a held letter); set it to `as_is` or
`mirrored` once tools/try_letters.py shows which one your hand reads as.
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
        allowed = str(config.get("recognition.letter_set", "") or "").upper()
        names = [self.classes[i].upper() for i in self.letter_index]
        self.allowed = [k for k, name in enumerate(names) if not allowed or name in allowed]
        self.top_k = int(config.get("recognition.letter_top_k", 3))
        self.last_orientation = ""
        self.scores = dict.fromkeys(ORIENTATIONS, 0.0)  # auto: how sure each has been

    def predict(self, hand: Sequence[Point]) -> tuple[str, float] | None:
        if len(hand) < 21:
            return None
        tries = ORIENTATIONS if self.orientation == "auto" else (self.orientation,)
        guesses = {o: self.guess(hand, o == "mirrored") for o in tries}
        if len(guesses) == 1:
            (self.last_orientation,) = guesses
        else:
            for o, g in guesses.items():
                if g is not None and g[1] >= 0.5:
                    self.scores[o] += g[1]
            if any(self.scores.values()):
                self.last_orientation = max(self.scores, key=self.scores.__getitem__)
            else:
                self.last_orientation = max(guesses, key=lambda o: (guesses[o] or ("", 0))[1])
        return guesses[self.last_orientation]

    def ranked(self, hand: Sequence[Point], mirrored: bool, n: int = 5) -> list[tuple[str, float]]:
        """The model's n likeliest of all 26 letters, ignoring letter_set (for diagnosis)."""
        logits = np.asarray(self.run(normalize(hand, mirrored))).reshape(-1)[self.letter_index]
        probs = softmax(logits)
        order = np.argsort(probs)[::-1][:n]
        return [(self.classes[self.letter_index[i]].upper(), float(probs[i])) for i in order]

    def guess(self, hand: Sequence[Point], mirrored: bool) -> tuple[str, float] | None:
        """The likeliest allowed letter and its probability among the allowed letters, or
        None when no allowed letter is among the model's top_k."""
        logits = np.asarray(self.run(normalize(hand, mirrored))).reshape(-1)[self.letter_index]
        if len(self.allowed) < len(self.letter_index):
            top = set(np.argsort(logits)[::-1][: self.top_k].tolist())
            if not top & set(self.allowed):
                return None
        probs = softmax(logits[self.allowed])
        i = int(probs.argmax())
        return self.classes[self.letter_index[self.allowed[i]]].upper(), float(probs[i])


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
    challenger: str = ""  # another letter showing up: since when, and how sure
    challenger_since: float = 0.0
    challenger_confidences: list[float] = field(default_factory=list)


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
        # Fingerspelling is done in front of the shoulder; a hand up by the face is signing
        # (HELLO starts at the forehead with a flat hand that reads as a letter).
        self.below_mouth = bool(config.get("recognition.letter_below_mouth", True))
        self.switch = float(config.get("recognition.letter_switch_seconds", 0.3))
        self.release = float(config.get("recognition.letter_release_seconds", 0.5))
        self.slide_doubles = bool(config.get("recognition.letter_slide_doubles", True))
        self.start_count = int(config.get("recognition.letter_start_count", 2))
        self.spelling = False  # letters are being published: other signs are ignored
        self._run: _Run | None = None
        self._last: str | None = None  # the last letter counted: it can't count again yet
        self._pending: Letter | None = None  # a first letter, waiting for a second one
        self._last_time = 0.0
        self._seen = 0.0  # when the spelling hand was last seen
        self._now = 0.0
        self.status = ""  # why the last frame did or didn't count (tools/try_letters.py)

    def end(self) -> None:
        """Spelling is over (a control sign, or the hands went down)."""
        self.spelling = False
        self._pending = None
        self._run = None
        self._last = None

    @property
    def holding(self) -> tuple[str, float] | None:
        """The letter being held and how far to counting it (0..1), or None."""
        run = self._run
        if run is None or run.counted or run.letter == self._last or not run.confidences:
            return None
        return run.letter, min(1.0, (self._now - run.start) / self.hold) if self.hold else 1.0

    def push(self, frame: LandmarkFrame, space: SigningSpace) -> list[Letter]:
        now = self._now = frame.ts
        if self.spelling and now - self._last_time > self.end_after:
            self.spelling = False  # the word is over, but a letter being held still counts
        if self._pending is not None and now - self._pending.ts > self.gap:
            self._pending = None
        hand = self.spelling_hand(frame, space)
        if hand and self.below_mouth and self.by_the_face(hand, frame.pose):
            self._run = None
            self.status = "hand by the face: signing, not spelling"
            return []
        if not hand:
            if now - self._seen > self.release:  # gone, not a tracking blip
                self._run = None
                self._last = None  # the hand dropped: the same letter may come again
            self.status = "raise one hand into the box"
            return []
        self._seen = now
        guess = self.model.predict(hand)
        if guess is None or guess[1] < self.threshold:
            self.status = f"unsure ({guess[1]:.0%})" if guess else "not one of the letters"
            return []  # one unsure frame doesn't break a hold
        letter, confidence = guess
        wrist = (hand[0][0], hand[0][1])
        size = float(np.hypot(hand[9][0] - hand[0][0], hand[9][1] - hand[0][1])) or 1.0
        run = self._run
        if run is not None:
            moved = np.hypot(wrist[0] - run.wrist[0], wrist[1] - run.wrist[1]) / size
            if moved > self.still:
                if self.slide_doubles:
                    self._last = None  # moved: a double letter, or a sign
                run = None
            elif run.letter != letter:
                if run.challenger != letter:
                    run.challenger, run.challenger_since = letter, now
                    run.challenger_confidences = []
                run.challenger_confidences.append(confidence)
                if now - run.challenger_since < self.switch:
                    self.status = f"holding {run.letter}"
                    return []  # a flicker: keep holding
                # It lasted: the new letter, held since it first showed.
                seen = run.challenger_confidences[:-1]
                run = _Run(letter, run.challenger_since, wrist, seen)
                self._run = run
            else:
                run.challenger = ""
        if run is None:
            run = self._run = _Run(letter, now, wrist)
        run.confidences.append(confidence)
        held = now - run.start >= self.hold and len(run.confidences) >= self.min_frames
        if run.counted or letter == self._last:
            again = "slide or drop your hand" if self.slide_doubles else "drop your hand"
            self.status = f"{letter} counted; next letter ({again} for a double)"
            return []
        if not held:
            self.status = f"holding {letter} {now - run.start:.1f}/{self.hold:g} s"
            return []
        run.counted = True
        self._last = letter
        mean = sum(run.confidences) / len(run.confidences)
        return self._count(Letter(letter, round(mean, 3), ts=now))

    def _count(self, letter: Letter) -> list[Letter]:
        self._last_time = letter.ts
        self.status = f"{letter.letter} counted"
        if self.spelling or self.start_count <= 1:
            self.spelling = True
            return [letter]
        if self._pending is not None:
            first, self._pending = self._pending, None
            self.spelling = True
            log.debug("fingerspelling started")
            return [first, letter]
        self._pending = letter
        self.status = f"{letter.letter} held: shows once a second letter comes"
        return []

    @staticmethod
    def by_the_face(hand: Sequence[Point], pose: Sequence[Point]) -> bool:
        """The wrist is above the mouth (pose points 9 and 10; y grows downward)."""
        if len(pose) < 11:
            return False
        return hand[0][1] < (pose[9][1] + pose[10][1]) / 2

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
