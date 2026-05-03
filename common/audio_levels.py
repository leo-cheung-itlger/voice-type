import math
import sys
from array import array
from typing import Any


def _pcm16_samples(audio_data: bytes) -> array:
    sample_bytes = audio_data[: len(audio_data) - (len(audio_data) % 2)]
    samples = array("h")
    samples.frombytes(sample_bytes)
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _quality_state(
    has_signal: bool,
    peak_ratio: float,
    clipping_ratio: float,
    dc_offset_ratio: float,
    zero_crossing_rate: float,
    rms_ratio: float,
) -> str:
    if not has_signal:
        return "too_quiet"
    if clipping_ratio >= 0.01 or peak_ratio >= 0.995:
        return "clipping"
    if dc_offset_ratio >= 0.08:
        return "dc_offset"
    if zero_crossing_rate >= 0.35 and rms_ratio <= 0.05 and peak_ratio <= 0.4:
        return "noisy_or_distorted"
    return "ok"


def quality_message(level: dict[str, Any]) -> str:
    labels = {
        "ok": "正常语音输入",
        "too_quiet": "太安静或未检测到有效输入",
        "clipping": "疑似爆音或削顶",
        "dc_offset": "疑似电流声或直流偏移",
        "noisy_or_distorted": "疑似噪声或失真",
    }
    return labels.get(str(level.get("quality_state") or ""), "输入状态未知")


def measure_pcm16_level(audio_data: bytes) -> dict[str, Any]:
    if not audio_data:
        return {
            "bytes": 0,
            "samples": 0,
            "rms": 0.0,
            "peak": 0,
            "rms_ratio": 0.0,
            "peak_ratio": 0.0,
            "has_signal": False,
            "mean": 0.0,
            "mean_ratio": 0.0,
            "clipping_ratio": 0.0,
            "dc_offset_ratio": 0.0,
            "zero_crossing_rate": 0.0,
            "quality_state": "too_quiet",
        }

    samples = _pcm16_samples(audio_data)

    if not samples:
        return {
            "bytes": len(audio_data),
            "samples": 0,
            "rms": 0.0,
            "peak": 0,
            "rms_ratio": 0.0,
            "peak_ratio": 0.0,
            "has_signal": False,
            "mean": 0.0,
            "mean_ratio": 0.0,
            "clipping_ratio": 0.0,
            "dc_offset_ratio": 0.0,
            "zero_crossing_rate": 0.0,
            "quality_state": "too_quiet",
        }

    peak = max(abs(value) for value in samples)
    square_sum = sum(float(value) * float(value) for value in samples)
    mean = sum(float(value) for value in samples) / len(samples)
    clipped = sum(1 for value in samples if abs(value) >= 32760)
    zero_crossings = sum(
        1
        for previous, current in zip(samples, samples[1:])
        if (previous < 0 <= current) or (previous > 0 >= current)
    )
    rms = math.sqrt(square_sum / len(samples))
    rms_ratio = rms / 32768.0
    peak_ratio = peak / 32768.0
    mean_ratio = mean / 32768.0
    clipping_ratio = clipped / len(samples)
    dc_offset_ratio = abs(mean_ratio)
    zero_crossing_rate = zero_crossings / max(1, len(samples) - 1)
    has_signal = bool(rms_ratio >= 0.003 or peak_ratio >= 0.02)
    quality_state = _quality_state(
        has_signal=has_signal,
        peak_ratio=peak_ratio,
        clipping_ratio=clipping_ratio,
        dc_offset_ratio=dc_offset_ratio,
        zero_crossing_rate=zero_crossing_rate,
        rms_ratio=rms_ratio,
    )
    return {
        "bytes": len(audio_data),
        "samples": len(samples),
        "rms": round(rms, 2),
        "peak": int(peak),
        "rms_ratio": round(rms_ratio, 6),
        "peak_ratio": round(peak_ratio, 6),
        "has_signal": has_signal,
        "mean": round(mean, 2),
        "mean_ratio": round(mean_ratio, 6),
        "clipping_ratio": round(clipping_ratio, 6),
        "dc_offset_ratio": round(dc_offset_ratio, 6),
        "zero_crossing_rate": round(zero_crossing_rate, 6),
        "quality_state": quality_state,
    }


def pcm16_waveform(audio_data: bytes, points: int = 64) -> list[float]:
    if not audio_data or points <= 0:
        return []

    samples = _pcm16_samples(audio_data)
    if not samples:
        return []

    bucket_size = max(1, len(samples) // points)
    waveform: list[float] = []
    for start in range(0, len(samples), bucket_size):
        bucket = samples[start:start + bucket_size]
        if not bucket:
            continue
        peak = max(abs(value) for value in bucket) / 32768.0
        waveform.append(round(min(1.0, peak), 4))
        if len(waveform) >= points:
            break
    while len(waveform) < points:
        waveform.append(0.0)
    return waveform
