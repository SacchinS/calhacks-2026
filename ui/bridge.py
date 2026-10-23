"""Bridge between the asyncio bus and Qt.

The app runs on one thread: qasync drives asyncio from Qt's event loop. The bridge reads
bus events in an asyncio task and re-emits each as a Qt signal, so windows only ever deal
with signals and slots. Windows send input back with send_mock_input() / send_control().
"""

from __future__ import annotations

import asyncio
import contextlib

from PySide6.QtCore import QObject, Signal

from shared.bus import Bus
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
    UtteranceProgress,
)

# Signs the windows' buttons may publish. YES / NO must be signed, never clicked.
BUTTON_SIGNS = frozenset({"CLEAR", "MODE"})


class BusBridge(QObject):
    sign = Signal(object)  # SignEvent
    progress = Signal(object)  # UtteranceProgress
    translation = Signal(object)  # Translation
    confirm_request = Signal(object)  # ConfirmRequest
    confirm_result = Signal(object)  # ConfirmResult
    mode_changed = Signal(object)  # ModeChanged
    output_sent = Signal(object)  # OutputSent
    output_reply = Signal(object)  # OutputReply
    caption = Signal(object)  # Caption
    notice = Signal(object)  # Notice
    frame = Signal(object)  # LandmarkFrame (latest only; older frames are dropped)

    def __init__(self, bus: Bus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus
        self._signals = {
            SignEvent: self.sign,
            UtteranceProgress: self.progress,
            Translation: self.translation,
            ConfirmRequest: self.confirm_request,
            ConfirmResult: self.confirm_result,
            ModeChanged: self.mode_changed,
            OutputSent: self.output_sent,
            OutputReply: self.output_reply,
            Caption: self.caption,
            Notice: self.notice,
        }
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Start forwarding. Call before the app starts so no early events are missed."""
        if self._tasks:
            return
        events = self.bus.subscribe(*self._signals)
        # Frames arrive at camera rate with images: keep only the newest couple.
        frames = self.bus.subscribe(LandmarkFrame, maxsize=2)
        self._tasks = [
            asyncio.create_task(self._forward(events), name="ui-bridge-events"),
            asyncio.create_task(self._forward(frames), name="ui-bridge-frames"),
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
                self.emit_event(event)
        finally:
            sub.close()

    def emit_event(self, event: object) -> None:
        if isinstance(event, LandmarkFrame):
            self.frame.emit(event)
        elif (signal := self._signals.get(type(event))) is not None:
            signal.emit(event)

    # Window -> bus

    def send_mock_input(self, text: str) -> None:
        if text.strip():
            self.bus.publish(MockInput(text))

    def send_control(self, sign: str) -> None:
        if sign not in BUTTON_SIGNS:
            raise ValueError(f"{sign} can't be sent from a button")
        self.bus.publish(SignEvent(sign, 1.0, "control"))
