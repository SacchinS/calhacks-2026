import asyncio

import pytest

from outputs.console import ConsoleOutput
from outputs.router import Router
from shared.bus import Bus
from shared.events import (
    ConfirmRequest,
    ConfirmResult,
    Notice,
    OutputSent,
    SignEvent,
    Translation,
)


class RecordingOutput(ConsoleOutput):
    def __init__(self, name, available=True, fail=False):
        super().__init__()
        self.name = name
        self._available = available
        self._fail = fail

    def available(self):
        return self._available

    async def send(self, text):
        if self._fail:
            raise RuntimeError("boom")
        self.sent.append(text)


def control(gloss):
    return SignEvent(gloss, 1.0, "control")


def translation(text="Hello, nice to meet you."):
    return Translation(gloss=["HELLO", "NICE", "MEET-YOU"], english=text, provider="test")


@pytest.fixture
def setup():
    bus = Bus()
    events = bus.subscribe()
    tts = RecordingOutput("tts")
    console = RecordingOutput("console")
    router = Router(bus, tts=tts, console=console)
    return bus, events, router, tts, console


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.get_nowait())
    return out


async def test_speaks_without_confirm(setup):
    bus, events, router, tts, console = setup
    await router.handle(translation())
    assert tts.sent == ["Hello, nice to meet you."]
    published = drain(events)
    assert not any(isinstance(e, ConfirmRequest) for e in published)
    assert any(isinstance(e, OutputSent) and e.output == "tts" for e in published)


async def test_review_before_speaking_waits_for_yes():
    bus = Bus()
    events = bus.subscribe()
    tts = RecordingOutput("tts")
    router = Router(bus, tts=tts, review_before_speaking=True)
    await router.handle(translation())
    (request,) = [e for e in drain(events) if isinstance(e, ConfirmRequest)]
    assert request.english == "Hello, nice to meet you." and tts.sent == []
    await router.handle(control("NO"))
    await router.handle(control("YES"))  # nothing pending any more
    assert tts.sent == []
    results = [e for e in drain(events) if isinstance(e, ConfirmResult)]
    assert [(r.request_id, r.approved) for r in results] == [(request.request_id, False)]

    await router.handle(translation())
    await router.handle(control("YES"))
    assert tts.sent == ["Hello, nice to meet you."]


async def test_a_new_sentence_cancels_the_one_waiting_for_review():
    bus = Bus()
    events = bus.subscribe()
    router = Router(bus, tts=RecordingOutput("tts"), review_before_speaking=True)
    await router.handle(translation("First."))
    await router.handle(translation("Second."))
    published = drain(events)
    assert [e.approved for e in published if isinstance(e, ConfirmResult)] == [False]
    assert router.pending is not None and router.pending.english == "Second."


@pytest.mark.parametrize("available,fail", [(False, False), (True, True)])
async def test_unavailable_or_failing_output_falls_back_to_console(available, fail):
    bus = Bus()
    events = bus.subscribe()
    console = RecordingOutput("console")
    tts = RecordingOutput("tts", available=available, fail=fail)
    router = Router(bus, tts=tts, console=console)
    await router.handle(translation("Hi."))
    assert console.sent == ["Hi."]
    published = drain(events)
    assert any(isinstance(e, Notice) and e.level == "warning" for e in published)
    assert any(isinstance(e, OutputSent) and e.output == "console" for e in published)


async def test_started_router_processes_the_bus():
    bus = Bus()
    tts = RecordingOutput("tts")
    router = Router(bus, tts=tts, review_before_speaking=True)
    await router.start()
    bus.publish(translation())
    bus.publish(control("YES"))
    for _ in range(50):
        if tts.sent:
            break
        await asyncio.sleep(0.01)
    await router.stop()
    assert tts.sent == ["Hello, nice to meet you."]
