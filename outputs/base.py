"""Output interface: somewhere English text can be sent (Claude Code, a voice, the console)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.bus import Bus
from shared.config import Config


class Output(ABC):
    name: str = "output"

    def __init__(self, bus: Bus, config: Config) -> None:
        self.bus = bus
        self.config = config

    @abstractmethod
    def available(self) -> bool:
        """True if send() can work right now (CLI installed, device present, key set...).

        Must be fast and must not raise. The router falls back to the console when False.
        """

    @abstractmethod
    async def send(self, text: str) -> None:
        """Deliver the text. Raise on failure; the router catches it and falls back."""
