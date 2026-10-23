"""End to end on mocks: typed signs -> utterance -> translation -> router -> output."""

import asyncio

import pytest

from app import App
from shared.config import load_config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    MockInput,
    ModeChanged,
    OutputReply,
    OutputSent,
    Translation,
)


@pytest.fixture
async def app():
    app = App(load_config().all_mocks())
    app.router.claude_code.chunk_delay = 0
    yield app
    await app.stop()


async def next_of(sub, kind):
    async def find():
        while True:
            event = await sub.get()
            if isinstance(event, kind):
                return event

    return await asyncio.wait_for(find(), 5)


async def settle():
    for _ in range(10):
        await asyncio.sleep(0.01)


@pytest.mark.parametrize("answer", ["/yes", "/no"])
async def test_claude_code_confirm_sends_to_console_only_on_yes(app, answer):
    # Claude Code goes to the console output here, as when the real CLI is unavailable.
    app.router.claude_code = app.console
    events = app.bus.subscribe()
    await app.start()

    app.bus.publish(MockInput("ME WANT FIX BUG LOGIN PAGE"))
    app.bus.publish(MockInput("/send"))
    request = await next_of(events, ConfirmRequest)
    assert request.gloss == ["ME", "WANT", "FIX", "BUG", "LOGIN", "PAGE"]
    assert request.english == "I want fix bug login page."
    assert app.console.sent == []

    app.bus.publish(MockInput(answer))
    result = await next_of(events, ConfirmResult)
    await settle()
    assert result.request_id == request.request_id
    if answer == "/yes":
        assert result.approved
        assert app.console.sent == ["I want fix bug login page."]
    else:
        assert not result.approved
        assert app.console.sent == []


async def test_mock_claude_code_streams_reply_after_yes(app):
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("make #title red /send"))
    request = await next_of(events, ConfirmRequest)
    assert request.english == "Make title red."
    app.bus.publish(MockInput("/yes"))
    replies = [await next_of(events, OutputReply) for _ in range(4)]
    assert replies[-1].done
    sent = await next_of(events, OutputSent)
    assert (sent.output, sent.text) == ("claude_code", "Make title red.")


async def test_clear_empties_the_utterance(app):
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("wrong signs /clear hello /send"))
    translation = await next_of(events, Translation)
    assert translation.gloss == ["HELLO"]


async def test_voice_mode_speaks_without_confirm(app):
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("/mode"))
    assert (await next_of(events, ModeChanged)).mode == "claude_code"  # initial mode
    assert (await next_of(events, ModeChanged)).mode == "voice"
    app.bus.publish(MockInput("tomorrow rain /send"))
    sent = await next_of(events, OutputSent)
    assert (sent.output, sent.text) == ("tts", "Tomorrow rain.")


async def test_meet_mode_shows_captions_only_in_meet(app):
    events = app.bus.subscribe()
    await app.start()
    await settle()
    assert not any(isinstance(e, Caption) for e in drain(events))
    app.bus.publish(MockInput("/mode /mode"))
    caption = await next_of(events, Caption)
    assert caption.text
    app.bus.publish(MockInput("/mode"))  # back to claude_code: captions stop
    await settle()
    drain(events)
    await asyncio.sleep(0.2)
    assert not any(isinstance(e, Caption) for e in drain(events))


async def test_replay_runs_demo_script_from_fixture():
    config = load_config().all_mocks()
    config.recognizer = "replay"
    config.sections["recognition"]["replay_fps"] = 1000
    app = App(config)
    app.router.claude_code.chunk_delay = 0
    events = app.bus.subscribe()
    await app.start()
    try:
        request = await next_of(events, ConfirmRequest)
        assert request.gloss == ["MAKE", "fs-TITLE", "RED"]
        sent = await next_of(events, OutputSent)  # fixture ends with YES
        assert (sent.output, sent.text) == ("claude_code", "Make title red.")
    finally:
        await app.stop()


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.get_nowait())
    return out
