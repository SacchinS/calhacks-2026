"""End to end on mocks: typed signs -> utterance -> translation -> router -> the voice."""

import asyncio

import pytest

from app import App
from shared.config import load_config
from shared.events import (
    Caption,
    ConfirmRequest,
    ConfirmResult,
    MockInput,
    OutputSent,
    Translation,
)


@pytest.fixture
async def app():
    app = App(load_config().all_mocks())
    app.config.sections["mock_tts"]["seconds_per_word"] = 0  # instant mock speech
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


async def test_signs_are_spoken_in_the_call(app):
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("hello #priyanka nice meet-you /send"))
    sent = await next_of(events, OutputSent)
    assert (sent.output, sent.text) == ("tts", "Hello priyanka nice meet-you.")
    assert not any(isinstance(e, ConfirmRequest) for e in drain(events))


@pytest.mark.parametrize("answer", ["/yes", "/no"])
async def test_review_before_speaking_speaks_only_on_yes(app, answer):
    app.router.review_before_speaking = True
    app.router.tts = app.console  # as when the voice is unavailable
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


async def test_clear_empties_the_utterance(app):
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("wrong signs /clear hello /send"))
    translation = await next_of(events, Translation)
    assert translation.gloss == ["HELLO"]


async def test_captions_start_with_the_app(app):
    events = app.bus.subscribe()
    await app.start()
    caption = await next_of(events, Caption)
    assert caption.text
    await app.captions.stop()
    await settle()
    drain(events)
    await asyncio.sleep(0.2)
    assert not any(isinstance(e, Caption) for e in drain(events))


async def test_replay_runs_the_sample_fixture():
    config = load_config().all_mocks()
    config.recognizer = "replay"
    config.sections["recognition"]["replay_fps"] = 1000
    config.sections["mock_tts"]["seconds_per_word"] = 0
    app = App(config)
    events = app.bus.subscribe()
    await app.start()
    try:
        translation = await next_of(events, Translation)
        assert translation.gloss == ["MAKE", "fs-TITLE", "RED"]
        sent = await next_of(events, OutputSent)
        assert (sent.output, sent.text) == ("tts", "Make title red.")
    finally:
        await app.stop()


def drain(sub):
    out = []
    while not sub.queue.empty():
        out.append(sub.get_nowait())
    return out


async def test_users_words_never_reach_info_logs(app, caplog):
    """Privacy: the packaged app saves INFO logs to disk, so no transcripts at INFO."""
    caplog.set_level("INFO")
    events = app.bus.subscribe()
    await app.start()
    app.bus.publish(MockInput("zebra purple /send"))
    await next_of(events, OutputSent)
    app.router.review_before_speaking = True
    app.bus.publish(MockInput("zebra purple /send"))
    await next_of(events, ConfirmRequest)
    app.bus.publish(MockInput("/yes"))
    await next_of(events, OutputSent)
    logged = " ".join(r.getMessage() for r in caplog.records).lower()
    assert "zebra" not in logged and "purple" not in logged
