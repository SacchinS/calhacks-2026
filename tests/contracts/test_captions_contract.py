"""Contract for CaptionSource: every implementation must pass this.

Cartesia captions need a live Meet call's audio, so they only run with `pytest --live`.
"""

import asyncio

import pytest

from app import load_class
from captions.base import CaptionSource
from shared.events import Caption
from tests.contracts.conftest import live


@pytest.mark.parametrize("name", ["mock", live("cartesia")])
async def test_captions_contract(name, bus, config):
    source = load_class("captions", name)(bus, config)
    assert isinstance(source, CaptionSource)
    captions = bus.subscribe(Caption)

    for _ in range(2):  # start/stop/start again must work
        await source.start()
        try:
            caption = await asyncio.wait_for(captions.get(), 30)
        finally:
            await source.stop()
            await source.stop()
        assert isinstance(caption.text, str) and caption.text.strip()

    while not captions.queue.empty():
        captions.get_nowait()
    await asyncio.sleep(0.1)
    assert captions.queue.empty(), "no captions after stop()"
