"""Meet call manners, spoken in the signer's voice through the TTS output.

- Call intro: say who's calling and that they sign, because hearing people hang up on relay
  calls when they don't know who's calling (docs/user-research.md). That's a problem on
  calls with strangers, not team meetings, so it's said on Meet start only with
  `meet.intro_on_start`; `introduce()` says it any time (the app's "Introduce me" button).
- Signing cue: if the signer has been signing for a few seconds without sending, say
  "One moment, I'm signing." at most once per utterance. Off by default
  (`meet.signing_cue_seconds`): in a video meeting people can see you signing.

Both go through the router's delivery, so they show up in the app like anything else sent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from outputs.router import Router
from shared.bus import Bus
from shared.config import Config
from shared.events import ModeChanged, UtteranceProgress

log = logging.getLogger(__name__)

INTRO = (
    "Hi, this is {name}. I'm Deaf and signing through {app}, "
    "so there may be a short pause before I answer."
)
INTRO_NO_NAME = (
    "Hi. I'm Deaf and signing through {app}, so there may be a short pause before I answer."
)
CUE = "One moment, I'm signing."


class CallHost:
    def __init__(self, bus: Bus, config: Config, router: Router) -> None:
        self.bus = bus
        self.router = router
        self.name = str(config.get("meet.signer_name", "") or "").strip()
        self.app_name = str(config.get("meet.app_name", "SignBridge"))
        self.intro_on_start = bool(config.get("meet.intro_on_start", False))
        self.cue_seconds = float(config.get("meet.signing_cue_seconds", 0))
        self.mode = router.mode
        self._cue_timer: asyncio.Task[None] | None = None
        self._cued = False  # the cue was said for the current utterance
        self._task: asyncio.Task[None] | None = None
        self._speaking: set[asyncio.Task[None]] = set()

    def intro_text(self) -> str:
        template = INTRO if self.name else INTRO_NO_NAME
        return template.format(name=self.name, app=self.app_name)

    def introduce(self) -> None:
        self._say(self.intro_text())

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(ModeChanged, UtteranceProgress)
            self._task = asyncio.create_task(self._run(sub), name="call-host")

    async def stop(self) -> None:
        for task in [self._task, self._cue_timer, *self._speaking]:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = self._cue_timer = None
        self._speaking.clear()

    async def _run(self, sub) -> None:
        try:
            async for event in sub:
                if isinstance(event, ModeChanged):
                    entering = event.mode == "meet" and self.mode != "meet"
                    self.mode = event.mode
                    if entering and self.intro_on_start:
                        self.introduce()
                elif self.mode == "meet":
                    self._on_progress(event)
        finally:
            sub.close()

    def _on_progress(self, event: UtteranceProgress) -> None:
        if not event.gloss:  # sent or cleared: the next utterance gets its own cue
            self._cancel_timer()
            self._cued = False
        elif self._cue_timer is None and not self._cued and self.cue_seconds > 0:
            self._cue_timer = asyncio.create_task(self._cue_later())

    async def _cue_later(self) -> None:
        await asyncio.sleep(self.cue_seconds)
        self._cue_timer = None
        floor_free = getattr(self.router.tts, "is_floor_free", lambda: True)()
        if self.mode == "meet" and floor_free:  # never talk over them just to say "one moment"
            self._cued = True
            self._say(CUE)

    def _cancel_timer(self) -> None:
        if self._cue_timer is not None:
            self._cue_timer.cancel()
            self._cue_timer = None

    def _say(self, text: str) -> None:
        task = asyncio.create_task(self.router.deliver(self.router.tts, text))
        self._speaking.add(task)
        task.add_done_callback(self._speaking.discard)
