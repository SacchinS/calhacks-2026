"""Meet call manners: the spoken intro and the "One moment, I'm signing." cue."""

import asyncio

import pytest

from outputs.call_host import CUE, CallHost
from outputs.router import Router
from shared.bus import Bus
from shared.config import Config
from shared.events import UtteranceProgress
from tests.test_router_confirm import RecordingOutput


@pytest.fixture
async def call():
    bus = Bus()
    tts = RecordingOutput("tts")
    router = Router(bus, claude_code=RecordingOutput("claude_code"), tts=tts)
    meet = {"signer_name": "Sam", "signing_cue_seconds": 0.05, "intro_on_start": True}
    config = Config(sections={"meet": meet})
    host = CallHost(bus, config, router)
    await router.start()
    await host.start()
    await asyncio.sleep(0.01)
    yield bus, router, host, tts
    await host.stop()
    await router.stop()


async def settle(seconds=0.02):
    await asyncio.sleep(seconds)


async def test_intro_once_when_meet_starts(call):
    bus, router, host, tts = call
    router.set_mode("meet")
    await settle()
    assert tts.sent == [
        "Hi, this is Sam. I'm Deaf and signing through SignBridge, "
        "so there may be a short pause before I answer."
    ]
    router.set_mode("meet")  # already in Meet: no second intro
    router.set_mode("voice")
    await settle()
    assert len(tts.sent) == 1
    host.introduce()  # the "Introduce me" button
    await settle()
    assert len(tts.sent) == 2


async def test_intro_without_a_name():
    host = CallHost(Bus(), Config(), Router(Bus(), RecordingOutput("c"), RecordingOutput("t")))
    assert host.intro_text().startswith("Hi. I'm Deaf and signing through SignBridge")


async def test_signing_cue_once_per_utterance_and_only_in_meet(call):
    bus, router, host, tts = call
    bus.publish(UtteranceProgress(("HELLO",)))  # not in Meet: no cue
    await settle(0.1)
    assert tts.sent == []

    router.set_mode("meet")
    await settle()
    tts.sent.clear()
    bus.publish(UtteranceProgress(("HELLO",)))
    bus.publish(UtteranceProgress(("HELLO", "NICE")))
    await settle(0.1)
    assert tts.sent == [CUE]
    bus.publish(UtteranceProgress(("HELLO", "NICE", "MEET-YOU")))
    await settle(0.1)
    assert tts.sent == [CUE]  # once per utterance

    bus.publish(UtteranceProgress(()))  # sent
    bus.publish(UtteranceProgress(("HOW",)))
    bus.publish(UtteranceProgress(()))  # sent quickly: no cue
    await settle(0.1)
    assert tts.sent == [CUE]


def test_meeting_defaults_have_no_automatic_intro_or_cue():
    from shared.config import load_config

    host = CallHost(Bus(), load_config(), Router(Bus(), RecordingOutput("c"), RecordingOutput("t")))
    assert not host.intro_on_start and host.cue_seconds == 0
