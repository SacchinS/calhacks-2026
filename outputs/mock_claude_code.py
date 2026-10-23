"""Pretends to be Claude Code: streams a canned reply back to the UI."""

from __future__ import annotations

import asyncio
import logging

from outputs.base import Output
from shared.events import OutputReply

log = logging.getLogger(__name__)


class MockClaudeCodeOutput(Output):
    name = "claude_code"
    chunk_delay = 0.25

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        log.info("mock Claude Code got: %s", text)
        reply = [
            f"(mock Claude Code) Request: {text}",
            "Reading the project files...",
            "Editing index.html...",
            "Done. 1 file changed.",
        ]
        for i, line in enumerate(reply):
            await asyncio.sleep(self.chunk_delay)
            self.bus.publish(OutputReply(self.name, line, done=i == len(reply) - 1))
