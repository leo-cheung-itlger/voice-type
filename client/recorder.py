import asyncio
import os
import time
from typing import Any, Optional

from common.audio_capture import (
    normalize_pcm16_to_mono,
    open_input_stream_with_profile,
    resolve_input_device_index,
    wav_bytes_from_pcm16,
)
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
        self._active_capture_channels = max(1, int(channels or 1))
        self._normalized_channels = 1
        self._recording = False
        self._audio_chunks: list = []
        self._stream = None
        self._pyaudio = None
        self._last_capture: dict[str, Any] | None = None

    def configure(
        self,
        sample_rate: int,
        channels: int,
        input_device_index: int,
        input_device_name: str,
        input_device_host_api: str,
        input_device_sample_rate: int,
    ):
        self._sample_rate = int(sample_rate or self._sample_rate)
        self._channels = int(channels or self._channels)
        self._input_device_index = int(input_device_index if input_device_index is not None else -1)
        self._input_device_name = input_device_name or ""
        self._input_device_host_api = input_device_host_api or ""
        self._input_device_sample_rate = int(input_device_sample_rate or 0)

    def start(self) -> bool:
        try:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
            selected_device = resolve_input_device_index(
                self._pyaudio,
                selected_index=self._input_device_index,
                selected_name=self._input_device_name,
                selected_host_api=self._input_device_host_api,
                selected_sample_rate=self._input_device_sample_rate,
                logger=logger,
            )
            try:
                self._stream, profile = open_input_stream_with_profile(
                    self._pyaudio,
                    pyaudio,
                    selected_device,
                    preferred_sample_rate=self._input_device_sample_rate,
                    configured_sample_rate=self._sample_rate,
                    preferred_channels=self._channels,
                    frames_per_buffer=self._chunk_size,
                    logger=logger,
                )
            except Exception as selected_error:
                fallback_device = resolve_input_device_index(
                    self._pyaudio,
                    selected_index=-1,
                    selected_name="",
                    selected_host_api="",
                    selected_sample_rate=0,
                    exclude_indexes={selected_device} if selected_device is not None else set(),
                    logger=None,
                )
                if fallback_device == selected_device:
                    raise
                logger.warning(
                    "Selected input device failed, falling back to smart default: selected=%s name=%s fallback=%s error=%s",
                    selected_device,
                    self._input_device_name,
                    "default" if fallback_device is None else fallback_device,
                    selected_error,
                )
                self._stream, profile = open_input_stream_with_profile(
                    self._pyaudio,
                    pyaudio,
                    fallback_device,
                    preferred_sample_rate=0,
                    configured_sample_rate=self._sample_rate,
                    preferred_channels=self._channels,
                    frames_per_buffer=self._chunk_size,
                    logger=logger,
                )
            self._set_active_profile(profile)
            self._audio_chunks.clear()
            self._recording = True
            self._last_capture = None
            device_label = "default" if self._active_device_index is None else f"{self._active_device_index}:{self._active_device_name}"
            logger.info(
                "Recording started (rate=%s, channels=%s->%s, device=%s, host_api=%s)",
                self._active_sample_rate,
                self._active_capture_channels,
                self._normalized_channels,
                device_label,
                self._active_host_api or "-",
            )
            return True
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            return False

    def _set_active_profile(self, profile: dict[str, Any]):
        self._active_device_index = profile.get("device_index")
        self._active_device_name = str(profile.get("device_name") or self._input_device_name or "")
        self._active_sample_rate = int(profile.get("sample_rate") or self._sample_rate)
        self._active_host_api = str(profile.get("host_api") or self._input_device_host_api or "")
        self._active_capture_channels = int(profile.get("capture_channels") or self._channels or 1)
        self._normalized_channels = int(profile.get("normalized_channels") or 1)

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

    def stop(self) -> dict[str, Any]:
        self._recording = False
        raw_audio = b"".join(self._audio_chunks)

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

        normalized_audio = normalize_pcm16_to_mono(raw_audio, self._active_capture_channels)
        level = measure_pcm16_level(normalized_audio)
        capture = {
            "raw_audio": raw_audio,
            "normalized_audio": normalized_audio,
            "sample_rate": self._active_sample_rate,
            "capture_channels": self._active_capture_channels,
            "normalized_channels": self._normalized_channels,
            "device_index": self._active_device_index,
            "device_name": self._active_device_name,
            "host_api": self._active_host_api,
            "audio_level": level,
        }
        self._last_capture = capture
        logger.info(
            "Recording stopped, raw=%s bytes normalized=%s bytes rms=%s peak=%s signal=%s quality=%s",
            len(raw_audio),
            len(normalized_audio),
            level["rms_ratio"],
            level["peak_ratio"],
            level["has_signal"],
            level.get("quality_state"),
        )
        return capture

    def save_wav(self, filepath: str, capture: Optional[dict[str, Any]] = None):
        payload = capture or self._last_capture or {}
        data = payload.get("normalized_audio") if isinstance(payload, dict) else payload
        if not data:
            return

        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            wav_data = wav_bytes_from_pcm16(
                data,
                int(payload.get("sample_rate") or self._active_sample_rate),
                int(payload.get("normalized_channels") or self._normalized_channels),
            )
            with open(filepath, "wb") as f:
                f.write(wav_data)
            logger.info(f"Audio saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")

    def to_wav_bytes(self, capture: Optional[dict[str, Any]] = None) -> bytes:
        payload = capture or self._last_capture or {}
        data = payload.get("normalized_audio") if isinstance(payload, dict) else payload
        if not data:
            return b""
        return wav_bytes_from_pcm16(
            data,
            int(payload.get("sample_rate") or self._active_sample_rate),
            int(payload.get("normalized_channels") or self._normalized_channels),
        )

    def audio_level(self, capture: Optional[dict[str, Any]] = None) -> dict:
        payload = capture or self._last_capture or {}
        if isinstance(payload, dict) and payload.get("audio_level"):
            return dict(payload["audio_level"])
        data = payload.get("normalized_audio") if isinstance(payload, dict) else payload
        return measure_pcm16_level(data or b"")

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def sample_rate(self) -> int:
        return self._active_sample_rate

    @property
    def capture_channels(self) -> int:
        return self._active_capture_channels

    @property
    def normalized_channels(self) -> int:
        return self._normalized_channels

    @property
    def host_api(self) -> str:
        return self._active_host_api
