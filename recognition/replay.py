"""Replays a landmark fixture (.jsonl, one LandmarkFrame per line) as if from a webcam.

Each line: {"left_hand": [[x, y, z], ...], "right_hand": [...], "pose": [...],
"face": [...], "label": "MAKE" | "#TITLE" | null, "t": 0.033}. `label` is the ground-truth
gloss (`#` = fingerspelled); null while no sign is being made. `t` (optional) is seconds
since the recording started (tools/record_script.py writes it; tools/tune_recognition.py
uses it for frame timing).

By default the replay classifies frames from their labels, so it produces the right
SignEvents before any model works. Set `recognition.replay_classifier: model` to run the
real models on the replayed landmarks instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

from recognition.base import FrameClassifier, FrameRecognizer, Prediction, sign_classifiers
from shared.events import LandmarkFrame, Notice

log = logging.getLogger(__name__)


def frame_to_json(frame: LandmarkFrame, t: float | None = None) -> dict[str, Any]:
    def points(pts):
        return [[round(c, 4) for c in p] for p in pts]

    data = {
        "left_hand": points(frame.left_hand),
        "right_hand": points(frame.right_hand),
        "pose": points(frame.pose),
        "face": points(frame.face),
        "label": frame.label,
    }
    if t is not None:
        data["t"] = round(t, 4)
    return data


def frame_from_json(data: dict[str, Any]) -> LandmarkFrame:
    def points(key):
        return tuple(tuple(float(c) for c in p) for p in data.get(key) or ())

    return LandmarkFrame(
        left_hand=points("left_hand"),
        right_hand=points("right_hand"),
        pose=points("pose"),
        face=points("face"),
        label=data.get("label"),
    )


def read_fixture(path: Path) -> Iterator[LandmarkFrame]:
    with path.open() as f:
        for line in f:
            if line.strip():
                yield frame_from_json(json.loads(line))


class FixtureLabelClassifier(FrameClassifier):
    """Mock classifier: predicts the fixture's ground-truth label for each frame."""

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        if not frame.label:
            return None
        if frame.label.startswith("#"):
            return Prediction(frame.label[1:], 0.95, "fingerspell")
        return Prediction(frame.label, 0.95, "isolated")


class ReplayRecognizer(FrameRecognizer):
    name = "replay"

    @property
    def path(self) -> Path:
        return self.config.path("recognition.replay_file", "fixtures/landmarks_sample.jsonl")

    async def frames(self) -> AsyncIterator[LandmarkFrame]:
        fps = float(self.config.get("recognition.replay_fps", 30))
        log.info("replaying %s at %s fps", self.path, fps)
        for frame in read_fixture(self.path):
            yield frame
            await asyncio.sleep(1 / fps)
        self.bus.publish(Notice("info", f"Replay of {self.path.name} finished"))

    def classifiers(self) -> list[FrameClassifier]:
        if self.config.get("recognition.replay_classifier", "labels") == "model":
            return sign_classifiers(self.config)
        return [FixtureLabelClassifier()]
