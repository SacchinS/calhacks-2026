"""Mock Siri: logs the question it "typed" to Siri."""

from __future__ import annotations

import logging
import sys

from outputs.base import Output

log = logging.getLogger(__name__)


class MockSiriOutput(Output):
    name = "siri"

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        log.debug("mock Siri typed: %s", text)
        if sys.stderr.isatty():  # never into the packaged app's log file
            print(f"[mock siri] typed: {text}", file=sys.stderr, flush=True)
