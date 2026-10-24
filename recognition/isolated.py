"""Isolated sign model: the Kaggle ISLR 2023 1st-place TFLite model (250 signs, MIT).

Model: `sign/kaggle-asl-signs-1st-place` on Hugging Face, downloaded to models/islr/ on
first use. Needs the camera extra (`uv sync --extra camera`, which has the LiteRT runtime).

The model takes a window of frames of the 543 MediaPipe Holistic landmarks, in the
competition's order (face 468, left hand 21, pose 33, right hand 21; x, y, z; NaN when a
part isn't detected) and returns 250 logits. We keep a rolling window while the hands are
in the signing space, run the model every few frames, and report the top sign until the
next run, so the segmenter sees a steady per-frame prediction.

Glosses are uppercased to our style ("thankyou" -> "THANKYOU"); YES / NO / FINISH become
control signs in make_sign_event.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np

from recognition.base import FrameClassifier, Prediction
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)

MODEL_URL = "https://huggingface.co/sign/kaggle-asl-signs-1st-place/resolve/main/"
FACE, HAND, POSE = 468, 21, 33
LANDMARKS = FACE + HAND + POSE + HAND  # 543


def frame_array(frame: LandmarkFrame) -> np.ndarray:
    """One frame as the competition's (543, 3) array, NaN where a part is missing."""
    out = np.full((LANDMARKS, 3), np.nan, dtype=np.float32)
    for start, points, size in (
        (0, frame.face, FACE),
        (FACE, frame.left_hand, HAND),
        (FACE + HAND, frame.pose, POSE),
        (FACE + HAND + POSE, frame.right_hand, HAND),
    ):
        if points:
            part = np.asarray(points[:size], dtype=np.float32)
            out[start : start + len(part)] = part
    return out


def softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


def ensure_file(path: Path, url: str) -> Path:
    if not path.exists():
        log.info("downloading %s", path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(path)
    return path


class IsolatedSignModel(FrameClassifier):
    def __init__(self, config: Config, runner=None, labels: list[str] | None = None) -> None:
        self.config = config
        self.window = int(config.get("recognition.isolated_window", 48))
        self.min_window = int(config.get("recognition.isolated_min_frames", 12))
        self.stride = int(config.get("recognition.isolated_stride", 4))
        self.floor = float(config.get("recognition.isolated_floor", 0.3))
        # A gap this long (hands left the signing space) starts a fresh window.
        self.gap_seconds = float(config.get("recognition.isolated_gap_seconds", 0.4))
        self.runner = runner
        self.labels = labels
        if runner is None or labels is None:
            self._load()
        self.frames: deque[np.ndarray] = deque(maxlen=self.window)
        self.last: Prediction | None = None
        self._last_ts: float | None = None
        self._since_run = 0

    def _load(self) -> None:
        try:
            from ai_edge_litert.interpreter import Interpreter
        except ImportError as exc:
            raise RuntimeError("the sign model needs `uv sync --extra camera`") from exc
        folder = self.config.path("recognition.isolated_model_dir", "models/islr")
        model = ensure_file(folder / "model.tflite", MODEL_URL + "model.tflite")
        index = ensure_file(
            folder / "sign_to_prediction_index_map.json",
            MODEL_URL + "sign_to_prediction_index_map.json",
        )
        self.runner = Interpreter(str(model)).get_signature_runner("serving_default")
        by_index = {i: sign for sign, i in json.loads(index.read_text()).items()}
        self.labels = [by_index[i].upper() for i in range(len(by_index))]

    def reset(self) -> None:
        self.frames.clear()
        self.last = None
        self._since_run = 0

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        if self._last_ts is not None and frame.ts - self._last_ts > self.gap_seconds:
            self.reset()
        self._last_ts = frame.ts
        self.frames.append(frame_array(frame))
        self._since_run += 1
        if len(self.frames) >= self.min_window and self._since_run >= self.stride:
            self._since_run = 0
            self.last = self.classify(np.stack(self.frames))
        return self.last

    def classify(self, window: np.ndarray) -> Prediction | None:
        probs = softmax(np.asarray(self.runner(inputs=window)["outputs"], dtype=np.float64))
        best = int(probs.argmax())
        if probs[best] < self.floor:
            return None
        return Prediction(self.labels[best], float(probs[best]), "isolated")

    def top(self, window: np.ndarray, k: int = 5) -> list[tuple[str, float]]:
        """The k most likely signs for a window (for tools and debugging)."""
        probs = softmax(np.asarray(self.runner(inputs=window)["outputs"], dtype=np.float64))
        return [(self.labels[i], float(probs[i])) for i in np.argsort(probs)[::-1][:k]]
