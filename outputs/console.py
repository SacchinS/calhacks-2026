"""Prints to the terminal. Always available; the fallback for every other output.

Only prints when stderr is a terminal (`make run`, `app.py --mock`). In the packaged app,
stderr is the engine log file, and the user's text must never be saved there.
"""

from __future__ import annotations

import logging
import sys

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)


class ConsoleOutput(Output):
    name = "console"

    def __init__(self, bus: Bus | None = None, config: Config | None = None) -> None:
        super().__init__(bus or Bus(), config or Config())
        self.sent: list[str] = []

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        self.sent.append(text)
        if sys.stderr.isatty():
            print(f"[console] {text}", file=sys.stderr, flush=True)
        else:
            log.debug("console: %s", text)
