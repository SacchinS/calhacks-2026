"""The engine side of the Mac app: bus events out, window commands in, as JSON lines.

The SwiftUI app (ui/macos) launches `python app.py` and talks to it over stdin/stdout.

Events (stdout, one JSON object per line):
  {"type": "ready", "components": {...}, "mirror": true, "signing_space": {...}}   first
  {"type": "components", "components": {...}}       after start (a part may have fallen back)
  {"type": "<EventClassName>", ...fields}           every UI-relevant bus event, e.g.
      SignEvent, UtteranceProgress, Utterance, Translation, ConfirmRequest, ConfirmResult,
      ModeChanged, OutputSent, OutputReply, Caption, Notice
  {"type": "LandmarkFrame", "left_hand": [[x, y], ...], "right_hand": [...], "pose": [...],
   "face": [...], "hands_in_signing_space": bool, "jpeg": "<base64>" | null}
      newest frames only; the image is raw (not mirrored), landmarks are normalized 0..1

Commands (stdin, one JSON object per line):
  {"cmd": "mock_input", "text": "me want #title /send"}   the mock-sign box
  {"cmd": "control", "sign": "CLEAR" | "MODE"}            buttons (YES / NO must be signed)
  {"cmd": "quit"}

Run by hand to see the protocol: uv run python app.py --mock
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import sys
from dataclasses import asdict
from typing import Any, TextIO

from recognition.gating import SigningSpace
from shared.bus import Bus
from shared.config import Config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    LandmarkFrame,
    MockInput,
    ModeChanged,
    Notice,
    OutputReply,
    OutputSent,
    SignEvent,
    Translation,
    Utterance,
    UtteranceProgress,
)

log = logging.getLogger(__name__)

# Events forwarded to the app (LandmarkFrames go through their own, lossy subscription).
UI_EVENTS = (
    SignEvent,
    UtteranceProgress,
    Utterance,
    Translation,
    ConfirmRequest,
    ConfirmResult,
    ModeChanged,
    OutputSent,
    OutputReply,
    Caption,
    Notice,
)
BUTTON_SIGNS = frozenset({"CLEAR", "MODE"})  # YES / NO must be signed, never clicked
POSE_POINTS = 25  # upper body is enough for the overlay
FACE_STRIDE = 8  # send every 8th face point (468 -> 59)


def event_to_json(event: Any) -> dict[str, Any]:
    if isinstance(event, LandmarkFrame):
        return frame_to_json(event)
    data = asdict(event)
    if isinstance(event, Utterance):
        data = {"gloss": event.gloss, "ts": event.ts}
    return {"type": type(event).__name__, **data}


def frame_to_json(frame: LandmarkFrame) -> dict[str, Any]:
    def points(pts) -> list[list[float]]:
        return [[round(p[0], 4), round(p[1], 4)] for p in pts]

    return {
        "type": "LandmarkFrame",
        "left_hand": points(frame.left_hand),
        "right_hand": points(frame.right_hand),
        "pose": points(frame.pose[:POSE_POINTS]),
        "face": points(frame.face[::FACE_STRIDE]),
        "hands_in_signing_space": frame.hands_in_signing_space,
        "jpeg": encode_jpeg(frame.image),
        "ts": frame.ts,
    }


def encode_jpeg(image: Any, quality: int = 70) -> str | None:
    """RGB numpy image -> base64 JPEG, or None (no image, or OpenCV not installed)."""
    if image is None:
        return None
    try:
        import cv2
    except ImportError:
        return None
    ok, jpeg = cv2.imencode(
        ".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality]
    )
    return base64.b64encode(jpeg.tobytes()).decode() if ok else None


def protocol_stdout() -> TextIO:
    """The real stdout for protocol lines; anything else printed goes to stderr instead."""
    out = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    return out


class EngineServer:
    def __init__(self, bus: Bus, config: Config, out: TextIO) -> None:
        self.bus = bus
        self.config = config
        self.out = out
        self._tasks: list[asyncio.Task[None]] = []

    def emit(self, message: dict[str, Any]) -> None:
        try:
            self.out.write(json.dumps(message) + "\n")
            self.out.flush()
        except (BrokenPipeError, ValueError):  # the app went away
            pass

    def send_ready(self, components: dict[str, str]) -> None:
        space = SigningSpace.from_config(self.config)
        self.emit(
            {
                "type": "ready",
                "components": components,
                "mirror": bool(self.config.get("ui.mirror_camera", True)),
                "signing_space": asdict(space),
            }
        )

    def send_components(self, components: dict[str, str]) -> None:
        self.emit({"type": "components", "components": components})

    async def start(self) -> None:
        """Start forwarding bus events. Call before the app starts so none are missed."""
        if self._tasks:
            return
        events = self.bus.subscribe(*UI_EVENTS)
        frames = self.bus.subscribe(LandmarkFrame, maxsize=2)  # newest frames only
        self._tasks = [
            asyncio.create_task(self._forward(events), name="engine-events"),
            asyncio.create_task(self._forward(frames), name="engine-frames"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def _forward(self, sub) -> None:
        try:
            async for event in sub:
                self.emit(event_to_json(event))
        finally:
            sub.close()

    def handle_command(self, command: dict[str, Any]) -> bool:
        """Apply one command. Returns False for quit."""
        cmd = command.get("cmd")
        if cmd == "quit":
            return False
        if cmd == "mock_input" and str(command.get("text", "")).strip():
            self.bus.publish(MockInput(str(command["text"])))
        elif cmd == "control" and command.get("sign") in BUTTON_SIGNS:
            self.bus.publish(SignEvent(command["sign"], 1.0, "control"))
        else:
            log.warning("ignoring command %r", command)
        return True

    async def serve(self, reader: asyncio.StreamReader) -> None:
        """Read commands until quit or end of input (the app closed the pipe)."""
        while line := await reader.readline():
            try:
                command = json.loads(line)
            except json.JSONDecodeError:
                log.warning("not JSON: %r", line[:200])
                continue
            if not self.handle_command(command):
                return


async def stdin_reader() -> asyncio.StreamReader:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    return reader
