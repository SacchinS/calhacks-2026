"""Signing-space gating: only recognize while the hands are up in front of the chest/face.

Resting hands and typing hands are low in the frame, so they fall outside the box and the
frame is marked `hands_in_signing_space=False`; classifiers never see it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from shared.config import Config
from shared.events import LandmarkFrame, Point


@dataclass(frozen=True)
class SigningSpace:
    """A box in normalized image coordinates (0..1, y grows downward)."""

    x_min: float = 0.1
    x_max: float = 0.9
    y_min: float = 0.05
    y_max: float = 0.8

    @classmethod
    def from_config(cls, config: Config) -> SigningSpace:
        box = config.get("recognition.signing_space", {}) or {}
        return cls(**{k: float(v) for k, v in box.items()})

    def contains(self, hand: tuple[Point, ...]) -> bool:
        """True if the hand's center is inside the box."""
        if not hand:
            return False
        x = sum(p[0] for p in hand) / len(hand)
        y = sum(p[1] for p in hand) / len(hand)
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def hands_in_space(self, frame: LandmarkFrame) -> bool:
        # TODO(Person A): tune with real webcam data, e.g. derive the box from the pose
        # (shoulders/face) instead of a fixed box, and require the dominant hand.
        return self.contains(frame.left_hand) or self.contains(frame.right_hand)

    def apply(self, frame: LandmarkFrame) -> LandmarkFrame:
        """The same frame with hands_in_signing_space computed from its landmarks."""
        return replace(frame, hands_in_signing_space=self.hands_in_space(frame))
