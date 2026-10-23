"""Translator interface: ASL gloss tokens -> natural English."""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared.config import Config
from shared.events import Translation


class Translator(ABC):
    provider: str = "translator"

    def __init__(self, config: Config) -> None:
        self.config = config

    @abstractmethod
    async def translate(self, gloss: list[str]) -> Translation:
        """Translate gloss tokens (e.g. ["ME", "WANT", "fs-TITLE"]) into English.

        `fs-` marks a fingerspelled word. Control signs are never passed in. Must not
        return an empty `english` for a non-empty gloss.
        """
