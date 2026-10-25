"""ASL Citizen sign model: Microsoft's ST-GCN on MediaPipe Holistic points, 2,731 signs.

Set up once with tools/setup_asl_citizen.py (weights from microsoft/ASL-citizen-code, MIT,
exported to ONNX; the word list from the dataset, Microsoft Research License: research and
non-commercial use only). Runs with ONNX Runtime, ~20 ms per window on an M1.

The model sees 27 points (nose, eyes, shoulders, elbows, and 10 points of each hand), x and
y only, over 128 frames. Its training clips were whole videos of one sign, so we keep a
rolling window while the hands are in the signing space and run it every few frames, like
the Kaggle model (recognition/isolated.py). Each window gets the training code's own
preprocessing (ST-GCN/asl_citizen_dataset_pose.py): sample down or zero-pad to 128 frames,
then center on the shoulders and scale by their width, both averaged over the clip,
padding included.

`asl_citizen_signs` limits the answer to the signs the demo uses, so the model only has to
tell those apart. With that many signs it's sure of something for any movement (a still
pose reads as BOW3 at 99.9%), so a demo sign only counts when it's also among the
`asl_citizen_top_k` likeliest of all 2,731 and has at least `asl_citizen_min_prob` of the
whole model's probability (a still pose put THANKYOU 5th, at 2.8%). Variants (HOW1, HOW2)
come out as one gloss (HOW).
"""

from __future__ import annotations

import logging
import re
from collections import deque
from collections.abc import Sequence

import numpy as np

from recognition.base import FrameClassifier, Prediction
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)

FRAMES = 128
POSE, HAND = 33, 21
# Into the training code's 75-point order (pose 33, left hand 21, right hand 21).
KEYPOINTS = [0, 2, 5, 11, 12, 13, 14, 33, 37, 38, 41, 42, 45, 46, 49, 50, 53,
             54, 58, 59, 62, 63, 66, 67, 70, 71, 74]  # fmt: skip
# A mirror image swaps left and right: the pose's eyes, shoulders, elbows (and the rest).
POSE_MIRROR = [0, 4, 5, 6, 1, 2, 3, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15, 18, 17, 20, 19,
               22, 21, 24, 23, 26, 25, 28, 27, 30, 29, 32, 31]  # fmt: skip
DEMO_SIGNS = ["HELLO", "NICE", "MEET", "YES", "NO", "FINISH", "THANKYOU"]


def frame_points(frame: LandmarkFrame, mirrored: bool = False) -> np.ndarray:
    """(75, 2): pose, left hand, right hand, x and y; zeros where a part isn't seen."""
    out = np.zeros((POSE + 2 * HAND, 2), dtype=np.float32)
    left, right = frame.left_hand, frame.right_hand
    if mirrored:
        left, right = right, left
    for start, points, size in (
        (0, frame.pose, POSE),
        (POSE, left, HAND),
        (POSE + HAND, right, HAND),
    ):
        if points:
            part = np.asarray(points[:size], dtype=np.float32)[:, :2]
            if mirrored:
                part[:, 0] = 1.0 - part[:, 0]
            out[start : start + len(part)] = part
    if mirrored and frame.pose:
        out[:POSE] = out[:POSE][POSE_MIRROR]
    return out


def downsample(frames: np.ndarray, max_frames: int) -> np.ndarray:
    """The training code's downsample: keep frames at an even rate until max_frames."""
    increment = min(1.0, max_frames / len(frames))
    kept, total, taken = [], 0.0, 0
    for f in frames:
        total += increment
        if total > taken:
            taken += 1
            kept.append(f)
    return np.array(kept[:max_frames])


def clip_input(frames: Sequence[np.ndarray]) -> np.ndarray:
    """A window of frame_points -> the model input (1, 2, 128, 27), as in training."""
    data = np.stack(frames)
    if len(data) > FRAMES:
        data = downsample(data, FRAMES)
    if len(data) < FRAMES:
        data = np.pad(data, ((0, FRAMES - len(data)), (0, 0), (0, 0)))
    left, right = data[:, 11], data[:, 12]  # shoulders, padding frames included
    center = ((left + right) / 2).mean(axis=0)
    width = float(np.sqrt(((left - right) ** 2).sum(-1)).mean())
    if width != 0:
        data = (data - center) / width
    return np.transpose(data[:, KEYPOINTS], (2, 0, 1))[None].astype(np.float32)


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def display(gloss: str) -> str:
    """ASL Citizen's gloss in our style: variants merged (HOW1 -> HOW)."""
    return re.sub(r"\d+$", "", gloss.strip().upper()) or gloss


class ASLCitizenModel(FrameClassifier):
    def __init__(self, config: Config, run=None, glosses: Sequence[str] | None = None) -> None:
        self.config = config
        self.window = int(config.get("recognition.asl_citizen_window", 60))
        self.min_window = int(config.get("recognition.asl_citizen_min_frames", 15))
        self.stride = int(config.get("recognition.asl_citizen_stride", 4))
        self.floor = float(config.get("recognition.asl_citizen_floor", 0.5))
        self.top_k = int(config.get("recognition.asl_citizen_top_k", 10))
        self.min_prob = float(config.get("recognition.asl_citizen_min_prob", 0.1))
        self.mirror = str(config.get("recognition.asl_citizen_mirror", "false")).lower()
        self.gap_seconds = float(config.get("recognition.isolated_gap_seconds", 0.4))
        if run is None or glosses is None:
            run, glosses = self._load()
        self.run = run
        self.glosses = list(glosses)
        wanted = config.get("recognition.asl_citizen_signs", DEMO_SIGNS)
        self.allowed = self._allowed(wanted)
        self.frames: deque[LandmarkFrame] = deque(maxlen=self.window)
        self.last: Prediction | None = None
        self._last_ts: float | None = None
        self._since_run = 0

    def _load(self):
        folder = self.config.path("recognition.asl_citizen_dir", "models/asl_citizen")
        model, names = folder / "stgcn.onnx", folder / "glosses.txt"
        if not model.exists() or not names.exists():
            raise RuntimeError(
                "ASL Citizen isn't set up: run tools/setup_asl_citizen.py (see its docstring)"
            )
        import onnxruntime as ort

        session = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        return (lambda x: session.run(None, {"pose": x})[0]), names.read_text().split()

    def _allowed(self, wanted) -> list[int]:
        """Indexes of the allowed signs (all of a sign's variants); empty list = all signs."""
        if not wanted:
            return list(range(len(self.glosses)))
        # Unquoted YES / NO in a YAML list arrive as booleans.
        wanted = {
            display({True: "YES", False: "NO"}.get(w, w) if isinstance(w, bool) else str(w))
            for w in wanted
        }
        found = [i for i, g in enumerate(self.glosses) if display(g) in wanted]
        missing = wanted - {display(self.glosses[i]) for i in found}
        if missing:
            log.warning("ASL Citizen doesn't know: %s", ", ".join(sorted(missing)))
        return found

    def reset(self) -> None:
        self.frames.clear()
        self.last = None
        self._since_run = 0

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        if self._last_ts is not None and frame.ts - self._last_ts > self.gap_seconds:
            self.reset()
        self._last_ts = frame.ts
        self.frames.append(frame)
        self._since_run += 1
        if len(self.frames) >= self.min_window and self._since_run >= self.stride:
            self._since_run = 0
            self.last = self.classify(list(self.frames))
        return self.last

    def scores(self, frames: Sequence[LandmarkFrame], mirrored: bool) -> np.ndarray:
        x = clip_input([frame_points(f, mirrored) for f in frames])
        return softmax(np.asarray(self.run(x), dtype=np.float64).reshape(-1))

    def classify(self, frames: Sequence[LandmarkFrame]) -> Prediction | None:
        tries = {"auto": (False, True), "true": (True,)}.get(self.mirror, (False,))
        best: Prediction | None = None
        for mirrored in tries:
            probs = self.scores(frames, mirrored)
            top = set(np.argsort(probs)[::-1][: self.top_k].tolist())
            allowed = [i for i in self.allowed if i in top and probs[i] >= self.min_prob]
            if not allowed:
                continue
            # Probability among the allowed signs (variants of one sign added together).
            total = float(probs[self.allowed].sum()) or 1.0
            by_sign: dict[str, float] = {}
            for i in self.allowed:
                by_sign[display(self.glosses[i])] = by_sign.get(
                    display(self.glosses[i]), 0.0
                ) + float(probs[i])
            sign = display(self.glosses[max(allowed, key=lambda i: probs[i])])
            confidence = by_sign[sign] / total
            if confidence >= self.floor and (best is None or confidence > best.confidence):
                best = Prediction(sign, confidence, "isolated")
        return best

    def top(self, frames: Sequence[LandmarkFrame], k: int = 5, mirrored: bool = False):
        """The k likeliest of all 2,731 signs for a window (for tools and debugging)."""
        probs = self.scores(frames, mirrored)
        return [(self.glosses[i], float(probs[i])) for i in np.argsort(probs)[::-1][:k]]
