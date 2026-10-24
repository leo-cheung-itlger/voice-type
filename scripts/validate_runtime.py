"""Replay caller-supplied audio through the real service; keep results in ignored data/."""
import argparse
import json
import sys
import time
import wave
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common.remote_asr import RemoteASREngine


def api(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request("http://127.0.0.1:55342/api" + path, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=300) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, required=True, help="Folder with zh.wav, en.wav and yue.wav, PCM16 mono")
    parser.add_argument("--model", default="sensevoice")
    parser.add_argument("--mode", choices=["cpu", "auto", "cuda"], default="cpu")
    parser.add_argument("--output", type=Path, default=ROOT / "data/portable-validation/runtime.json")
    args = parser.parse_args()
    report = {"model": args.model, "mode": args.mode, "samples": [], "limitations": ["This host is not a clean Windows VM or a physical low-end CPU.", "No physical hotkey/paste assertion."]}
    import psutil
    for language, filename in [("zh", "zh.wav"), ("auto", "zh.wav"), ("en", "en.wav"), ("yue", "yue.wav")]:
        started = time.perf_counter()
        response = api("/models/apply", {"model": args.model, "language": language, "compute_mode": args.mode})
        state = response["runtime"]
        engine = RemoteASREngine(55341, state)
        with wave.open(str(args.fixtures / filename)) as source:
            assert source.getnchannels() == 1 and source.getsampwidth() == 2
            audio, rate = source.readframes(source.getnframes()), source.getframerate()
        row = {"language": language, "file": filename, "service_restart_seconds": round(time.perf_counter() - started, 3), "engine_load_seconds": state.get("load_seconds"), "actual_model": engine.model_name, "device": state["actual_device"], "duration_seconds": len(audio) / rate / 2, "runs": []}
        for _ in range(3):
            started = time.perf_counter()
            text = engine.recognize(audio, rate)
            assert text.strip(), f"Empty recognition for {language}"
            row["runs"].append({"seconds": round(time.perf_counter() - started, 3), "text": text, "gpu_memory": engine.last_result.get("gpu_memory", {})})
        row["rss_mb"] = round(psutil.Process(state["pid"]).memory_info().rss / 1024**2, 1)
        row["peak_working_set_mb"] = round(getattr(psutil.Process(state["pid"]).memory_info(), "peak_wset", 0) / 1024**2, 1)
        report["samples"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    task = api("/transcriptions", {"input_files": [str((args.fixtures / "en.wav").resolve())], "model": args.model, "language": "en", "output_dir": str((args.output.parent / (args.model + "-transcript")).resolve())})
    assert task["language"] == "en"
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        task = api("/transcriptions/" + task["task_id"])
        if task["status"] not in {"queued", "transcribing", "polishing"}:
            break
        time.sleep(.5)
    assert task["status"] == "completed", task
    assert "en" == task["language"]
    report["file_task"] = task
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PASS: replay, language persistence, shared-service file transcription", args.output)


if __name__ == "__main__":
    main()
