"""Fingerspelling model. STUB: logs that it's a stub and predicts nothing."""

from __future__ import annotations

import logging

from recognition.base import FrameClassifier, Prediction
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)


class FingerspellingModel(FrameClassifier):
    """TODO(Person A): run a winning Kaggle "Google - ASL Fingerspelling" (2023) model.

    - Use a released top solution's TFLite export (it takes a sequence of hand + pose
      landmarks and outputs a character string). Store files in `models/` (gitignored).
    - Buffer frames while fingerspelling is going on (dominant hand in the signing space,
      little arm motion), run the model when the hand pauses or drops, and return
      Prediction(word.upper(), confidence, kind="fingerspell") for the whole word.
    - Decide with the isolated model which one wins: e.g. only fingerspell when the isolated
      model's confidence is low.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        log.warning("FingerspellingModel is a stub: no fingerspelling will be recognized")

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        return None
