"""Types a question to Siri with Type to Siri, the way SignBridge's engine did.

"Hey Siri" can't be triggered through a virtual mic, so Siri gets text, not speech:
hold Cmd-Space to open Siri, wait, paste the question, press Return (SignBridge's route, 10/10
in its tests). Run it with another app in front, not a terminal: a terminal catches the Cmd-V.
Needs:
- Siri's keyboard shortcut set to "Hold Command Space" (Apple Intelligence & Siri settings)
- Type to Siri turned on (Accessibility > Siri)
- Accessibility permission for the app (or the terminal running `make run`), to post keystrokes
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import time

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)

KEY_V, KEY_RETURN, KEY_SPACE, KEY_COMMAND = 9, 36, 49, 55


def accessibility_ok() -> bool:
    """True if this process may post keystrokes (System Settings > Privacy > Accessibility)."""
    if sys.platform != "darwin":
        return False
    try:
        from ApplicationServices import AXIsProcessTrusted

        return bool(AXIsProcessTrusted())
    except Exception as exc:  # pyobjc missing
        log.warning("can't check Accessibility permission: %s", exc)
        return False


def post_key(keycode: int, down: bool, flags: int = 0) -> None:
    import Quartz

    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    Quartz.CGEventSetFlags(event, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    time.sleep(0.02)


def press(keycode: int, flags: int = 0) -> None:
    post_key(keycode, True, flags)
    post_key(keycode, False, flags)


def open_siri(hold_seconds: float) -> None:
    """Hold Cmd-Space, sending real modifier key events (a flag alone doesn't open Siri)."""
    import Quartz

    cmd = Quartz.kCGEventFlagMaskCommand
    post_key(KEY_COMMAND, True, cmd)
    post_key(KEY_SPACE, True, cmd)
    time.sleep(hold_seconds)
    post_key(KEY_SPACE, False, cmd)
    post_key(KEY_COMMAND, False, 0)


def type_to_siri_enabled() -> bool:
    """Type to Siri must be on, or holding the shortcut opens voice Siri and the paste is lost."""
    try:
        out = subprocess.run(
            ["defaults", "read", "com.apple.Siri", "TypeToSiriEnabled"],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.stdout.strip() == "1"


def paste(text: str, restore_delay: float = 0.3) -> None:
    """Paste with Cmd-V, then put the user's clipboard back."""
    import Quartz
    from AppKit import NSPasteboard, NSPasteboardTypeString

    board = NSPasteboard.generalPasteboard()
    saved = board.stringForType_(NSPasteboardTypeString)
    board.clearContents()
    board.setString_forType_(text, NSPasteboardTypeString)
    time.sleep(0.05)
    press(KEY_V, Quartz.kCGEventFlagMaskCommand)
    time.sleep(restore_delay)
    if saved is not None:
        board.clearContents()
        board.setString_forType_(saved, NSPasteboardTypeString)


class SiriOutput(Output):
    name = "siri"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.hold_seconds = float(config.get("type_to_siri.hold_seconds", 0.8))
        self.open_delay = float(config.get("type_to_siri.open_delay", 0.4))

    def available(self) -> bool:
        return accessibility_ok()

    async def send(self, text: str) -> None:
        if not accessibility_ok():
            raise RuntimeError("needs Accessibility permission to type to Siri")
        if not type_to_siri_enabled():
            raise RuntimeError("turn on Type to Siri (System Settings > Accessibility > Siri)")
        log.info("typing to Siri: %s", text)
        await asyncio.to_thread(self._type, text)

    def _type(self, text: str) -> None:
        open_siri(self.hold_seconds)
        time.sleep(self.open_delay)
        paste(text)
        press(KEY_RETURN)
