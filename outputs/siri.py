"""Types a question to Siri with Type to Siri. STUB: unavailable, so the router uses the console.

"Hey Siri" can't be triggered through a virtual mic, so Siri gets text, not speech. Needs:
- Siri's keyboard shortcut set to "Hold Command Space" (Apple Intelligence & Siri settings)
- Type to Siri turned on (Accessibility > Siri)
- Accessibility permission for the app, to post keystrokes
"""

from __future__ import annotations

import logging

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)


class SiriOutput(Output):
    name = "siri"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.hold_seconds = float(config.get("type_to_siri.hold_seconds", 0.8))
        self.open_delay = float(config.get("type_to_siri.open_delay", 0.4))
        log.warning("SiriOutput is a stub: questions go to the console")

    def available(self) -> bool:
        # TODO(Person C): return sys.platform == "darwin" and AXIsProcessTrusted()
        # (from ApplicationServices, pyobjc-framework-ApplicationServices).
        return False

    async def send(self, text: str) -> None:
        # TODO(Person C): port route_siri from SignBridge's signbridge/routes.py, in a thread
        # (asyncio.to_thread) so the event loop keeps running:
        #   1. Hold Cmd-Space for self.hold_seconds with Quartz CGEventCreateKeyboardEvent /
        #      CGEventPost (key down Command 55, Space 49; wait; key up Space, Command).
        #   2. Wait self.open_delay for the Type to Siri field to open.
        #   3. Paste the text: save the clipboard (NSPasteboard), set it to `text`, post Cmd-V
        #      (key 9), then restore the old clipboard.
        #   4. Press Return (key 36).
        # Needs pyobjc-framework-Quartz and pyobjc-framework-Cocoa. Raise on failure.
        raise NotImplementedError("SiriOutput is a stub")
