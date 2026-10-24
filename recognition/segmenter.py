"""Turns a stream of per-frame predictions into discrete SignEvents.

A sign is emitted once, after `min_frames` consecutive frames predict the same gloss with
a mean confidence of at least `confidence_threshold`. The same gloss is not emitted again
until the prediction changes or drops out (None), so holding a sign gives one event.

Control signs (YES, NO, FINISH = SEND) need a longer hold, `control_min_frames`: FINISH also
means "already" or "done" inside a sentence (FINISH BUY = "already bought"), so a quick
FINISH mid-sentence must not send. Hold it to send.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from recognition.base import make_sign_event
from shared.config import Config
from shared.events import CONTROL_ALIASES, CONTROL_SIGNS, SignEvent

if TYPE_CHECKING:
    from recognition.base import Prediction


class Segmenter:
    def __init__(
        self,
        min_frames: int = 5,
        confidence_threshold: float = 0.6,
        control_min_frames: int | None = None,
    ) -> None:
        self.min_frames = min_frames
        self.confidence_threshold = confidence_threshold
        self.control_min_frames = control_min_frames or 2 * min_frames
        self.reset()

    @classmethod
    def from_config(cls, config: Config) -> Segmenter:
        return cls(
            min_frames=int(config.get("recognition.min_frames", 5)),
            confidence_threshold=float(config.get("recognition.confidence_threshold", 0.6)),
            control_min_frames=int(config.get("recognition.control_min_frames", 0)) or None,
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
        needed = self.min_frames
        if prediction.kind != "fingerspell" and is_control(prediction.gloss):
            needed = self.control_min_frames
        if self._emitted or self._count < needed or mean < self.confidence_threshold:
            return None
        self._emitted = True
        return make_sign_event(prediction.gloss, mean, prediction.kind)


def is_control(gloss: str) -> bool:
    gloss = gloss.strip().upper()
    return CONTROL_ALIASES.get(gloss, gloss) in CONTROL_SIGNS
