import math
import sys
from array import array
from typing import Any


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
        }

    sample_bytes = audio_data[: len(audio_data) - (len(audio_data) % 2)]
    samples = array("h")
    samples.frombytes(sample_bytes)
    if sys.byteorder != "little":
        samples.byteswap()

    if not samples:
        return {
            "bytes": len(audio_data),
            "samples": 0,
            "rms": 0.0,
            "peak": 0,
            "rms_ratio": 0.0,
            "peak_ratio": 0.0,
            "has_signal": False,
        }

    peak = max(abs(value) for value in samples)
    square_sum = sum(float(value) * float(value) for value in samples)
    rms = math.sqrt(square_sum / len(samples))
    rms_ratio = rms / 32768.0
    peak_ratio = peak / 32768.0
    return {
        "bytes": len(audio_data),
        "samples": len(samples),
        "rms": round(rms, 2),
        "peak": int(peak),
        "rms_ratio": round(rms_ratio, 6),
        "peak_ratio": round(peak_ratio, 6),
        "has_signal": bool(rms_ratio >= 0.003 or peak_ratio >= 0.02),
    }
