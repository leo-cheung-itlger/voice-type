from __future__ import annotations

from typing import Any, Iterable


VIRTUAL_INPUT_TERMS = [
    "声音映射器",
    "sound mapper",
    "主声音捕获",
    "primary sound capture",
    "虚拟",
    "virtual",
    "vb-audio",
    "cable output",
    "output",
    "hands-free",
    "hands free",
    "网易",
    "netease",
    "远控",
    "remote",
]

REAL_MIC_TERMS = [
    "3.5mm",
    "3.5 mm",
    "麦克风",
    "microphone",
    "mic",
    "array",
    "阵列",
]


def audio_device_label(name: str) -> str:
    raw = (name or "").replace("（", "(").replace("）", ")").strip()
    variants = [raw]
    try:
        repaired = raw.encode("latin1").decode("utf-8")
        if repaired and repaired != raw:
            variants.append(repaired)
    except Exception:
        pass
    return " ".join(variants).lower()


def is_virtual_input_name(name: str) -> bool:
    lower_name = audio_device_label(name)
    return any(term in lower_name for term in VIRTUAL_INPUT_TERMS)


def looks_like_real_microphone(name: str) -> bool:
    lower_name = audio_device_label(name)
    return any(term in lower_name for term in REAL_MIC_TERMS)


def device_name_matches(configured_name: str, actual_name: str) -> bool:
    configured = audio_device_label(configured_name)
    actual = audio_device_label(actual_name)
    if not configured or not actual:
        return False
    return configured == actual or configured in actual or actual in configured


def input_device_recommendation(name: str, host_api: str, is_default: bool, sample_rate: int) -> tuple[bool, str]:
    lower_host = (host_api or "").lower()
    if is_virtual_input_name(name):
        return False, "已隐藏：虚拟/远控/映射输入"
    if looks_like_real_microphone(name) and ("wasapi" in lower_host or "directsound" in lower_host):
        return True, "推荐：真实麦克风输入"
    if "wasapi" not in lower_host and "directsound" not in lower_host:
        return False, "默认隐藏：低层驱动或重复设备"
    if looks_like_real_microphone(name) and sample_rate >= 44100:
        return True, "推荐：名称匹配麦克风"
    if is_default:
        return True, "系统默认输入"
    return False, "默认隐藏：非推荐输入"


def _host_score(host_api: str) -> int:
    lower_host = (host_api or "").lower()
    if "wasapi" in lower_host:
        return 300
    if "directsound" in lower_host:
        return 220
    if "mme" in lower_host:
        return 60
    return 0


def input_device_score(
    name: str,
    host_api: str,
    is_default: bool,
    sample_rate: int,
    preferred_name: str = "",
    preferred_host_api: str = "",
    preferred_sample_rate: int = 0,
) -> int:
    lower_name = audio_device_label(name)
    if is_virtual_input_name(name) and not is_virtual_input_name(preferred_name):
        return -100_000

    score = _host_score(host_api)
    if is_default:
        score += 100
    if "3.5mm" in lower_name or "3.5 mm" in lower_name:
        score += 1400
    if "麦克风" in lower_name or "microphone" in lower_name:
        score += 700
    if "mic" in lower_name:
        score += 450
    if "array" in lower_name or "阵列" in lower_name:
        score += 260
    if sample_rate in (44100, 48000):
        score += 40
    if preferred_name and device_name_matches(preferred_name, name):
        score += 5000
    if preferred_host_api and preferred_host_api.lower() == (host_api or "").lower():
        score += 300
    if preferred_sample_rate and int(sample_rate or 0) == int(preferred_sample_rate):
        score += 30
    return score


def device_matches_selection(device: dict[str, Any], selected_index: int, selected_name: str, selected_host_api: str) -> bool:
    index_matches = int(device.get("index", -1)) == int(selected_index)
    if selected_name:
        if not device_name_matches(selected_name, str(device.get("name") or "")):
            return False
        if selected_host_api and selected_host_api.lower() != str(device.get("host_api") or "").lower():
            return False
        return True
    return index_matches


def best_input_device(
    devices: Iterable[dict[str, Any]],
    default_index: int = -1,
    preferred_name: str = "",
    preferred_host_api: str = "",
    preferred_sample_rate: int = 0,
    exclude_indexes: set[int] | None = None,
) -> int | None:
    rows = list(devices)
    excluded = exclude_indexes or set()
    allow_virtual = bool(preferred_name and is_virtual_input_name(preferred_name))
    candidates = []
    for device in rows:
        index = int(device.get("index", -1))
        if index < 0 or index in excluded:
            continue
        name = str(device.get("name") or "")
        if is_virtual_input_name(name) and not allow_virtual:
            continue
        sample_rate = int(float(device.get("default_sample_rate") or device.get("sample_rate") or 0))
        score = input_device_score(
            name=name,
            host_api=str(device.get("host_api") or ""),
            is_default=index == int(default_index),
            sample_rate=sample_rate,
            preferred_name=preferred_name,
            preferred_host_api=preferred_host_api,
            preferred_sample_rate=preferred_sample_rate,
        )
        if score > 0:
            candidates.append((score, index))
    if candidates:
        return max(candidates)[1]

    for device in rows:
        index = int(device.get("index", -1))
        if index == int(default_index) and index not in excluded:
            return index
    return None


def unique_sample_rates(*rates: int) -> list[int]:
    result = []
    for rate in rates:
        value = int(float(rate or 0))
        if value > 0 and value not in result:
            result.append(value)
    return result


def candidate_input_sample_rates(
    default_sample_rate: int,
    preferred_sample_rate: int = 0,
    configured_sample_rate: int = 48000,
) -> list[int]:
    return unique_sample_rates(
        default_sample_rate,
        preferred_sample_rate,
        configured_sample_rate,
        48000,
        44100,
        16000,
    )


def supported_input_sample_rates(
    audio: Any,
    pyaudio_module: Any,
    device_index: int | None,
    channels: int,
    rates: Iterable[int],
) -> list[int]:
    supported = []
    for rate in unique_sample_rates(*list(rates)):
        kwargs = {
            "input_channels": channels,
            "input_format": pyaudio_module.paInt16,
        }
        if device_index is not None and device_index >= 0:
            kwargs["input_device"] = device_index
        try:
            audio.is_format_supported(rate, **kwargs)
            supported.append(rate)
        except Exception:
            continue
    return supported
