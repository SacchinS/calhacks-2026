"""Local web UI: FastAPI serves ui/static and a WebSocket at /ws.

Server -> browser: {"type": "snapshot", ...} on connect, then every UI-relevant bus event
as {"type": "<EventClassName>", ...fields}.
Browser -> server: {"type": "mock_input", "text": "..."} (mock-sign box) and
{"type": "control", "sign": "CLEAR" | "MODE"} (buttons).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shared.bus import Bus
from shared.config import Config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    MockInput,
    ModeChanged,
    Notice,
    OutputReply,
    OutputSent,
    SignEvent,
    Translation,
    UtteranceProgress,
)

log = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"

# Events forwarded to the browser. LandmarkFrames are left out (30/s, too heavy for now).
UI_EVENTS = (
    SignEvent,
    UtteranceProgress,
    Translation,
    ConfirmRequest,
    ConfirmResult,
    ModeChanged,
    OutputSent,
    OutputReply,
    Caption,
    Notice,
)
BUTTON_SIGNS = {"CLEAR", "MODE"}


def to_json(event: Any) -> dict[str, Any]:
    return {"type": type(event).__name__, **asdict(event)}


class UIState:
    """What a newly connected browser needs to draw the current screen."""

    def __init__(self, components: dict[str, str]) -> None:
        self.components = components
        self.mode = "claude_code"
        self.gloss: list[str] = []
        self.translation: dict[str, Any] | None = None
        self.pending: dict[str, Any] | None = None
        self.sent: deque[dict[str, Any]] = deque(maxlen=20)
        self.replies: deque[dict[str, Any]] = deque(maxlen=50)
        self.captions: deque[dict[str, Any]] = deque(maxlen=20)
        self.notices: deque[dict[str, Any]] = deque(maxlen=10)

    def apply(self, event: Any) -> None:
        data = to_json(event)
        if isinstance(event, ModeChanged):
            self.mode = event.mode
        elif isinstance(event, UtteranceProgress):
            self.gloss = list(event.gloss)
        elif isinstance(event, Translation):
            self.translation = data
        elif isinstance(event, ConfirmRequest):
            self.pending = data
        elif isinstance(event, ConfirmResult):
            if self.pending and self.pending["request_id"] == event.request_id:
                self.pending = None
        elif isinstance(event, OutputSent):
            self.sent.append(data)
        elif isinstance(event, OutputReply):
            self.replies.append(data)
        elif isinstance(event, Caption):
            self.captions.append(data)
        elif isinstance(event, Notice):
            self.notices.append(data)

    def snapshot(self) -> dict[str, Any]:
        return {
            "type": "snapshot",
            "components": self.components,
            "mode": self.mode,
            "gloss": self.gloss,
            "translation": self.translation,
            "pending": self.pending,
            "sent": list(self.sent),
            "replies": list(self.replies),
            "captions": list(self.captions),
            "notices": list(self.notices),
        }


def create_app(bus: Bus, state: UIState) -> FastAPI:
    app = FastAPI(title="calhacks-2026")
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        sub = bus.subscribe(*UI_EVENTS, maxsize=500)
        await socket.send_json(state.snapshot())

        async def forward() -> None:
            async for event in sub:
                await socket.send_json(to_json(event))

        sender = asyncio.create_task(forward())
        try:
            while True:
                handle_message(bus, await socket.receive_json())
        except WebSocketDisconnect:
            pass
        finally:
            sub.close()
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender

    return app


def handle_message(bus: Bus, message: dict[str, Any]) -> None:
    kind = message.get("type")
    if kind == "mock_input":
        bus.publish(MockInput(str(message.get("text", ""))))
    elif kind == "control" and message.get("sign") in BUTTON_SIGNS:
        bus.publish(SignEvent(message["sign"], 1.0, "control"))
    else:
        log.warning("ignoring UI message %r", message)


class UIServer:
    """Keeps UIState current from the bus and serves the app with uvicorn."""

    def __init__(self, bus: Bus, config: Config, components: dict[str, str]) -> None:
        self.bus = bus
        self.config = config
        self.state = UIState(components)
        self.app = create_app(bus, self.state)
        self._state_task: asyncio.Task[None] | None = None

    @property
    def url(self) -> str:
        host = self.config.get("ui.host", "127.0.0.1")
        return f"http://{'localhost' if host == '127.0.0.1' else host}:{self.port}"

    @property
    def port(self) -> int:
        return int(self.config.get("ui.port", 8000))

    async def start(self) -> None:
        """Start tracking state. Call before the other components start publishing."""
        sub = self.bus.subscribe(*UI_EVENTS)

        async def track() -> None:
            async for event in sub:
                self.state.apply(event)

        self._state_task = asyncio.create_task(track(), name="ui-state")

    async def serve(self) -> None:
        """Serve until Ctrl-C."""
        server = uvicorn.Server(
            uvicorn.Config(
                self.app,
                host=self.config.get("ui.host", "127.0.0.1"),
                port=self.port,
                log_level="warning",
            )
        )
        log.info("UI at %s", self.url)
        print(f"UI: {self.url}", flush=True)
        await server.serve()

    async def stop(self) -> None:
        if self._state_task is not None:
            self._state_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._state_task
            self._state_task = None
