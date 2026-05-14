"""
Async mic capture + speaker playback for Gemini Live.

Audio is raw PCM (16-bit little-endian, mono). Sample rates differ for
input and output — see config.py. We push input frames continuously
(Gemini Live handles VAD internally) and play output frames the moment
they arrive.

Optional deps. Import lazily so text mode runs without sounddevice.
"""

from __future__ import annotations

import asyncio
import queue
from typing import AsyncIterator

import config


class MicCapture:
    """Continuous mic stream as small PCM frames."""

    def __init__(self, frame_ms: int = 20) -> None:
        import sounddevice as sd  # noqa
        self._sd = sd
        self.frame_samples = int(config.INPUT_SAMPLE_RATE * frame_ms / 1000)
        self._q: queue.Queue[bytes] = queue.Queue()
        self._stream = sd.RawInputStream(
            samplerate=config.INPUT_SAMPLE_RATE,
            channels=config.AUDIO_CHANNELS,
            dtype=config.AUDIO_DTYPE,
            blocksize=self.frame_samples,
            callback=self._cb,
        )
        self._stream.start()

    def _cb(self, indata, frames, _t, _status):  # noqa: ANN001
        self._q.put(bytes(indata))

    async def frames(self) -> AsyncIterator[bytes]:
        loop = asyncio.get_event_loop()
        while True:
            data = await loop.run_in_executor(None, self._q.get)
            yield data

    def close(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass


class Speaker:
    """Streaming PCM playback. Writes are non-blocking; the underlying
    sounddevice OutputStream buffers."""

    def __init__(self) -> None:
        import sounddevice as sd  # noqa
        self._sd = sd
        self._stream = sd.RawOutputStream(
            samplerate=config.OUTPUT_SAMPLE_RATE,
            channels=config.AUDIO_CHANNELS,
            dtype=config.AUDIO_DTYPE,
        )
        self._stream.start()

    def write(self, pcm_bytes: bytes) -> None:
        try:
            self._stream.write(pcm_bytes)
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:  # noqa: BLE001
            pass
