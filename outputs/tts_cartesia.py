"""Cartesia Sonic TTS, streamed into the virtual mic (BlackHole 2ch) as it's generated.

Select BlackHole 2ch as the microphone in Meet or dictation, and the other side hears the
signer's English in a Cartesia voice. Audio starts playing before synthesis finishes (the
SSE endpoint sends raw PCM chunks). If Cartesia fails, the UI gets a warning and the same
text is spoken with the offline `say` voice instead, so a call never goes silent.

Only the English text goes to Cartesia; it's never logged at INFO.
"""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import numpy as np

from outputs.base import Output
from outputs.tts_say import SayTTSOutput, find_output_device
from shared.bus import Bus
from shared.config import Config
from shared.events import Notice

log = logging.getLogger(__name__)

SAMPLE_RATES = (8000, 16000, 22050, 24000, 44100, 48000)


class CartesiaTTSOutput(Output):
    name = "tts"

    def __init__(self, bus: Bus, config: Config, client: Any = None) -> None:
        super().__init__(bus, config)
        self.model = config.get("cartesia.tts_model", "sonic-latest")
        self.voice_id = str(config.get("cartesia.voice_id", "") or "")
        rate = int(config.get("cartesia.sample_rate", 44100))
        self.sample_rate = rate if rate in SAMPLE_RATES else 44100
        self.device_name = config.get("audio.virtual_mic_device", "BlackHole 2ch")
        self._client = client
        self.fallback = SayTTSOutput(bus, config)

    @property
    def client(self) -> Any:
        if self._client is None:
            from cartesia import AsyncCartesia

            self._client = AsyncCartesia(api_key=Config.secret("CARTESIA_API_KEY"))
        return self._client

    def available(self) -> bool:
        return bool(Config.secret("CARTESIA_API_KEY")) and (
            find_output_device(self.device_name) is not None
        )

    async def send(self, text: str) -> None:
        device = find_output_device(self.device_name)
        if device is None:
            raise RuntimeError(f"audio device {self.device_name!r} not found")
        try:
            await self.stream(text, device)
        except Exception as exc:
            log.warning("Cartesia TTS failed (%s); using `say`", type(exc).__name__)
            self.bus.publish(Notice("warning", f"Cartesia voice failed ({exc}); used `say`"))
            await self.fallback.send(text)

    async def stream(self, text: str, device: int) -> None:
        log.info("Cartesia TTS (%d chars) -> %s", len(text), self.device_name)
        events = await self.client.tts.generate_sse(
            model_id=self.model,
            transcript=text,
            voice=await self.voice(),
            output_format={
                "container": "raw",
                "encoding": "pcm_f32le",
                "sample_rate": self.sample_rate,
            },
            language="en",
        )
        player = Player(device, self.sample_rate)
        try:
            async for event in events:
                kind = getattr(event, "type", None)
                if kind == "chunk" and event.data:
                    await asyncio.to_thread(player.write, decode(event.data))
                elif kind == "error":
                    raise RuntimeError(getattr(event, "message", None) or "Cartesia error")
                elif kind == "done":
                    break
            await asyncio.to_thread(player.drain)
        finally:
            await asyncio.to_thread(player.close)

    async def voice(self) -> str:
        """The configured voice, or the first voice the account can use (picked once)."""
        if not self.voice_id:
            page = await self.client.voices.list(limit=1)
            voices = list(getattr(page, "data", None) or [])
            if not voices:
                raise RuntimeError("no Cartesia voices: set cartesia.voice_id in config.yaml")
            self.voice_id = voices[0].id
            log.warning("cartesia.voice_id is empty; using voice %s", self.voice_id)
        return self.voice_id


def decode(data: str) -> np.ndarray:
    """One SSE chunk (base64 pcm_f32le mono) -> float32 stereo frames for BlackHole 2ch."""
    mono = np.frombuffer(base64.b64decode(data), dtype="<f4")
    return np.column_stack([mono, mono])


class Player:
    """A sounddevice output stream on the virtual mic, fed chunk by chunk (blocking calls)."""

    def __init__(self, device: int, rate: int) -> None:
        import sounddevice as sd

        self.stream = sd.OutputStream(samplerate=rate, channels=2, dtype="float32", device=device)
        self.stream.start()

    def write(self, frames: np.ndarray) -> None:
        self.stream.write(np.ascontiguousarray(frames, dtype=np.float32))

    def drain(self) -> None:
        self.stream.stop()  # waits for buffered audio to finish playing

    def close(self) -> None:
        self.stream.close()
