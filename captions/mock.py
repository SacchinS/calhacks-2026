"""Mock captions: emits the lines of fixtures/captions_sample.txt on a timer, looping.

Each line is a "turn": TurnEvent start, `talk_seconds` of talking, the caption, then
TurnEvent end, so turn-aware speaking can be tried on mocks (it waits for the pause).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import logging

from captions.base import CaptionSource
from shared.events import Caption, TurnEvent

log = logging.getLogger(__name__)


class MockCaptionSource(CaptionSource):
    name = "mock"

    def __init__(self, bus, config) -> None:
        super().__init__(bus, config)
        self.interval = float(config.get("captions_mock.interval_seconds", 3.0))
        self.talk_seconds = float(config.get("captions_mock.talk_seconds", 0.0))
        self._task: asyncio.Task[None] | None = None

    def lines(self) -> list[str]:
        path = self.config.path("captions_mock.file", "fixtures/captions_sample.txt")
        lines = [line.strip() for line in path.read_text().splitlines()]
        return [line for line in lines if line and not line.startswith("#")]

    async def start(self) -> None:
        if self._task is None:
            lines = self.lines()
            self._task = asyncio.create_task(self._run(lines), name="mock-captions")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, lines: list[str]) -> None:
        for line in itertools.cycle(lines):
            log.debug("mock caption: %s", line)
            self.bus.publish(TurnEvent("start"))
            try:
                await asyncio.sleep(self.talk_seconds)
                self.bus.publish(Caption(line))
            finally:
                self.bus.publish(TurnEvent("end"))
            await asyncio.sleep(max(0.0, self.interval - self.talk_seconds))
