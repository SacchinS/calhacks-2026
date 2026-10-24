"""Webcam capture + MediaPipe Holistic landmarks, published as LandmarkFrames.

Needs the camera extra: `uv sync --extra camera`. The Holistic model file is downloaded
to `models/` on first run, and so is the sign model. Signs come from recorded custom signs,
the Kaggle isolated-sign model, and fingerspelling (recognition.base.sign_classifiers).
Camera images stay in memory: they're drawn in the app's preview and never saved or sent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import urllib.request
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from recognition.base import FrameClassifier, FrameRecognizer, sign_classifiers
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)


def open_holistic(config: Config) -> Any:
    """Create a MediaPipe HolisticLandmarker in VIDEO mode, downloading the model if needed."""
    try:
        from mediapipe.tasks.python import BaseOptions, vision
    except ImportError as exc:
        raise RuntimeError("MediaPipe isn't installed: run `uv sync --extra camera`") from exc

    path = config.path("recognition.holistic_model_path", "models/holistic_landmarker.task")
    if not path.exists():
        url = config.get("recognition.holistic_model_url")
        log.info("downloading MediaPipe Holistic model to %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, path)
    options = vision.HolisticLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(path)),
        running_mode=vision.RunningMode.VIDEO,
    )
    return vision.HolisticLandmarker.create_from_options(options)


def holistic_to_frame(result: Any) -> LandmarkFrame:
    def points(landmarks) -> tuple:
        return tuple((lm.x, lm.y, lm.z) for lm in landmarks or ())

    return LandmarkFrame(
        left_hand=points(result.left_hand_landmarks),
        right_hand=points(result.right_hand_landmarks),
        pose=points(result.pose_landmarks),
        face=points(result.face_landmarks),
    )


class Camera:
    """Blocking webcam + Holistic wrapper, shared with tools/record_landmarks.py."""

    def __init__(self, config: Config) -> None:
        try:
            import cv2
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError("Camera needs `uv sync --extra camera`") from exc
        self._cv2, self._mp = cv2, mp
        self.landmarker = open_holistic(config)
        self.capture = cv2.VideoCapture(int(config.get("recognition.camera_index", 0)))
        if not self.capture.isOpened():
            self.landmarker.close()
            raise RuntimeError("Can't open the webcam (check macOS camera permission)")
        self._start = time.monotonic()

    def read(self) -> LandmarkFrame | None:
        ok, bgr = self.capture.read()
        if not ok:
            return None
        rgb = self._cv2.cvtColor(bgr, self._cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = int((time.monotonic() - self._start) * 1000)
        frame = holistic_to_frame(self.landmarker.detect_for_video(image, timestamp_ms))
        return replace(frame, image=rgb)

    def close(self) -> None:
        self.capture.release()
        self.landmarker.close()


class CameraRecognizer(FrameRecognizer):
    name = "camera"

    def __init__(self, bus, config: Config) -> None:
        super().__init__(bus, config)
        self.camera: Camera | None = None

    async def start(self) -> None:
        # Open on the main thread so failures (no MediaPipe, no permission) raise here and
        # the app can fall back to the mock recognizer.
        if self.camera is None:
            self.camera = Camera(self.config)
        await super().start()

    async def stop(self) -> None:
        await super().stop()
        if self.camera is not None:
            with contextlib.suppress(Exception):
                self.camera.close()
            self.camera = None

    async def frames(self) -> AsyncIterator[LandmarkFrame]:
        assert self.camera is not None
        while True:
            frame = await asyncio.to_thread(self.camera.read)
            if frame is None:
                await asyncio.sleep(0.05)
                continue
            yield frame

    def classifiers(self) -> list[FrameClassifier]:
        return sign_classifiers(self.config)
