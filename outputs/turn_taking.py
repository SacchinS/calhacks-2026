"""Turn-aware speaking in a call: speak the signer's approved words at the right moment.

Wraps the voice output. Cartesia Ink's turn detection on the other side's audio
(captions/cartesia_stt.py publishes TurnEvents) says whether someone has the floor:

- Floor free: speak right away.
- Someone is talking: wait for them to finish (`turn.end`), then speak.
- Still talking after `chime_in_seconds` (people talking over each other, or one long
  monologue): say "Sorry, can I jump in?", give them a moment to yield, then speak.
- Someone starts talking over our voice and keeps going for `barge_in_seconds`: stop, wait
  for the floor, and say the sentence again once.

Timing only: the signer already approved the exact words, and this never changes them.
With `chime_in_seconds: 0` it's turn-based: never interject, wait for the pause however
long it takes. `hurry()` (the signer signed NOW) says the waiting sentence right away,
without the interjection, and talking over it doesn't stop it.

Approved sentences are spoken one at a time, in order. Without turn events (mock captions
with no turns) the floor is always free and this passes straight through.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config
from shared.events import SpeechState, SpeechStatus, TurnEvent

log = logging.getLogger(__name__)

INTERJECTION = "Sorry, can I jump in?"


class TurnTakingOutput(Output):
    def __init__(self, bus: Bus, config: Config, inner: Output) -> None:
        super().__init__(bus, config)
        self.inner = inner
        self.name = inner.name  # still "tts" to the router and the app
        self.chime_in_seconds = float(config.get("meet.chime_in_seconds", 8))
        self.yield_seconds = float(config.get("meet.yield_seconds", 2.5))
        self.barge_in_seconds = float(config.get("meet.barge_in_seconds", 1.0))
        # A turn with no end for this long is treated as over (Ink missed the end).
        self.stale_seconds = float(config.get("meet.stale_turn_seconds", 20))
        self.interjection = str(config.get("meet.interjection", INTERJECTION))
        self.floor_free = asyncio.Event()  # set: nobody on the other side is talking
        self.floor_taken = asyncio.Event()  # the opposite, so both can be awaited
        self.floor_free.set()
        self._last_turn = 0.0
        self._lock = asyncio.Lock()
        self._hurry = asyncio.Event()  # NOW: stop waiting for the pause
        self._waiting = False
        self._task: asyncio.Task[None] | None = None

    def available(self) -> bool:
        return self.inner.available()

    def is_floor_free(self) -> bool:
        if not self.floor_free.is_set() and time.monotonic() - self._last_turn > self.stale_seconds:
            self._set_floor(free=True)
        return self.floor_free.is_set()

    def _set_floor(self, free: bool) -> None:
        if free:
            self.floor_taken.clear()
            self.floor_free.set()
        else:
            self.floor_free.clear()
            self.floor_taken.set()

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(TurnEvent)
            self._task = asyncio.create_task(self._follow(sub), name="turn-taking")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _follow(self, sub) -> None:
        try:
            async for event in sub:
                if event.kind in ("start", "resume"):
                    self._last_turn = time.monotonic()
                    self._set_floor(free=False)
                elif event.kind == "end":
                    self._set_floor(free=True)
        finally:
            sub.close()

    async def send(self, text: str) -> None:
        async with self._lock:
            try:
                hurried = await self._take_floor(text)
                for attempt in range(2):
                    self._status("speaking", text)
                    if await self._speak(text, interruptible=attempt == 0 and not hurried):
                        return
                    log.info("talked over; waiting to say it again")
                    await self._take_floor(text, chime_in=False)
            finally:
                self._status("idle")

    async def send_now(self, text: str) -> None:
        """Say it right away, without waiting for a pause ("Please slow down")."""
        self._status("speaking", text)
        try:
            await self.inner.send(text)
        finally:
            self._status("idle")

    def hurry(self) -> None:
        """The signer signed NOW: say the sentence waiting for the pause right away."""
        if self._waiting:
            self._hurry.set()

    async def _take_floor(self, text: str, chime_in: bool = True) -> bool:
        """Return when it's our turn: the floor is free, we've politely jumped in, or the
        signer said NOW (then True)."""
        if self.is_floor_free():
            return False
        self._status("waiting", text)
        turn_based = self.chime_in_seconds <= 0
        deadline = time.monotonic() + self.chime_in_seconds
        self._waiting = True
        self._hurry.clear()
        try:
            while not self.is_floor_free() and not self._hurry.is_set():
                left = 1.0 if turn_based else deadline - time.monotonic()
                if left <= 0:
                    break
                free = asyncio.create_task(self.floor_free.wait())
                hurry = asyncio.create_task(self._hurry.wait())
                await asyncio.wait(
                    {free, hurry}, timeout=min(left, 1.0), return_when=asyncio.FIRST_COMPLETED
                )
                free.cancel()
                hurry.cancel()
        finally:
            self._waiting = False
        if self._hurry.is_set():
            self._hurry.clear()
            return True
        if self.is_floor_free() or not chime_in or turn_based:
            return False
        self._status("interjecting", text)
        await self.inner.send(self.interjection)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self.floor_free.wait(), self.yield_seconds)
        return False

    async def _speak(self, text: str, interruptible: bool) -> bool:
        """Speak; False if someone talked over us long enough that we stopped."""
        speech = asyncio.create_task(self.inner.send(text))
        if not interruptible:
            await speech
            return True
        talked_over = asyncio.create_task(self._talked_over())
        try:
            done, _ = await asyncio.wait({speech, talked_over}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            talked_over.cancel()
        if speech in done:
            speech.result()  # re-raise a voice failure for the router's fallback
            return True
        speech.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await speech
        return False

    async def _talked_over(self) -> None:
        """Finish when someone has been talking over our voice for barge_in_seconds."""
        while True:
            await self.floor_taken.wait()
            try:
                await asyncio.wait_for(self.floor_free.wait(), self.barge_in_seconds)
            except TimeoutError:
                return  # still talking: they really want the floor

    def _status(self, state: SpeechState, text: str = "") -> None:
        self.bus.publish(SpeechStatus(state, text))
