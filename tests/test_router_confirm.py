import asyncio

import pytest

from outputs.console import ConsoleOutput
from outputs.router import Router
from shared.bus import Bus
from shared.events import (
    ConfirmRequest,
    ConfirmResult,
    ModeChanged,
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


def translation(text="Fix the login page."):
    return Translation(gloss=["FIX", "LOGIN", "PAGE"], english=text, provider="test")


@pytest.fixture
def setup():
    bus = Bus()
    events = bus.subscribe()
    claude_code = RecordingOutput("claude_code")
    tts = RecordingOutput("tts")
    console = RecordingOutput("console")
    router = Router(bus, claude_code=claude_code, tts=tts, console=console)
    return bus, events, router, claude_code, tts, console


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.get_nowait())
    return out


async def test_yes_sends_to_claude_code(setup):
    bus, events, router, claude_code, tts, console = setup
    await router.handle(translation())
    (request,) = [e for e in drain(events) if isinstance(e, ConfirmRequest)]
    assert request.english == "Fix the login page."
    assert claude_code.sent == []  # nothing goes out before YES

    await router.handle(control("YES"))
    assert claude_code.sent == ["Fix the login page."]
    published = drain(events)
    results = [e for e in published if isinstance(e, ConfirmResult)]
    assert [(r.request_id, r.approved) for r in results] == [(request.request_id, True)]
    assert any(isinstance(e, OutputSent) and e.output == "claude_code" for e in published)


async def test_no_discards(setup):
    bus, events, router, claude_code, tts, console = setup
    await router.handle(translation())
    await router.handle(control("NO"))
    await router.handle(control("YES"))  # nothing pending any more
    assert claude_code.sent == [] and console.sent == []
    results = [e for e in drain(events) if isinstance(e, ConfirmResult)]
    assert [r.approved for r in results] == [False]


async def test_voice_mode_speaks_without_confirm(setup):
    bus, events, router, claude_code, tts, console = setup
    await router.handle(control("MODE"))
    assert router.mode == "voice"
    await router.handle(translation("Hello."))
    assert tts.sent == ["Hello."]
    assert not any(isinstance(e, ConfirmRequest) for e in drain(events))


async def test_mode_cycles_and_cancels_pending(setup):
    bus, events, router, *_ = setup
    await router.handle(translation())
    for _ in range(3):
        await router.handle(control("MODE"))
    published = drain(events)
    assert [e.mode for e in published if isinstance(e, ModeChanged)] == [
        "voice",
        "meet",
        "claude_code",
    ]
    assert [e.approved for e in published if isinstance(e, ConfirmResult)] == [False]


@pytest.mark.parametrize("available,fail", [(False, False), (True, True)])
async def test_unavailable_or_failing_output_falls_back_to_console(available, fail):
    bus = Bus()
    events = bus.subscribe()
    console = RecordingOutput("console")
    tts = RecordingOutput("tts", available=available, fail=fail)
    router = Router(bus, claude_code=console, tts=tts, console=console, mode="voice")
    await router.handle(translation("Hi."))
    assert console.sent == ["Hi."]
    published = drain(events)
    assert any(isinstance(e, Notice) and e.level == "warning" for e in published)
    assert any(isinstance(e, OutputSent) and e.output == "console" for e in published)


async def test_started_router_publishes_mode_and_processes_bus():
    bus = Bus()
    events = bus.subscribe()
    claude_code = RecordingOutput("claude_code")
    router = Router(bus, claude_code=claude_code, tts=RecordingOutput("tts"))
    await router.start()
    bus.publish(translation())
    bus.publish(control("YES"))
    for _ in range(50):
        if claude_code.sent:
            break
        await asyncio.sleep(0.01)
    await router.stop()
    assert claude_code.sent == ["Fix the login page."]
    assert isinstance(events.get_nowait(), ModeChanged)
