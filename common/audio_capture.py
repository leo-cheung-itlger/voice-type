from __future__ import annotations

import io
import wave
from array import array
from typing import Any, Optional

from common.audio_devices import (
    best_input_device,
    candidate_input_sample_rates,
    device_matches_selection,
    input_device_recommendation,
    is_virtual_input_name,
    supported_input_sample_rates,
)
from common.audio_levels import measure_pcm16_level, pcm16_waveform, quality_message


def pyaudio_host_api(audio: Any, host_api_index: int) -> str:
    try:
        return str(audio.get_host_api_info_by_index(host_api_index).get("name") or "")
    except Exception:
        return ""


def pyaudio_default_input_index(audio: Any) -> int:
    try:
        return int(audio.get_default_input_device_info().get("index", -1))
    except Exception:
        return -1


def pyaudio_input_devices(
    audio: Any,
    selected_index: int = -1,
    selected_name: str = "",
    selected_host_api: str = "",
) -> list[dict[str, Any]]:
    devices = []
    default_index = pyaudio_default_input_index(audio)
    for index in range(audio.get_device_count()):
        try:
            info = audio.get_device_info_by_index(index)
        except Exception:
            continue
        max_channels = int(info.get("maxInputChannels", 0) or 0)
        if max_channels <= 0:
            continue
        name = str(info.get("name") or "")
        host_api_index = int(info.get("hostApi", -1) or -1)
        host_api = pyaudio_host_api(audio, host_api_index)
        sample_rate = int(float(info.get("defaultSampleRate", 0) or 0))
        is_default = index == default_index
        recommended, reason = input_device_recommendation(name, host_api, is_default, sample_rate)
        selected = device_matches_selection(
            {
                "index": index,
                "name": name,
                "host_api": host_api,
                "default_sample_rate": sample_rate,
            },
            selected_index,
            selected_name,
            selected_host_api,
        )
        devices.append({
            "index": index,
            "name": name,
            "host_api": host_api,
            "host_api_index": host_api_index,
            "channels": max_channels,
            "default_sample_rate": sample_rate,
            "is_default": is_default,
            "selected": selected,
            "recommended": recommended,
            "reason": reason,
            "level_supported": True,
        })
    return devices


def resolve_input_device_index(
    audio: Any,
    selected_index: int = -1,
    selected_name: str = "",
    selected_host_api: str = "",
    selected_sample_rate: int = 0,
    exclude_indexes: set[int] | None = None,
    logger: Any | None = None,
) -> Optional[int]:
    devices = pyaudio_input_devices(audio, selected_index, selected_name, selected_host_api)
    default_index = pyaudio_default_input_index(audio)
    excluded = exclude_indexes or set()

    preferred_best = None
    if selected_name:
        preferred_best = best_input_device(
            devices,
            default_index=default_index,
            preferred_name=selected_name,
            preferred_host_api=selected_host_api,
            preferred_sample_rate=selected_sample_rate,
            exclude_indexes=excluded,
        )
        if preferred_best is not None:
            if logger and preferred_best != selected_index:
                best_device = next((device for device in devices if int(device["index"]) == preferred_best), {})
                logger.info(
                    "Selected input device resolved by saved name: saved_index=%s actual_index=%s name=%s host_api=%s",
                    selected_index,
                    preferred_best,
                    best_device.get("name", selected_name),
                    best_device.get("host_api", ""),
                )
            return preferred_best

    selected = next(
        (
            device for device in devices
            if int(device.get("index", -1)) not in excluded
            and device_matches_selection(device, selected_index, selected_name, selected_host_api)
        ),
        None,
    )
    if selected:
        resolved_index = int(selected["index"])
        resolved_name = str(selected.get("name") or "")
        explicit_virtual = bool(selected_name and is_virtual_input_name(selected_name))
        if explicit_virtual or not is_virtual_input_name(resolved_name):
            if logger and resolved_index != selected_index:
                logger.info(
                    "Selected input device remapped by name: saved_index=%s actual_index=%s name=%s",
                    selected_index,
                    resolved_index,
                    resolved_name,
                )
            return resolved_index
        if logger:
            logger.warning(
                "Saved input device points to virtual input, ignoring: index=%s name=%s",
                resolved_index,
                resolved_name,
            )

    if logger and selected_name:
        logger.warning(
            "Saved input device was not found by identity, selecting smart default: saved_index=%s name=%s host_api=%s",
            selected_index,
            selected_name,
            selected_host_api or "-",
        )

    best = best_input_device(
        devices,
        default_index=default_index,
        preferred_name=selected_name,
        preferred_host_api=selected_host_api,
        preferred_sample_rate=selected_sample_rate,
        exclude_indexes=excluded,
    )
    if best is not None and logger and (selected_index < 0 or best != selected_index):
        best_device = next((device for device in devices if int(device["index"]) == best), {})
        logger.info(
            "Smart input device selected: index=%s name=%s host_api=%s default_index=%s",
            best,
            best_device.get("name", ""),
            best_device.get("host_api", ""),
            default_index,
        )
    return best


def capture_channel_candidates(max_channels: int, preferred_channels: int = 1) -> list[int]:
    rows: list[int] = []
    if preferred_channels > 0 and preferred_channels <= max_channels:
        rows.append(int(preferred_channels))
    for candidate in (2, 1):
        if candidate <= max_channels and candidate not in rows:
            rows.append(candidate)
    if not rows:
        rows.append(1)
    return rows


def normalize_pcm16_to_mono(audio_data: bytes, capture_channels: int) -> bytes:
    if capture_channels <= 1 or not audio_data:
        return audio_data
    sample_bytes = audio_data[: len(audio_data) - (len(audio_data) % 2)]
    samples = array("h")
    samples.frombytes(sample_bytes)
    if not samples:
        return b""
    frame_count = len(samples) // capture_channels
    if frame_count <= 0:
        return b""
    mono = array("h")
    mono.extend(
        max(-32768, min(32767, round(sum(samples[offset:offset + capture_channels]) / capture_channels)))
        for offset in range(0, frame_count * capture_channels, capture_channels)
    )
    return mono.tobytes()


def wav_bytes_from_pcm16(audio_data: bytes, sample_rate: int, channels: int = 1) -> bytes:
    if not audio_data:
        return b""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(audio_data)
    return buf.getvalue()


def open_input_stream_with_profile(
    audio: Any,
    pyaudio_module: Any,
    input_device_index: Optional[int],
    preferred_sample_rate: int = 0,
    configured_sample_rate: int = 48000,
    preferred_channels: int = 1,
    frames_per_buffer: int = 960,
    logger: Any | None = None,
) -> tuple[Any, dict[str, Any]]:
    info = (
        dict(audio.get_default_input_device_info())
        if input_device_index is None
        else dict(audio.get_device_info_by_index(input_device_index))
    )
    device_index = int(info.get("index", -1))
    host_api = pyaudio_host_api(audio, int(info.get("hostApi", -1) or -1))
    default_rate = int(float(info.get("defaultSampleRate", 0) or 0)) or configured_sample_rate or 48000
    max_channels = max(1, min(int(info.get("maxInputChannels", 1) or 1), 2))
    candidate_rates = candidate_input_sample_rates(
        default_sample_rate=default_rate,
        preferred_sample_rate=preferred_sample_rate or default_rate,
        configured_sample_rate=configured_sample_rate or default_rate,
    )
    attempts: list[tuple[int, int]] = []
    for capture_channels in capture_channel_candidates(max_channels, preferred_channels):
        supported = supported_input_sample_rates(
            audio,
            pyaudio_module,
            device_index if device_index >= 0 else None,
            capture_channels,
            candidate_rates,
        )
        if supported:
            skipped = [rate for rate in candidate_rates if rate not in supported]
            if logger and skipped:
                logger.info(
                    "Skipping unsupported input sample rates for device=%s channels=%s: %s",
                    "default" if device_index < 0 else device_index,
                    capture_channels,
                    skipped,
                )
            attempts.extend((capture_channels, rate) for rate in supported)
        else:
            attempts.extend((capture_channels, rate) for rate in candidate_rates)

    last_error: Exception | None = None
    for capture_channels, sample_rate in attempts:
        try:
            stream = audio.open(
                format=pyaudio_module.paInt16,
                channels=capture_channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index if device_index >= 0 else None,
                frames_per_buffer=frames_per_buffer,
            )
            return stream, {
                "device_index": None if device_index < 0 else device_index,
                "device_name": str(info.get("name") or ""),
                "host_api": host_api,
                "sample_rate": int(sample_rate),
                "capture_channels": int(capture_channels),
                "normalized_channels": 1,
                "frames_per_buffer": int(frames_per_buffer),
            }
        except Exception as exc:
            last_error = exc
            if logger:
                logger.info(
                    "Input stream candidate failed at %sHz/%sch for device=%s: %s",
                    sample_rate,
                    capture_channels,
                    "default" if device_index < 0 else device_index,
                    exc,
                )
    if last_error:
        raise last_error
    raise RuntimeError("No input stream profile was attempted")


def capture_input_once(
    audio: Any,
    pyaudio_module: Any,
    input_device_index: Optional[int],
    seconds: float,
    preferred_sample_rate: int = 0,
    configured_sample_rate: int = 48000,
    preferred_channels: int = 1,
    waveform_points: int = 0,
    logger: Any | None = None,
) -> dict[str, Any]:
    seconds = max(0.08, float(seconds or 0.0))
    stream = None
    profile: dict[str, Any] = {}
    try:
        frames_per_buffer = max(240, min(2048, int((configured_sample_rate or 48000) * 0.02)))
        stream, profile = open_input_stream_with_profile(
            audio,
            pyaudio_module,
            input_device_index,
            preferred_sample_rate=preferred_sample_rate,
            configured_sample_rate=configured_sample_rate,
            preferred_channels=preferred_channels,
            frames_per_buffer=frames_per_buffer,
            logger=logger,
        )
        sample_rate = int(profile["sample_rate"])
        chunk = max(240, min(2048, int(sample_rate * 0.02)))
        total_chunks = max(1, int(sample_rate / chunk * seconds))
        chunks = [stream.read(chunk, exception_on_overflow=False) for _ in range(total_chunks)]
        raw_audio = b"".join(chunks)
        normalized_audio = normalize_pcm16_to_mono(raw_audio, int(profile["capture_channels"]))
        audio_level = measure_pcm16_level(normalized_audio)
        message = quality_message(audio_level)
        result = {
            **profile,
            "raw_audio": raw_audio,
            "normalized_audio": normalized_audio,
            "audio_level": audio_level,
            "message": message,
        }
        if waveform_points > 0:
            result["waveform"] = pcm16_waveform(normalized_audio, waveform_points)
        return result
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
