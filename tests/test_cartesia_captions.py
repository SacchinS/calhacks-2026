"""Cartesia captions with a fake websocket and a fake capture device."""

import asyncio
import contextlib
from types import SimpleNamespace

import pytest

import captions.cartesia_stt as stt
from captions.cartesia_stt import CartesiaCaptionSource
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, Notice


class FakeConnection:
    def __init__(self, events):
        self.events = events
        self.sent = []

    async def send_raw(self, data):
        self.sent.append(data)

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for event in self.events:
            await asyncio.sleep(0.01)
            yield event
        await asyncio.sleep(3600)  # the call goes on


class FakeWebsocket:
    def __init__(self, connection):
        self.connection = connection
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *exc):
        return False


def source(events, **audio):
    connection = FakeConnection(events)
    websocket = FakeWebsocket(connection)
    client = SimpleNamespace(
        stt=SimpleNamespace(auto_finalize=SimpleNamespace(websocket=websocket))
    )
    config = Config(sections={"audio": audio})
    src = CartesiaCaptionSource(Bus(), config, client=client)

    @contextlib.contextmanager
    def fake_microphone(device, queue):
        queue.put_nowait(b"\x00\x01" * 1600)
        yield

    src._microphone = fake_microphone
    return src, connection, websocket


@pytest.fixture(autouse=True)
def capture_device(monkeypatch):
    monkeypatch.setattr(stt, "find_input_device", lambda name: 7)


async def test_partial_then_final_captions():
    events = [
        SimpleNamespace(type="connected"),
        SimpleNamespace(type="turn.update", transcript="Hi Sam"),
        SimpleNamespace(type="turn.update", transcript="Hi Sam, how are"),
        SimpleNamespace(type="turn.end", transcript="Hi Sam, how are you?"),
    ]
    src, connection, websocket = source(events)
    captions = src.bus.subscribe(Caption)
    await src.start()
    got = [await asyncio.wait_for(captions.get(), 2) for _ in range(3)]
    await src.stop()
    assert [(c.text, c.is_final) for c in got] == [
        ("Hi Sam", False),
        ("Hi Sam, how are", False),
        ("Hi Sam, how are you?", True),
    ]
    assert websocket.kwargs == {"encoding": "pcm_s16le", "model": "ink-2", "sample_rate": 16000}
    assert connection.sent == [b"\x00\x01" * 1600]


async def test_remembered_words_are_sent_as_keyterms():
    """So Ink writes "Priyanka", not "Prianca", and the mention alert matches."""
    src, _, websocket = source([SimpleNamespace(type="connected")])
    src.keyterms = ["Sam", "Priyanka", "Figma"]
    await src.start()
    for _ in range(50):
        if websocket.kwargs is not None:
            break
        await asyncio.sleep(0.01)
    await src.stop()
    assert websocket.kwargs["keyterm"] == ["Sam", "Priyanka", "Figma"]


async def test_no_keyterm_argument_when_nothing_is_remembered():
    src, _, websocket = source([SimpleNamespace(type="connected")])
    await src.start()
    for _ in range(50):
        if websocket.kwargs is not None:
            break
        await asyncio.sleep(0.01)
    await src.stop()
    assert "keyterm" not in websocket.kwargs


async def test_refuses_to_caption_our_own_voice():
    src, _, _ = source([], meet_capture_device="BlackHole 2ch", virtual_mic_device="BlackHole 2ch")
    with pytest.raises(RuntimeError, match="our own voice"):
        await src.start()


async def test_an_error_event_stops_with_a_notice():
    src, _, _ = source([SimpleNamespace(type="error", message="bad key")])
    notices = src.bus.subscribe(Notice)
    await src.start()
    notice = await asyncio.wait_for(notices.get(), 2)
    assert "bad key" in notice.message
    await src.stop()


async def test_ink_turn_events_become_turn_events():
    from shared.events import TurnEvent

    events = [
        SimpleNamespace(type="turn.start", transcript=""),
        SimpleNamespace(type="turn.eager_end", transcript="Can you"),
        SimpleNamespace(type="turn.resume", transcript="Can you"),
        SimpleNamespace(type="turn.end", transcript="Can you take it?"),
    ]
    src, _, _ = source(events)
    turns = src.bus.subscribe(TurnEvent)
    await src.start()
    kinds = [(await asyncio.wait_for(turns.get(), 2)).kind for _ in range(4)]
    await src.stop()
    assert kinds == ["start", "eager_end", "resume", "end"]
