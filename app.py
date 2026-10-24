"""Engine entry point: wires the bus, recognizer, utterance buffer + translator, router, and
captions, and serves them to the Mac app's windows (ui/macos) as JSON lines.

    make run     # build and open the Mac app; components as chosen in config.yaml
    make mock    # same, with every component forced to its mock
    uv run python app.py --mock    # the engine alone, speaking the protocol in the terminal

Any component that fails to load or start falls back to its mock (or the console) with a
warning in the UI; the app never crashes because one part isn't ready.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib
import logging
from typing import Any

from captions.base import CaptionSource
from language.base import Translator
from language.utterance import UtteranceBuffer
from outputs.call_host import CallHost
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
    "siri": {
        "mock": "outputs.mock_siri:MockSiriOutput",
        "real": "outputs.siri:SiriOutput",
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
    def __init__(self, config: Config, bus: Bus | None = None):
        self.config = config
        self.bus = bus or Bus()
        self.notices: list[Notice] = []  # published in start(), once the UI is listening
        self.chosen = {key: getattr(config, key) for key in REGISTRY}

        self.recognizer: Recognizer = self._build("recognizer", self.bus, config)
        self.translator: Translator = self._build("translator", config)
        self.buffer = UtteranceBuffer(self.bus, self.translator)
        self.console = ConsoleOutput(self.bus, config)
        self.router = Router(
            self.bus,
            claude_code=self._build("claude_code", self.bus, config),
            siri=self._build("siri", self.bus, config),
            tts=self._build("tts", self.bus, config),
            console=self.console,
            mode=config.mode,  # type: ignore[arg-type]
            review_before_speaking=bool(config.get("meet.review_before_speaking", False)),
        )
        self.call_host = CallHost(self.bus, config, self.router)
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

    def _warn(self, message: str) -> None:
        self.notices.append(Notice("warning", message))

    async def start(self) -> None:
        mode_changes = self.bus.subscribe(ModeChanged)
        self._captions_task = asyncio.create_task(self._captions_follow_mode(mode_changes))
        await self.buffer.start()
        await self.router.start()
        await self.call_host.start()
        try:
            await self.recognizer.start()
        except Exception as exc:
            log.exception("recognizer failed to start")
            self._warn(f"recognizer '{self.chosen['recognizer']}' failed ({exc}); using 'mock'")
            self.chosen["recognizer"] = "mock"
            self.recognizer = MockRecognizer(self.bus, self.config)
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
        await self.call_host.stop()
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
    """Run as the engine of the Mac app (ui/macos), which launches this process and talks to
    it in JSON lines: commands on stdin, events on stdout. See ui/server.py."""
    from ui.server import EngineServer, protocol_stdout, stdin_reader

    app = App(config)
    server = EngineServer(app, protocol_stdout())
    server.send_ready()
    await server.start()  # before the app, so the windows see the first ModeChanged and notices
    await app.start()
    await server.set_mode("off")  # paused until the app starts listening, like SignBridge
    try:
        await server.serve(await stdin_reader())
    finally:
        await app.stop()
        await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign to Claude Code, Siri, and Meet (engine).")
    parser.add_argument("--mock", action="store_true", help="force every component to its mock")
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--overlay", help="settings on top of config.yaml, e.g. config.demo.yaml")
    args = parser.parse_args()

    # Logs go to stderr: stdout carries the protocol.
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = load_config(args.config, overlay=args.overlay)
    if args.mock:
        config = config.all_mocks()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(config))


if __name__ == "__main__":
    main()
