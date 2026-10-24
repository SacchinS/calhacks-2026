"""Cartesia TTS into the virtual mic, with a fake Cartesia client and a fake audio device."""

import base64
from types import SimpleNamespace

import numpy as np
import pytest

import outputs.tts_cartesia as tts_cartesia
from outputs.tts_cartesia import CartesiaTTSOutput, decode
from shared.bus import Bus
from shared.config import Config
from shared.events import Notice


def chunk(samples):
    data = base64.b64encode(np.asarray(samples, dtype="<f4").tobytes()).decode()
    return SimpleNamespace(type="chunk", data=data)


class FakeTTS:
    def __init__(self, events):
        self.events = events
        self.calls = []

    async def generate_sse(self, **kwargs):
        self.calls.append(kwargs)

        async def stream():
            for event in self.events:
                if isinstance(event, Exception):
                    raise event
                yield event

        return stream()


class FakePlayer:
    played: list = []

    def __init__(self, device, rate):
        self.rate = rate

    def write(self, frames):
        FakePlayer.played.append(frames)

    def drain(self):
        pass

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake_audio(monkeypatch):
    FakePlayer.played = []
    monkeypatch.setattr(tts_cartesia, "Player", FakePlayer)
    monkeypatch.setattr(tts_cartesia, "find_output_device", lambda name: 3)


def output(events, voice_id="voice-1"):
    tts = FakeTTS(events)
    voices = SimpleNamespace(list=None)
    client = SimpleNamespace(tts=tts, voices=voices)
    config = Config(sections={"cartesia": {"voice_id": voice_id, "tts_model": "sonic-latest"}})
    return CartesiaTTSOutput(Bus(), config, client=client), tts


def test_decode_makes_stereo_float32():
    frames = decode(chunk([0.1, -0.2]).data)
    assert frames.shape == (2, 2) and frames.dtype == np.float32
    assert np.allclose(frames[:, 0], frames[:, 1])


async def test_streams_chunks_into_the_virtual_mic():
    out, tts = output([chunk([0.1] * 4), chunk([0.2] * 4), SimpleNamespace(type="done")])
    await out.send("Hello, nice to meet you.")
    (call,) = tts.calls
    assert call["transcript"] == "Hello, nice to meet you."
    assert call["voice"] == "voice-1" and call["model_id"] == "sonic-latest"
    assert call["output_format"] == {
        "container": "raw",
        "encoding": "pcm_f32le",
        "sample_rate": 44100,
    }
    assert sum(len(f) for f in FakePlayer.played) == 8


async def test_falls_back_to_say_on_a_cartesia_error():
    out, _ = output([RuntimeError("401 unauthorized")])
    notices = out.bus.subscribe(Notice)
    spoken = []

    async def fake_say(text):
        spoken.append(text)

    out.fallback.send = fake_say
    await out.send("Thank you.")
    assert spoken == ["Thank you."]
    assert "Cartesia voice failed" in notices.get_nowait().message


async def test_picks_a_voice_when_none_is_set():
    out, tts = output([SimpleNamespace(type="done")], voice_id="")

    async def list_voices(limit):
        return SimpleNamespace(data=[SimpleNamespace(id="first-voice")])

    out.client.voices.list = list_voices
    await out.send("Hi.")
    assert tts.calls[0]["voice"] == "first-voice"


async def test_without_a_key_it_speaks_with_say_and_warns_once(monkeypatch):
    monkeypatch.delenv("CARTESIA_API_KEY", raising=False)
    out = CartesiaTTSOutput(Bus(), Config())
    assert out.available()  # the virtual mic is there
    notices = out.bus.subscribe(Notice)
    spoken = []

    async def fake_say(text):
        spoken.append(text)

    out.fallback.send = fake_say
    await out.send("Hello.")
    await out.send("Thank you.")
    assert spoken == ["Hello.", "Thank you."]
    assert notices.queue.qsize() == 1
