from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import wave
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.audio_capture import pyaudio_default_input_index, pyaudio_host_api, pyaudio_input_devices
from common.audio_devices import best_input_device, device_name_matches, supported_input_sample_rates
from common.audio_levels import measure_pcm16_level
from config.settings import DATA_DIR, load_app_config, resolve_model_dir
from server.asr_engine import ASREngine


TARGET_SAMPLE_RATE = 48000
ASR_SAMPLE_RATE = 16000
TARGET_CHANNELS = 2
OUTPUT_ROOT = Path(DATA_DIR) / "mic_format_tests"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record one microphone sample and export raw/minimal/ASR-ready WAV variants."
    )
    parser.add_argument("--seconds", type=float, default=5.0, help="Recording duration in seconds.")
    parser.add_argument("--device-index", type=int, default=None, help="PyAudio input device index.")
    parser.add_argument("--device-name", default="", help="Input device name substring to select.")
    parser.add_argument("--output-dir", default="", help="Optional output directory.")
    parser.add_argument("--no-asr", action="store_true", help="Only write WAV files; skip Qwen3-ASR recognition.")
    return parser.parse_args()


def pcm16_array(audio_data: bytes):
    import numpy as np

    aligned = audio_data[: len(audio_data) - (len(audio_data) % 2)]
    return np.frombuffer(aligned, dtype="<i2")


def pcm16_bytes(samples: Any) -> bytes:
    import numpy as np

    clipped = np.clip(samples, -32768, 32767).astype("<i2", copy=False)
    return clipped.tobytes()


def write_wav(path: Path, audio_data: bytes, sample_rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(int(channels))
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(audio_data)


def read_wav_pcm(path: Path) -> tuple[bytes, int, int]:
    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), int(handle.getframerate()), int(handle.getnchannels())


def channel_bytes(raw_audio: bytes, channels: int, channel_index: int) -> bytes:
    samples = pcm16_array(raw_audio)
    if channels <= 1:
        return samples.tobytes()
    frame_count = len(samples) // channels
    framed = samples[: frame_count * channels].reshape((-1, channels))
    return pcm16_bytes(framed[:, channel_index])


def mix_to_mono_float(raw_audio: bytes, channels: int):
    import numpy as np

    samples = pcm16_array(raw_audio).astype(np.float32) / 32768.0
    if channels <= 1:
        return samples
    frame_count = len(samples) // channels
    framed = samples[: frame_count * channels].reshape((-1, channels))
    return framed.mean(axis=1)


def resample_float(audio: Any, source_rate: int, target_rate: int):
    if int(source_rate) == int(target_rate):
        return audio
    # Keep SciPy optional: this probe is a developer diagnostic, while the
    # shipped CPU runtime must not carry its large native wheel.  NumPy's
    # interpolation is sufficient for the short microphone probe.
    try:
        from scipy.signal import resample_poly
    except ImportError:
        import numpy as np
        source = np.asarray(audio, dtype=np.float32)
        length = max(1, round(len(source) * int(target_rate) / int(source_rate)))
        return np.interp(np.linspace(0, len(source) - 1, length), np.arange(len(source)), source)
    divisor = math.gcd(int(source_rate), int(target_rate))
    return resample_poly(audio, int(target_rate) // divisor, int(source_rate) // divisor)


def float_to_pcm16_bytes(audio: Any) -> bytes:
    import numpy as np

    clipped = np.clip(audio, -1.0, 1.0)
    return pcm16_bytes(np.round(clipped * 32767.0))


def audio_metrics(path: Path) -> dict[str, Any]:
    audio_data, sample_rate, channels = read_wav_pcm(path)
    level = measure_pcm16_level(audio_data)
    return {
        "path": str(path),
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": round(len(audio_data) / max(1, sample_rate * channels * 2), 3),
        "audio_level": level,
    }


def select_device(args: argparse.Namespace) -> tuple[int | None, dict[str, Any]]:
    import pyaudio

    config = load_app_config().client
    audio = pyaudio.PyAudio()
    try:
        devices = pyaudio_input_devices(audio)
        default_index = pyaudio_default_input_index(audio)
        selected_index: int | None
        if args.device_index is not None:
            selected_index = int(args.device_index)
        elif args.device_name:
            matches = [device for device in devices if device_name_matches(args.device_name, str(device.get("name") or ""))]
            selected_index = int(matches[0]["index"]) if matches else None
        elif config.input_device_name:
            selected_index = best_input_device(
                devices,
                default_index=default_index,
                preferred_name=config.input_device_name,
                preferred_host_api=config.input_device_host_api,
                preferred_sample_rate=config.input_device_sample_rate,
            )
        elif config.input_device_index >= 0:
            selected_index = int(config.input_device_index)
        else:
            selected_index = best_input_device(devices, default_index=default_index)

        if selected_index is None:
            selected_index = default_index if default_index >= 0 else None
        info = dict(audio.get_default_input_device_info()) if selected_index is None else dict(audio.get_device_info_by_index(selected_index))
        info["host_api"] = pyaudio_host_api(audio, int(info.get("hostApi", -1)) if info.get("hostApi", -1) is not None else -1)
        return selected_index, info
    finally:
        audio.terminate()


def open_recording_stream(audio: Any, pyaudio_module: Any, device_index: int | None, device_info: dict[str, Any]):
    max_channels = max(1, min(int(device_info.get("maxInputChannels", 1) or 1), TARGET_CHANNELS))
    default_rate = int(float(device_info.get("defaultSampleRate", 0) or 0))
    channel_candidates = [value for value in (TARGET_CHANNELS, 1) if value <= max_channels]
    rate_candidates = []
    for rate in (TARGET_SAMPLE_RATE, default_rate, 44100, 16000):
        value = int(rate or 0)
        if value > 0 and value not in rate_candidates:
            rate_candidates.append(value)

    attempts: list[tuple[int, int]] = []
    for channels in channel_candidates:
        supported = supported_input_sample_rates(audio, pyaudio_module, device_index, channels, rate_candidates)
        attempts.extend((channels, rate) for rate in (supported or rate_candidates))

    last_error: Exception | None = None
    for channels, sample_rate in attempts:
        try:
            kwargs = {
                "format": pyaudio_module.paInt16,
                "channels": channels,
                "rate": sample_rate,
                "input": True,
                "frames_per_buffer": max(240, min(2048, int(sample_rate * 0.02))),
            }
            if device_index is not None and device_index >= 0:
                kwargs["input_device_index"] = device_index
            return audio.open(**kwargs), int(sample_rate), int(channels)
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("No recording stream candidate was attempted.")


def record_raw(device_index: int | None, device_info: dict[str, Any], seconds: float) -> tuple[bytes, int, int]:
    import pyaudio

    audio = pyaudio.PyAudio()
    stream = None
    try:
        stream, sample_rate, channels = open_recording_stream(audio, pyaudio, device_index, device_info)
        chunk = max(240, min(2048, int(sample_rate * 0.02)))
        total_chunks = max(1, int(sample_rate / chunk * max(0.1, seconds)))
        chunks = [stream.read(chunk, exception_on_overflow=False) for _ in range(total_chunks)]
        return b"".join(chunks), sample_rate, channels
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
        audio.terminate()


def build_outputs(raw_audio: bytes, sample_rate: int, channels: int, output_dir: Path) -> dict[str, Path]:
    raw_name = "raw_48k_stereo.wav" if sample_rate == 48000 and channels == 2 else f"raw_{sample_rate}hz_{channels}ch.wav"
    outputs = {"raw": output_dir / raw_name}
    write_wav(outputs["raw"], raw_audio, sample_rate, channels)

    outputs["minimal_channel0_48k"] = output_dir / f"minimal_channel0_{sample_rate // 1000}k.wav"
    write_wav(outputs["minimal_channel0_48k"], channel_bytes(raw_audio, channels, 0), sample_rate, 1)

    if channels >= 2:
        outputs["minimal_channel1_48k"] = output_dir / f"minimal_channel1_{sample_rate // 1000}k.wav"
        write_wav(outputs["minimal_channel1_48k"], channel_bytes(raw_audio, channels, 1), sample_rate, 1)

    mono = mix_to_mono_float(raw_audio, channels)
    asr_audio = resample_float(mono, sample_rate, ASR_SAMPLE_RATE)
    outputs["standard_asr_16k_mono"] = output_dir / "standard_asr_16k_mono.wav"
    write_wav(outputs["standard_asr_16k_mono"], float_to_pcm16_bytes(asr_audio), ASR_SAMPLE_RATE, 1)
    return outputs


def init_qwen17_engine() -> ASREngine:
    server_config = load_app_config().server
    engine = ASREngine(
        model="qwen3-asr-1.7b",
        model_dir=resolve_model_dir("qwen3-asr-1.7b"),
        gpu=server_config.gpu,
        gpu_backend=server_config.gpu_backend,
        gpu_required=server_config.gpu_required,
        allow_cpu_fallback=server_config.allow_cpu_fallback,
    )
    if not engine.initialize():
        raise RuntimeError(engine.last_error or "Failed to initialize qwen3-asr-1.7b")
    return engine


def recognize_files(paths: dict[str, Path], skip_asr: bool) -> dict[str, Any]:
    candidates = {
        key: path
        for key, path in paths.items()
        if key.startswith("minimal_channel") or key == "standard_asr_16k_mono"
    }
    if skip_asr:
        return {key: {"skipped": True, "reason": "--no-asr"} for key in candidates}

    engine = init_qwen17_engine()
    results = {}
    for key, path in candidates.items():
        audio_data, sample_rate, _channels = read_wav_pcm(path)
        started = time.time()
        try:
            text = engine.recognize(audio_data, sample_rate) or ""
            error = ""
        except Exception as exc:
            text = ""
            error = str(exc)
        results[key] = {
            "text": text,
            "seconds": round(time.time() - started, 3),
            "sample_rate": sample_rate,
            "error": error,
        }
    return results


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else OUTPUT_ROOT / time.strftime("%Y%m%d-%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)

    device_index, device_info = select_device(args)
    print(f"Recording {args.seconds:.1f}s from device={device_index} name={device_info.get('name')} host={device_info.get('host_api')}")
    raw_audio, sample_rate, channels = record_raw(device_index, device_info, args.seconds)
    outputs = build_outputs(raw_audio, sample_rate, channels, output_dir)

    metrics = {key: audio_metrics(path) for key, path in outputs.items()}
    asr_results = recognize_files(outputs, args.no_asr)
    summary = {
        "output_dir": str(output_dir),
        "device": {
            "index": device_index,
            "name": str(device_info.get("name") or ""),
            "host_api": str(device_info.get("host_api") or ""),
            "default_sample_rate": int(float(device_info.get("defaultSampleRate", 0) or 0)),
            "max_input_channels": int(device_info.get("maxInputChannels", 0) or 0),
        },
        "recording": {
            "requested_seconds": args.seconds,
            "sample_rate": sample_rate,
            "channels": channels,
            "format": "PCM16/int16",
            "auto_gain": False,
            "noise_reduction": False,
            "compression": False,
        },
        "files": metrics,
        "asr": {
            "model": "qwen3-asr-1.7b",
            "results": asr_results,
        },
    }
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote: {result_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
