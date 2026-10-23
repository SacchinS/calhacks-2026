"""Contract for Recognizer: every implementation must pass this.

Each implementation gets a driver that makes it produce at least one sign: the mock is
fed typed input, replay plays the fixture, and the camera needs someone to sign HELLO.
"""

import asyncio

import pytest

from app import load_class
from recognition.base import Recognizer
from shared.events import CONTROL_SIGNS, MockInput, SignEvent
from tests.contracts.conftest import live

TIMEOUT = {"mock": 2, "replay": 10, "camera": 30}


def drive(name, bus):
    if name == "mock":
        bus.publish(MockInput("hello #title /send"))
    elif name == "camera":
        print("Sign HELLO to the webcam now")


@pytest.mark.parametrize("name", ["mock", "replay", live("camera")])
async def test_recognizer_contract(name, bus, config):
    recognizer = load_class("recognizer", name)(bus, config)
    assert isinstance(recognizer, Recognizer)
    signs = bus.subscribe(SignEvent)

    await recognizer.start()
    try:
        drive(name, bus)
        event = await asyncio.wait_for(signs.get(), TIMEOUT[name])
    finally:
        await recognizer.stop()
        await recognizer.stop()  # stop() is idempotent

    assert event.gloss and event.gloss == event.gloss.upper()
    assert 0.0 <= event.confidence <= 1.0
    assert event.kind in ("isolated", "fingerspell", "control")
    if event.kind == "control":
        assert event.gloss in CONTROL_SIGNS

    # No events after stop().
    while not signs.queue.empty():
        signs.get_nowait()
    drive(name, bus)
    await asyncio.sleep(0.2)
    assert signs.queue.empty()
