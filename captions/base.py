"""CaptionSource interface: incoming speech (the Meet call) -> Caption events on the bus.

The app starts the source when the mode becomes `meet` and stops it when leaving.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.bus import Bus
from shared.config import Config


class CaptionSource(ABC):
    name: str = "captions"

    def __init__(self, bus: Bus, config: Config) -> None:
        self.bus = bus
        self.config = config

    @abstractmethod
    async def start(self) -> None:
        """Start publishing Captions in the background. Raise if it can't start."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop publishing. Safe to call more than once, and start() may be called again."""
