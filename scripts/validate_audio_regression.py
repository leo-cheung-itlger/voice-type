from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common.audio_capture import capture_input_once, pyaudio_input_devices, remember_capture_profile, wav_bytes_from_pcm16
from common.audio_devices import device_name_matches
from config.settings import DATA_DIR, load_app_config
from server.asr_engine import ASREngine


DEFAULT_REFERENCE_FILES = [
    Path(r"D:\1a-LEO-Fire\Downloads\Edge\你好，请问听得到我说话吗？这边正在测试麦克风.weba"),
    ROOT / "你好，请问听得到我说话吗？这边正在测试麦克风.weba",
]
DEFAULT_TARGETS = [
    "3.5mm麦克风 (Senary Audio)",
    "麦克风阵列 (Senary Audio)",
]
EXPECTED_TEXT = "你好，请问听得到我说话吗？这边正在测试麦克风"
VALIDATION_DIR = Path(DATA_DIR) / "transcription_validation" / "audio_regression"
PUNCT_RE = re.compile(r"[\s,.!?;:，。！？；：、]")


def canonical_text(text: str) -> str:
    return PUNCT_RE.sub("", text or "").strip()


def find_reference_file(explicit_path: str = "") -> Path:
    candidates = [Path(explicit_path)] if explicit_path else []
    candidates.extend(DEFAULT_REFERENCE_FILES)
    for path in candidates:
        if path and path.exists():
            return path
    raise FileNotFoundError("No reference audio file was found.")


def convert_reference_to_wav(reference_path: Path) -> Path:
    ffmpeg = ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if not ffmpeg.exists():
        raise FileNotFoundError(f"ffmpeg missing: {ffmpeg}")
    target = Path(tempfile.gettempdir()) / "voicetype_reference_validation.wav"
    subprocess.run(
        [str(ffmpeg), "-y", "-i", str(reference_path), "-ac", "1", "-ar", "48000", str(target)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    return target


def load_wav_bytes(path: Path) -> tuple[bytes, int]:
    import wave

    with wave.open(str(path), "rb") as handle:
        return handle.readframes(handle.getnframes()), int(handle.getframerate())


def init_engine() -> ASREngine:
    config = load_app_config().server
    engine = ASREngine(
        model=config.model,
        model_dir=config.model_dir,
        gpu=config.gpu,
        gpu_backend=config.gpu_backend,
        gpu_required=config.gpu_required,
        allow_cpu_fallback=config.allow_cpu_fallback,
    )
    if not engine.initialize():
        raise RuntimeError(engine.last_error or "Failed to initialize ASR engine")
    return engine


def playback_and_capture(reference_wav: Path, device_index: int, seconds: float) -> dict:
    import pyaudio

    ffplay = ROOT / "tools" / "ffmpeg" / "bin" / "ffplay.exe"
    if not ffplay.exists():
        raise FileNotFoundError(f"ffplay missing: {ffplay}")
    player = subprocess.Popen(
        [str(ffplay), "-nodisp", "-autoexit", "-loglevel", "error", str(reference_wav)],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    audio = pyaudio.PyAudio()
    try:
        time.sleep(0.18)
        capture = capture_input_once(
            audio,
            pyaudio,
            device_index,
            seconds=seconds,
            preferred_sample_rate=0,
            configured_sample_rate=48000,
            preferred_channels=2,
            waveform_points=64,
            logger=None,
        )
    finally:
        audio.terminate()
        try:
            player.wait(timeout=max(2.0, seconds + 2.0))
        except subprocess.TimeoutExpired:
            player.kill()
    return capture


def save_capture_wav(path: Path, capture: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    wav_data = wav_bytes_from_pcm16(
        capture["normalized_audio"],
        int(capture["sample_rate"]),
        int(capture.get("normalized_channels") or 1),
    )
    path.write_bytes(wav_data)


def score_capture(text: str, expected: str, quality_state: str) -> int:
    score = 0
    if canonical_text(text) == canonical_text(expected):
        score += 100000
    if quality_state == "ok":
        score += 1000
    score += len(text or "")
    return score


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate VoiceType microphone capture against a reference sentence.")
    parser.add_argument("--reference", default="", help="Path to the reference .weba/.wav file.")
    parser.add_argument("--expected", default=EXPECTED_TEXT, help="Expected transcription text.")
    parser.add_argument("--device-name", action="append", dest="device_names", help="Physical microphone name to validate.")
    args = parser.parse_args()

    reference_file = find_reference_file(args.reference)
    reference_wav = convert_reference_to_wav(reference_file)
    reference_bytes, reference_rate = load_wav_bytes(reference_wav)
    expected = args.expected
    targets = args.device_names or list(DEFAULT_TARGETS)

    engine = init_engine()
    baseline_text = engine.recognize(reference_bytes, reference_rate) or ""
    baseline_ok = canonical_text(baseline_text) == canonical_text(expected)

    import pyaudio

    audio = pyaudio.PyAudio()
    try:
        devices = pyaudio_input_devices(audio)
    finally:
        audio.terminate()

    started = time.strftime("%Y%m%d-%H%M%S")
    target_root = VALIDATION_DIR / started
    target_root.mkdir(parents=True, exist_ok=True)

    summary = {
        "reference_file": str(reference_file),
        "reference_wav": str(reference_wav),
        "expected_text": expected,
        "baseline_text": baseline_text,
        "baseline_ok": baseline_ok,
        "targets": [],
    }

    if not baseline_ok:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    overall_ok = True
    duration_seconds = max(3.2, reference_bytes.__len__() / 2 / reference_rate + 0.55)

    for target_name in targets:
        matches = [device for device in devices if device_name_matches(target_name, str(device.get("name") or ""))]
        target_result = {"target_name": target_name, "results": [], "best": None}
        if not matches:
            target_result["error"] = "no matching input devices"
            summary["targets"].append(target_result)
            overall_ok = False
            continue

        best_result = None
        best_score = -10**9
        for device in matches:
            capture = playback_and_capture(reference_wav, int(device["index"]), duration_seconds)
            recognized_text = engine.recognize(capture["normalized_audio"], int(capture["sample_rate"])) or ""
            match_ok = canonical_text(recognized_text) == canonical_text(expected)
            quality_state = str(capture.get("quality_state") or capture["audio_level"].get("quality_state") or "")
            score = score_capture(recognized_text, expected, quality_state)

            output_name = f"{audio_device_slug(device['name'])}_{device['index']}_{device.get('host_api','unknown').replace(' ', '_')}.wav"
            output_path = target_root / output_name
            save_capture_wav(output_path, capture)

            row = {
                "device_index": int(device["index"]),
                "device_name": device["name"],
                "host_api": device.get("host_api", ""),
                "sample_rate": int(capture["sample_rate"]),
                "capture_channels": int(capture["capture_channels"]),
                "normalized_strategy": capture.get("normalized_strategy", "mono"),
                "normalized_channel_index": (
                    int(capture.get("normalized_channel_index"))
                    if capture.get("normalized_channel_index") is not None
                    else -1
                ),
                "quality_state": quality_state,
                "recognized_text": recognized_text,
                "matched_expected": match_ok,
                "stereo_correlation": capture.get("stereo_correlation"),
                "audio_level": capture["audio_level"],
                "recording_wav": str(output_path),
            }
            target_result["results"].append(row)
            if score > best_score:
                best_score = score
                best_result = row
                best_capture = capture

        target_result["best"] = best_result
        summary["targets"].append(target_result)
        if best_result and best_result["matched_expected"]:
            remember_capture_profile({
                "device_name": best_result["device_name"],
                "host_api": best_result["host_api"],
                "sample_rate": best_result["sample_rate"],
                "capture_channels": best_result["capture_channels"],
                "normalized_strategy": best_result["normalized_strategy"],
                "normalized_channel_index": best_result["normalized_channel_index"],
                "quality_state": best_result["quality_state"],
                "recognized_text": best_result["recognized_text"],
            }, reason="validation_script")
        else:
            overall_ok = False

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


def audio_device_slug(name: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", name or "").strip("-")
    return slug or "device"


if __name__ == "__main__":
    raise SystemExit(main())
