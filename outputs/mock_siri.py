"""Mock Siri: logs the question it "typed" to Siri."""

from __future__ import annotations

import logging

from outputs.base import Output

log = logging.getLogger(__name__)


class MockSiriOutput(Output):
    name = "siri"

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        log.info("mock Siri typed: %s", text)
        print(f"[mock siri] typed: {text}", flush=True)
