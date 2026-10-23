"""Every message passed between modules.

HEADS-UP: changes to this file affect all three people. Tell the whole team before you
change, rename, or remove anything here.

All events are frozen dataclasses with a `ts` timestamp (seconds since the epoch).
Modules never call each other directly: they publish and subscribe to these on the bus.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, get_args

Point = tuple[float, float, float]  # normalized x, y (0..1, y down) and relative depth z
Mode = Literal["claude_code", "voice", "meet"]
SignKind = Literal["isolated", "fingerspell", "control"]
NoticeLevel = Literal["info", "warning", "error"]

MODES: tuple[Mode, ...] = get_args(Mode)

# Control signs are ordinary SignEvents with kind="control". They are never translated.
CONTROL_SIGNS = frozenset({"YES", "NO", "SEND", "CLEAR", "MODE"})
# Signs that act as a control sign. FINISH is in the Kaggle vocabulary and means SEND.
CONTROL_ALIASES = {"FINISH": "SEND"}


def _now() -> float:
    return time.time()


@dataclass(frozen=True)
class LandmarkFrame:
    """One webcam frame of MediaPipe landmarks. Empty tuple = not detected this frame."""

    left_hand: tuple[Point, ...] = ()
    right_hand: tuple[Point, ...] = ()
    pose: tuple[Point, ...] = ()
    face: tuple[Point, ...] = ()
    hands_in_signing_space: bool = False
    # Ground-truth gloss for labeled fixture frames (replay only); None from a live camera.
    label: str | None = None
    # The camera image for this frame (numpy uint8 array, height x width x 3, RGB), so the UI
    # can draw the feed without opening the camera itself. None in mock and replay modes.
    image: Any = field(default=None, compare=False, repr=False)
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class SignEvent:
    gloss: str
    confidence: float
    kind: SignKind
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class Utterance:
    """The SignEvents between an utterance start and SEND (control signs excluded)."""

    signs: tuple[SignEvent, ...]
    ts: float = field(default_factory=_now)

    @property
    def gloss(self) -> list[str]:
        """Gloss tokens for the translator. Fingerspelled words are prefixed `fs-`."""
        return [f"fs-{s.gloss}" if s.kind == "fingerspell" else s.gloss for s in self.signs]


@dataclass(frozen=True)
class UtteranceProgress:
    """The live gloss collected so far (published on every change, empty after SEND/CLEAR)."""

    gloss: tuple[str, ...]
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class Translation:
    gloss: list[str]
    english: str
    provider: str
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class ConfirmRequest:
    """Ask the signer to sign YES or NO before `english` is sent to `target`."""

    request_id: str
    english: str
    gloss: list[str]
    target: str = "claude_code"
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class ConfirmResult:
    request_id: str
    approved: bool
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class ModeChanged:
    mode: Mode
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class Caption:
    """Incoming speech (Meet mode), shown to the signer as a caption."""

    text: str
    is_final: bool = True
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class OutputSent:
    """English was sent to an output (`output` is the Output's name)."""

    output: str
    text: str
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class OutputReply:
    """A streamed chunk of an output's reply, e.g. Claude Code's answer. `done` ends it."""

    output: str
    text: str
    done: bool = False
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class MockInput:
    """A line typed into the UI's mock-sign box (same syntax as the terminal)."""

    text: str
    ts: float = field(default_factory=_now)


@dataclass(frozen=True)
class Notice:
    """Status or warning for the UI, e.g. an output fell back to the console."""

    level: NoticeLevel
    message: str
    ts: float = field(default_factory=_now)
