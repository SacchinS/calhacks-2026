"""Turns a stream of per-frame predictions into discrete SignEvents.

A sign is emitted once, after `min_frames` consecutive frames predict the same gloss with
a mean confidence of at least `confidence_threshold`. The same gloss is not emitted again
until the prediction changes or drops out (None), so holding a sign gives one event.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from recognition.base import make_sign_event
from shared.config import Config
from shared.events import SignEvent

if TYPE_CHECKING:
    from recognition.base import Prediction


class Segmenter:
    def __init__(self, min_frames: int = 5, confidence_threshold: float = 0.6) -> None:
        self.min_frames = min_frames
        self.confidence_threshold = confidence_threshold
        self.reset()

    @classmethod
    def from_config(cls, config: Config) -> Segmenter:
        return cls(
            min_frames=int(config.get("recognition.min_frames", 5)),
            confidence_threshold=float(config.get("recognition.confidence_threshold", 0.6)),
        )

    def reset(self) -> None:
        self._key: tuple[str, str] | None = None
        self._count = 0
        self._confidence_sum = 0.0
        self._emitted = False

    def push(self, prediction: Prediction | None) -> SignEvent | None:
        """Feed one frame's prediction; returns a SignEvent when a sign is complete."""
        if prediction is None:
            self.reset()
            return None
        key = (prediction.gloss, prediction.kind)
        if key != self._key:
            self.reset()
            self._key = key
        self._count += 1
        self._confidence_sum += prediction.confidence
        mean = self._confidence_sum / self._count
        if self._emitted or self._count < self.min_frames or mean < self.confidence_threshold:
            return None
        self._emitted = True
        return make_sign_event(prediction.gloss, mean, prediction.kind)
