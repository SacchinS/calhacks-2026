"""Cartesia Sonic TTS into the virtual mic. STUB: unavailable, so the router uses the console."""

from __future__ import annotations

import logging

from outputs.base import Output
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)


class CartesiaTTSOutput(Output):
    name = "tts"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.model = config.get("cartesia.tts_model", "sonic-3.6")
        self.voice_id = config.get("cartesia.voice_id", "")
        self.sample_rate = int(config.get("cartesia.sample_rate", 44100))
        self.device_name = config.get("audio.virtual_mic_device", "BlackHole 2ch")
        log.warning("CartesiaTTSOutput is a stub (model %s)", self.model)

    def available(self) -> bool:
        # TODO(Person C): return bool(Config.secret("CARTESIA_API_KEY")) and the
        # virtual mic device exists (outputs.tts_say.find_output_device(self.device_name)).
        return False

    async def send(self, text: str) -> None:
        # TODO(Person C): stream Cartesia Sonic audio into the virtual mic:
        #   client = cartesia.AsyncCartesia(api_key=Config.secret("CARTESIA_API_KEY"))
        #   stream TTS for `text` with model_id=self.model, voice id=self.voice_id,
        #   output format raw pcm_f32le at self.sample_rate (check docs.cartesia.ai for the
        #   current SDK call), and write each chunk to a sounddevice.OutputStream opened on
        #   find_output_device(self.device_name), so audio starts before synthesis ends.
        # On any Cartesia error: warn in the UI (self.bus.publish(Notice("warning", ...)))
        # and fall back to outputs.tts_say.SayTTSOutput(self.bus, self.config).send(text).
        raise NotImplementedError("CartesiaTTSOutput is a stub")
