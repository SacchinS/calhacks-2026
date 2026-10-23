"""Utterance buffer: collects SignEvents until SEND, then translates them.

- Isolated and fingerspelled signs are appended (UtteranceProgress shows the live gloss).
- SEND publishes the Utterance, translates it, and publishes the Translation.
- CLEAR empties the buffer. YES / NO / MODE belong to the router and are ignored here.
- Control signs are never passed to the translator.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from language.base import Translator
from language.mock import MockTranslator
from shared.bus import Bus
from shared.events import Notice, SignEvent, Translation, Utterance, UtteranceProgress

log = logging.getLogger(__name__)


class UtteranceBuffer:
    def __init__(self, bus: Bus, translator: Translator, fallback: Translator | None = None):
        self.bus = bus
        self.translator = translator
        self.fallback = fallback or MockTranslator(translator.config)
        self.signs: list[SignEvent] = []
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(SignEvent)
            self._task = asyncio.create_task(self._run(sub), name="utterance-buffer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, sub) -> None:
        try:
            async for event in sub:
                await self.handle(event)
        finally:
            sub.close()

    async def handle(self, event: SignEvent) -> None:
        if event.kind != "control":
            self.signs.append(event)
            self._progress()
        elif event.gloss == "CLEAR":
            self.signs.clear()
            self._progress()
        elif event.gloss == "SEND" and self.signs:
            utterance = Utterance(signs=tuple(self.signs))
            self.signs.clear()
            self._progress()
            self.bus.publish(utterance)
            self.bus.publish(await self.translate(utterance.gloss))

    async def translate(self, gloss: list[str]) -> Translation:
        try:
            translation = await self.translator.translate(gloss)
            if translation.english.strip():
                return translation
            raise ValueError("empty translation")
        except Exception as exc:
            if self.translator is self.fallback:
                raise
            log.warning("translator %s failed: %r", self.translator.provider, exc)
            self.bus.publish(
                Notice(
                    "warning",
                    f"Translator '{self.translator.provider}' failed ({exc}); "
                    f"using '{self.fallback.provider}'",
                )
            )
            return await self.fallback.translate(gloss)

    def _progress(self) -> None:
        gloss = Utterance(signs=tuple(self.signs)).gloss
        self.bus.publish(UtteranceProgress(gloss=tuple(gloss)))
