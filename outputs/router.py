"""Router: sends each Translation to the call, spoken in the signer's voice (the TTS output
into the virtual mic).

With `review_before_speaking`, it asks for YES / NO first (a ConfirmRequest), so a
misrecognized sign is never spoken in the signer's name. Quick replies skip the review:
pressing one is the approval.

If the voice is unavailable or fails, the text goes to the console and the UI gets a
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
from shared.events import ConfirmRequest, ConfirmResult, Notice, OutputSent, SignEvent, Translation

log = logging.getLogger(__name__)


class Router:
    def __init__(
        self,
        bus: Bus,
        tts: Output,
        console: Output | None = None,
        review_before_speaking: bool = False,
    ) -> None:
        self.bus = bus
        self.tts = tts
        self.console = console or ConsoleOutput(bus)
        self.review_before_speaking = review_before_speaking
        self.pending: ConfirmRequest | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            sub = self.bus.subscribe(Translation, SignEvent)
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

    async def on_translation(self, translation: Translation) -> None:
        if self.review_before_speaking:
            self.ask(translation)
        else:
            await self.deliver(self.tts, translation.english)

    def ask(self, translation: Translation) -> None:
        if self.pending is not None:
            self.bus.publish(ConfirmResult(self.pending.request_id, approved=False))
        self.pending = ConfirmRequest(
            request_id=uuid.uuid4().hex[:8],
            english=translation.english,
            gloss=list(translation.gloss),
        )
        self.bus.publish(self.pending)

    async def confirm(self, approved: bool) -> None:
        if self.pending is None:
            return  # YES/NO with nothing to confirm
        request, self.pending = self.pending, None
        self.bus.publish(ConfirmResult(request.request_id, approved))
        if approved:
            await self.deliver(self.tts, request.english)

    async def quick_reply(self, text: str, urgent: bool = False) -> None:
        """A one-tap reply in the signer's voice. Pressing it is the approval: no YES step.
        Urgent replies skip waiting for a pause, when the voice supports that."""
        send_now = getattr(self.tts, "send_now", None) if urgent else None
        await self.deliver(self.tts, text, send=send_now)

    async def deliver(self, output: Output, text: str, send=None) -> None:
        if output is not self.console:
            try:
                if output.available():
                    await (send or output.send)(text)
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
