import argparse
import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import load_app_config


DEFAULT_ASSET_DIR = Path(r"C:\Program Files\CapsWriter-Offline-Windows-64bit\2026\04\assets")


def expected_from_name(path: Path) -> str:
    match = re.match(r"^\([^)]*\)(.*)\.mp3$", path.name, re.IGNORECASE)
    return match.group(1) if match else path.stem


def normalize_text(text: str) -> str:
    digit_map = str.maketrans({
        "0": "零",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    })
    text = text.translate(digit_map)
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).lower()


def is_match(expected: str, actual: str) -> bool:
    left = normalize_text(expected)
    right = normalize_text(actual)
    if not left or not right:
        return False
    return left in right or right in left


def fixture_files(asset_dir: Path, limit: int) -> list[Path]:
    files = sorted(asset_dir.glob("(20260429-200*.mp3"))
    if limit > 0:
        return files[:limit]
    return files


def direct_recognize(files: list[Path], model_dir: str) -> list[dict]:
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    from qwen_asr import Qwen3ASRModel

    started = time.time()
    model = Qwen3ASRModel.from_pretrained(model_dir)
    load_seconds = time.time() - started

    rows = []
    for path in files:
        expected = expected_from_name(path)
        item_started = time.time()
        try:
            result = model.transcribe(audio=str(path), language=None)
            text = ""
            if result:
                text = getattr(result[0], "text", "") or str(result[0])
            status = "ok" if text and is_match(expected, text) else "mismatch"
            error = ""
        except Exception as exc:
            text = ""
            status = "error"
            error = str(exc)
        rows.append({
            "mode": "direct",
            "file": str(path),
            "expected": expected,
            "text": text,
            "status": status,
            "seconds": round(time.time() - item_started, 2),
            "model_load_seconds": round(load_seconds, 2),
            "error": error,
        })
    return rows


def decode_audio(path: Path) -> tuple[bytes, int]:
    import librosa
    import numpy as np

    audio, sample_rate = librosa.load(str(path), sr=None, mono=True)
    audio = np.clip(audio, -1.0, 1.0)
    pcm = (audio * 32767.0).astype(np.int16)
    return pcm.tobytes(), int(sample_rate)


async def service_recognize_one(path: Path, host: str, port: int, timeout: float) -> dict:
    import websockets

    expected = expected_from_name(path)
    started = time.time()
    try:
        audio, sample_rate = decode_audio(path)
        task_id = str(uuid.uuid4())
        async with websockets.connect(f"ws://{host}:{port}", max_size=None, ping_interval=20, ping_timeout=10) as ws:
            await ws.send(json.dumps({
                "type": "audio_start",
                "task_id": task_id,
                "sample_rate": sample_rate,
            }))
            chunk_size = 32_000
            for index in range(0, len(audio), chunk_size):
                await ws.send(audio[index:index + chunk_size])
            await ws.send(json.dumps({
                "type": "audio_end",
                "audio_path": str(path),
                "sample_rate": sample_rate,
            }, ensure_ascii=False))
            message = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(message)
        text = data.get("text", "")
        status = "ok" if text and is_match(expected, text) else "mismatch"
        error = data.get("error", "")
    except Exception as exc:
        text = ""
        status = "error"
        error = str(exc)
    return {
        "mode": "service",
        "file": str(path),
        "expected": expected,
        "text": text,
        "status": status,
        "seconds": round(time.time() - started, 2),
        "error": error,
    }


async def service_recognize(files: list[Path], host: str, port: int, timeout: float) -> list[dict]:
    rows = []
    for path in files:
        rows.append(await service_recognize_one(path, host, port, timeout))
    return rows


def print_rows(rows: list[dict]):
    for row in rows:
        print(json.dumps(row, ensure_ascii=False))

    passed = sum(1 for row in rows if row["status"] == "ok")
    print(json.dumps({
        "summary": {
            "passed": passed,
            "total": len(rows),
            "failed": len(rows) - passed,
        }
    }, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed audio ASR smoke tests.")
    parser.add_argument("--mode", choices=["direct", "service"], default="direct")
    parser.add_argument("--asset-dir", default=str(DEFAULT_ASSET_DIR))
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    asset_dir = Path(args.asset_dir)
    files = fixture_files(asset_dir, args.limit)
    if not files:
        print(f"No fixture mp3 files found in {asset_dir}", file=sys.stderr)
        return 2

    config = load_app_config()
    if args.mode == "direct":
        rows = direct_recognize(files, config.server.model_dir)
    else:
        port = args.port or config.server.port
        rows = asyncio.run(service_recognize(files, args.host, port, args.timeout))

    print_rows(rows)
    return 0 if all(row["status"] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
