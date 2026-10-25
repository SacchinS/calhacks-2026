"""Live captions of the Meet call with Cartesia Ink STT (realtime websocket, turn detection).

Meet's speaker output has to reach a capture device that is NOT the one our voice goes into,
or we'd caption ourselves: install BlackHole 16ch, make a Multi-Output Device in Audio MIDI
Setup (your speakers + BlackHole 16ch), and pick it as Meet's speaker. We read
`audio.meet_capture_device` at 16 kHz mono and stream it to Cartesia; `turn.update` events
become partial captions and `turn.end` the final one. Ink's turn events (start, eager end,
resume, end) are also published as TurnEvents, so our voice knows when the floor is free
(outputs/turn_taking.py).

Only the other side's call audio goes to Cartesia, and nothing is saved or logged at INFO.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from captions.base import CaptionSource
from shared.bus import Bus
from shared.config import Config
from shared.events import Caption, Notice, TurnEvent

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK_FRAMES = SAMPLE_RATE // 10  # 100 ms of audio per websocket message
TURN_KINDS = {
    "turn.start": "start",
    "turn.eager_end": "eager_end",
    "turn.resume": "resume",
    "turn.end": "end",
}


def find_input_device(name: str) -> int | None:
    """Index of the first input device whose name contains `name`, or None."""
    try:
        import sounddevice as sd

        for index, device in enumerate(sd.query_devices()):
            if name.lower() in device["name"].lower() and device["max_input_channels"] > 0:
                return index
    except Exception as exc:  # PortAudio missing, etc.
        log.warning("can't list audio devices: %s", exc)
    return None


class CartesiaCaptionSource(CaptionSource):
    name = "cartesia"

    def __init__(self, bus: Bus, config: Config, client: Any = None) -> None:
        super().__init__(bus, config)
        self.model = config.get("cartesia.stt_model", "ink-2")
        # Must NOT be audio.virtual_mic_device, or we'd caption our own TTS.
        self.device_name = config.get("audio.meet_capture_device", "BlackHole 16ch")
        self.voice_device = config.get("audio.virtual_mic_device", "BlackHole 2ch")
        self._client = client
        self._task: asyncio.Task[None] | None = None
        # Remembered names and jargon, so Ink spells them the way the signer does (app.py
        # fills this from the word memory before start). Ink takes them when the connection
        # opens and they can't change mid-stream, so words learned during a call reach it on
        # the next start.
        self.keyterms: list[str] = []
        # Optional Ink turn-detection tuning (cartesia.turn_* in config.yaml).
        keys = (
            "turn_start_threshold",
            "turn_end_threshold",
            "turn_eager_end_threshold",
            "turn_end_timeout_ms",
        )
        self.turns = {
            k: float(config.get(f"cartesia.{k}"))
            for k in keys
            if config.get(f"cartesia.{k}") is not None
        }

    @property
    def client(self) -> Any:
        if self._client is None:
            from cartesia import AsyncCartesia

            self._client = AsyncCartesia(api_key=Config.secret("CARTESIA_API_KEY"))
        return self._client

    def check(self) -> int:
        """The capture device's index. Raises with what to fix if captions can't run."""
        if self.device_name.strip().lower() == self.voice_device.strip().lower():
            raise RuntimeError(
                "audio.meet_capture_device is the virtual mic: we'd caption our own voice"
            )
        if self._client is None and not Config.secret("CARTESIA_API_KEY"):
            raise RuntimeError("CARTESIA_API_KEY isn't set (.env)")
        device = find_input_device(self.device_name)
        if device is None:
            raise RuntimeError(f"capture device {self.device_name!r} not found")
        return device

    async def start(self) -> None:
        if self._task is None or self._task.done():
            device = self.check()
            self._task = asyncio.create_task(self._run(device), name="cartesia-captions")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self, device: int) -> None:
        try:
            audio: asyncio.Queue[bytes] = asyncio.Queue(maxsize=50)
            with self._microphone(device, audio):
                terms = {"keyterm": list(self.keyterms)} if self.keyterms else {}
                if terms:
                    log.debug("Cartesia captions: %d keyterms", len(self.keyterms))
                ws = self.client.stt.auto_finalize.websocket(
                    encoding="pcm_s16le",
                    model=self.model,
                    sample_rate=SAMPLE_RATE,
                    **terms,
                    **self.turns,
                )
                async with ws as connection:
                    sender = asyncio.create_task(self._send_audio(connection, audio))
                    try:
                        await self._receive(connection)
                    finally:
                        sender.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await sender
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Cartesia captions stopped: %s", type(exc).__name__)
            self.bus.publish(Notice("warning", f"Captions stopped ({exc})"))

    async def _send_audio(self, connection: Any, audio: asyncio.Queue[bytes]) -> None:
        while True:
            await connection.send_raw(await audio.get())

    async def _receive(self, connection: Any) -> None:
        async for event in connection:
            kind = getattr(event, "type", None)
            text = (getattr(event, "transcript", "") or "").strip()
            if kind in TURN_KINDS:
                self.bus.publish(TurnEvent(TURN_KINDS[kind]))
            if kind == "turn.update" and text:
                self.bus.publish(Caption(text, is_final=False))
            elif kind == "turn.end" and text:
                self.bus.publish(Caption(text, is_final=True))
            elif kind == "error":
                raise RuntimeError(getattr(event, "message", None) or "Cartesia STT error")

    @contextlib.contextmanager
    def _microphone(self, device: int, audio: asyncio.Queue[bytes]):
        """Capture 16 kHz mono int16 audio from `device` into `audio`, dropping if behind."""
        import sounddevice as sd

        loop = asyncio.get_running_loop()

        def put(chunk: bytes) -> None:
            if audio.full():
                audio.get_nowait()
            audio.put_nowait(chunk)

        def callback(indata, frames, time, status) -> None:  # PortAudio's thread
            loop.call_soon_threadsafe(put, bytes(indata))

        stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_FRAMES,
            channels=1,
            dtype="int16",
            device=device,
            callback=callback,
        )
        with stream:
            yield
