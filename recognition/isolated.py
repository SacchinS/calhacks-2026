"""Isolated sign model. STUB: logs that it's a stub and predicts nothing."""

from __future__ import annotations

import logging

from recognition.base import FrameClassifier, Prediction
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)


class IsolatedSignModel(FrameClassifier):
    """TODO(Person A): run the Kaggle ISLR 2023 1st-place model.

    - Model: `sign/kaggle-asl-signs-1st-place` on Hugging Face (MIT license). Download
      `model.tflite` (11.2 MB) and `sign_to_prediction_index_map.json` (250 signs) into
      `models/` (gitignored), with paths in config.yaml under `recognition:`.
    - Runtime: TFLite (`ai-edge-litert` or `tflite-runtime`), added to the `camera` extra.
    - Input: the model takes a window of frames of the 543 MediaPipe Holistic landmarks
      (face 468 + left hand 21 + pose 33 + right hand 21, x/y/z, NaN when missing).
      Buffer frames here, build that array, and run the model every few frames.
    - Output: the top gloss and its probability as a Prediction(kind="isolated"), uppercased
      to match our gloss style (e.g. "thankyou" -> "THANKYOU"). Return None below a floor.
    - YES / NO / FINISH come out as normal glosses; make_sign_event turns them into control
      signs (FINISH -> SEND).
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        log.warning("IsolatedSignModel is a stub: no signs will be recognized from landmarks")

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        return None
