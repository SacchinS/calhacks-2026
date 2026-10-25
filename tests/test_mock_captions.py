"""Mock captions play the demo call once (or loop with captions_mock.loop)."""

import asyncio

import pytest

from captions.mock import MockCaptionSource
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption


@pytest.mark.parametrize("loop", [False, True])
async def test_the_script_plays_once_unless_looping(tmp_path, loop):
    script = tmp_path / "call.txt"
    script.write_text("# a comment\nFirst.\nSecond.\n")
    settings = {"file": str(script), "interval_seconds": 0.01, "talk_seconds": 0, "loop": loop}
    bus = Bus()
    captions = bus.subscribe(Caption)
    source = MockCaptionSource(bus, Config(sections={"captions_mock": settings}))
    await source.start()
    await asyncio.sleep(0.2)
    await source.stop()
    said = [captions.get_nowait().text for _ in range(captions.queue.qsize())]
    assert said[:2] == ["First.", "Second."]
    assert (len(said) > 2) == loop
