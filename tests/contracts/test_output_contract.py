"""Contract for Output: every implementation must pass this.

Real outputs (Claude Code, `say` into BlackHole, Cartesia) only run with `pytest --live`.
"""

import time

import pytest

from app import load_class
from outputs.base import Output
from outputs.console import ConsoleOutput
from shared.events import OutputReply
from tests.contracts.conftest import live

OUTPUTS = [
    ("claude_code", "mock"),
    ("tts", "mock"),
    live("claude_code", "real"),
    live("tts", "say"),
    live("tts", "cartesia"),
]


def build(component, name, bus, config):
    if component == "console":
        return ConsoleOutput(bus, config)
    return load_class(component, name)(bus, config)


@pytest.mark.parametrize("component,name", [("console", "console"), *OUTPUTS])
async def test_output_contract(component, name, bus, config):
    output = build(component, name, bus, config)
    assert isinstance(output, Output)
    assert isinstance(output.name, str) and output.name

    start = time.monotonic()
    available = output.available()
    assert isinstance(available, bool)
    assert time.monotonic() - start < 1.0, "available() must be fast"

    if not available:
        pytest.skip(f"{component}:{name} reports unavailable on this machine")
    await output.send("Hello.")


async def test_mock_claude_code_streams_a_reply(bus, config):
    output = load_class("claude_code", "mock")(bus, config)
    output.chunk_delay = 0
    replies = bus.subscribe(OutputReply)
    await output.send("Make the title red.")
    chunks = [replies.get_nowait() for _ in range(replies.queue.qsize())]
    assert chunks and chunks[-1].done
    assert "Make the title red." in chunks[0].text
