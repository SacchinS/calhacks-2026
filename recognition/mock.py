"""Keyboard-driven mock recognizer: type gloss, get SignEvents. No webcam needed.

Input comes from the terminal (one line per Enter) and from the UI's mock-sign box:

    hello              -> isolated sign HELLO
    me want fix bug    -> one isolated sign per word: ME, WANT, FIX, BUG
    #sarah             -> fingerspelled SARAH (the whole word at once)
    ~pr                -> fingerspelled letters P, R one at a time (autocomplete suggests
                          the word; /yes accepts it, /no dismisses it)
    /yes /no /send /clear /now   -> control signs (/finish is the same as /send; /now sends
                          and says it right away)

Facial grammar goes after the signs it covers (back to the start of the line, a comma, or
the previous marker), the way the docs write it:

    title /\\ red                -> raised brows over TITLE (topic)
    you like coffee [q]         -> raised brows over all three ([yes/no question])
    where you live [wh]         -> furrowed brows; [neg] head shake, [nod] head nod

The long forms work too: [yes/no question], [wh-question], [negation], [affirmation].
Commas, periods, and question marks are dropped from signs (`morning,` -> MORNING).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys
from dataclasses import replace

from recognition.base import Recognizer, make_sign_event
from shared.bus import Bus
from shared.config import Config
from shared.events import (
    CONTROL_ALIASES,
    CONTROL_SIGNS,
    FaceMarker,
    Letter,
    MockInput,
    Notice,
    SignEvent,
)

log = logging.getLogger(__name__)


# Marker tokens -> the face marker they put on the signs before them.
MARKERS: dict[str, FaceMarker] = {
    "/\\": "brows_raised",
    "[q]": "brows_raised",
    "[yes/no question]": "brows_raised",
    "[wh]": "brows_furrowed",
    "[wh-question]": "brows_furrowed",
    "[neg]": "head_shake",
    "[negation]": "head_shake",
    "[nod]": "head_nod",
    "[affirmation]": "head_nod",
}


def parse_line(line: str) -> list[SignEvent | Letter]:
    """Turn one typed line into SignEvents (and Letters for `~abc`). Raises ValueError on an
    unknown /command or [tag]."""
    line = line.replace("[yes/no question]", "[q]")
    events: list[SignEvent | Letter] = []
    span_start = 0  # first sign the next marker covers
    for token in line.split():
        if token.lower() in MARKERS:
            span = events[span_start:]
            if not any(isinstance(e, SignEvent) and e.kind != "control" for e in span):
                raise ValueError(f"{token} needs signs before it")
            marker = MARKERS[token.lower()]
            events[span_start:] = [_with_marker(e, marker) for e in span]
            span_start = len(events)
            continue
        if token.startswith("["):
            raise ValueError(f"unknown marker {token!r}")
        clause_ends = token.endswith(",")
        token = token.rstrip(",.?!")
        if token.startswith("/"):
            command = token[1:].upper()
            command = CONTROL_ALIASES.get(command, command)
            if command not in CONTROL_SIGNS:
                raise ValueError(f"unknown control sign {token!r}")
            events.append(make_sign_event(command, 1.0, "control"))
            span_start = len(events)
        elif token.startswith("~"):
            events.extend(Letter(c.upper()) for c in token[1:] if c.isalpha())
        elif token.startswith("#"):
            if token[1:]:
                events.append(make_sign_event(token[1:], 1.0, "fingerspell"))
        elif token:
            events.append(make_sign_event(token, 1.0, "isolated"))
        if clause_ends:
            span_start = len(events)
    return events


def _with_marker(event: SignEvent | Letter, marker: FaceMarker) -> SignEvent | Letter:
    if isinstance(event, Letter) or event.kind == "control":
        return event
    return replace(event, markers=event.markers | {marker})


class MockRecognizer(Recognizer):
    name = "mock"

    def __init__(self, bus: Bus, config: Config, read_stdin: bool = False) -> None:
        super().__init__(bus, config)
        self.read_stdin = read_stdin
        self._task: asyncio.Task[None] | None = None
        self._stdin_attached = False

    def feed(self, line: str) -> None:
        """Publish the SignEvents for one typed line."""
        try:
            events = parse_line(line)
        except ValueError as exc:
            self.bus.publish(Notice("warning", f"Mock recognizer: {exc}"))
            return
        for event in events:
            self.bus.publish(event)

    async def start(self) -> None:
        if self._task is not None:
            return
        inputs = self.bus.subscribe(MockInput)
        self._task = asyncio.create_task(self._ui_loop(inputs), name="mock-recognizer")
        if self.read_stdin and sys.stdin.isatty():
            self._attach_stdin()

    async def stop(self) -> None:
        if self._stdin_attached:
            with contextlib.suppress(Exception):
                asyncio.get_running_loop().remove_reader(sys.stdin.fileno())
            self._stdin_attached = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _ui_loop(self, inputs) -> None:
        try:
            async for message in inputs:
                self.feed(message.text)
        finally:
            inputs.close()

    def _attach_stdin(self) -> None:
        loop = asyncio.get_running_loop()

        def on_line() -> None:
            line = sys.stdin.readline()
            if not line:  # EOF
                loop.remove_reader(sys.stdin.fileno())
                self._stdin_attached = False
                return
            self.feed(line)

        try:
            loop.add_reader(sys.stdin.fileno(), on_line)
            self._stdin_attached = True
            print("Mock signs: type gloss + Enter (#word = fingerspell, ~abc = letters, /send)")
        except (NotImplementedError, OSError, ValueError) as exc:
            log.warning("can't read terminal input (%s); use the UI's mock-sign box", exc)
