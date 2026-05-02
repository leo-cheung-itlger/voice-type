import asyncio
import io
import os
import time
import wave
from typing import Optional

from common.audio_levels import measure_pcm16_level
from common.logger import setup_logger

logger = setup_logger("recorder")


class AudioRecorder:
    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 1,
        chunk_size: int = 960,
        input_device_index: int = -1,
        input_device_name: str = "",
        input_device_host_api: str = "",
        input_device_sample_rate: int = 0,
    ):
        self._sample_rate = sample_rate
        self._active_sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._input_device_index = input_device_index
        self._input_device_name = input_device_name
        self._input_device_host_api = input_device_host_api
        self._input_device_sample_rate = input_device_sample_rate
        self._active_device_index: Optional[int] = input_device_index if input_device_index >= 0 else None
        self._active_device_name = input_device_name
        self._active_host_api = input_device_host_api
        self._recording = False
        self._audio_chunks: list = []
        self._stream = None
        self._pyaudio = None

    def start(self) -> bool:
        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
            selected_device = self._input_device_index if self._input_device_index >= 0 else None
            try:
                self._stream = self._open_stream(pyaudio, selected_device)
            except Exception as selected_error:
                if selected_device is None:
                    raise
                logger.warning(
                    "Selected input device failed, falling back to default: index=%s name=%s error=%s",
                    self._input_device_index,
                    self._input_device_name,
                    selected_error,
                )
                self._stream = self._open_stream(pyaudio, None)
            self._audio_chunks.clear()
            self._recording = True
            device_label = "default" if self._active_device_index is None else f"{self._active_device_index}:{self._active_device_name}"
            logger.info(
                "Recording started (rate=%s, channels=%s, device=%s, host_api=%s)",
                self._active_sample_rate,
                self._channels,
                device_label,
                self._active_host_api or "-",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    def _open_stream(self, pyaudio_module, input_device_index: Optional[int]):
        info = self._device_info(input_device_index)
        preferred_rate = self._preferred_sample_rate(info)
        rates = [preferred_rate]
        if self._sample_rate not in rates:
            rates.append(self._sample_rate)
        last_error: Optional[Exception] = None
        for rate in rates:
            try:
                stream = self._open_stream_at_rate(pyaudio_module, input_device_index, rate)
                self._set_active_device(input_device_index, info, rate)
                return stream
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Failed to open input stream at %sHz for device=%s: %s",
                    rate,
                    "default" if input_device_index is None else input_device_index,
                    exc,
                )
        if last_error:
            raise last_error
        raise RuntimeError("No input stream rate was attempted")

    def _open_stream_at_rate(self, pyaudio_module, input_device_index: Optional[int], sample_rate: int):
        kwargs = {
            "format": pyaudio_module.paInt16,
            "channels": self._channels,
            "rate": sample_rate,
            "input": True,
            "frames_per_buffer": self._chunk_size,
        }
        if input_device_index is not None:
            kwargs["input_device_index"] = input_device_index
        return self._pyaudio.open(**kwargs)

    def _device_info(self, input_device_index: Optional[int]) -> dict:
        if not self._pyaudio:
            return {}
        try:
            if input_device_index is None:
                return dict(self._pyaudio.get_default_input_device_info())
            return dict(self._pyaudio.get_device_info_by_index(input_device_index))
        except Exception:
            return {}

    def _preferred_sample_rate(self, info: dict) -> int:
        if self._input_device_sample_rate > 0:
            return int(self._input_device_sample_rate)
        default_rate = int(float(info.get("defaultSampleRate", 0) or 0))
        return default_rate or self._sample_rate

    def _set_active_device(self, input_device_index: Optional[int], info: dict, sample_rate: int):
        self._active_device_index = input_device_index
        self._active_device_name = str(info.get("name") or self._input_device_name or "")
        self._active_sample_rate = int(sample_rate)
        host_api = ""
        if self._pyaudio and "hostApi" in info:
            try:
                host_api = str(self._pyaudio.get_host_api_info_by_index(int(info["hostApi"])).get("name") or "")
            except Exception:
                host_api = ""
        self._active_host_api = host_api or self._input_device_host_api

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

        level = measure_pcm16_level(audio_data)
        logger.info(
            "Recording stopped, %s bytes captured, rms=%s peak=%s signal=%s",
            len(audio_data),
            level["rms_ratio"],
            level["peak_ratio"],
            level["has_signal"],
        )
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
                wf.setframerate(self._active_sample_rate)
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
            wf.setframerate(self._active_sample_rate)
            wf.writeframes(data)
        return buf.getvalue()

    def audio_level(self, audio_data: Optional[bytes] = None) -> dict:
        data = audio_data or b"".join(self._audio_chunks)
        return measure_pcm16_level(data)

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def sample_rate(self) -> int:
        return self._active_sample_rate
