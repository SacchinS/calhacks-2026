"""Utterance buffer: collects SignEvents until SEND, then translates them.

- Isolated and fingerspelled signs are appended (UtteranceProgress shows the live gloss).
- SEND publishes the Utterance, translates it, and publishes the Translation. NOW does the
  same with the Translation marked urgent (said right away, not at the next pause).
- CLEAR empties the buffer. YES / NO / MODE belong to the router and are ignored here.
  A SEND or NOW with nothing signed is the router's too: it approves a sentence waiting
  for review.
- Control signs are never passed to the translator.
- Fingerspelled letters (Letter events) go to the autocompleter (`spelling`), in order with
  the signs: while a word is being spelled, YES accepts its suggestion and NO dismisses it,
  and the next sign or SEND keeps the letters as spelled. The word is appended as one
  fingerspelled sign.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import replace

from language.base import Translator
from language.mock import MockTranslator
from shared.bus import Bus
from shared.events import Letter, Notice, SignEvent, Translation, Utterance, UtteranceProgress

log = logging.getLogger(__name__)


class UtteranceBuffer:
    def __init__(self, bus: Bus, translator: Translator, fallback: Translator | None = None):
        self.bus = bus
        self.translator = translator
        self.fallback = fallback or MockTranslator(translator.config)
        self.signs: list[SignEvent] = []
        self.spelling = None  # the Autocompleter (language/autocomplete.py), if any
        # The SEND / NOW events that ended a sentence here, so the router doesn't also take
        # them as approving the sentence that's waiting for review (outputs/router.py).
        self.ended: deque[SignEvent] = deque(maxlen=8)
        self._task: asyncio.Task[None] | None = None
        self._warming: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(SignEvent, Letter)
            self._task = asyncio.create_task(self._run(sub), name="utterance-buffer")
            self._warming = asyncio.create_task(self._warm(), name="translator-warmup")

    async def _warm(self) -> None:
        """The first sentence of a call shouldn't pay for the connection and the prompt
        cache. Nothing waits for this, and a failure only means the first sentence is
        slower."""
        try:
            await self.translator.warm()
        except Exception as exc:
            log.debug("translator warm-up skipped: %s", exc)

    async def stop(self) -> None:
        if self._warming is not None:
            self._warming.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._warming
            self._warming = None
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

    async def handle(self, event: SignEvent | Letter) -> None:
        if isinstance(event, Letter):
            if self.spelling is not None:
                self.spelling.add(event.letter)
            return
        if self.spelling is not None and self.spelling.active:
            if event.gloss == "YES" and event.kind == "control":
                # Spent on the suggestion, so the router must not also approve a sentence
                # waiting for review. Recorded before accepting, because accepting ends
                # spelling and the router may only look afterwards.
                self.spelling.consumed.append(event)
                self.accept_suggestion()
                return
            if event.gloss == "NO" and event.kind == "control":
                self.spelling.consumed.append(event)
                self.spelling.dismiss()
                return
            if event.gloss == "CLEAR":
                self.spelling.clear()
            elif event.kind != "control" or event.gloss in ("SEND", "NOW"):
                self._append(self.spelling.finish())  # moved on: keep the letters as spelled
        if event.kind != "control":
            self.signs.append(event)
            self._progress()
        elif event.gloss == "CLEAR":
            self.signs.clear()
            self._progress()
        elif event.gloss in ("SEND", "NOW") and self.signs:
            self.ended.append(event)
            utterance = Utterance(signs=tuple(self.signs))
            self.signs.clear()
            self._progress()
            self.bus.publish(utterance)
            translation = await self.translate(utterance.gloss)
            if event.gloss == "NOW":
                translation = replace(translation, urgent=True)
            self.bus.publish(translation)

    def accept_suggestion(self, index: int = 0) -> None:
        """YES while spelling (or a click on a suggestion in the app)."""
        if self.spelling is not None:
            self._append(self.spelling.accept(index))

    def _append(self, word: SignEvent | None) -> None:
        if word is not None:
            self.signs.append(word)
            self._progress()

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
        if self.spelling is not None:
            self.spelling.gloss = tuple(gloss)  # the signs so far are context for suggestions
        self.bus.publish(UtteranceProgress(gloss=tuple(gloss)))
