"""Type to Siri: opens Siri, pastes, presses Return, in that order (keystrokes faked)."""

import pytest

from outputs import siri
from outputs.siri import KEY_RETURN, SiriOutput
from shared.bus import Bus
from shared.config import load_config


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def bus():
    return Bus()


async def test_types_the_question_into_siri(monkeypatch, bus, config):
    steps = []
    monkeypatch.setattr(siri, "accessibility_ok", lambda: True)
    monkeypatch.setattr(siri, "open_siri", lambda hold: steps.append(("open", hold)))
    monkeypatch.setattr(siri, "paste", lambda text: steps.append(("paste", text)))
    monkeypatch.setattr(siri, "press", lambda key, flags=0: steps.append(("press", key)))
    monkeypatch.setattr(siri.time, "sleep", lambda s: None)
    output = SiriOutput(bus, config)
    assert output.available()
    await output.send("Will it rain tomorrow?")
    assert steps == [("open", 0.8), ("paste", "Will it rain tomorrow?"), ("press", KEY_RETURN)]


async def test_without_accessibility_it_is_unavailable_and_send_raises(monkeypatch, bus, config):
    monkeypatch.setattr(siri, "accessibility_ok", lambda: False)
    output = SiriOutput(bus, config)
    assert not output.available()
    with pytest.raises(RuntimeError, match="Accessibility"):
        await output.send("Hi.")
