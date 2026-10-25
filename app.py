"""Engine entry point: wires the bus, recognizer, utterance buffer + translator, the voice in
the call (router, turn-taking, call manners), captions, and fingerspelling autocomplete, and
serves them to the Mac app's windows (ui/macos) as JSON lines.

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
from captions.mentions import MentionDetector
from language.autocomplete import Autocompleter
from language.base import Translator
from language.tickets import TicketAgent
from language.utterance import UtteranceBuffer
from language.vocab import VocabStore, vocab_path
from language.vocab_terms import keyterms
from outputs.call_host import CallHost
from outputs.console import ConsoleOutput
from outputs.jira import JiraClient
from outputs.router import Router
from outputs.turn_taking import TurnTakingOutput
from recognition.base import Recognizer
from recognition.mock import MockRecognizer
from shared.bus import Bus
from shared.config import CHOICES, Config, load_config
from shared.events import Notice

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
    "tts": {
        "mock": "outputs.mock_tts:MockTTSOutput",
        "say": "outputs.tts_say:SayTTSOutput",
        "cartesia": "outputs.tts_cartesia:CartesiaTTSOutput",
    },
    "captions": {
        "mock": "captions.mock:MockCaptionSource",
        "cartesia": "captions.cartesia_stt:CartesiaCaptionSource",
    },
    "vocab_search": {
        "mock": "language.vocab_search:KeywordSearch",
        "moss": "language.vocab_search:MossSearch",
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
            tts=self._voice(config),
            console=self.console,
            review_before_speaking=bool(config.get("meet.review_before_speaking", False)),
        )
        self.call_host = CallHost(self.bus, config, self.router)
        self.captions: CaptionSource = self._build("captions", self.bus, config)
        self.mentions = MentionDetector(self.bus, config)
        # Fingerspelling autocomplete: the word memory (a local SQLite file) and its search.
        self.vocab = VocabStore(vocab_path(config))
        self.autocomplete = Autocompleter(
            self.bus, config, self.vocab, self._build("vocab_search", config)
        )
        self.buffer.spelling = self.autocomplete
        self.router.spelling = self.autocomplete  # a YES on a suggestion isn't an approval
        self.jira = JiraClient(config)
        self.tickets = TicketAgent(
            self.bus,
            config,
            self.jira,
            autocomplete=self.autocomplete,
            announcer=self.router,
        )
        self.router.tickets = self.tickets

    def _voice(self, config: Config) -> Any:
        """The TTS output, turn-aware in calls (waits for the other side to finish)."""
        tts = self._build("tts", self.bus, config)
        if config.get("meet.turn_taking", True):
            tts = TurnTakingOutput(self.bus, config, tts)
        return tts

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

    def _caption_keyterms(self) -> None:
        """Give the captions the names and jargon we remember, so they're spelled our way and
        the mention alerts match. The mock captions have no keyterms to set."""
        if not hasattr(self.captions, "keyterms"):
            return
        signer = self.config.get("meet.signer_name", "")
        names = [signer, *self.config.get("meet.mention_names", [])]
        self.captions.keyterms = keyterms(self.vocab.all(), names)
        log.debug("captions: %d keyterms", len(self.captions.keyterms))

    async def start(self) -> None:
        await self.buffer.start()
        await self.autocomplete.start()
        await self.router.start()
        await self.tickets.start()
        await self.call_host.start()
        await self.mentions.start()
        if isinstance(self.router.tts, TurnTakingOutput):
            await self.router.tts.start()
        try:
            await self.recognizer.start()
        except Exception as exc:
            log.exception("recognizer failed to start")
            self._warn(f"recognizer '{self.chosen['recognizer']}' failed ({exc}); using 'mock'")
            self.chosen["recognizer"] = "mock"
            self.recognizer = MockRecognizer(self.bus, self.config)
            await self.recognizer.start()
        try:
            self._caption_keyterms()
            await self.captions.start()
        except Exception as exc:
            log.exception("captions failed to start")
            self._warn(f"Captions '{self.captions.name}' failed: {exc}")
        for notice in self.notices:
            self.bus.publish(notice)

    async def stop(self) -> None:
        with contextlib.suppress(Exception):
            await self.recognizer.stop()
        with contextlib.suppress(Exception):
            await self.captions.stop()
        await self.call_host.stop()
        await self.mentions.stop()
        if isinstance(self.router.tts, TurnTakingOutput):
            await self.router.tts.stop()
        await self.router.stop()
        await self.tickets.stop()
        await self.autocomplete.stop()
        await self.buffer.stop()
        self.vocab.close()


async def run(config: Config) -> None:
    """Run as the engine of the Mac app (ui/macos), which launches this process and talks to
    it in JSON lines: commands on stdin, events on stdout. See ui/server.py."""
    from ui.server import EngineServer, protocol_stdout, stdin_reader

    app = App(config)
    server = EngineServer(app, protocol_stdout())
    server.send_ready()
    await server.start()  # before the app, so the windows see its first notices
    await app.start()
    await server.set_mode("off")  # paused until the app starts listening, like SignBridge
    try:
        await server.serve(await stdin_reader())
    finally:
        await app.stop()
        await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign in Google Meet calls (engine).")
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
