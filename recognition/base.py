"""Recognizer interface, plus the shared frame pipeline used by replay and camera.

A Recognizer publishes SignEvents to the bus. Landmark-based recognizers (replay, camera)
run every frame through: gating -> classifiers -> segmenter -> SignEvent, and through the
letter reader (recognition/fingerspelling.py) -> Letter events for fingerspelling.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, replace

from shared.bus import Bus
from shared.config import Config
from shared.events import (
    CONTROL_ALIASES,
    CONTROL_SIGNS,
    FaceMarker,
    LandmarkFrame,
    Notice,
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


def sign_classifiers(config: Config) -> list[FrameClassifier]:
    """The real sign models, in the order tried: custom signs (only when clearly matched),
    then the Kaggle isolated-sign model. Fingerspelled letters are read separately
    (FrameRecognizer.letter_reader)."""
    from recognition.custom_signs import CustomSignModel
    from recognition.isolated import IsolatedSignModel

    return [CustomSignModel(config), IsolatedSignModel(config)]


class FrameRecognizer(Recognizer):
    """Base for recognizers that produce LandmarkFrames (replay, camera).

    Subclasses implement frames(); this class gates each frame, publishes it, runs the
    classifiers, and turns per-frame predictions into SignEvents with the segmenter. With a
    letter reader, it also publishes fingerspelled Letters, and while a word is being spelled
    only control signs (YES / NO / FINISH) get through.
    """

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        from recognition.face_markers import FaceMarkerDetector, MarkerTally
        from recognition.gating import SigningSpace
        from recognition.segmenter import Segmenter

        self.gate = SigningSpace.from_config(config)
        self.segmenter = Segmenter.from_config(config)
        self.faces = FaceMarkerDetector(config)
        self.markers = MarkerTally()
        self.letters = None  # the letter reader, once running (the app shows its hold)
        self._task: asyncio.Task[None] | None = None

    @abstractmethod
    def frames(self) -> AsyncIterator[LandmarkFrame]:
        """Yield LandmarkFrames until the source ends."""

    @abstractmethod
    def classifiers(self) -> list[FrameClassifier]:
        """Classifiers to try in order; the first non-None prediction wins."""

    def letter_reader(self):
        """The fingerspelled-letter reader (recognition.fingerspelling.LetterReader), or None."""
        return None

    def _letters(self):
        try:
            return self.letter_reader()
        except Exception as exc:  # no model download, no ONNX Runtime: signs still work
            log.exception("letter reader failed to load")
            self.bus.publish(Notice("warning", f"Fingerspelled letters are off ({exc})"))
            return None

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
        from recognition.segmenter import is_control

        classifiers = self.classifiers()
        letters = self.letters = self._letters()
        async for raw in self.frames():
            frame = self.gate.apply(raw)
            self.bus.publish(frame)
            prediction = None
            if frame.hands_in_signing_space:
                # Every classifier sees every frame (they keep windows); the first answer wins.
                answers = [classifier.predict(frame) for classifier in classifiers]
                prediction = next((a for a in answers if a is not None), None)
                self.markers.add(self.faces.update(frame))
            else:
                self.faces.update(frame)  # resting frames teach the neutral face
            if letters is not None:
                for letter in letters.push(frame, self.gate):
                    self.bus.publish(letter)
                if letters.spelling and prediction is not None and not is_control(prediction.gloss):
                    prediction = None  # spelling: a handshape isn't a sign
            event = self.segmenter.push(prediction)
            if event is not None and letters is not None and event.kind == "control":
                letters.end()  # YES / NO / FINISH: the word is done
            if event is not None:
                markers = self.markers.take()
                if event.kind != "control" and markers:
                    event = replace(event, markers=markers)
                log.debug(
                    "%s recognized %s (%s, %.2f)",
                    self.name,
                    event.gloss,
                    event.kind,
                    event.confidence,
                )
                self.bus.publish(event)
