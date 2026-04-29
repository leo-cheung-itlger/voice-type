import base64
import json
import os
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from common.logger import setup_logger
from config.settings import BASE_DIR, DATA_DIR, resolve_model_dir
from server.asr_engine import ASREngine

logger = setup_logger("transcription")

TRANSCRIPTION_DB = os.path.join(DATA_DIR, "transcriptions.json")
LLM_CONFIG_FILE = os.path.join(DATA_DIR, "llm_config.json")
UPLOAD_DIR = os.path.join(DATA_DIR, "transcription_uploads")

SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
}

DEFAULT_LLM_CONFIG = {
    "base_url": "https://api.openai.com/v1",
    "model": "",
    "api_key": "",
    "temperature": 0.2,
    "max_segment_chars": 1800,
}

POLISH_PROMPTS = {
    "correct": "仅修正语音识别错误、错别字和明显断句问题，保留原意和口语风格。",
    "deoralize": "去除口头禅、重复词、无意义停顿和犹豫表达，让文本更顺畅，但不要改变事实含义。",
    "formal": "将内容改写为更书面、清晰、连贯的表达，保留信息密度和原始语义。",
}


def load_llm_config(mask: bool = False) -> Dict[str, Any]:
    config = dict(DEFAULT_LLM_CONFIG)
    if os.path.exists(LLM_CONFIG_FILE):
        try:
            with open(LLM_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in config:
                if key in data:
                    config[key] = data[key]
        except Exception as exc:
            logger.error(f"Failed to load LLM config: {exc}")
    if mask and config.get("api_key"):
        config["api_key"] = "********"
    return config


def save_llm_config(values: Dict[str, Any]) -> Dict[str, Any]:
    current = load_llm_config(mask=False)
    for key in DEFAULT_LLM_CONFIG:
        if key not in values:
            continue
        if key == "api_key" and values[key] == "********":
            continue
        current[key] = values[key]
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LLM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return load_llm_config(mask=True)


def ffmpeg_status() -> Dict[str, Any]:
    ffmpeg_path = os.environ.get("VOICETYPE_FFMPEG_PATH") or shutil.which("ffmpeg")
    ffprobe_path = os.environ.get("VOICETYPE_FFPROBE_PATH") or shutil.which("ffprobe")
    return {
        "available": bool(ffmpeg_path),
        "ffmpeg": ffmpeg_path or "",
        "ffprobe": ffprobe_path or "",
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "message": "ffmpeg is available" if ffmpeg_path else "ffmpeg not found. Install ffmpeg or set VOICETYPE_FFMPEG_PATH.",
    }


def _safe_name(name: str) -> str:
    keep = []
    for char in name:
        if char.isalnum() or char in ("-", "_", ".", " "):
            keep.append(char)
        else:
            keep.append("_")
    value = "".join(keep).strip(" .")
    return value or "media"


def _format_srt_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    millis = int(round((seconds - int(seconds)) * 1000))
    whole = int(seconds)
    h = whole // 3600
    m = (whole % 3600) // 60
    s = whole % 60
    return f"{h:02d}:{m:02d}:{s:02d},{millis:03d}"


def _write_outputs(result: Dict[str, Any], output_dir: str, formats: List[str], suffix: str = "") -> Dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    source = Path(result["source_file"])
    stem = _safe_name(source.stem)
    suffix_part = f"_{suffix}" if suffix else ""
    outputs: Dict[str, str] = {}

    if "json" in formats:
        path = os.path.join(output_dir, f"{stem}{suffix_part}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        outputs["json" if not suffix else f"json_{suffix}"] = path

    if "txt" in formats:
        path = os.path.join(output_dir, f"{stem}{suffix_part}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(segment.get("text", "") for segment in result.get("segments", []) if segment.get("text")))
            f.write("\n")
        outputs["txt" if not suffix else f"txt_{suffix}"] = path

    if "srt" in formats:
        path = os.path.join(output_dir, f"{stem}{suffix_part}.srt")
        with open(path, "w", encoding="utf-8") as f:
            index = 1
            for segment in result.get("segments", []):
                text = segment.get("text", "").strip()
                if not text:
                    continue
                start = _format_srt_time(float(segment.get("start", 0)))
                end = _format_srt_time(float(segment.get("end", 0)))
                f.write(f"{index}\n{start} --> {end}\n{text}\n\n")
                index += 1
        outputs["srt" if not suffix else f"srt_{suffix}"] = path

    return outputs


def _split_text(text: str, max_chars: int) -> List[str]:
    chunks: List[str] = []
    current = ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks or ([text] if text else [])


def _call_openai_compatible(messages: List[Dict[str, str]], config: Dict[str, Any]) -> str:
    base_url = str(config.get("base_url", "")).rstrip("/")
    api_key = str(config.get("api_key", ""))
    model = str(config.get("model", ""))
    if not base_url or not api_key or not model:
        raise RuntimeError("LLM config requires base_url, model, and api_key")

    body = json.dumps(
        {
            "model": model,
            "messages": messages,
            "temperature": float(config.get("temperature", 0.2)),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urlrequest.Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM request failed: HTTP {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc

    return data["choices"][0]["message"]["content"].strip()


def polish_segments(segments: List[Dict[str, Any]], mode: str, custom_prompt: str = "") -> List[Dict[str, Any]]:
    config = load_llm_config(mask=False)
    max_chars = int(config.get("max_segment_chars") or 1800)
    original_text = "\n".join(segment.get("text", "") for segment in segments if segment.get("text"))
    if not original_text.strip():
        return segments

    overview = _call_openai_compatible(
        [
            {"role": "system", "content": "你是字幕转写校对助手。请先判断全文主题和上下文，不要改写全文。"},
            {"role": "user", "content": f"请用不超过120字概括这份转写内容的主题和术语背景：\n{original_text[:6000]}"},
        ],
        config,
    )
    instruction = custom_prompt.strip() or POLISH_PROMPTS.get(mode, POLISH_PROMPTS["correct"])
    polished_texts: List[str] = []
    for chunk in _split_text(original_text, max_chars):
        polished_texts.append(
            _call_openai_compatible(
                [
                    {"role": "system", "content": f"你是字幕文本润色助手。全文背景：{overview}"},
                    {"role": "user", "content": f"{instruction}\n\n要求：只输出处理后的文本，不要解释。\n\n原文：\n{chunk}"},
                ],
                config,
            )
        )

    polished_lines = "\n".join(polished_texts).splitlines()
    non_empty_segments = [segment for segment in segments if segment.get("text")]
    if not non_empty_segments:
        return segments

    next_lines = iter([line.strip() for line in polished_lines if line.strip()])
    output = []
    for segment in segments:
        cloned = dict(segment)
        if segment.get("text"):
            cloned["text"] = next(next_lines, segment.get("text", ""))
        output.append(cloned)
    return output


class TranscriptionManager:
    def __init__(self, filepath: str = TRANSCRIPTION_DB):
        self._filepath = filepath
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._tasks = data.get("tasks", {})
            for task in self._tasks.values():
                if task.get("status") in {"queued", "transcribing", "polishing"}:
                    task["status"] = "failed"
                    task["error"] = "API restarted before task completed"
        except Exception as exc:
            logger.error(f"Failed to load transcriptions: {exc}")

    def _save(self):
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump({"tasks": self._tasks}, f, ensure_ascii=False, indent=2)

    def list_tasks(self) -> List[Dict[str, Any]]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda task: task.get("created_at", 0), reverse=True)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def create_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        files = [str(Path(path)) for path in payload.get("input_files", []) if str(path).strip()]
        if not files:
            raise ValueError("input_files is required")

        task_id = str(uuid.uuid4())
        now = time.time()
        model = payload.get("model") or ""
        formats = [fmt.lower() for fmt in (payload.get("formats") or ["json", "txt", "srt"])]
        formats = [fmt for fmt in formats if fmt in {"json", "txt", "srt"}] or ["json", "txt", "srt"]
        file_rows = []
        for path in files:
            ext = Path(path).suffix.lower()
            file_rows.append({
                "path": path,
                "status": "queued",
                "error": "" if ext in SUPPORTED_EXTENSIONS else f"Unsupported extension: {ext}",
                "outputs": {},
            })

        task = {
            "task_id": task_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "progress": 0,
            "input_files": files,
            "files": file_rows,
            "model": model,
            "output_dir": payload.get("output_dir") or "",
            "formats": formats,
            "polish": bool(payload.get("polish", False)),
            "polish_mode": payload.get("polish_mode") or "correct",
            "custom_prompt": payload.get("custom_prompt") or "",
            "chunk_seconds": int(payload.get("chunk_seconds") or 30),
            "cancel_requested": False,
            "error": "",
        }
        with self._lock:
            self._tasks[task_id] = task
            self._save()
        return dict(task)

    def save_uploaded_files(self, files: List[Any]) -> List[str]:
        batch_dir = os.path.join(UPLOAD_DIR, datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])
        os.makedirs(batch_dir, exist_ok=True)
        paths = []
        for upload in files:
            filename = _safe_name(upload.filename or "media")
            path = os.path.join(batch_dir, filename)
            with open(path, "wb") as f:
                shutil.copyfileobj(upload.file, f)
            paths.append(path)
        return paths

    def cancel_task(self, task_id: str) -> Dict[str, Any]:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise KeyError(task_id)
            task["cancel_requested"] = True
            if task.get("status") == "queued":
                task["status"] = "cancelled"
            task["updated_at"] = time.time()
            self._save()
            return dict(task)

    def outputs(self, task_id: str) -> Dict[str, str]:
        task = self.get_task(task_id)
        if not task:
            raise KeyError(task_id)
        outputs: Dict[str, str] = {}
        for row in task.get("files", []):
            for key, path in row.get("outputs", {}).items():
                outputs[f"{Path(row.get('path', '')).name}:{key}"] = path
        return outputs

    def _update(self, task_id: str, **values):
        with self._lock:
            task = self._tasks[task_id]
            task.update(values)
            task["updated_at"] = time.time()
            self._save()

    def _update_file(self, task_id: str, index: int, **values):
        with self._lock:
            task = self._tasks[task_id]
            task["files"][index].update(values)
            task["updated_at"] = time.time()
            self._save()

    def _cancelled(self, task_id: str) -> bool:
        with self._lock:
            return bool(self._tasks.get(task_id, {}).get("cancel_requested"))

    def run_task(self, task_id: str, default_model: str, default_model_dir: str, gpu: bool, gpu_backend: str):
        task = self.get_task(task_id)
        if not task:
            return
        ffmpeg = ffmpeg_status().get("ffmpeg")
        if not ffmpeg:
            self._update(task_id, status="failed", error="ffmpeg not found")
            return

        model = task.get("model") or default_model
        model_dir = resolve_model_dir(model) or default_model_dir
        self._update(task_id, status="transcribing", model=model, progress=1)
        engine = ASREngine(model=model, model_dir=model_dir, gpu=gpu, gpu_backend=gpu_backend)
        if not engine.initialize():
            self._update(task_id, status="failed", error=f"Failed to initialize model: {model}")
            return

        try:
            files = task.get("files", [])
            for index, row in enumerate(files):
                if self._cancelled(task_id):
                    self._update(task_id, status="cancelled")
                    return
                self._process_file(task_id, index, row, engine, ffmpeg)
                completed = sum(1 for item in self.get_task(task_id).get("files", []) if item.get("status") in {"completed", "failed"})
                self._update(task_id, progress=int((completed / max(1, len(files))) * 100))

            final_task = self.get_task(task_id)
            failed = [row for row in final_task.get("files", []) if row.get("status") == "failed"]
            self._update(task_id, status="failed" if failed and len(failed) == len(files) else "completed", progress=100)
        except Exception as exc:
            logger.exception(f"Transcription task failed: {task_id}")
            self._update(task_id, status="failed", error=str(exc))

    def _process_file(self, task_id: str, index: int, row: Dict[str, Any], engine: ASREngine, ffmpeg: str):
        source = row.get("path", "")
        source_path = Path(source)
        if row.get("error"):
            self._update_file(task_id, index, status="failed")
            return
        if not source_path.exists():
            self._update_file(task_id, index, status="failed", error="File not found")
            return

        task = self.get_task(task_id)
        output_dir = task.get("output_dir") or str(source_path.with_name(f"{_safe_name(source_path.stem)}_transcript"))
        sample_rate = 16000
        chunk_seconds = max(5, int(task.get("chunk_seconds") or 30))
        chunk_bytes = sample_rate * 2 * chunk_seconds

        self._update_file(task_id, index, status="transcribing", output_dir=output_dir)
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "pipe:1",
        ]
        decoded = subprocess.check_output(command, cwd=BASE_DIR)
        segments = []
        total_chunks = max(1, (len(decoded) + chunk_bytes - 1) // chunk_bytes)
        for chunk_index, offset in enumerate(range(0, len(decoded), chunk_bytes)):
            if self._cancelled(task_id):
                self._update_file(task_id, index, status="cancelled")
                return
            chunk = decoded[offset : offset + chunk_bytes]
            if not chunk:
                continue
            started = offset / 2 / sample_rate
            ended = min(len(decoded) / 2 / sample_rate, started + chunk_seconds)
            text = engine.recognize(chunk, sample_rate=sample_rate) or ""
            segments.append({
                "index": chunk_index + 1,
                "start": round(started, 3),
                "end": round(ended, 3),
                "text": text,
            })
            file_progress = int(((chunk_index + 1) / total_chunks) * 100)
            self._update_file(task_id, index, progress=file_progress)

        result = {
            "source_file": str(source_path),
            "model": engine.model_name,
            "backend": engine.backend,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "approximate_timestamps": True,
            "sample_rate": sample_rate,
            "segments": segments,
        }
        outputs = _write_outputs(result, output_dir, task.get("formats", ["json", "txt", "srt"]))

        if task.get("polish"):
            self._update(task_id, status="polishing")
            polished_segments = polish_segments(segments, task.get("polish_mode", "correct"), task.get("custom_prompt", ""))
            polished = dict(result)
            polished["segments"] = polished_segments
            polished["polish_mode"] = task.get("polish_mode", "correct")
            outputs.update(_write_outputs(polished, output_dir, task.get("formats", ["json", "txt", "srt"]), suffix="polished"))

        self._update_file(task_id, index, status="completed", progress=100, outputs=outputs)
