"""Custom signs the Kaggle model doesn't know (WW, YOU-REMIND-ME, MEET-YOU, BUY, HOW, ...),
learned from a few recorded examples each.

    uv run python tools/record_signs.py WW --takes 5      # record examples from the webcam

Each example is a clip of Holistic landmarks saved under models/custom_signs/<GLOSS>/
(gitignored: it's a teammate's body-tracking data). Matching is nearest-neighbour: a clip
becomes hand shapes and hand positions relative to the shoulders, resampled to a fixed
length, and is compared with every example.

`custom_mode: segment` (the default) matches the way the examples were recorded: one sign
per raise of the hands. The clip grows from a hand entering the signing space; as soon as
the whole clip so far clearly matches a sign (and is at least `custom_early_fraction` of
that sign's recorded length), the sign is out (`direct`: the recognizer emits it at once)
and nothing more is read until the hands have been down for `custom_end_seconds`. A clip
that never matched gets one last try when the hands drop (`end_segment`). `state` is idle,
signing or detected (the preview's gray, yellow and green box).

`window` instead slides over the last frames while signing; it lines up with a whole sign
only for a frame or two at its end, which the segmenter's min_frames then usually misses.

Either way, a sign is reported only when it's clearly closer than the threshold learned from
the examples themselves, so unknown movement isn't forced into a sign.

Learn every sign from a Deaf signer or the source videos in docs/asl-demo-script-research.md.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

import numpy as np

from recognition.base import FrameClassifier, Prediction
from shared.config import Config
from shared.events import LandmarkFrame

log = logging.getLogger(__name__)

STEPS = 24  # every clip is resampled to this many steps before comparing
L_SHOULDER, R_SHOULDER, NOSE = 11, 12, 0


def frame_features(frame: LandmarkFrame) -> np.ndarray | None:
    """Both hands (shape and position) relative to the shoulders, scaled by their width.

    Returns None without a pose. A missing hand is zeros plus a 0 presence flag.
    """
    if len(frame.pose) <= R_SHOULDER:
        return None
    pose = np.asarray(frame.pose, dtype=np.float32)[:, :2]
    center = (pose[L_SHOULDER] + pose[R_SHOULDER]) / 2
    width = float(np.linalg.norm(pose[L_SHOULDER] - pose[R_SHOULDER])) or 1.0
    parts = []
    for hand in (frame.left_hand, frame.right_hand):
        if len(hand) >= 21:
            pts = np.asarray(hand[:21], dtype=np.float32)[:, :2]
            wrist = pts[0]
            shape = (pts - wrist) / width  # hand shape, independent of where the hand is
            where = (wrist - center) / width  # where the hand is, relative to the body
            parts += [shape.ravel(), where * 2, [1.0]]
        else:
            parts += [np.zeros(42, np.float32), np.zeros(2, np.float32), [0.0]]
    return np.concatenate(parts).astype(np.float32)


def resample(clip: np.ndarray, steps: int = STEPS) -> np.ndarray:
    """A (frames, features) clip linearly resampled to (steps, features)."""
    if len(clip) == 1:
        return np.repeat(clip, steps, axis=0)
    src = np.linspace(0, len(clip) - 1, steps)
    lo = np.floor(src).astype(int)
    hi = np.minimum(lo + 1, len(clip) - 1)
    t = (src - lo)[:, None]
    return clip[lo] * (1 - t) + clip[hi] * t


def clip_features(frames: list[LandmarkFrame]) -> np.ndarray | None:
    feats = [f for f in (frame_features(fr) for fr in frames) if f is not None]
    return resample(np.stack(feats)) if len(feats) >= 4 else None


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sqrt(((a - b) ** 2).sum(axis=1)).mean())


class CustomSignLibrary:
    """Recorded examples: gloss -> list of resampled clips, plus each sign's typical length."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.examples: dict[str, list[np.ndarray]] = {}
        self.lengths: dict[str, int] = {}
        self.load()

    def load(self) -> None:
        self.examples.clear()
        if not self.folder.is_dir():
            return
        for sign_dir in sorted(p for p in self.folder.iterdir() if p.is_dir()):
            clips, lengths = [], []
            for path in sorted(sign_dir.glob("*.npz")):
                data = np.load(path)
                clips.append(data["features"])
                lengths.append(int(data["frames"]))
            if clips:
                self.examples[sign_dir.name.upper()] = clips
                self.lengths[sign_dir.name.upper()] = int(np.median(lengths))

    def add(self, gloss: str, frames: list[LandmarkFrame]) -> Path:
        features = clip_features(frames)
        if features is None:
            raise ValueError("too few frames with a visible body to learn from")
        sign_dir = self.folder / gloss.upper()
        sign_dir.mkdir(parents=True, exist_ok=True)
        path = sign_dir / f"{len(list(sign_dir.glob('*.npz'))) + 1:02d}.npz"
        np.savez_compressed(path, features=features, frames=len(frames))
        self.load()
        return path

    def threshold(self) -> float:
        """How close a match must be, learned from the examples: a little more than the
        spread of each sign's own examples, or a fraction of the gap between different
        signs if the examples are very consistent."""
        spreads, gaps = [], []
        signs = list(self.examples.items())
        for gloss, clips in signs:
            for i, a in enumerate(clips):
                spreads += [distance(a, b) for b in clips[i + 1 :]]
                others = [distance(a, b) for g, cs in signs if g != gloss for b in cs]
                if others:
                    gaps.append(min(others))
        spread = 2 * float(np.median(spreads)) if spreads else 0.0
        gap = 0.2 * float(np.median(gaps)) if gaps else 4 * spread
        return max(spread, gap) or 0.6

    def match(self, clip: np.ndarray) -> tuple[str, float, float] | None:
        """(gloss, distance to its nearest example, distance to the nearest other sign)."""
        best: dict[str, float] = {}
        for gloss, clips in self.examples.items():
            best[gloss] = min(distance(clip, c) for c in clips)
        if not best:
            return None
        ranked = sorted(best.items(), key=lambda kv: kv[1])
        runner_up = ranked[1][1] if len(ranked) > 1 else float("inf")
        return ranked[0][0], ranked[0][1], runner_up


class CustomSignModel(FrameClassifier):
    def __init__(self, config: Config, library: CustomSignLibrary | None = None) -> None:
        self.config = config
        folder = config.path("recognition.custom_signs_dir", "models/custom_signs")
        self.library = library or CustomSignLibrary(folder)
        # Only the signs in use (recognition.custom_signs; empty = every recorded sign):
        # fewer signs to tell apart, and recordings stay on disk for later.
        wanted = config.get("recognition.custom_signs", []) or []
        flags = {True: "YES", False: "NO"}  # unquoted YES / NO in YAML arrive as booleans
        wanted = {str(flags.get(w, w) if isinstance(w, bool) else w).upper() for w in wanted}
        if wanted:
            for gloss in [g for g in self.library.examples if g not in wanted]:
                del self.library.examples[gloss]
                self.library.lengths.pop(gloss, None)
        self.stride = int(config.get("recognition.custom_stride", 3))
        self.mode = str(config.get("recognition.custom_mode", "segment"))
        self.end_gap = float(config.get("recognition.custom_end_seconds", 0.35))
        self.early = float(config.get("recognition.custom_early_fraction", 0.6))
        self.segment: list[LandmarkFrame] = []  # this sign so far (segment mode)
        self.locked = False  # a sign came out: wait for the hands to drop
        self.spelling = False  # this raise of the hands is fingerspelling: not a sign
        self._last_in = 0.0
        self.gap_seconds = float(config.get("recognition.isolated_gap_seconds", 0.4))
        scale = float(config.get("recognition.custom_threshold_scale", 1.0))
        self.limit = self.library.threshold() * scale
        longest = max(self.library.lengths.values(), default=30)
        self.frames: deque[LandmarkFrame] = deque(maxlen=int(longest * 1.5) + 1)
        self.last: Prediction | None = None
        self._last_ts: float | None = None
        self._since_run = 0
        if self.library.examples:
            log.info("custom signs: %s", ", ".join(sorted(self.library.examples)))

    def predict(self, frame: LandmarkFrame) -> Prediction | None:
        if not self.library.examples:
            return None
        if self.mode == "segment":
            if frame.ts - self._last_in > self.end_gap:  # the hands were down: a new sign
                self.segment, self.locked, self.spelling = [], False, False
            self._last_in = frame.ts
            if self.locked or self.spelling:
                return None  # one sign per raise of the hands; none while spelling
            self.segment.append(frame)
            self._since_run += 1
            if self._since_run < self.stride:
                return None
            self._since_run = 0
            match = self.early_match(self.segment)
            if match is not None:
                self.segment, self.locked = [], True
            return match
        if self._last_ts is not None and frame.ts - self._last_ts > self.gap_seconds:
            self.frames.clear()
            self.last = None
        self._last_ts = frame.ts
        self.frames.append(frame)
        self._since_run += 1
        if self._since_run >= self.stride:
            self._since_run = 0
            self.last = self.classify(list(self.frames))
        return self.last

    def end_segment(self, now: float) -> Prediction | None:
        """Called on frames with the hands out of the signing space: once they've been out
        for end_gap, the clip since they came in is classified (segment mode)."""
        if self.mode != "segment" or now - self._last_in < self.end_gap:
            return None
        if self.locked or self.spelling:
            self.locked = self.spelling = False  # the hands are down: ready for the next sign
            self.segment = []
            return None
        if not self.segment:
            return None
        frames, self.segment = self.segment, []
        return self.classify_segment(frames)

    def spelled(self) -> None:
        """The letter reader sees a letter held: this raise of the hands is fingerspelling,
        so nothing in it is a sign (a held P read as ME) until the hands drop."""
        if self.mode == "segment":
            self.spelling = True
            self.segment = []

    @property
    def direct(self) -> bool:
        """Answers are whole signs, to emit at once (not per-frame guesses for the segmenter)."""
        return self.mode == "segment"

    def state(self, hands_up: bool) -> str:
        """idle (hands down) | signing (a sign is being made) | detected (one came out)."""
        if self.locked:
            return "detected"
        return "signing" if hands_up else "idle"

    def early_match(self, frames: list[LandmarkFrame]) -> Prediction | None:
        """The clip so far, if it already clearly is a sign (and long enough to be all of it)."""
        match = self.segment_match(frames)
        if match is None:
            return None
        gloss, near, other = match
        if len(frames) < self.early * self.library.lengths.get(gloss, 0):
            return None
        if near > self.limit or near > 0.8 * other:
            return None
        return Prediction(gloss, float(0.99 - 0.39 * near / self.limit), "isolated")

    def classify_segment(self, frames: list[LandmarkFrame]) -> Prediction | None:
        """One whole sign (hands in to hands out) against the examples."""
        match = self.segment_match(frames)
        if match is None:
            return None
        gloss, near, other = match
        if near > self.limit or near > 0.8 * other:
            return None
        return Prediction(gloss, float(0.99 - 0.39 * near / self.limit), "isolated")

    def segment_match(self, frames: list[LandmarkFrame]) -> tuple[str, float, float] | None:
        """(nearest sign, its distance, the runner-up's) for a whole clip (for tools too)."""
        longest = max(self.library.lengths.values(), default=30)
        clip = clip_features(frames[-int(longest * 2) :]) if len(frames) >= 4 else None
        return self.library.match(clip) if clip is not None else None

    def nearest(self, frames: list[LandmarkFrame]) -> list[tuple[str, float, float]]:
        """For each sign's typical length: (nearest sign, its distance, the runner-up's) for
        the window's tail at that length (what classify judges; for tools)."""
        out = []
        for length in sorted(set(self.library.lengths.values())):
            if len(frames) < max(4, int(length * 0.7)):
                continue
            clip = clip_features(frames[-length:])
            match = self.library.match(clip) if clip is not None else None
            if match is not None:
                out.append(match)
        return out

    def classify(self, frames: list[LandmarkFrame]) -> Prediction | None:
        """Try the window's tail at each sign's typical length; keep the closest match."""
        best: Prediction | None = None
        for gloss, length in self.library.lengths.items():
            if len(frames) < max(4, int(length * 0.7)):
                continue
            clip = clip_features(frames[-length:])
            if clip is None:
                continue
            match = self.library.match(clip)
            if match is None or match[0] != gloss:
                continue
            _, near, other = match
            if near > self.limit or near > 0.8 * other:
                continue
            # 0.99 for a perfect match down to 0.6 at the limit: every accepted match clears
            # the segmenter's confidence_threshold (it used to bottom out at 0.5 and vanish).
            confidence = float(0.99 - 0.39 * near / self.limit)
            if best is None or confidence > best.confidence:
                best = Prediction(gloss, confidence, "isolated")
        return best
