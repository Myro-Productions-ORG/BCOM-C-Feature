"""PCM audio playback via sounddevice with cancellable stop()."""

import asyncio
import logging
from typing import AsyncIterator

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class AudioPlayer:
    def __init__(self, sample_rate: int = 22050, device: str = ""):
        self._sample_rate = sample_rate
        self._device = device or None   # None = sounddevice default
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        """Signal playback to stop at the next chunk boundary."""
        self._stop_event.set()

    async def play(self, stream: AsyncIterator[bytes]) -> None:
        """Stream PCM chunks to the output device. Returns when done or stop() called."""
        self._stop_event.clear()
        loop = asyncio.get_running_loop()

        with sd.OutputStream(
            samplerate=self._sample_rate,
            channels=1,
            dtype="int16",
            device=self._device,
        ) as out_stream:
            remainder = b""
            async for chunk in stream:
                if self._stop_event.is_set():
                    logger.info("AudioPlayer: stop() called — interrupting playback")
                    break
                data = remainder + chunk
                # int16 requires even byte count — carry odd byte to next chunk
                if len(data) % 2 != 0:
                    remainder = data[-1:]
                    data = data[:-1]
                else:
                    remainder = b""
                if data:
                    samples = np.frombuffer(data, dtype=np.int16)
                    await loop.run_in_executor(None, out_stream.write, samples)


def find_device(name_fragment: str) -> int | None:
    """Return sounddevice index of first output device matching name_fragment (case-insensitive)."""
    devices = sd.query_devices()
    for i, dev in enumerate(devices):
        if name_fragment.lower() in dev["name"].lower() and dev["max_output_channels"] > 0:
            return i
    return None
