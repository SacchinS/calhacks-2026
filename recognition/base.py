"""Recognizer interface, plus the shared frame pipeline used by replay and camera.

A Recognizer publishes SignEvents to the bus. Landmark-based recognizers (replay, camera)
run every frame through: gating -> classifiers -> segmenter -> SignEvent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass

from shared.bus import Bus
from shared.config import Config
from shared.events import (
    CONTROL_ALIASES,
    CONTROL_SIGNS,
    FaceMarker,
    LandmarkFrame,
    SignEvent,
    SignKind,
)

log = logging.getLogger(__name__)


def make_sign_event(
    gloss: str,
    confidence: float,
    kind: SignKind = "isolated",
    markers: frozenset[FaceMarker] = frozenset(),
) -> SignEvent:
    """Build a SignEvent, uppercasing the gloss and turning control signs into kind=control."""
    gloss = gloss.strip().upper()
    gloss = CONTROL_ALIASES.get(gloss, gloss) if kind != "fingerspell" else gloss
    if gloss in CONTROL_SIGNS and kind != "fingerspell":
        kind = "control"
    confidence = max(0.0, min(1.0, confidence))
    if kind == "control":
        markers = frozenset()  # control signs are never translated
    return SignEvent(gloss=gloss, confidence=confidence, kind=kind, markers=markers)


class Recognizer(ABC):
    """Publishes SignEvents to the bus between start() and stop()."""

    name: str = "recognizer"

    def __init__(self, bus: Bus, config: Config) -> None:
        self.bus = bus
        self.config = config

    @abstractmethod
    async def start(self) -> None:
        """Start recognizing in the background and return once running."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop and release the camera/files. Safe to call more than once."""


@dataclass(frozen=True)
class Prediction:
    """One classifier's output for one frame."""

    gloss: str
    confidence: float
    kind: SignKind = "isolated"


class FrameClassifier(ABC):
    """Per-frame sign classifier (isolated signs, fingerspelling, fixture labels)."""

    @abstractmethod
    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        """Prediction for the sign in progress at this frame, or None if nothing is signed."""


class FrameRecognizer(Recognizer):
    """Base for recognizers that produce LandmarkFrames (replay, camera).

    Subclasses implement frames(); this class gates each frame, publishes it, runs the
    classifiers, and turns per-frame predictions into SignEvents with the segmenter.
    """

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        from recognition.gating import SigningSpace
        from recognition.segmenter import Segmenter

        self.gate = SigningSpace.from_config(config)
        self.segmenter = Segmenter.from_config(config)
        self._task: asyncio.Task[None] | None = None

    @abstractmethod
    def frames(self) -> AsyncIterator[LandmarkFrame]:
        """Yield LandmarkFrames until the source ends."""

    @abstractmethod
    def classifiers(self) -> list[FrameClassifier]:
        """Classifiers to try in order; the first non-None prediction wins."""

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"{self.name}-recognizer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        classifiers = self.classifiers()
        async for raw in self.frames():
            frame = self.gate.apply(raw)
            self.bus.publish(frame)
            prediction = None
            if frame.hands_in_signing_space:
                for classifier in classifiers:
                    prediction = classifier.predict(frame)
                    if prediction is not None:
                        break
            event = self.segmenter.push(prediction)
            if event is not None:
                log.info(
                    "%s recognized %s (%s, %.2f)",
                    self.name,
                    event.gloss,
                    event.kind,
                    event.confidence,
                )
                self.bus.publish(event)
