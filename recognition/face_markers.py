"""Facial grammar from the Holistic face landmarks: raised or furrowed brows, head shakes
and nods. Set on each SignEvent as `markers`; Utterance.gloss turns them into `/\\`,
`[yes/no question]`, `[wh-question]`, `[negation]`, `[affirmation]` for the translator.

Measured per signer: the neutral face is learned from frames where the hands are down
(resting, so the face is usually neutral), and a marker counts only when it's clearly
away from that. Off by default (`recognition.face_markers: true` turns it on); check it
with a Deaf signer before relying on it, since a wrong [negation] flips the meaning.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from shared.config import Config
from shared.events import FaceMarker, LandmarkFrame

# MediaPipe face mesh indices.
LEFT_BROW, RIGHT_BROW = (70, 63, 105, 66, 107), (300, 293, 334, 296, 336)
LEFT_EYE_TOP, RIGHT_EYE_TOP = 159, 386
LEFT_EYE_OUT, RIGHT_EYE_OUT = 33, 263
INNER_BROWS = (107, 336)
NOSE, FOREHEAD, CHIN, CHEEK_L, CHEEK_R = 1, 10, 152, 234, 454


def face_measures(face: tuple) -> dict[str, float] | None:
    """Brow height, inner-brow gap, yaw and pitch for one frame (scale-free), or None."""
    if len(face) < 468:
        return None
    p = np.asarray(face[:468], dtype=np.float32)[:, :2]
    eyes = float(np.linalg.norm(p[LEFT_EYE_OUT] - p[RIGHT_EYE_OUT])) or 1.0
    brow_l = p[list(LEFT_BROW), 1].mean()
    brow_r = p[list(RIGHT_BROW), 1].mean()
    height = ((p[LEFT_EYE_TOP, 1] - brow_l) + (p[RIGHT_EYE_TOP, 1] - brow_r)) / 2 / eyes
    gap = float(np.linalg.norm(p[INNER_BROWS[0]] - p[INNER_BROWS[1]])) / eyes
    width = float(p[CHEEK_R, 0] - p[CHEEK_L, 0]) or 1.0
    yaw = float(p[NOSE, 0] - (p[CHEEK_L, 0] + p[CHEEK_R, 0]) / 2) / width
    length = float(p[CHIN, 1] - p[FOREHEAD, 1]) or 1.0
    pitch = float(p[NOSE, 1] - (p[FOREHEAD, 1] + p[CHIN, 1]) / 2) / length
    return {"height": float(height), "gap": gap, "yaw": yaw, "pitch": pitch}


def swings(values: list[float], amplitude: float) -> int:
    """How many times the series turns back after moving at least `amplitude` one way."""
    if not values:
        return 0
    extreme, direction, turns = values[0], 0, 0
    for v in values[1:]:
        if direction <= 0 and v >= extreme + amplitude:
            turns += direction < 0
            extreme, direction = v, 1
        elif direction >= 0 and v <= extreme - amplitude:
            turns += direction > 0
            extreme, direction = v, -1
        elif (direction > 0 and v > extreme) or (direction < 0 and v < extreme):
            extreme = v
    return turns


class FaceMarkerDetector:
    def __init__(self, config: Config) -> None:
        self.enabled = bool(config.get("recognition.face_markers", False))
        self.raise_ratio = float(config.get("recognition.brow_raise_ratio", 1.15))
        self.furrow_ratio = float(config.get("recognition.brow_furrow_ratio", 0.92))
        self.shake = float(config.get("recognition.head_shake_amplitude", 0.05))
        self.nod = float(config.get("recognition.head_nod_amplitude", 0.04))
        self.neutral: deque[dict[str, float]] = deque(maxlen=90)  # ~3 s of resting frames
        self.recent: deque[dict[str, float]] = deque(maxlen=24)  # ~0.8 s for shakes and nods

    def calibrated(self) -> bool:
        return len(self.neutral) >= 10

    def update(self, frame: LandmarkFrame) -> frozenset[FaceMarker]:
        """Markers active at this frame. Resting frames (hands down) teach the neutral face."""
        if not self.enabled:
            return frozenset()
        m = face_measures(frame.face)
        if m is None:
            self.recent.clear()
            return frozenset()
        if not frame.hands_in_signing_space:
            self.neutral.append(m)
            self.recent.clear()
            return frozenset()
        self.recent.append(m)
        if not self.calibrated():
            return frozenset()
        base = {k: float(np.median([n[k] for n in self.neutral])) for k in m}
        markers: set[FaceMarker] = set()
        if m["height"] > base["height"] * self.raise_ratio:
            markers.add("brows_raised")
        elif m["height"] < base["height"] * self.furrow_ratio and m["gap"] < base["gap"] * 0.97:
            markers.add("brows_furrowed")
        yaw = [r["yaw"] for r in self.recent]
        pitch = [r["pitch"] for r in self.recent]
        shaking = swings(yaw, self.shake) >= 2
        if shaking:
            markers.add("head_shake")
        elif swings(pitch, self.nod) >= 2:
            markers.add("head_nod")
        return frozenset(markers)


class MarkerTally:
    """Collects per-frame markers between signs; a sign gets those seen in enough frames."""

    def __init__(self, share: float = 0.4) -> None:
        self.share = share
        self.frames: list[frozenset[FaceMarker]] = []

    def add(self, markers: frozenset[FaceMarker]) -> None:
        self.frames.append(markers)

    def take(self) -> frozenset[FaceMarker]:
        frames, self.frames = self.frames, []
        if not frames:
            return frozenset()
        counts: dict[FaceMarker, int] = {}
        for markers in frames:
            for marker in markers:
                counts[marker] = counts.get(marker, 0) + 1
        return frozenset(m for m, n in counts.items() if n >= self.share * len(frames))
