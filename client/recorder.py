import asyncio
import io
import os
import time
import wave
from typing import Optional

from common.logger import setup_logger

logger = setup_logger("recorder")


class AudioRecorder:
    def __init__(self, sample_rate: int = 48000, channels: int = 1, chunk_size: int = 960):
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._recording = False
        self._audio_chunks: list = []
        self._stream = None
        self._pyaudio = None

    def start(self) -> bool:
        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=self._channels,
                rate=self._sample_rate,
                input=True,
                frames_per_buffer=self._chunk_size,
            )
            self._audio_chunks.clear()
            self._recording = True
            logger.info(f"Recording started (rate={self._sample_rate}, channels={self._channels})")
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    def read_chunk(self) -> Optional[bytes]:
        if not self._recording or self._stream is None:
            return None
        try:
            data = self._stream.read(self._chunk_size, exception_on_overflow=False)
            self._audio_chunks.append(data)
            return data
        except Exception as e:
            logger.error(f"Failed to read audio chunk: {e}")
            return None

    def stop(self) -> bytes:
        self._recording = False
        audio_data = b"".join(self._audio_chunks)

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

        logger.info(f"Recording stopped, {len(audio_data)} bytes captured")
        return audio_data

    def save_wav(self, filepath: str, audio_data: Optional[bytes] = None):
        data = audio_data or b"".join(self._audio_chunks)
        if not data:
            return

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(self._channels)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(data)
            logger.info(f"Audio saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")

    def to_wav_bytes(self, audio_data: Optional[bytes] = None) -> bytes:
        data = audio_data or b"".join(self._audio_chunks)
        if not data:
            return b""

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)
            wf.setframerate(self._sample_rate)
            wf.writeframes(data)
        return buf.getvalue()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def sample_rate(self) -> int:
        return self._sample_rate
