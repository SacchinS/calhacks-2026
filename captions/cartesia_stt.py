"""Live captions of the Meet call with Cartesia Ink STT. STUB: start() raises, and the app
shows a warning and runs without captions."""

from __future__ import annotations

import logging

from captions.base import CaptionSource
from shared.bus import Bus
from shared.config import Config

log = logging.getLogger(__name__)


class CartesiaCaptionSource(CaptionSource):
    name = "cartesia"

    def __init__(self, bus: Bus, config: Config) -> None:
        super().__init__(bus, config)
        self.model = config.get("cartesia.stt_model", "ink-2")
        # Must NOT be audio.virtual_mic_device, or we'd caption our own TTS.
        self.device_name = config.get("audio.meet_capture_device", "BlackHole 16ch")
        log.warning("CartesiaCaptionSource is a stub (model %s)", self.model)

    async def start(self) -> None:
        # TODO(Person C): caption the other side of the Meet call:
        # 1. Route Meet's speaker output to a capture device that is separate from the one
        #    our TTS writes into (e.g. a Multi-Output Device -> "BlackHole 16ch"), named in
        #    config.yaml as audio.meet_capture_device. Refuse to start if it equals
        #    audio.virtual_mic_device.
        # 2. Open a sounddevice.InputStream on that device (16 kHz mono PCM) and stream the
        #    chunks over Cartesia's STT websocket with model self.model (`cartesia` SDK, key
        #    from Config.secret("CARTESIA_API_KEY"); check docs.cartesia.ai for the call).
        # 3. Publish Caption(text, is_final=...) for each transcript (partial and final).
        # Run it all in a background task so start() returns quickly; stop() cancels it.
        raise NotImplementedError("CartesiaCaptionSource is a stub")

    async def stop(self) -> None:
        pass
