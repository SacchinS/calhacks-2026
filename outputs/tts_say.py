"""Offline backup voice: macOS `say` rendered to audio and played into the virtual mic.

Works with no API key. Needs macOS and the device in `audio.virtual_mic_device`
(BlackHole 2ch). Select that device as the microphone in dictation / Meet.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

from outputs.base import Output

log = logging.getLogger(__name__)

SAMPLE_RATE = 22050


def find_output_device(name: str) -> int | None:
    """Index of the first output device whose name contains `name`, or None."""
    try:
        import sounddevice as sd

        for index, device in enumerate(sd.query_devices()):
            if name.lower() in device["name"].lower() and device["max_output_channels"] > 0:
                return index
    except Exception as exc:  # PortAudio missing, etc.
        log.warning("can't list audio devices: %s", exc)
    return None


def play_on_device(samples: np.ndarray, rate: int, device: int) -> None:
    """Blocking: play float32 samples (frames x channels) on a sounddevice output."""
    import sounddevice as sd

    sd.play(samples, rate, device=device)
    sd.wait()


class SayTTSOutput(Output):
    name = "tts"

    @property
    def device_name(self) -> str:
        return self.config.get("audio.virtual_mic_device", "BlackHole 2ch")

    def available(self) -> bool:
        return (
            sys.platform == "darwin"
            and shutil.which("say") is not None
            and find_output_device(self.device_name) is not None
        )

    async def send(self, text: str) -> None:
        device = find_output_device(self.device_name)
        if device is None:
            raise RuntimeError(f"audio device {self.device_name!r} not found")
        samples = await self.render(text)
        log.info("say -> %s (%d chars)", self.device_name, len(text))
        await asyncio.to_thread(play_on_device, samples, SAMPLE_RATE, device)

    @staticmethod
    async def render(text: str) -> np.ndarray:
        """Render text with `say` to float32 stereo samples at SAMPLE_RATE."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "say.wav"
            proc = await asyncio.create_subprocess_exec(
                "say",
                "-o",
                str(path),
                "--file-format=WAVE",
                f"--data-format=LEI16@{SAMPLE_RATE}",
                text,
            )
            if await proc.wait() != 0:
                raise RuntimeError(f"`say` exited with {proc.returncode}")
            with wave.open(str(path)) as wav:
                pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
        mono = pcm.astype(np.float32) / 32768.0
        return np.column_stack([mono, mono])  # BlackHole 2ch is stereo
