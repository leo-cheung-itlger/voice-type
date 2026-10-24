import os
import subprocess
import time
import uuid
import wave
from typing import Any, Optional

from common.audio_capture import (
    normalize_capture_audio,
    open_input_stream_with_profile,
    resolve_input_device_index,
    wav_bytes_from_pcm16,
)
from common.audio_levels import measure_pcm16_level
from common.logger import setup_logger
from config.settings import BASE_DIR, DATA_DIR

logger = setup_logger("recorder")


def _repair_windows_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_windows_text(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_windows_text(item) for item in value]
    if not isinstance(value, str):
        return value
    if not any(marker in value for marker in ("é", "å", "è", "\x85", "\x8b", "\x8e")):
        return value
    try:
        repaired = value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value
    original_cjk = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
    repaired_cjk = sum(1 for char in repaired if "\u4e00" <= char <= "\u9fff")
    return repaired if repaired_cjk > original_cjk else value


def _read_wav_pcm16(path: str) -> tuple[bytes, int, int]:
    with wave.open(path, "rb") as wav_file:
        sample_rate = int(wav_file.getframerate())
        channels = int(wav_file.getnchannels())
        sample_width = int(wav_file.getsampwidth())
        if sample_width != 2:
            raise ValueError(f"Expected PCM16 WAV, got sample width {sample_width}")
        data = wav_file.readframes(wav_file.getnframes())
    return data, sample_rate, channels


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
        windows_voice_capture_enabled: bool = True,
        auto_gain_enabled: bool = True,
    ):
        self._sample_rate = sample_rate
        self._active_sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._input_device_index = input_device_index
        self._input_device_name = input_device_name
        self._input_device_host_api = input_device_host_api
        self._input_device_sample_rate = input_device_sample_rate
        self._windows_voice_capture_enabled = bool(windows_voice_capture_enabled)
        self._auto_gain_enabled = bool(auto_gain_enabled)
        self._active_device_index: Optional[int] = input_device_index if input_device_index >= 0 else None
        self._active_device_name = input_device_name
        self._active_host_api = input_device_host_api
        self._active_capture_channels = max(1, int(channels or 1))
        self._normalized_channels = 1
        self._normalized_strategy = "mono"
        self._normalized_channel_index = 0
        self._preferred_normalized_strategy = ""
        self._preferred_normalized_channel_index = -1
        self._recording = False
        self._audio_chunks: list = []
        self._stream = None
        self._pyaudio = None
        self._capture_backend = "pyaudio_wasapi"
        self._windows_process: Optional[subprocess.Popen] = None
        self._windows_output_path = ""
        self._windows_started_at = 0.0
        self._last_capture: dict[str, Any] | None = None

    def configure(
        self,
        sample_rate: int,
        channels: int,
        input_device_index: int,
        input_device_name: str,
        input_device_host_api: str,
        input_device_sample_rate: int,
        windows_voice_capture_enabled: bool,
        auto_gain_enabled: bool,
    ):
        self._sample_rate = int(sample_rate or self._sample_rate)
        self._channels = int(channels or self._channels)
        self._input_device_index = int(input_device_index if input_device_index is not None else -1)
        self._input_device_name = input_device_name or ""
        self._input_device_host_api = input_device_host_api or ""
        self._input_device_sample_rate = int(input_device_sample_rate or 0)
        self._windows_voice_capture_enabled = bool(windows_voice_capture_enabled)
        self._auto_gain_enabled = bool(auto_gain_enabled)

    def start(self) -> bool:
        self._last_capture = None
        if self._windows_voice_capture_enabled and os.name == "nt":
            try:
                return self._start_windows_voice_capture()
            except Exception as e:
                logger.warning("Windows voice capture failed to start, falling back to PyAudio/WASAPI: %s", e)

        try:
            import pyaudio

            self._capture_backend = "pyaudio_wasapi"
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

    def _windows_helper_command(self, output_path: str) -> list[str]:
        helper_project = os.path.join(BASE_DIR, "tools", "windows_voice_capture", "VoiceCaptureHelper.csproj")
        helper_dll = os.path.join(
            BASE_DIR,
            "tools",
            "windows_voice_capture",
            "bin",
            "x64",
            "Release",
            "net10.0-windows10.0.26100.0",
            "VoiceCaptureHelper.dll",
        )
        helper_args = [
            "--seconds",
            "120",
            "--output",
            output_path,
            "--device-name",
            self._input_device_name or "",
            "--category",
            "VoiceTyping",
            "--processing",
            "Default",
            "--wait-for-stdin",
        ]
        published = os.path.join(BASE_DIR, "tools", "windows_voice_capture", "publish", "VoiceCaptureHelper.exe")
        if os.path.isfile(published):
            return [published, *helper_args]
        if os.path.isfile(os.path.join(BASE_DIR, "portable.json")):
            raise FileNotFoundError("Windows 语音增强不可用，将使用基础录音")
        if not os.path.isfile(helper_project):
            raise FileNotFoundError(f"Windows voice capture helper is missing: {helper_project}")
        if os.path.isfile(helper_dll):
            return ["dotnet", helper_dll, *helper_args]
        return ["dotnet", "run", "--project", helper_project, "-c", "Release", "-p:Platform=x64", "--", *helper_args]

    def _start_windows_voice_capture(self) -> bool:
        runtime_dir = os.path.join(DATA_DIR, "runtime_capture")
        os.makedirs(runtime_dir, exist_ok=True)
        output_path = os.path.join(runtime_dir, f"windows_voice_{uuid.uuid4().hex}.wav")
        command = self._windows_helper_command(output_path)
        dotnet_home = os.path.join(DATA_DIR, "dotnet_home")
        os.makedirs(dotnet_home, exist_ok=True)
        env = os.environ.copy()
        env["DOTNET_CLI_HOME"] = dotnet_home
        env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
        env["DOTNET_NOLOGO"] = "1"
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._windows_process = subprocess.Popen(
            command,
            cwd=BASE_DIR,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        time.sleep(0.25)
        if self._windows_process.poll() is not None:
            stdout, stderr = self._windows_process.communicate(timeout=2)
            self._windows_process = None
            raise RuntimeError((stderr or stdout or "Windows voice capture helper exited early").strip())
        self._windows_output_path = output_path
        self._windows_started_at = time.monotonic()
        self._capture_backend = "windows_mediacapture"
        self._active_sample_rate = 16000
        self._active_capture_channels = 1
        self._normalized_channels = 1
        self._normalized_strategy = "windows_mediacapture"
        self._normalized_channel_index = 0
        self._active_host_api = "Windows MediaCapture"
        self._active_device_name = self._input_device_name
        self._audio_chunks.clear()
        self._recording = True
        logger.info(
            "Recording started with Windows voice capture (device=%s, category=VoiceTyping, processing=Default)",
            self._input_device_name or "default",
        )
        return True

    def _set_active_profile(self, profile: dict[str, Any]):
        self._active_device_index = profile.get("device_index")
        self._active_device_name = str(profile.get("device_name") or self._input_device_name or "")
        self._active_sample_rate = int(profile.get("sample_rate") or self._sample_rate)
        self._active_host_api = str(profile.get("host_api") or self._input_device_host_api or "")
        self._active_capture_channels = int(profile.get("capture_channels") or self._channels or 1)
        self._normalized_channels = int(profile.get("normalized_channels") or 1)
        self._preferred_normalized_strategy = str(profile.get("preferred_normalized_strategy") or "")
        self._preferred_normalized_channel_index = (
            int(profile.get("preferred_normalized_channel_index"))
            if profile.get("preferred_normalized_channel_index") is not None
            else -1
        )

    def read_chunk(self) -> Optional[bytes]:
        if self._recording and self._capture_backend == "windows_mediacapture":
            return None
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
        if self._capture_backend == "windows_mediacapture" and self._windows_process is not None:
            return self._stop_windows_voice_capture()

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

        normalized = normalize_capture_audio(
            raw_audio,
            self._active_capture_channels,
            preferred_strategy=self._preferred_normalized_strategy,
            preferred_channel_index=self._preferred_normalized_channel_index,
            auto_gain_enabled=self._auto_gain_enabled,
        )
        normalized_audio = normalized["normalized_audio"]
        level = normalized["audio_level"] or measure_pcm16_level(normalized_audio)
        self._normalized_channels = int(normalized.get("normalized_channels") or 1)
        self._normalized_strategy = str(normalized.get("normalized_strategy") or "mono")
        self._normalized_channel_index = (
            int(normalized.get("normalized_channel_index"))
            if normalized.get("normalized_channel_index") is not None
            else -1
        )
        capture = {
            "raw_audio": raw_audio,
            "normalized_audio": normalized_audio,
            "capture_backend": self._capture_backend,
            "sample_rate": self._active_sample_rate,
            "capture_channels": self._active_capture_channels,
            "normalized_channels": self._normalized_channels,
            "normalized_strategy": self._normalized_strategy,
            "normalized_channel_index": self._normalized_channel_index,
            "preferred_normalized_strategy": self._preferred_normalized_strategy,
            "preferred_normalized_channel_index": self._preferred_normalized_channel_index,
            "channel_analysis": normalized.get("channel_analysis") or [],
            "stereo_correlation": normalized.get("stereo_correlation"),
            "source_audio_level": normalized.get("source_audio_level") or level,
            "processed_audio_level": normalized.get("processed_audio_level") or level,
            "input_output_gain_ratio": normalized.get("input_output_gain_ratio", 1.0),
            "gain_db": normalized.get("gain_db", 0.0),
            "volume_policy": normalized.get("volume_policy", "passthrough_no_gain"),
            "auto_gain_enabled": self._auto_gain_enabled,
            "device_index": self._active_device_index,
            "device_name": self._active_device_name,
            "host_api": self._active_host_api,
            "audio_level": level,
            "quality_state": str(level.get("quality_state") or ""),
        }
        self._last_capture = capture
        logger.info(
            "Recording stopped, raw=%s bytes normalized=%s bytes rms=%s peak=%s signal=%s quality=%s strategy=%s volume_policy=%s gain_ratio=%s gain_db=%s auto_gain=%s preferred=%s:%s",
            len(raw_audio),
            len(normalized_audio),
            level["rms_ratio"],
            level["peak_ratio"],
            level["has_signal"],
            level.get("quality_state"),
            self._normalized_strategy,
            capture["volume_policy"],
            capture["input_output_gain_ratio"],
            capture["gain_db"],
            self._auto_gain_enabled,
            self._preferred_normalized_strategy or "-",
            self._preferred_normalized_channel_index,
        )
        return capture

    def _stop_windows_voice_capture(self) -> dict[str, Any]:
        process = self._windows_process
        output_path = self._windows_output_path
        self._windows_process = None
        stdout = ""
        stderr = ""
        try:
            if process.stdin:
                process.stdin.write("\n")
                process.stdin.flush()
            stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            raise RuntimeError("Windows voice capture helper did not stop in time")
        finally:
            self._windows_output_path = ""

        if process.returncode != 0:
            raise RuntimeError((stderr or stdout or "Windows voice capture helper failed").strip())
        if not output_path or not os.path.isfile(output_path):
            raise RuntimeError("Windows voice capture helper did not produce a WAV file")

        audio_data, sample_rate, channels = _read_wav_pcm16(output_path)
        helper_info: dict[str, Any] = {}
        for line in reversed((stdout or "").splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                import json

                helper_info = _repair_windows_text(json.loads(line))
                break
            except Exception:
                continue
        try:
            os.remove(output_path)
        except OSError:
            pass

        level = measure_pcm16_level(audio_data)
        device = helper_info.get("device") if isinstance(helper_info.get("device"), dict) else {}
        device_name = str(device.get("name") or self._input_device_name or "")
        self._active_sample_rate = sample_rate
        self._active_capture_channels = channels
        self._normalized_channels = channels
        self._normalized_strategy = "windows_mediacapture"
        self._normalized_channel_index = 0
        self._active_host_api = "Windows MediaCapture"
        self._active_device_name = device_name
        capture = {
            "raw_audio": audio_data,
            "normalized_audio": audio_data,
            "capture_backend": "windows_mediacapture",
            "sample_rate": sample_rate,
            "capture_channels": channels,
            "normalized_channels": channels,
            "normalized_strategy": "windows_mediacapture",
            "normalized_channel_index": 0,
            "preferred_normalized_strategy": "",
            "preferred_normalized_channel_index": -1,
            "channel_analysis": [],
            "stereo_correlation": None,
            "source_audio_level": level,
            "processed_audio_level": level,
            "input_output_gain_ratio": 1.0,
            "gain_db": 0.0,
            "volume_policy": "windows_mediacapture_default_processing",
            "auto_gain_enabled": False,
            "windows_voice_capture_enabled": True,
            "device_index": self._active_device_index,
            "device_name": device_name,
            "host_api": "Windows MediaCapture",
            "audio_level": level,
            "quality_state": str(level.get("quality_state") or ""),
            "windows_voice_capture": {
                "media_category": helper_info.get("media_category", "VoiceTyping"),
                "audio_processing": helper_info.get("audio_processing", "Default"),
                "helper_ok": bool(helper_info.get("ok", True)),
                "helper_stdout": stdout[-1000:],
                "helper_stderr": stderr[-1000:],
            },
        }
        self._last_capture = capture
        logger.info(
            "Recording stopped with Windows voice capture, bytes=%s rms=%s peak=%s signal=%s quality=%s elapsed=%.3fs",
            len(audio_data),
            level["rms_ratio"],
            level["peak_ratio"],
            level["has_signal"],
            level.get("quality_state"),
            time.monotonic() - self._windows_started_at,
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
