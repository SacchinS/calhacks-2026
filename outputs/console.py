"""Prints to the terminal. Always available; the fallback for every other output."""

from __future__ import annotations

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config


class ConsoleOutput(Output):
    name = "console"

    def __init__(self, bus: Bus | None = None, config: Config | None = None) -> None:
        super().__init__(bus or Bus(), config or Config())
        self.sent: list[str] = []

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        self.sent.append(text)
        print(f"[console] {text}", flush=True)
