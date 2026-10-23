"""Router: sends each Translation to the output for the current mode.

- claude_code: publish a ConfirmRequest and wait. YES sends it to Claude Code, NO drops it.
- voice / meet: send straight to the TTS output (the virtual mic).
- MODE cycles claude_code -> voice -> meet.

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
    ) -> None:
        self.bus = bus
        self.claude_code = claude_code
        self.tts = tts
        self.console = console or ConsoleOutput(bus)
        self.mode: Mode = mode
        self.pending: ConfirmRequest | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(Translation, SignEvent)
            self.bus.publish(ModeChanged(self.mode))
            self._task = asyncio.create_task(self._run(sub), name="router")

    async def stop(self) -> None:
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
                    log.exception("router failed on %r", event)
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
            if self.pending is not None:
                self.bus.publish(ConfirmResult(self.pending.request_id, approved=False))
            self.pending = ConfirmRequest(
                request_id=uuid.uuid4().hex[:8],
                english=translation.english,
                gloss=list(translation.gloss),
            )
            self.bus.publish(self.pending)
        else:
            await self.deliver(self.tts, translation.english)

    async def confirm(self, approved: bool) -> None:
        if self.pending is None:
            return  # YES/NO with nothing to confirm
        request, self.pending = self.pending, None
        self.bus.publish(ConfirmResult(request.request_id, approved))
        if approved:
            await self.deliver(self.claude_code, request.english)

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
