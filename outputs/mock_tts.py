"""Mock TTS: logs the text it "spoke". With `mock_tts.say_aloud: true`, also says it on
your speakers with macOS `say` (never into BlackHole)."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys

from outputs.base import Output

log = logging.getLogger(__name__)


class MockTTSOutput(Output):
    name = "tts"

    def available(self) -> bool:
        return True

    async def send(self, text: str) -> None:
        log.debug("mock TTS spoke: %s", text)
        if sys.stderr.isatty():  # never into the packaged app's log file
            print(f"[mock tts] spoke: {text}", file=sys.stderr, flush=True)
        if self.config.get("mock_tts.say_aloud", False) and shutil.which("say"):
            proc = await asyncio.create_subprocess_exec("say", text)
            await proc.wait()
