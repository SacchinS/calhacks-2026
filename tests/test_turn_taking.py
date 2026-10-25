"""Turn-aware speaking: wait for the other side to finish, chime in, stop when talked over."""

import asyncio

import pytest

from outputs.turn_taking import INTERJECTION, TurnTakingOutput
from shared.bus import Bus
from shared.config import Config
from shared.events import SpeechStatus, TurnEvent
from tests.test_router_confirm import RecordingOutput


class TimedVoice(RecordingOutput):
    """Speech that takes `seconds`; records what finished and what was cut off."""

    def __init__(self, seconds=0.2):
        super().__init__("tts")
        self.seconds = seconds
        self.cut = []

    async def send(self, text):
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cut.append(text)
            raise
        self.sent.append(text)


@pytest.fixture
async def call():
    bus = Bus()
    voice = TimedVoice()
    meet = {"chime_in_seconds": 0.4, "yield_seconds": 0.2, "barge_in_seconds": 0.1}
    out = TurnTakingOutput(bus, Config(sections={"meet": meet}), voice)
    await out.start()
    yield bus, out, voice
    await out.stop()


async def turn(bus, kind):
    bus.publish(TurnEvent(kind))
    await asyncio.sleep(0.01)


async def test_speaks_right_away_when_nobody_is_talking(call):
    bus, out, voice = call
    states = bus.subscribe(SpeechStatus)
    await out.send("Hello, nice to meet you.")
    assert voice.sent == ["Hello, nice to meet you."]
    assert [states.get_nowait().state for _ in range(2)] == ["speaking", "idle"]


async def test_waits_for_them_to_finish(call):
    bus, out, voice = call
    await turn(bus, "start")
    speaking = asyncio.create_task(out.send("Yes, I can."))
    await asyncio.sleep(0.15)
    assert voice.sent == []  # they're still talking
    await turn(bus, "eager_end")
    await turn(bus, "resume")  # not done after all
    await asyncio.sleep(0.1)
    assert voice.sent == []
    await turn(bus, "end")
    await speaking
    assert voice.sent == ["Yes, I can."]


async def test_chimes_in_when_the_floor_never_frees(call):
    bus, out, voice = call
    states = bus.subscribe(SpeechStatus)
    await turn(bus, "start")  # and they never stop
    await out.send("I have a question.")
    assert voice.sent == [INTERJECTION, "I have a question."]
    seen = []
    while not states.queue.empty():
        seen.append(states.get_nowait().state)
    assert seen[:2] == ["waiting", "interjecting"] and "speaking" in seen


async def test_talked_over_stops_and_says_it_again_at_the_pause(call):
    bus, out, voice = call
    voice.seconds = 0.5
    speaking = asyncio.create_task(out.send("The dashboard is done."))
    await asyncio.sleep(0.05)
    await turn(bus, "start")  # they start talking over us and keep going
    await asyncio.sleep(0.2)
    assert voice.cut == ["The dashboard is done."]
    await turn(bus, "end")
    await speaking
    assert voice.sent == ["The dashboard is done."]


async def test_a_short_backchannel_does_not_stop_us(call):
    bus, out, voice = call
    voice.seconds = 0.4
    speaking = asyncio.create_task(out.send("Let me explain the plan."))
    await asyncio.sleep(0.05)
    await turn(bus, "start")  # "mm-hm"
    await asyncio.sleep(0.03)
    await turn(bus, "end")
    await speaking
    assert voice.cut == [] and voice.sent == ["Let me explain the plan."]


async def test_sentences_are_spoken_one_at_a_time_in_order(call):
    bus, out, voice = call
    await asyncio.gather(out.send("First."), out.send("Second."))
    assert voice.sent == ["First.", "Second."]


async def test_urgent_quick_replies_skip_the_wait_normal_ones_wait(call):
    from outputs.router import Router

    bus, out, voice = call
    router = Router(bus, tts=out)
    await turn(bus, "start")  # they're mid-sentence
    await router.quick_reply("Please slow down a little.", urgent=True)
    assert voice.sent == ["Please slow down a little."]  # said right away
    normal = asyncio.create_task(router.quick_reply("Yes."))
    await asyncio.sleep(0.1)
    assert voice.sent == ["Please slow down a little."]  # "Yes." waits for the pause
    await turn(bus, "end")
    await normal
    assert voice.sent[-1] == "Yes."


@pytest.fixture
async def turn_based():
    bus = Bus()
    voice = TimedVoice()
    meet = {"chime_in_seconds": 0, "barge_in_seconds": 0.1}
    out = TurnTakingOutput(bus, Config(sections={"meet": meet}), voice)
    await out.start()
    yield bus, out, voice
    await out.stop()


async def test_turn_based_waits_for_the_pause_and_never_interjects(turn_based):
    bus, out, voice = turn_based
    await turn(bus, "start")
    speaking = asyncio.create_task(out.send("Wait, there's a color problem."))
    await asyncio.sleep(1.5)  # longer than any chime-in
    assert voice.sent == []
    await turn(bus, "end")
    await asyncio.wait_for(speaking, 2)
    assert voice.sent == ["Wait, there's a color problem."]  # no "Sorry, can I jump in?"


async def test_now_says_the_waiting_sentence_at_once_and_isnt_cut_off(turn_based):
    bus, out, voice = turn_based
    await turn(bus, "start")
    speaking = asyncio.create_task(out.send("Wait, there's a color problem."))
    await asyncio.sleep(0.2)
    out.hurry()  # the signer signed NOW
    await asyncio.wait_for(speaking, 2)  # they're still talking, but it's said, whole
    assert voice.sent == ["Wait, there's a color problem."] and voice.cut == []
    out.hurry()  # nothing waiting: nothing happens
