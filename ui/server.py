"""The engine side of the Mac app (ui/macos, the SignBridge SwiftUI app), as JSON lines.

The app launches `python app.py` and speaks SignBridge's engine protocol; this module maps
it onto our bus. Commands (stdin, one JSON object per line):

  {"cmd": "mode", "mode": "off|run|framing"}   off pauses the recognizer
  {"cmd": "preview", "on": true}                        send camera frames
  {"cmd": "gesture", "name": "wake|confirm|cancel|now"}  on-screen buttons and backup keys:
        confirm = YES (or SEND while signing), cancel = NO (or CLEAR while signing)
  {"cmd": "fake", "glosses": ["RAIN", "TOMORROW"]}      test phrases: the signs, then SEND
  {"cmd": "check", "name": "claude|voice"}              setup checks (translator, BlackHole)
  {"cmd": "test_route", "route": "voice", "text": "SignBridge voice test."}
  {"cmd": "calibrate"}
  {"cmd": "config", "values": {...}}                    saves the app's settings
  {"cmd": "mock_input", "text": "title /\\ red /send"}      (ours) the mock-sign box
  {"cmd": "introduce"}                                  (ours) say the Meet call intro again
  {"cmd": "quick_reply", "text": "Can you repeat that?"}  (ours) one of meet.quick_replies
  {"cmd": "letters", "text": "pr"}                      (ours) fingerspelled letters, typed
  {"cmd": "autocomplete", "action": "accept|dismiss", "index": 0}   (ours) while spelling,
        the suggestion to accept (0 = top). Send / Cancel (buttons, keys) do the same.
  {"cmd": "vocab_list"}                                 (ours) the remembered words
  {"cmd": "vocab_delete", "term": "Julian"} | {"cmd": "vocab_delete", "id": "<occurrence>"}
  {"cmd": "quit"}

Events (stdout):
  {"type": "ready", "config": {...}, "quick_replies": [{"text": ..., "urgent": bool}]}
  {"type": "status", "state": "idle|listening|thinking|confirming|sending", "mode": ...,
   "glosses": [...], "intent": {"sentence": ..., "route": "voice"} | null,
   "target": "Google Meet", "log": [...], "fps": ..., "error": null,
   "holding": ["P", 0.4] | null (a fingerspelled letter being held, and how far to counting),
   "components": {...}, "mock": bool, "camera_on": bool,
   "speech": {"state": "idle|waiting|interjecting|speaking", "text": ...},
   "them_talking": bool,
   "autocomplete": {"letters": "JU", "top": {"term", "kind"} | null, "alternates": [...],
                    "dismissed": bool, "search": "moss|keyword|letters"} | null,
   "autocomplete_stats": {"accepted", "letters_saved", "last_accept": {"spelled",
                    "length"} | null, "latency_ms", "search_ms", "search", "words"}}
                                                         on change, and every second
  {"type": "frame", "seq": n, "jpeg": "<base64>"}   while the preview is on (mirrored, drawn)
  {"type": "check" | "route_tested" | "calibrated" | "config" | "error", ...}
  {"type": "caption", "text": ..., "final": bool}   (ours) a partial caption is replaced
  {"type": "sent", "output": "tts|console", "text": ...}   (ours) what was said in the call
  {"type": "mention", "text": ..., "question": bool, "final": bool, "turn": n}   (ours)
        someone said the signer's name; the same turn comes again with the full sentence
  {"type": "vocab", "words": [{"term", "term_norm", "kind", "count", "last_used", "tags",
   "occurrences": [{"id", "source", "used_at", "tags"}]}]}   (ours) after vocab_list / delete

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
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, TextIO

from recognition.gating import SigningSpace, space_from_pose
from recognition.mock import parse_line
from shared.events import (
    AutocompleteUpdate,
    Caption,
    ConfirmRequest,
    ConfirmResult,
    LandmarkFrame,
    Letter,
    Mention,
    MockInput,
    Notice,
    OutputSent,
    SignEvent,
    SpeechStatus,
    Translation,
    TurnEvent,
    Utterance,
    UtteranceProgress,
)

if TYPE_CHECKING:
    from app import App

log = logging.getLogger(__name__)

APP_MODES = ("off", "run", "framing")
UI_CONFIG = Path("~/Library/Application Support/calhacks-2026/ui.json").expanduser()
JOINT_BGR = (255, 132, 10)  # the tracked joints, drawn as blue dots (macOS accent blue)
TARGET = "Google Meet"  # where the signer's English is spoken


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


# The signing space's color: gray with the hands down, yellow while a sign is being made,
# green once it's recognized (then nothing more is read until the hands drop).
BOX_BGR = {"idle": (120, 120, 120), "signing": (0, 210, 255), "detected": (80, 220, 80)}


def render_preview(
    frame: LandmarkFrame, space: SigningSpace, mirror: bool, state: str | None = None
) -> bytes | None:
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
    state = state or ("signing" if frame.hands_in_signing_space else "idle")
    box_color = BOX_BGR.get(state, BOX_BGR["idle"])
    cv2.rectangle(
        canvas,
        (int(space.x_min * w), int(space.y_min * h)),
        (int(space.x_max * w), int(space.y_max * h)),
        box_color,
        1 if state == "idle" else 3,
    )
    for points in (frame.pose, frame.left_hand, frame.right_hand):
        for p in points:
            cv2.circle(canvas, (int(p[0] * w), int(p[1] * h)), 3, JOINT_BGR, -1)
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
        self.space = SigningSpace.from_config(self.config)
        self.ui_config = self._load_ui_config()
        self._apply_settings()
        self.mirror = bool(self.config.get("ui.mirror_camera", True))

        self.mode = "off"  # the app's mode: off | run | framing
        self.preview = False
        self.woke = False
        self.gloss: list[str] = []  # live, until SEND
        self.utterance: list[str] = []  # the phrase being translated / confirmed / sent
        self.english: str | None = None
        self.pending_id: str | None = None
        self.thinking = False
        self.sending = False
        self.speech = "idle"  # our voice in a call: idle | waiting | interjecting | speaking
        self.speech_text = ""
        self.them_talking = False  # the other side has the floor (Ink turn detection)
        self.spelling: AutocompleteUpdate | None = None  # a word being fingerspelled
        self.log: deque[str] = deque(["ready: sign, then FINISH"], maxlen=3)
        self.frame: LandmarkFrame | None = None
        self.frame_times: deque[float] = deque(maxlen=60)
        self.frame_seq = 0
        # The preview is drawn off the event loop, at most preview_fps, skipping frames while
        # one is still being drawn: tracking gets the time first (a busy loop lost hands).
        self.preview_fps = float(self.config.get("ui.preview_fps", 15))
        self._drawing: asyncio.Task[None] | None = None
        self._last_drawn = 0.0
        self._holding: list[Any] | None = None
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
        self.emit({"type": "ready", "config": self.ui_config, "quick_replies": self.quick_replies})

    @property
    def quick_replies(self) -> list[dict[str, Any]]:
        """The Meet panel's one-tap replies (meet.quick_replies in config.yaml)."""
        replies = []
        for item in self.config.get("meet.quick_replies", []) or []:
            if isinstance(item, str):
                item = {"text": item}
            if isinstance(item, dict) and str(item.get("text", "")).strip():
                replies.append({"text": str(item["text"]), "urgent": bool(item.get("urgent"))})
        return replies

    def state(self) -> str:
        if self.pending_id:
            return "confirming"
        if self.sending:
            return "sending"
        if self.thinking:
            return "thinking"
        if self.gloss or self.woke or self.spelling is not None:
            return "listening"
        return "idle"

    def status(self) -> dict[str, Any]:
        state = self.state()
        glosses = self.gloss if state in ("idle", "listening") else self.utterance
        intent = None
        if state in ("confirming", "sending") and self.english:
            intent = {"sentence": self.english, "route": "voice"}
        recent = [t for t in self.frame_times if time.monotonic() - t < 1]
        status = {
            "state": state,
            "mode": self.mode,
            "glosses": [g.removeprefix("fs-") for g in glosses],
            "intent": intent,
            "target": TARGET,
            "log": list(self.log),
            "holding": self.letter_holding(),
            "fps": float(len(recent)),
            "error": None,
            # The webcam is open (only the camera recognizer opens it; the app always shows this).
            "camera_on": self.app.chosen.get("recognizer") == "camera" and self.mode != "off",
            # Turn-aware speaking in Meet: what our voice is doing, and whether they're talking.
            "speech": {"state": self.speech, "text": self.speech_text},
            "them_talking": self.them_talking,
            "autocomplete": self._autocomplete(),
            "autocomplete_stats": self.app.autocomplete.metrics(),
            "components": self.app.chosen,
            "mock": self.app.chosen.get("recognizer") == "mock",
        }
        if self.mode == "framing":
            status["framing"] = self._framing_hint()
        return status

    def letter_holding(self) -> list[Any] | None:
        """The letter being held for fingerspelling and its progress (0..1), for the app's bar."""
        reader = getattr(self.app.recognizer, "letters", None)
        holding = reader.holding if reader is not None else None
        return [holding[0], round(holding[1], 2)] if holding else None

    def _autocomplete(self) -> dict[str, Any] | None:
        update = self.spelling
        if update is None:
            return None
        words = [{"term": s.term, "kind": s.kind} for s in update.suggestions]
        return {
            "letters": update.letters,
            "top": words[0] if words else None,
            "alternates": words[1:],
            "dismissed": update.dismissed,
            "search": update.search,
        }

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
            OutputSent,
            Caption,
            Notice,
            SpeechStatus,
            TurnEvent,
            Mention,
            AutocompleteUpdate,
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
            holding = self.letter_holding()
            if holding != self._holding:  # the hold bar moves with the frames
                self._holding = holding
                self.emit_status()
            if self.preview:
                self._draw(event)
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
            self.sending = True  # straight to the voice (a review turns it into confirming)
        elif isinstance(event, ConfirmRequest):
            self.pending_id = event.request_id
            self.english = event.english
            self.sending = False
        elif isinstance(event, ConfirmResult):
            if event.request_id == self.pending_id:
                self.pending_id = None
                if event.approved:
                    self.sending = True  # reviewed: now it's spoken
                else:
                    self.log.append("cancelled")
        elif isinstance(event, OutputSent):
            self.sending = False
            self.log.append("sent" if event.output != "console" else "printed to the console")
            self.emit({"type": "sent", "output": event.output, "text": event.text})
        elif isinstance(event, Caption):
            self.emit({"type": "caption", "text": event.text, "final": event.is_final})
        elif isinstance(event, Notice):
            self.log.append(event.message)
        elif isinstance(event, Mention):
            mention = {"text": event.text, "question": event.question, "final": event.final}
            self.emit({"type": "mention", "turn": event.turn, **mention})
        elif isinstance(event, SpeechStatus):
            self.speech, self.speech_text = event.state, event.text
        elif isinstance(event, TurnEvent):
            self.them_talking = event.kind in ("start", "eager_end", "resume")
        elif isinstance(event, AutocompleteUpdate):
            self.spelling = event if event.letters else None
        self.emit_status()

    def _draw(self, frame: LandmarkFrame) -> None:
        now = time.monotonic()
        busy = self._drawing is not None and not self._drawing.done()
        if busy or now - self._last_drawn < 1 / self.preview_fps:
            return
        self._last_drawn = now
        state = getattr(self.app.recognizer, "sign_state", None)
        self._drawing = asyncio.get_running_loop().create_task(self._draw_frame(frame, state))

    async def _draw_frame(self, frame: LandmarkFrame, state: str | None) -> None:
        jpeg = await asyncio.to_thread(render_preview, frame, self.space, self.mirror, state)
        if jpeg and self.preview:
            self.frame_seq += 1
            self.emit(
                {"type": "frame", "seq": self.frame_seq, "jpeg": base64.b64encode(jpeg).decode()}
            )

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
            self._background(self.test_route(msg.get("text", "SignBridge voice test.")))
        elif cmd == "calibrate":
            self.calibrate()
        elif cmd == "config":
            self.ui_config.update(msg.get("values") or {})
            self._save_ui_config()
            self._apply_settings()
            self.emit({"type": "config", "config": self.ui_config})
        elif cmd == "introduce":
            self.app.call_host.introduce()
        elif cmd == "quick_reply":
            self.quick_reply(str(msg.get("text", "")))
        elif cmd == "letters":
            for letter in str(msg.get("text", "")):
                if letter.isalpha():
                    self.bus.publish(Letter(letter.upper()))
        elif cmd == "autocomplete":
            if msg.get("action") == "dismiss":
                self.app.autocomplete.dismiss()
            else:
                self.app.buffer.accept_suggestion(int(msg.get("index", 0) or 0))
        elif cmd == "vocab_list":
            self.emit({"type": "vocab", "words": await self.app.autocomplete.words()})
        elif cmd == "vocab_delete":
            if msg.get("id"):
                await self.app.autocomplete.delete_occurrence(str(msg["id"]))
            elif msg.get("term"):
                await self.app.autocomplete.delete_word(str(msg["term"]))
            self.emit({"type": "vocab", "words": await self.app.autocomplete.words()})
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
        if mode != "run":
            self.gesture("cancel")
        recognizer = self.app.recognizer
        if mode == "off":
            await recognizer.stop()
        else:
            await recognizer.start()

    def gesture(self, name: str) -> None:
        state = self.state()
        if state != "confirming" and self.app.autocomplete.active and name != "wake":
            # Spelling a word: thumbs up takes the suggestion, thumbs down dismisses it.
            if name == "confirm":
                self.app.buffer.accept_suggestion()
            elif name == "cancel":
                self.app.autocomplete.dismiss()
            return
        if name == "now":  # say it right away: ends the sentence, or hurries a waiting one
            self.control("NOW")
            return
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
            if not isinstance(event, SignEvent) or event.kind != "control":
                self.bus.publish(event)
        self.control("SEND")

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

    async def test_route(self, text: str) -> None:
        """Setup's voice test: say `text` into the virtual mic."""
        output = self.app.router.tts
        try:
            if not output.available():
                detail = f"The voice ({self.app.chosen.get('tts')}) isn't available."
                ok = False
            else:
                await output.send(text)
                ok, detail = True, ""
        except Exception as exc:
            ok, detail = False, str(exc)
        self.emit({"type": "route_tested", "route": "voice", "ok": ok, "detail": detail})

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

    def quick_reply(self, text: str) -> None:
        """Speak one of the configured replies (only those: the app can't make up words)."""
        reply = next((r for r in self.quick_replies if r["text"] == text), None)
        if reply is None:
            self.emit({"type": "error", "message": f"not a quick reply: {text!r}"})
            return
        self.log.append(f"quick reply: {text}")
        self._background(self.app.router.quick_reply(reply["text"], urgent=reply["urgent"]))

    def calibrate(self) -> None:
        """Setup's "Save This Position": fit the signing space to where the signer sits."""
        space = space_from_pose(self.frame.pose) if self.frame is not None else None
        if space is None:
            message = "I can't see your shoulders and face. Sit back so they show, then try again."
            self.emit({"type": "calibrated", "ok": False, "message": message})
            return
        self.ui_config["signing_space"] = asdict(space)
        self._save_ui_config()
        self._apply_settings()
        message = "Saved. Signs are read when your hands are up in the green box."
        self.emit({"type": "calibrated", "ok": True, "message": message})

    def _apply_settings(self) -> None:
        """Settings the app's Settings window changes that the engine uses."""
        self.app.call_host.name = str(self.ui_config.get("signer_name") or "").strip()
        self.app.mentions.set_name(self.app.call_host.name)
        self.app.router.review_before_speaking = bool(self.ui_config.get("review_before_speaking"))
        box = self.ui_config.get("signing_space")
        if isinstance(box, dict):
            with contextlib.suppress(TypeError, ValueError):
                self.space = SigningSpace(**{k: float(v) for k, v in box.items()})
                gate = getattr(self.app.recognizer, "gate", None)
                if gate is not None:
                    self.app.recognizer.gate = self.space

    def _save_ui_config(self) -> None:
        self.ui_config_path.parent.mkdir(parents=True, exist_ok=True)
        self.ui_config_path.write_text(json.dumps(self.ui_config, indent=2))
