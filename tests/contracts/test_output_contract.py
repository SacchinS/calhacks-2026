"""Contract for Output: every implementation must pass this.

Real outputs (`say` into BlackHole, Cartesia) only run with
`pytest --live`.
"""

import time

import pytest

from app import load_class
from outputs.base import Output
from outputs.console import ConsoleOutput
from tests.contracts.conftest import live

OUTPUTS = [
    ("tts", "mock"),
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
