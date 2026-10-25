"""Mention alerts: notice when someone on the call says the signer's name or asks them
something, so a signer watching the Meet window (not ours) doesn't miss it.

Reads the captions (any source) and publishes a Mention once per turn, as soon as a name
is heard in a partial caption, then again with the final sentence. Names come from the
signer's name in Settings plus `meet.mention_names` (nicknames, or how captions tend to
spell it). With `meet.alert_on_questions` (for 1:1 calls), every question counts too.
"""

from __future__ import annotations

import asyncio
import contextlib
import re

from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, Mention

QUESTION_START = re.compile(
    r"\b(can|could|would|will|do|did|does|are|have|is|should|what|when|where|who|why|how)"
    r"\s+(you|your)\b",
    re.I,
)


def is_question(text: str) -> bool:
    return "?" in text or QUESTION_START.search(text) is not None


class MentionDetector:
    def __init__(self, bus: Bus, config: Config) -> None:
        self.bus = bus
        self.extra_names = [str(n) for n in config.get("meet.mention_names", []) or []]
        self.alert_on_questions = bool(config.get("meet.alert_on_questions", False))
        self.set_name(str(config.get("meet.signer_name", "") or ""))
        self.turn = 0
        self._alerted = False
        self._task: asyncio.Task[None] | None = None

    def set_name(self, name: str) -> None:
        names = [n.strip() for n in [name, *self.extra_names] if n and n.strip()]
        words = {w for n in names for w in [n, n.split()[0]]}  # "Sam Lee" also matches "Sam"
        self.pattern = (
            re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words)) + r")('s)?\b", re.I)
            if words
            else None
        )

    def matches(self, text: str) -> bool:
        named = self.pattern is not None and self.pattern.search(text) is not None
        return named or (self.alert_on_questions and is_question(text))

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(Caption)
            self._task = asyncio.create_task(self._run(sub), name="mentions")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, sub) -> None:
        try:
            async for caption in sub:
                self.on_caption(caption)
        finally:
            sub.close()

    def on_caption(self, caption: Caption) -> None:
        if self.matches(caption.text) and (not self._alerted or caption.is_final):
            question = is_question(caption.text)
            self.bus.publish(Mention(caption.text, question, caption.is_final, self.turn))
            self._alerted = True
        if caption.is_final:
            self.turn += 1
            self._alerted = False
