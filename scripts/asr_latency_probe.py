import argparse
import asyncio
import json
import os
import sys
import time
import uuid
import wave
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import websockets

from config.settings import DATA_DIR, load_app_config


def _latest_archive_wav() -> Path:
    archive = Path(DATA_DIR) / "archive"
    candidates = sorted(
        archive.glob("**/recording.wav"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No archive recording.wav found; pass --audio-file explicitly.")
    return candidates[0]


def _read_pcm16_wav(path: Path) -> tuple[bytes, int, int, float]:
    with wave.open(str(path), "rb") as wav_file:
        sample_rate = int(wav_file.getframerate())
        channels = int(wav_file.getnchannels())
        sample_width = int(wav_file.getsampwidth())
        if sample_width != 2:
            raise ValueError(f"Expected PCM16 WAV, got sample width {sample_width}: {path}")
        frames = wav_file.getnframes()
        data = wav_file.readframes(frames)
    duration = frames / sample_rate if sample_rate else 0.0
    return data, sample_rate, channels, duration


async def _send_probe(
    *,
    audio_file: Path,
    mode: str,
    chunk_ms: int,
    host: str,
    port: int,
    pace: bool,
) -> dict[str, Any]:
    audio_data, sample_rate, channels, audio_duration = _read_pcm16_wav(audio_file)
    if channels != 1:
        raise ValueError(f"Expected mono PCM16 WAV for ASR probe, got {channels} channels: {audio_file}")

    bytes_per_second = sample_rate * channels * 2
    if mode == "batch":
        chunk_size = len(audio_data)
    else:
        chunk_size = max(2, int(bytes_per_second * chunk_ms / 1000))
        chunk_size -= chunk_size % 2

    task_id = str(uuid.uuid4())
    ws_url = f"ws://{host}:{port}"
    started_at = time.time()
    mono_started = time.monotonic()
    chunks_sent = 0
    bytes_sent = 0

    async with websockets.connect(ws_url, max_size=None, ping_interval=20, ping_timeout=10) as ws:
        await ws.send(json.dumps({
            "type": "audio_start",
            "task_id": task_id,
            "sample_rate": sample_rate,
        }))
        send_started = time.monotonic()
        for index in range(0, len(audio_data), chunk_size):
            await ws.send(audio_data[index:index + chunk_size])
            chunks_sent += 1
            bytes_sent += min(chunk_size, len(audio_data) - index)
            if pace and mode != "batch":
                await asyncio.sleep(chunk_ms / 1000)
        send_completed = time.monotonic()
        time_submit_wall = time.time()
        await ws.send(json.dumps({
            "type": "audio_end",
            "audio_path": str(audio_file),
            "sample_rate": sample_rate,
        }, ensure_ascii=False))
        response_started = time.monotonic()
        response = json.loads(await ws.recv())
        completed = time.monotonic()

    server_submit = float(response.get("time_submit") or time_submit_wall)
    server_complete = float(response.get("time_complete") or time.time())
    server_inference = max(0.0, server_complete - server_submit)
    return {
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "audio_file": str(audio_file),
        "audio_duration_seconds": round(audio_duration, 3),
        "sample_rate": sample_rate,
        "channels": channels,
        "mode": mode,
        "chunk_ms": chunk_ms if mode != "batch" else None,
        "pace": pace if mode != "batch" else False,
        "chunks_sent": chunks_sent,
        "bytes_sent": bytes_sent,
        "send_seconds": round(send_completed - send_started, 4),
        "post_end_wait_seconds": round(completed - response_started, 4),
        "client_round_trip_seconds": round(completed - mono_started, 4),
        "server_inference_seconds": round(server_inference, 4),
        "text": response.get("text", ""),
        "model": response.get("model", ""),
        "server_duration_seconds": response.get("duration_seconds"),
        "started_at": started_at,
        "time_submit": server_submit,
        "time_complete": server_complete,
    }


def _write_result(result: dict[str, Any]) -> Path:
    output_path = Path(DATA_DIR) / "asr_latency_probe.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, Any]] = []
    if output_path.exists():
        try:
            loaded = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                existing = loaded
        except Exception:
            existing = []
    existing.append(result)
    output_path.write_text(json.dumps(existing[-100:], ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    config = load_app_config()
    parser = argparse.ArgumentParser(
        description="Probe VoiceType ASR WebSocket latency with batch or 50ms-style chunked uploads."
    )
    parser.add_argument("--audio-file", default="", help="Mono PCM16 WAV file. Defaults to latest archive recording.")
    parser.add_argument("--mode", choices=["batch", "chunked", "realtime"], default="chunked")
    parser.add_argument("--chunk-ms", type=int, default=50, help="Chunk size for chunked/realtime modes.")
    parser.add_argument("--host", default=config.client.server_host)
    parser.add_argument("--port", type=int, default=config.client.server_port)
    parser.add_argument("--no-write", action="store_true", help="Print only; do not update data/asr_latency_probe.json.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio_file = Path(args.audio_file) if args.audio_file else _latest_archive_wav()
    if not audio_file.is_file():
        raise FileNotFoundError(audio_file)
    if args.chunk_ms <= 0:
        raise ValueError("--chunk-ms must be positive")

    result = asyncio.run(_send_probe(
        audio_file=audio_file,
        mode=args.mode,
        chunk_ms=args.chunk_ms,
        host=args.host,
        port=args.port,
        pace=args.mode == "realtime",
    ))
    if not args.no_write:
        result["result_file"] = str(_write_result(result))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
