"""The engine side of the Mac app (ui/macos, the SignBridge SwiftUI app), as JSON lines.

The app launches `python app.py` and speaks SignBridge's engine protocol; this module maps
it onto our bus. Commands (stdin, one JSON object per line):

  {"cmd": "mode", "mode": "off|run|framing|gestures"}   off pauses the recognizer
  {"cmd": "preview", "on": true}                        send camera frames
  {"cmd": "gesture", "name": "wake|confirm|cancel"}     on-screen buttons and backup keys:
        confirm = YES (or SEND while signing), cancel = NO (or CLEAR while signing)
  {"cmd": "fake", "glosses": ["RAIN", "TOMORROW"]}      test phrases: the signs, then SEND
  {"cmd": "check", "name": "claude|voice"}              setup checks
  {"cmd": "test_route", "route": "siri|voice", "text": "What time is it?"}
  {"cmd": "calibrate"}
  {"cmd": "config", "values": {...}}                    saves the app's settings
  {"cmd": "output_mode", "mode": "claude_code|siri|voice|meet"}   (ours) where English goes
  {"cmd": "mock_input", "text": "title /\\ red /send"}      (ours) the mock-sign box
  {"cmd": "introduce"}                                  (ours) say the Meet call intro again
  {"cmd": "quit"}

Events (stdout):
  {"type": "ready", "config": {...}}
  {"type": "status", "state": "idle|listening|thinking|confirming|sending", "mode": ...,
   "glosses": [...], "intent": {"sentence": ..., "route": "text|siri|voice"} | null,
   "target": ..., "log": [...], "holding": null, "fps": ..., "error": null,
   "output_mode": ..., "components": {...}, "mock": bool,
   "claude_code_working": bool, "camera_on": bool}                                 on change, and every second
  {"type": "frame", "seq": n, "jpeg": "<base64>"}   while the preview is on (mirrored, drawn)
  {"type": "check" | "route_tested" | "calibrated" | "config" | "error", ...}
  {"type": "caption", "text": ...}, {"type": "reply", "text": ..., "done": bool}   (ours)
  {"type": "sent", "mode": ..., "output": ..., "text": ...}   (ours) what each output was given

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
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from recognition.gating import SigningSpace
from recognition.mock import parse_line
from shared.events import (
    MODES,
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

if TYPE_CHECKING:
    from app import App

log = logging.getLogger(__name__)

APP_MODES = ("off", "run", "framing", "gestures")
PRACTICE = ["wake", "confirm", "cancel"]
UI_CONFIG = Path("~/Library/Application Support/calhacks-2026/ui.json").expanduser()
# Where each output mode sends English, in the app's route vocabulary.
ROUTES = {"claude_code": "text", "siri": "siri", "voice": "voice", "meet": "voice"}
TARGETS = {"claude_code": "Claude Code", "siri": "Siri", "meet": "Google Meet"}


def protocol_stdout() -> TextIO:
    """The real stdout for protocol lines; anything else printed goes to stderr instead."""
    out = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    return out


async def stdin_reader() -> asyncio.StreamReader:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    return reader


def render_preview(frame: LandmarkFrame, space: SigningSpace, mirror: bool) -> bytes | None:
    """The preview JPEG: the camera image (or a dark canvas in replay) with the tracking drawn
    on it, mirrored like a mirror. None without OpenCV (the camera extra)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    if frame.image is not None:
        canvas = cv2.cvtColor(frame.image, cv2.COLOR_RGB2BGR)
    else:
        canvas = np.full((480, 640, 3), 18, dtype=np.uint8)
    h, w = canvas.shape[:2]
    box_color = (80, 220, 80) if frame.hands_in_signing_space else (120, 120, 120)
    cv2.rectangle(
        canvas,
        (int(space.x_min * w), int(space.y_min * h)),
        (int(space.x_max * w), int(space.y_max * h)),
        box_color,
        3 if frame.hands_in_signing_space else 1,
    )
    for points, color in (
        (frame.pose, (0, 200, 255)),
        (frame.left_hand, (0, 255, 0)),
        (frame.right_hand, (255, 0, 0)),
    ):
        for p in points:
            cv2.circle(canvas, (int(p[0] * w), int(p[1] * h)), 2, color, -1)
    if mirror:
        canvas = cv2.flip(canvas, 1)
    ok, jpeg = cv2.imencode(".jpg", canvas, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return jpeg.tobytes() if ok else None


class EngineServer:
    def __init__(self, app: App, out: TextIO, ui_config: Path = UI_CONFIG) -> None:
        self.app = app
        self.bus = app.bus
        self.config = app.config
        self.out = out
        self.ui_config_path = ui_config
        self.ui_config = self._load_ui_config()
        self._apply_settings()
        self.space = SigningSpace.from_config(self.config)
        self.mirror = bool(self.config.get("ui.mirror_camera", True))

        self.mode = "off"  # the app's mode: off | run | framing | gestures
        self.preview = False
        self.output_mode = self.config.mode
        self.woke = False
        self.gloss: list[str] = []  # live, until SEND
        self.utterance: list[str] = []  # the phrase being translated / confirmed / sent
        self.english: str | None = None
        self.pending_id: str | None = None
        self.pending_target = "claude_code"
        self.thinking = False
        self.sending = False
        self.claude_code_jobs: list[str] = []  # approved requests Claude Code is still working on
        self.log: deque[str] = deque(["ready: sign, then FINISH"], maxlen=3)
        self.practice = list(PRACTICE)
        self.frame: LandmarkFrame | None = None
        self.frame_times: deque[float] = deque(maxlen=60)
        self.frame_seq = 0
        self._last_status: dict[str, Any] | None = None
        self._tasks: list[asyncio.Task[None]] = []

    # ---- output ----

    def emit(self, message: dict[str, Any]) -> None:
        try:
            self.out.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.out.flush()
        except (BrokenPipeError, ValueError):  # the app went away
            pass

    def send_ready(self) -> None:
        self.emit({"type": "ready", "config": self.ui_config})

    def state(self) -> str:
        if self.pending_id:
            return "confirming"
        if self.sending:
            return "sending"
        if self.thinking:
            return "thinking"
        if self.gloss or self.woke:
            return "listening"
        return "idle"

    def status(self) -> dict[str, Any]:
        state = self.state()
        glosses = self.gloss if state in ("idle", "listening") else self.utterance
        intent = None
        if state in ("confirming", "sending") and self.english:
            intent = {"sentence": self.english, "route": ROUTES[self.output_mode]}
        recent = [t for t in self.frame_times if time.monotonic() - t < 1]
        status = {
            "state": state,
            "mode": self.mode,
            "glosses": [g.removeprefix("fs-") for g in glosses],
            "intent": intent,
            "target": TARGETS.get(self.output_mode),
            "log": list(self.log),
            "holding": None,
            "fps": float(len(recent)),
            "error": None,
            "output_mode": self.output_mode,
            "claude_code_working": bool(self.claude_code_jobs),
            # The webcam is open (only the camera recognizer opens it; the app always shows this).
            "camera_on": self.app.chosen.get("recognizer") == "camera" and self.mode != "off",
            "components": self.app.chosen,
            "mock": self.app.chosen.get("recognizer") == "mock",
        }
        if self.mode == "framing":
            status["framing"] = self._framing_hint()
        if self.mode == "gestures":
            status["practice"] = {
                "todo": list(self.practice),
                "done": [g for g in PRACTICE if g not in self.practice],
            }
        return status

    def emit_status(self, force: bool = False) -> None:
        status = self.status()
        if force or status != self._last_status:
            self.emit({"type": "status", **status})
            self._last_status = status

    def _framing_hint(self) -> dict[str, Any]:
        if self.app.chosen.get("recognizer") == "mock":
            return {"ok": False, "hint": "No camera with the mock recognizer."}
        if (
            self.frame is None
            or not self.frame_times
            or time.monotonic() - self.frame_times[-1] > 1
        ):
            return {"ok": False, "hint": "Starting the camera..."}
        if len(self.frame.pose) < 13:
            return {"ok": False, "hint": "I can't see your shoulders. Sit back so they show."}
        if self.frame.hands_in_signing_space:
            return {"ok": True, "hint": "Looks good. Your hands are in the signing space."}
        return {"ok": True, "hint": "Good position. Now raise your hands into the green box."}

    # ---- bus -> app ----

    async def start(self) -> None:
        """Start following the bus. Call before the app starts so no events are missed."""
        if self._tasks:
            return
        events = self.bus.subscribe(
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
        frames = self.bus.subscribe(LandmarkFrame, maxsize=2)  # newest frames only
        self._tasks = [
            asyncio.create_task(self._follow(events), name="engine-events"),
            asyncio.create_task(self._follow(frames), name="engine-frames"),
            asyncio.create_task(self._heartbeat(), name="engine-heartbeat"),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    async def _follow(self, sub) -> None:
        try:
            async for event in sub:
                self.on_event(event)
        finally:
            sub.close()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(1)
            self.emit_status(force=True)

    def on_event(self, event: Any) -> None:
        if isinstance(event, LandmarkFrame):
            self.frame = event
            self.frame_times.append(time.monotonic())
            if self.preview:
                jpeg = render_preview(event, self.space, self.mirror)
                if jpeg:
                    self.frame_seq += 1
                    self.emit(
                        {
                            "type": "frame",
                            "seq": self.frame_seq,
                            "jpeg": base64.b64encode(jpeg).decode(),
                        }
                    )
            return
        if isinstance(event, SignEvent):
            if event.kind != "control":
                self.log.append(f"saw {event.gloss} ({event.confidence:.0%})")
        elif isinstance(event, UtteranceProgress):
            self.gloss = list(event.gloss)
        elif isinstance(event, Utterance):
            self.utterance = event.gloss
            self.english = None
            self.thinking = True
            self.woke = False
            self.log.append(f"thinking: {' '.join(self.utterance)}")
        elif isinstance(event, Translation):
            self.english = event.english
            self.thinking = False
            if self.output_mode != "claude_code":
                self.sending = True  # voice / meet: straight to the voice
        elif isinstance(event, ConfirmRequest):
            self.pending_id = event.request_id
            self.pending_target = event.target
            self.english = event.english
            self.sending = False
        elif isinstance(event, ConfirmResult):
            if event.request_id == self.pending_id:
                self.pending_id = None
                if event.approved and self.pending_target != "claude_code":
                    self.sending = True  # reviewed in Meet / Voice: now it's spoken
                elif event.approved and self.english:
                    # Claude Code builds in the background: don't hold the app on "Sending".
                    self.claude_code_jobs.append(self.english)
                    self.log.append("Claude Code is working")
                else:
                    self.log.append("cancelled")
        elif isinstance(event, ModeChanged):
            self.output_mode = event.mode
        elif isinstance(event, OutputSent):
            mode = self.output_mode
            if event.output in ("claude_code", "console") and event.text in self.claude_code_jobs:
                self.claude_code_jobs.remove(event.text)
                mode = "claude_code"
            else:
                self.sending = False
            self.log.append("sent" if event.output != "console" else "printed to the console")
            sent = {"mode": mode, "output": event.output, "text": event.text}
            self.emit({"type": "sent", **sent})
        elif isinstance(event, OutputReply):
            self.emit({"type": "reply", "text": event.text, "done": event.done})
        elif isinstance(event, Caption):
            self.emit({"type": "caption", "text": event.text})
        elif isinstance(event, Notice):
            self.log.append(event.message)
        self.emit_status()

    # ---- app -> bus ----

    def control(self, sign: str) -> None:
        self.bus.publish(SignEvent(sign, 1.0, "control"))

    async def handle_command(self, msg: dict[str, Any]) -> bool:
        """Apply one command. Returns False for quit."""
        cmd = msg.get("cmd")
        if cmd == "quit":
            return False
        if cmd == "mode":
            await self.set_mode(str(msg.get("mode")))
        elif cmd == "preview":
            self.preview = bool(msg.get("on"))
        elif cmd == "gesture":
            self.gesture(str(msg.get("name")))
        elif cmd == "fake":
            self.fake([str(g) for g in msg.get("glosses", [])])
        elif cmd == "check":
            self._background(self.run_check(str(msg.get("name"))))
        elif cmd == "test_route":
            self._background(
                self.test_route(str(msg.get("route")), msg.get("text", "What time is it?"))
            )
        elif cmd == "calibrate":
            self.emit(
                {
                    "type": "calibrated",
                    "ok": False,
                    "message": "Not available yet: the signing space is set in config.yaml.",
                }
            )
        elif cmd == "config":
            self.ui_config.update(msg.get("values") or {})
            self._save_ui_config()
            self._apply_settings()
            self.emit({"type": "config", "config": self.ui_config})
        elif cmd == "output_mode":
            self.set_output_mode(str(msg.get("mode")))
        elif cmd == "introduce":
            self.app.call_host.introduce()
        elif cmd == "mock_input":
            if str(msg.get("text", "")).strip():
                self.bus.publish(MockInput(str(msg["text"])))
        else:
            self.emit({"type": "error", "message": f"unknown command {cmd!r}"})
        self.emit_status()
        return True

    async def set_mode(self, mode: str) -> None:
        if mode not in APP_MODES:
            raise ValueError(mode)
        self.mode = mode
        self.practice = list(PRACTICE)
        if mode != "run":
            self.gesture("cancel")
        recognizer = self.app.recognizer
        if mode == "off":
            await recognizer.stop()
        else:
            await recognizer.start()

    def gesture(self, name: str) -> None:
        if self.mode == "gestures":
            if self.practice and self.practice[0] == name:
                self.practice.pop(0)
            return
        state = self.state()
        if name == "wake" and state == "idle":
            self.woke = True
            self.log.append("listening: sign, then FINISH")
        elif name == "confirm":
            if state == "confirming":
                self.control("YES")
            elif state == "listening" and self.gloss:
                self.control("SEND")  # thumbs up while signing also means "done signing"
        elif name == "cancel":
            if state == "confirming":
                self.control("NO")
            elif state == "listening":
                self.woke = False
                self.control("CLEAR")
                self.log.append("cancelled")

    def fake(self, glosses: list[str]) -> None:
        """Inject signs as if recognized, then SEND (test phrases and backup keys).

        Tokens use the mock-sign syntax, so face markers work: ["TITLE", "/\\", "RED"].
        """
        try:
            events = parse_line(" ".join(glosses))
        except ValueError as exc:
            self.log.append(f"bad test phrase: {exc}")
            return
        if self.state() == "idle":
            self.gesture("wake")
        for event in events:
            if event.kind != "control":
                self.bus.publish(event)
        self.control("SEND")

    def set_output_mode(self, mode: str) -> None:
        """Pick a mode directly. (Pressing MODE N times raced: N came from a stale mode.)"""
        if mode in MODES:
            self.app.router.set_mode(mode)

    async def run_check(self, name: str) -> None:
        if name == "claude":
            ok, detail = await self._check_translator()
        else:
            from outputs.tts_say import find_output_device

            device = self.config.get("audio.virtual_mic_device", "BlackHole 2ch")
            found = find_output_device(device) is not None
            ok, detail = found, f"{device} is {'installed' if found else 'not installed'}"
        self.emit({"type": "check", "name": name, "ok": ok, "detail": detail})

    async def _check_translator(self) -> tuple[bool, str]:
        translator = self.app.translator
        if translator.provider != "claude":
            return (
                False,
                f"Using the '{translator.provider}' translator. Set translator: claude.",
            )
        start = time.monotonic()
        try:
            translation = await translator.translate(["HELLO"])
        except Exception as exc:
            return False, f"Claude call failed: {exc}"
        return True, f"Claude answered in {time.monotonic() - start:.1f}s: {translation.english}"

    async def test_route(self, route: str, text: str) -> None:
        component = "siri" if route == "siri" else "tts"
        output = self.app.router.siri if route == "siri" else self.app.router.tts
        try:
            if not output.available():
                chosen = self.app.chosen.get(component)
                detail = f"The {component} output ({chosen}) isn't available."
                if component == "siri":
                    detail += " Give SignBridge Accessibility permission, then try again."
                ok = False
            else:
                await output.send(text)
                ok, detail = True, ""
        except Exception as exc:
            ok, detail = False, str(exc)
        self.emit({"type": "route_tested", "route": route, "ok": ok, "detail": detail})

    def _background(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        task.add_done_callback(lambda t: t in self._tasks and self._tasks.remove(t))

    async def serve(self, reader: asyncio.StreamReader) -> None:
        """Read commands until quit or end of input (the app closed the pipe)."""
        while line := await reader.readline():
            if not line.strip():
                continue
            try:
                if not await self.handle_command(json.loads(line)):
                    return
            except Exception as exc:
                self.emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})

    # ---- the app's settings ----

    def _load_ui_config(self) -> dict[str, Any]:
        cfg: dict[str, Any] = {
            "onboarded": False,
            "still": 0.5,
            "phrase_rest": 1.5,
            "min_conf": float(self.config.get("recognition.confidence_threshold", 0.6)),
            "voice_device": self.config.get("audio.virtual_mic_device", "BlackHole 2ch"),
            "signer_name": self.config.get("meet.signer_name", "") or "",
            "review_before_speaking": bool(self.config.get("meet.review_before_speaking", False)),
        }
        with contextlib.suppress(OSError, ValueError):
            cfg.update(json.loads(self.ui_config_path.read_text()))
        return cfg

    def _apply_settings(self) -> None:
        """Settings the app's Settings window changes that the engine uses."""
        self.app.call_host.name = str(self.ui_config.get("signer_name") or "").strip()
        self.app.router.review_before_speaking = bool(self.ui_config.get("review_before_speaking"))

    def _save_ui_config(self) -> None:
        self.ui_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_config_path.write_text(json.dumps(self.ui_config, indent=2))
