"""Entry point: wires the bus, recognizer, utterance buffer + translator, router, captions,
and the two UI windows (PySide6, with asyncio running inside Qt's loop via qasync).

    uv run python app.py           # components as chosen in config.yaml   (make run)
    uv run python app.py --mock    # every component forced to its mock    (make mock)

Any component that fails to load or start falls back to its mock (or the console) with a
warning in the UI; the app never crashes because one part isn't ready.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import logging
import signal
import sys
from typing import Any

from captions.base import CaptionSource
from language.base import Translator
from language.utterance import UtteranceBuffer
from outputs.console import ConsoleOutput
from outputs.router import Router
from recognition.base import Recognizer
from recognition.mock import MockRecognizer
from shared.bus import Bus
from shared.config import CHOICES, Config, load_config
from shared.events import ModeChanged, Notice

log = logging.getLogger("app")

# config.yaml value -> implementation. The first entry of each is the mock.
REGISTRY: dict[str, dict[str, str]] = {
    "recognizer": {
        "mock": "recognition.mock:MockRecognizer",
        "replay": "recognition.replay:ReplayRecognizer",
        "camera": "recognition.camera:CameraRecognizer",
    },
    "translator": {
        "mock": "language.mock:MockTranslator",
        "claude": "language.claude:ClaudeTranslator",
    },
    "claude_code": {
        "mock": "outputs.mock_claude_code:MockClaudeCodeOutput",
        "real": "outputs.claude_code:ClaudeCodeOutput",
    },
    "tts": {
        "mock": "outputs.mock_tts:MockTTSOutput",
        "say": "outputs.tts_say:SayTTSOutput",
        "cartesia": "outputs.tts_cartesia:CartesiaTTSOutput",
    },
    "captions": {
        "mock": "captions.mock:MockCaptionSource",
        "cartesia": "captions.cartesia_stt:CartesiaCaptionSource",
    },
}
assert {k: tuple(v) for k, v in REGISTRY.items()} == CHOICES


def load_class(component: str, choice: str) -> type:
    module, _, name = REGISTRY[component][choice].partition(":")
    return getattr(importlib.import_module(module), name)


class App:
    def __init__(self, config: Config, bus: Bus | None = None, read_stdin: bool = False):
        self.config = config
        self.bus = bus or Bus()
        self.notices: list[Notice] = []  # published in start(), once the UI is listening
        self.chosen = {key: getattr(config, key) for key in REGISTRY}

        self.read_stdin = read_stdin
        self.recognizer: Recognizer = self._build("recognizer", self.bus, config)
        self._attach_stdin()
        self.translator: Translator = self._build("translator", config)
        self.buffer = UtteranceBuffer(self.bus, self.translator)
        self.console = ConsoleOutput(self.bus, config)
        self.router = Router(
            self.bus,
            claude_code=self._build("claude_code", self.bus, config),
            tts=self._build("tts", self.bus, config),
            console=self.console,
            mode=config.mode,  # type: ignore[arg-type]
        )
        self.captions: CaptionSource = self._build("captions", self.bus, config)
        self._captions_task: asyncio.Task[None] | None = None

    def _build(self, component: str, *args: Any) -> Any:
        choice = self.chosen[component]
        try:
            return load_class(component, choice)(*args)
        except Exception as exc:
            mock = next(iter(REGISTRY[component]))
            log.exception("%s '%s' failed to load", component, choice)
            self._warn(f"{component} '{choice}' failed to load ({exc}); using '{mock}'")
            self.chosen[component] = mock
            return load_class(component, mock)(*args)

    def _attach_stdin(self) -> None:
        if isinstance(self.recognizer, MockRecognizer):
            self.recognizer.read_stdin = self.read_stdin

    def _warn(self, message: str) -> None:
        self.notices.append(Notice("warning", message))

    async def start(self) -> None:
        mode_changes = self.bus.subscribe(ModeChanged)
        self._captions_task = asyncio.create_task(self._captions_follow_mode(mode_changes))
        await self.buffer.start()
        await self.router.start()
        try:
            await self.recognizer.start()
        except Exception as exc:
            log.exception("recognizer failed to start")
            self._warn(f"recognizer '{self.chosen['recognizer']}' failed ({exc}); using 'mock'")
            self.chosen["recognizer"] = "mock"
            self.recognizer = MockRecognizer(self.bus, self.config)
            self._attach_stdin()
            await self.recognizer.start()
        for notice in self.notices:
            self.bus.publish(notice)

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            await self.recognizer.stop()
        if self._captions_task is not None:
            self._captions_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._captions_task
        with contextlib.suppress(Exception):
            await self.captions.stop()
        await self.router.stop()
        await self.buffer.stop()

    async def _captions_follow_mode(self, mode_changes) -> None:
        """Captions run only in Meet mode."""
        try:
            async for event in mode_changes:
                if event.mode == "meet":
                    try:
                        await self.captions.start()
                    except Exception as exc:
                        log.exception("captions failed to start")
                        self.bus.publish(
                            Notice("warning", f"Captions '{self.captions.name}' failed: {exc}")
                        )
                else:
                    await self.captions.stop()
        finally:
            mode_changes.close()


async def run(config: Config) -> None:
    """Run the app with both windows until the control window (or every window) closes."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from ui.bridge import BusBridge
    from ui.camera_window import CameraWindow
    from ui.control_window import ControlWindow

    qt_app = QApplication.instance()
    closed = asyncio.Event()
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.lastWindowClosed.connect(closed.set)
    # Ctrl-C in the terminal: Python only sees the signal when it runs, so tick regularly.
    signal.signal(signal.SIGINT, lambda *_: closed.set())
    tick = QTimer(interval=200, timeout=lambda: None)
    tick.start()

    app = App(config, read_stdin=True)
    bridge = BusBridge(app.bus)
    camera = CameraWindow(bridge, config)
    control = ControlWindow(bridge, app.chosen)
    control.closing.connect(closed.set)
    await bridge.start()  # before the app, so the windows see the first ModeChanged and notices
    camera.show_restored()
    control.show()
    await app.start()
    control.set_components(app.chosen)  # a component may have fallen back while starting
    try:
        await closed.wait()
    finally:
        await app.stop()
        await bridge.stop()
        camera.close()
        control.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign to Claude Code, Siri, and Meet.")
    parser.add_argument("--mock", action="store_true", help="force every component to its mock")
    parser.add_argument("--config", help="path to config.yaml")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config)
    if args.mock:
        config = config.all_mocks()

    import qasync
    from PySide6.QtWidgets import QApplication

    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("calhacks-2026")
    with contextlib.suppress(KeyboardInterrupt):
        qasync.run(run(config))


if __name__ == "__main__":
    main()
