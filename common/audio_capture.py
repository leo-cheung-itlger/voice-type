from __future__ import annotations

import io
import json
import math
import os
import time
import wave
from array import array
from typing import Any, Optional

from config.settings import DATA_DIR
from common.audio_devices import (
    audio_device_label,
    best_input_device,
    candidate_input_sample_rates,
    device_matches_selection,
    input_device_recommendation,
    is_virtual_input_name,
    supported_input_sample_rates,
)
from common.audio_levels import measure_pcm16_level, pcm16_waveform, quality_message


PROFILE_STORE_PATH = os.path.join(DATA_DIR, "capture_profiles.json")


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


def _profile_key(device_name: str) -> str:
    return audio_device_label(device_name)


def _load_profile_store() -> dict[str, Any]:
    try:
        with open(PROFILE_STORE_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_profile_store(data: dict[str, Any]):
    try:
        os.makedirs(os.path.dirname(PROFILE_STORE_PATH), exist_ok=True)
        with open(PROFILE_STORE_PATH, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_capture_profile(device_name: str) -> dict[str, Any] | None:
    if not device_name:
        return None
    profile = _load_profile_store().get(_profile_key(device_name))
    return dict(profile) if isinstance(profile, dict) else None


def remember_capture_profile(profile: dict[str, Any], reason: str = ""):
    device_name = str(profile.get("device_name") or "")
    if not device_name:
        return
    payload = {
        "device_name": device_name,
        "host_api": str(profile.get("host_api") or profile.get("capture_host_api") or ""),
        "sample_rate": int(profile.get("sample_rate") or 0),
        "capture_channels": int(profile.get("capture_channels") or 1),
        "normalized_strategy": str(profile.get("normalized_strategy") or "mono"),
        "normalized_channel_index": int(profile.get("normalized_channel_index")) if profile.get("normalized_channel_index") is not None else -1,
        "quality_state": str(profile.get("quality_state") or profile.get("audio_level", {}).get("quality_state") or ""),
        "recognized_text": str(profile.get("recognized_text") or ""),
        "reason": reason,
        "updated_at": round(time.time(), 3),
    }
    store = _load_profile_store()
    store[_profile_key(device_name)] = payload
    _save_profile_store(store)


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
        host_api_index = int(info.get("hostApi", -1)) if info.get("hostApi", -1) is not None else -1
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
    remembered_profile = load_capture_profile(selected_name) if selected_name else None
    remembered_host_api = str(remembered_profile.get("host_api") or "") if remembered_profile else ""
    remembered_sample_rate = int(remembered_profile.get("sample_rate") or 0) if remembered_profile else 0

    preferred_best = None
    if selected_name:
        preferred_best = best_input_device(
            devices,
            default_index=default_index,
            preferred_name=selected_name,
            preferred_host_api=remembered_host_api or selected_host_api,
            preferred_sample_rate=remembered_sample_rate or selected_sample_rate,
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
        preferred_host_api=remembered_host_api or selected_host_api,
        preferred_sample_rate=remembered_sample_rate or selected_sample_rate,
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


def capture_channel_candidates(
    max_channels: int,
    preferred_channels: int = 1,
    remembered_channels: int = 0,
) -> list[int]:
    rows: list[int] = []
    for candidate in (remembered_channels, 2, preferred_channels, 1):
        value = int(candidate or 0)
        if value > 0 and value <= max_channels and value not in rows:
            rows.append(value)
    if not rows:
        rows.append(1)
    return rows


def _pcm16_samples(audio_data: bytes) -> array:
    sample_bytes = audio_data[: len(audio_data) - (len(audio_data) % 2)]
    samples = array("h")
    samples.frombytes(sample_bytes)
    return samples


def _channel_pcm16(audio_data: bytes, capture_channels: int, channel_index: int) -> bytes:
    if capture_channels <= 1:
        return audio_data
    samples = _pcm16_samples(audio_data)
    if not samples:
        return b""
    frame_count = len(samples) // capture_channels
    mono = array("h")
    mono.extend(samples[offset + channel_index] for offset in range(0, frame_count * capture_channels, capture_channels))
    return mono.tobytes()


def _average_pcm16(audio_data: bytes, capture_channels: int) -> bytes:
    if capture_channels <= 1:
        return audio_data
    samples = _pcm16_samples(audio_data)
    if not samples:
        return b""
    frame_count = len(samples) // capture_channels
    mono = array("h")
    for offset in range(0, frame_count * capture_channels, capture_channels):
        window = samples[offset:offset + capture_channels]
        value = round(sum(window) / capture_channels)
        mono.append(max(-32768, min(32767, value)))
    return mono.tobytes()


def _channel_correlation(audio_data: bytes, capture_channels: int) -> float:
    if capture_channels < 2 or not audio_data:
        return 1.0
    left = _pcm16_samples(_channel_pcm16(audio_data, capture_channels, 0))
    right = _pcm16_samples(_channel_pcm16(audio_data, capture_channels, 1))
    if not left or not right or len(left) != len(right):
        return 0.0
    mean_left = sum(left) / len(left)
    mean_right = sum(right) / len(right)
    numerator = 0.0
    left_sum = 0.0
    right_sum = 0.0
    for lhs, rhs in zip(left, right):
        dl = lhs - mean_left
        dr = rhs - mean_right
        numerator += dl * dr
        left_sum += dl * dl
        right_sum += dr * dr
    denominator = math.sqrt(left_sum * right_sum)
    if denominator <= 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def _quality_rank(level: dict[str, Any]) -> float:
    quality_state = str(level.get("quality_state") or "")
    state_score = {
        "ok": 9000.0,
        "too_quiet": -9000.0,
        "clipping": -5500.0,
        "dc_offset": -3500.0,
        "noisy_or_distorted": -2500.0,
    }.get(quality_state, 0.0)
    score = state_score
    score += min(float(level.get("rms_ratio") or 0.0), 0.25) * 4000.0
    score += min(float(level.get("peak_ratio") or 0.0), 0.95) * 800.0
    score -= float(level.get("clipping_ratio") or 0.0) * 200000.0
    score -= float(level.get("dc_offset_ratio") or 0.0) * 40000.0
    score -= abs(float(level.get("zero_crossing_rate") or 0.0) - 0.07) * 450.0
    return score


def _candidate_rank(candidate: dict[str, Any], remembered: dict[str, Any] | None = None) -> float:
    score = _quality_rank(candidate["audio_level"])
    strategy = str(candidate.get("normalized_strategy") or "")
    channel_index = int(candidate.get("normalized_channel_index")) if candidate.get("normalized_channel_index") is not None else -1
    if remembered:
        remembered_strategy = str(remembered.get("normalized_strategy") or "")
        remembered_channel = int(remembered.get("normalized_channel_index")) if remembered.get("normalized_channel_index") is not None else -1
        if remembered_strategy and remembered_strategy == strategy:
            score += 120.0
        if remembered_channel >= 0 and remembered_channel == channel_index:
            score += 40.0
    if strategy.startswith("channel_"):
        score += 20.0
    if strategy == "average":
        score -= 2000.0
    return score


def _level_ratio(output_level: dict[str, Any], source_level: dict[str, Any]) -> float:
    source_peak = float(source_level.get("peak_ratio") or 0.0)
    output_peak = float(output_level.get("peak_ratio") or 0.0)
    if source_peak <= 0:
        return 1.0 if output_peak <= 0 else 0.0
    return round(output_peak / source_peak, 6)


def normalize_capture_audio(
    audio_data: bytes,
    capture_channels: int,
    preferred_strategy: str = "",
    preferred_channel_index: int = -1,
) -> dict[str, Any]:
    if capture_channels <= 1 or not audio_data:
        level = measure_pcm16_level(audio_data)
        return {
            "normalized_audio": audio_data,
            "normalized_channels": 1,
            "normalized_strategy": "mono",
            "normalized_channel_index": 0 if audio_data else -1,
            "audio_level": level,
            "source_audio_level": level,
            "input_output_gain_ratio": 1.0,
            "volume_policy": "passthrough_no_gain",
            "channel_analysis": [
                {
                    "strategy": "mono",
                    "channel_index": 0 if audio_data else -1,
                    "audio_level": level,
                    "selectable": True,
                }
            ],
            "stereo_correlation": 1.0,
        }

    remembered = {
        "normalized_strategy": preferred_strategy,
        "normalized_channel_index": preferred_channel_index,
    }
    candidates: list[dict[str, Any]] = []
    for channel_index in range(min(capture_channels, 2)):
        mono = _channel_pcm16(audio_data, capture_channels, channel_index)
        candidates.append({
            "normalized_audio": mono,
            "normalized_strategy": f"channel_{channel_index}",
            "normalized_channel_index": channel_index,
            "audio_level": measure_pcm16_level(mono),
            "source_audio_level": measure_pcm16_level(mono),
            "selectable": True,
        })
    average_audio = _average_pcm16(audio_data, capture_channels)
    average_candidate = {
        "normalized_audio": average_audio,
        "normalized_strategy": "average",
        "normalized_channel_index": -1,
        "audio_level": measure_pcm16_level(average_audio),
        "source_audio_level": measure_pcm16_level(average_audio),
        "selectable": False,
    }
    best = max(candidates, key=lambda item: _candidate_rank(item, remembered))
    source_level = best.get("source_audio_level") or best["audio_level"]
    return {
        "normalized_audio": best["normalized_audio"],
        "normalized_channels": 1,
        "normalized_strategy": best["normalized_strategy"],
        "normalized_channel_index": best["normalized_channel_index"],
        "audio_level": best["audio_level"],
        "source_audio_level": source_level,
        "input_output_gain_ratio": _level_ratio(best["audio_level"], source_level),
        "volume_policy": "passthrough_no_gain",
        "channel_analysis": [
            {
                "strategy": item["normalized_strategy"],
                "channel_index": item["normalized_channel_index"],
                "audio_level": item["audio_level"],
                "selectable": bool(item.get("selectable", True)),
            }
            for item in [*candidates, average_candidate]
        ],
        "stereo_correlation": round(_channel_correlation(audio_data, capture_channels), 6),
    }


def normalize_pcm16_to_mono(audio_data: bytes, capture_channels: int) -> bytes:
    return normalize_capture_audio(audio_data, capture_channels)["normalized_audio"]


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
    device_name = str(info.get("name") or "")
    host_api = pyaudio_host_api(audio, int(info.get("hostApi", -1)) if info.get("hostApi", -1) is not None else -1)
    remembered = load_capture_profile(device_name)
    remembered_sample_rate = int(remembered.get("sample_rate") or 0) if remembered else 0
    remembered_channels = int(remembered.get("capture_channels") or 0) if remembered else 0
    default_rate = int(float(info.get("defaultSampleRate", 0) or 0)) or configured_sample_rate or 48000
    max_channels = max(1, min(int(info.get("maxInputChannels", 1) or 1), 2))
    candidate_rates = candidate_input_sample_rates(
        default_sample_rate=default_rate,
        preferred_sample_rate=remembered_sample_rate or preferred_sample_rate or default_rate,
        configured_sample_rate=configured_sample_rate or default_rate,
    )
    attempts: list[tuple[int, int]] = []
    for capture_channels in capture_channel_candidates(max_channels, preferred_channels, remembered_channels):
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
            open_kwargs = {
                "format": pyaudio_module.paInt16,
                "channels": capture_channels,
                "rate": sample_rate,
                "input": True,
                "frames_per_buffer": frames_per_buffer,
            }
            if device_index >= 0:
                open_kwargs["input_device_index"] = device_index
            stream = audio.open(**open_kwargs)
            return stream, {
                "device_index": None if device_index < 0 else device_index,
                "device_name": device_name,
                "host_api": host_api,
                "sample_rate": int(sample_rate),
                "capture_channels": int(capture_channels),
                "normalized_channels": 1,
                "frames_per_buffer": int(frames_per_buffer),
                "preferred_normalized_strategy": str(remembered.get("normalized_strategy") or "") if remembered else "",
                "preferred_normalized_channel_index": (
                    int(remembered.get("normalized_channel_index"))
                    if remembered and remembered.get("normalized_channel_index") is not None
                    else -1
                ),
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
        normalized = normalize_capture_audio(
            raw_audio,
            int(profile["capture_channels"]),
            preferred_strategy=str(profile.get("preferred_normalized_strategy") or ""),
            preferred_channel_index=(
                int(profile.get("preferred_normalized_channel_index"))
                if profile.get("preferred_normalized_channel_index") is not None
                else -1
            ),
        )
        audio_level = normalized["audio_level"]
        message = quality_message(audio_level)
        result = {
            **profile,
            "raw_audio": raw_audio,
            "normalized_audio": normalized["normalized_audio"],
            "normalized_channels": normalized["normalized_channels"],
            "normalized_strategy": normalized["normalized_strategy"],
            "normalized_channel_index": normalized["normalized_channel_index"],
            "channel_analysis": normalized["channel_analysis"],
            "stereo_correlation": normalized["stereo_correlation"],
            "source_audio_level": normalized.get("source_audio_level") or audio_level,
            "input_output_gain_ratio": normalized.get("input_output_gain_ratio", 1.0),
            "volume_policy": normalized.get("volume_policy", "passthrough_no_gain"),
            "audio_level": audio_level,
            "quality_state": str(audio_level.get("quality_state") or ""),
            "message": message,
        }
        if waveform_points > 0:
            result["waveform"] = pcm16_waveform(normalized["normalized_audio"], waveform_points)
        return result
    finally:
        if stream is not None:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
