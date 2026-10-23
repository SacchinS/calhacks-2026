"""Keyboard-driven mock recognizer: type gloss, get SignEvents. No webcam needed.

Input comes from the terminal (one line per Enter) and from the UI's mock-sign box:

    hello              -> isolated sign HELLO
    me want fix bug    -> one isolated sign per word: ME, WANT, FIX, BUG
    #title             -> fingerspelled TITLE
    /yes /no /send /clear /mode   -> control signs (/finish is the same as /send)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import sys

from recognition.base import Recognizer, make_sign_event
from shared.bus import Bus
from shared.config import Config
from shared.events import CONTROL_ALIASES, CONTROL_SIGNS, MockInput, Notice, SignEvent

log = logging.getLogger(__name__)


def parse_line(line: str) -> list[SignEvent]:
    """Turn one typed line into SignEvents. Raises ValueError on an unknown /command."""
    events = []
    for token in line.split():
        if token.startswith("/"):
            command = token[1:].upper()
            command = CONTROL_ALIASES.get(command, command)
            if command not in CONTROL_SIGNS:
                raise ValueError(f"unknown control sign {token!r}")
            events.append(make_sign_event(command, 1.0, "control"))
        elif token.startswith("#"):
            if token[1:]:
                events.append(make_sign_event(token[1:], 1.0, "fingerspell"))
        else:
            events.append(make_sign_event(token, 1.0, "isolated"))
    return events


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
            log.info("mock sign %s (%s)", event.gloss, event.kind)
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
            print("Mock signs: type gloss + Enter (#word = fingerspell, /yes /no /send ...)")
        except (NotImplementedError, OSError, ValueError) as exc:
            log.warning("can't read terminal input (%s); use the UI's mock-sign box", exc)
