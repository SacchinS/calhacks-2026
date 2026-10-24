"""Router: sends each Translation to the output for the current mode.

- claude_code: publish a ConfirmRequest and wait. YES sends it to Claude Code, NO drops it.
- siri: send straight to the Siri output (Type to Siri).
- voice / meet: send straight to the TTS output (the virtual mic), or, with
  `review_before_speaking`, ask for YES / NO first like Claude Code, so a misrecognized
  sign is never spoken in the signer's name.
- MODE cycles claude_code -> siri -> voice -> meet.

Claude Code runs in the background: a build takes minutes, and Siri, Voice, and Meet keep
working meanwhile. Approved requests run one at a time, in order.

If an output is unavailable or fails, the text goes to the console and the UI gets a
warning. The router never raises.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid

from outputs.base import Output
from outputs.console import ConsoleOutput
from shared.bus import Bus
from shared.events import (
    MODES,
    ConfirmRequest,
    ConfirmResult,
    Mode,
    ModeChanged,
    Notice,
    OutputSent,
    SignEvent,
    Translation,
)

log = logging.getLogger(__name__)


class Router:
    def __init__(
        self,
        bus: Bus,
        claude_code: Output,
        tts: Output,
        console: Output | None = None,
        mode: Mode = "claude_code",
        siri: Output | None = None,
        review_before_speaking: bool = False,
    ) -> None:
        self.bus = bus
        self.claude_code = claude_code
        self.tts = tts
        self.console = console or ConsoleOutput(bus)
        self.siri = siri or self.console
        self.mode: Mode = mode
        self.review_before_speaking = review_before_speaking
        self.pending: ConfirmRequest | None = None
        self._task: asyncio.Task[None] | None = None
        self._claude_code_job: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(Translation, SignEvent)
            self.bus.publish(ModeChanged(self.mode))
            self._task = asyncio.create_task(self._run(sub), name="router")

    async def stop(self) -> None:
        if self._claude_code_job is not None:
            self._claude_code_job.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._claude_code_job
            self._claude_code_job = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, sub) -> None:
        try:
            async for event in sub:
                try:
                    await self.handle(event)
                except Exception:  # never let one bad event kill the router
                    log.exception("router failed on %s", type(event).__name__)
                    self.bus.publish(Notice("error", f"Router error on {type(event).__name__}"))
        finally:
            sub.close()

    async def handle(self, event: Translation | SignEvent) -> None:
        if isinstance(event, Translation):
            await self.on_translation(event)
        elif event.kind == "control":
            if event.gloss == "YES":
                await self.confirm(True)
            elif event.gloss == "NO":
                await self.confirm(False)
            elif event.gloss == "MODE":
                self.set_mode(MODES[(MODES.index(self.mode) + 1) % len(MODES)])

    async def on_translation(self, translation: Translation) -> None:
        if self.mode == "claude_code":
            self.ask(translation, "claude_code")
        elif self.mode in ("voice", "meet") and self.review_before_speaking:
            self.ask(translation, "tts")
        elif self.mode == "siri":
            await self.deliver(self.siri, translation.english)
        else:
            await self.deliver(self.tts, translation.english)

    def ask(self, translation: Translation, target: str) -> None:
        if self.pending is not None:
            self.bus.publish(ConfirmResult(self.pending.request_id, approved=False))
        self.pending = ConfirmRequest(
            request_id=uuid.uuid4().hex[:8],
            english=translation.english,
            gloss=list(translation.gloss),
            target=target,
        )
        self.bus.publish(self.pending)

    async def confirm(self, approved: bool) -> None:
        if self.pending is None:
            return  # YES/NO with nothing to confirm
        request, self.pending = self.pending, None
        self.bus.publish(ConfirmResult(request.request_id, approved))
        if approved and request.target == "tts":
            await self.deliver(self.tts, request.english)
        elif approved:
            self._claude_code_job = asyncio.create_task(
                self._after(self._claude_code_job, request.english), name="claude-code"
            )

    @property
    def claude_code_busy(self) -> bool:
        return self._claude_code_job is not None and not self._claude_code_job.done()

    async def wait_for_claude_code(self) -> None:
        """Wait until every approved Claude Code request has finished (for tests)."""
        while self._claude_code_job is not None and not self._claude_code_job.done():
            await asyncio.wait([self._claude_code_job])

    async def _after(self, previous: asyncio.Task[None] | None, text: str) -> None:
        if previous is not None:
            await asyncio.wait([previous])
        try:
            await self.deliver(self.claude_code, text)
        except Exception:  # deliver never raises, but a background task must not die loudly
            log.exception("Claude Code request failed")

    def set_mode(self, mode: Mode) -> None:
        if self.pending is not None:
            self.bus.publish(ConfirmResult(self.pending.request_id, approved=False))
            self.pending = None
        self.mode = mode
        self.bus.publish(ModeChanged(mode))

    async def deliver(self, output: Output, text: str) -> None:
        if output is not self.console:
            try:
                if output.available():
                    await output.send(text)
                    self.bus.publish(OutputSent(output.name, text))
                    return
                reason = "not available"
            except Exception as exc:
                log.exception("output %s failed", output.name)
                reason = f"failed: {exc}"
            self.bus.publish(
                Notice("warning", f"Output '{output.name}' {reason}; sent to console instead")
            )
        await self.console.send(text)
        self.bus.publish(OutputSent(self.console.name, text))
