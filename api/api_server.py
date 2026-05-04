import asyncio
import argparse
import base64
import glob
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn
import websockets as ws_lib

from common.audio_capture import capture_input_once, remember_capture_profile, wav_bytes_from_pcm16
from common.audio_devices import (
    best_input_device,
    device_matches_selection,
    input_device_recommendation,
)
from common.audio_levels import quality_message
from common.history import HistoryManager
from common.hotword import HotwordManager
from common.logger import setup_logger
from common.transcription import (
    TranscriptionManager,
    ffmpeg_status,
    load_llm_config,
    save_llm_config,
)
from config.settings import (
    APIConfig,
    APP_CONFIG_FILE,
    BASE_DIR,
    ClientConfig,
    DATA_DIR,
    DEFAULT_API_PORT,
    DEFAULT_ASR_PORT,
    DEFAULT_FRONTEND_PORT,
    LOGS_DIR,
    MODEL_DIR_NAMES,
    MODELS_DIR,
    ServerConfig,
    app_config_to_dict,
    load_app_config,
    model_root_candidates,
    resolve_model_dir,
    save_app_config,
    update_app_config,
)
from server.asr_engine import ASREngine

logger = setup_logger("api_server")
API_STARTED_AT = time.time()
RECENT_ISSUE_WINDOW_SECONDS = 600

app = FastAPI(title="VoiceType API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODEL_DOWNLOAD_URLS = {
    "qwen3-asr-0.6b": "https://huggingface.co/Qwen/Qwen3-ASR-0.6B",
    "qwen3-asr-1.7b": "https://huggingface.co/Qwen/Qwen3-ASR-1.7B",
    "qwen3-asr-1.7b-gguf-vulkan": "https://huggingface.co/ggml-org/Qwen3-ASR-1.7B-GGUF",
    "funasr-nano": "https://huggingface.co/FunAudioLLM/Fun-ASR-Nano-2512",
    "sensevoice": "https://huggingface.co/FunAudioLLM/SenseVoiceSmall",
    "paraformer": "https://github.com/k2-fsa/sherpa-onnx/releases",
}

MODEL_MODELSCOPE_IDS = {
    "qwen3-asr-0.6b": "Qwen/Qwen3-ASR-0.6B",
    "qwen3-asr-1.7b": "Qwen/Qwen3-ASR-1.7B",
    "qwen3-asr-1.7b-gguf-vulkan": "Qwen/Qwen3-ASR-1.7B-GGUF",
}

history = HistoryManager()
transcriptions = TranscriptionManager()
server_process: Optional[subprocess.Popen] = None
client_process: Optional[subprocess.Popen] = None
_PROCESS_CACHE = {"time": 0.0, "rows": []}
model_download_jobs: dict[str, dict] = {}


class ErrorMarkRequest(BaseModel):
    text: str
    marked_text: str


class ConfigUpdateRequest(BaseModel):
    server: Optional[Dict[str, Any]] = None
    client: Optional[Dict[str, Any]] = None
    api: Optional[Dict[str, Any]] = None


class ModelSelectRequest(BaseModel):
    model: str
    model_dir: Optional[str] = None


class ModelBenchmarkRequest(BaseModel):
    model: Optional[str] = None
    models: Optional[list[str]] = None
    audio_file: Optional[str] = None
    all: bool = False
    acceleration: Optional[str] = None


class TranscriptionCreateRequest(BaseModel):
    input_files: list[str]
    model: Optional[str] = None
    output_dir: Optional[str] = None
    formats: list[str] = ["json", "txt", "srt"]
    polish: bool = False
    polish_mode: str = "correct"
    custom_prompt: str = ""
    chunk_seconds: int = 30


class LLMConfigRequest(BaseModel):
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    max_segment_chars: Optional[int] = None


class AudioTestRequest(BaseModel):
    device_index: int = -1
    seconds: float = 3.0


class AudioScanRequest(BaseModel):
    seconds: float = 0.25
    include_all: bool = True
    waveform_points: int = 64


class AudioFormatProbeRequest(BaseModel):
    seconds: float = 5.0
    device_index: Optional[int] = None
    device_name: str = ""
    run_asr: bool = True


class ProcessManager:
    @staticmethod
    def _find_python() -> str:
        project_python = os.path.join(BASE_DIR, "venv", "Scripts", "python.exe")
        if os.path.exists(project_python):
            return project_python
        return sys.executable

    @staticmethod
    def _get_script_path(name: str) -> str:
        return os.path.join(BASE_DIR, name)

    @staticmethod
    def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
        try:
            import psutil
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port == port:
                    return True
            return False
        except Exception:
            pass
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    async def wait_server_ready(timeout_seconds: float = 180.0) -> dict:
        config = load_app_config().server
        started = time.monotonic()
        while time.monotonic() - started < timeout_seconds:
            server = ProcessManager.check_server_health()
            if server.get("running") and server.get("port_open"):
                return {
                    "ready": True,
                    "elapsed_seconds": round(time.monotonic() - started, 2),
                    "server": server,
                }
            await asyncio.sleep(1)
        return {
            "ready": False,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "server": ProcessManager.check_server_health(),
            "message": f"ASR server did not become ready on port {config.port} within {timeout_seconds:.0f}s.",
        }

    @staticmethod
    def _server_args(config: ServerConfig) -> list:
        args = [
            f"--host={config.host}",
            f"--port={config.port}",
            f"--model={config.model}",
            f"--gpu-backend={config.gpu_backend}",
        ]
        if config.model_dir:
            args.append(f"--model-dir={config.model_dir}")
        args.append("--gpu" if config.gpu else "--no-gpu")
        args.append("--gpu-required" if config.gpu_required else "--no-gpu-required")
        args.append("--allow-cpu-fallback" if config.allow_cpu_fallback else "--no-allow-cpu-fallback")
        return args

    @staticmethod
    def _client_args() -> list:
        config = load_app_config().client
        args = [
            f"--server={config.server_host}",
            f"--port={config.server_port}",
            f"--output={config.output_mode}",
            f"--key={config.shortcut_key}",
            f"--audio-dir={config.audio_dir}",
            f"--archive-root={config.archive_root}",
            f"--input-device-index={config.input_device_index}",
            f"--input-device-name={config.input_device_name}",
            f"--input-device-host-api={config.input_device_host_api}",
            f"--input-device-sample-rate={config.input_device_sample_rate}",
            f"--min-press-seconds={config.min_press_seconds}",
        ]
        args.append("--windows-voice-capture" if config.windows_voice_capture_enabled else "--no-windows-voice-capture")
        args.append("--auto-gain" if config.auto_gain_enabled else "--no-auto-gain")
        args.append("--save-audio" if config.save_audio else "--no-save-audio")
        args.append("--notify" if config.notification_enabled else "--no-notify")
        args.append("--sound" if config.notification_sound else "--no-sound")
        return args

    @staticmethod
    def _creation_flags() -> int:
        if sys.platform != "win32":
            return 0
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)

    @staticmethod
    def _log_handles(name: str):
        os.makedirs(LOGS_DIR, exist_ok=True)
        stdout_path = os.path.join(LOGS_DIR, f"{name}_stdout.log")
        stderr_path = os.path.join(LOGS_DIR, f"{name}_stderr.log")
        stdout = open(stdout_path, "a", encoding="utf-8")
        stderr = open(stderr_path, "a", encoding="utf-8")
        return stdout, stderr

    @staticmethod
    def _project_processes() -> list[dict]:
        now = time.time()
        if now - _PROCESS_CACHE["time"] < 1.5:
            return list(_PROCESS_CACHE["rows"])
        if sys.platform != "win32":
            return []
        script = """
$items = Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($env:VOICETYPE_ROOT, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 } |
  Select-Object ProcessId,ParentProcessId,Name,CommandLine
$items | ConvertTo-Json -Compress
"""
        env = os.environ.copy()
        env["VOICETYPE_ROOT"] = BASE_DIR
        try:
            output = subprocess.check_output(
                ["powershell.exe", "-NoProfile", "-Command", script],
                cwd=BASE_DIR,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            ).strip()
        except Exception:
            return []
        if not output:
            return []
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            return []
        if isinstance(data, dict):
            data = [data]
        rows = []
        for item in data:
            command = item.get("CommandLine") or ""
            command_norm = command.replace("\\", "/").lower()
            role = "other"
            if "api_server.py" in command_norm:
                role = "api"
            elif "server/asr_server.py" in command_norm:
                role = "server"
            elif "client/client_core.py" in command_norm:
                role = "client"
            elif "vite/bin/vite.js" in command_norm or "npm run dev" in command_norm:
                role = "frontend"
            else:
                continue
            rows.append({
                "pid": int(item.get("ProcessId") or 0),
                "parent_pid": int(item.get("ParentProcessId") or 0),
                "name": item.get("Name") or "",
                "role": role,
                "command": command,
                "project_venv": os.path.join(BASE_DIR, "venv").lower() in command.lower(),
            })
        _PROCESS_CACHE["time"] = time.time()
        _PROCESS_CACHE["rows"] = rows
        return rows

    @staticmethod
    def _processes_by_role(role: str) -> list[dict]:
        current_pid = os.getpid()
        rows = [
            item for item in ProcessManager._project_processes()
            if item["role"] == role and item["pid"] != current_pid
        ]
        child_parent_pids = {item["parent_pid"] for item in rows if item.get("parent_pid")}
        leaf_rows = [item for item in rows if item["pid"] not in child_parent_pids]
        return leaf_rows or rows

    @staticmethod
    def _terminate_role(role: str) -> list[int]:
        pids = [item["pid"] for item in ProcessManager._processes_by_role(role)]
        for pid in pids:
            try:
                proc = subprocess.Popen(
                    ["powershell.exe", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force"],
                    cwd=BASE_DIR,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=ProcessManager._creation_flags(),
                )
                proc.wait(timeout=5)
            except Exception:
                pass
        return pids

    @staticmethod
    def start_server() -> dict:
        global server_process
        if server_process and server_process.poll() is None:
            return {"status": "already_running", "pid": server_process.pid}

        config = load_app_config().server
        server_rows = ProcessManager._processes_by_role("server")
        if len(server_rows) == 1 and ProcessManager._port_open("127.0.0.1", config.port):
            return {"status": "already_running", "pid": server_rows[0]["pid"], "managed": True}
        if len(server_rows) > 1:
            return {
                "status": "conflict",
                "message": "Multiple VoiceType ASR server processes are running. Stop services before starting.",
                "pids": [row["pid"] for row in server_rows],
            }
        if ProcessManager._port_open("127.0.0.1", config.port):
            return {
                "status": "external_running",
                "message": f"Port {config.port} is already in use by an unmanaged ASR service.",
                "port": config.port,
            }

        python = ProcessManager._find_python()
        script = ProcessManager._get_script_path("server/asr_server.py")
        stdout, stderr = ProcessManager._log_handles("managed_server")
        server_process = subprocess.Popen(
            [python, script, *ProcessManager._server_args(config)],
            cwd=BASE_DIR,
            stdout=stdout,
            stderr=stderr,
            creationflags=ProcessManager._creation_flags(),
        )
        logger.info(f"Server started (PID: {server_process.pid})")
        return {"status": "started", "pid": server_process.pid}

    @staticmethod
    def stop_server() -> dict:
        global server_process
        stopped = []
        if server_process and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
            stopped.append(server_process.pid)
            server_process = None
        stopped.extend(ProcessManager._terminate_role("server"))
        if stopped:
            logger.info(f"Server processes stopped: {stopped}")
            return {"status": "stopped", "pids": sorted(set(stopped))}
        return {"status": "not_running"}

    @staticmethod
    def start_client() -> dict:
        global client_process
        if client_process and client_process.poll() is None:
            return {"status": "already_running", "pid": client_process.pid}

        client_rows = ProcessManager._processes_by_role("client")
        if len(client_rows) == 1:
            return {"status": "already_running", "pid": client_rows[0]["pid"], "managed": True}
        if len(client_rows) > 1:
            return {
                "status": "conflict",
                "message": "Multiple VoiceType clients are running. Stop services before starting.",
                "pids": [row["pid"] for row in client_rows],
            }

        python = ProcessManager._find_python()
        script = ProcessManager._get_script_path("client/client_core.py")
        stdout, stderr = ProcessManager._log_handles("managed_client")
        client_process = subprocess.Popen(
            [python, script, *ProcessManager._client_args()],
            cwd=BASE_DIR,
            stdout=stdout,
            stderr=stderr,
            creationflags=ProcessManager._creation_flags(),
        )
        logger.info(f"Client started (PID: {client_process.pid})")
        return {"status": "started", "pid": client_process.pid}

    @staticmethod
    def stop_client() -> dict:
        global client_process
        stopped = []
        if client_process and client_process.poll() is None:
            client_process.terminate()
            try:
                client_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client_process.kill()
            stopped.append(client_process.pid)
            client_process = None
        stopped.extend(ProcessManager._terminate_role("client"))
        if stopped:
            logger.info(f"Client processes stopped: {stopped}")
            return {"status": "stopped", "pids": sorted(set(stopped))}
        return {"status": "not_running"}

    @staticmethod
    def check_server_health() -> dict:
        config = load_app_config().server
        process_running = server_process is not None and server_process.poll() is None
        server_rows = ProcessManager._processes_by_role("server")
        port_running = ProcessManager._port_open("127.0.0.1", config.port)
        managed = process_running or bool(server_rows)
        pids = [row["pid"] for row in server_rows] or ([server_process.pid] if process_running else [])
        pids = sorted(set(pids))
        return {
            "running": managed or port_running,
            "managed": managed and port_running,
            "port_open": port_running,
            "pid": pids[0] if pids else None,
            "pids": pids,
            "port": config.port,
            "conflict": len(pids) > 1 or (port_running and not managed),
            "process_count": len(pids),
        }

    @staticmethod
    def check_client_health() -> dict:
        process_running = client_process is not None and client_process.poll() is None
        client_rows = ProcessManager._processes_by_role("client")
        pids = [row["pid"] for row in client_rows] or ([client_process.pid] if process_running else [])
        pids = sorted(set(pids))
        running = bool(pids)
        return {
            "running": running,
            "managed": running,
            "pid": pids[0] if pids else None,
            "pids": pids,
            "conflict": len(pids) > 1,
            "process_count": len(pids),
        }

    @staticmethod
    def auto_restart():
        if server_process and server_process.poll() is not None:
            logger.warning("Server process died, auto-restarting...")
            ProcessManager.start_server()

        if client_process and client_process.poll() is not None:
            logger.warning("Client process died, auto-restarting...")
            ProcessManager.start_client()


def _tail_file(path: str, max_lines: int) -> list:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-max_lines:]
    except Exception:
        return []


def _line_is_recent_issue(line: str) -> bool:
    if "[ERROR]" not in line and "[WARNING]" not in line:
        return False

    if len(line) < 21 or line[0] != "[":
        return True

    try:
        timestamp = datetime.strptime(line[1:20], "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return True

    return timestamp >= API_STARTED_AT and time.time() - timestamp <= RECENT_ISSUE_WINDOW_SECONDS


def _model_entries() -> list:
    entries = []
    benchmark = _load_model_benchmark()
    diagnostics = _runtime_diagnostics()
    recommendation = _build_recommendation(benchmark, diagnostics)
    for model, dirname in MODEL_DIR_NAMES.items():
        path = resolve_model_dir(model)
        exists = os.path.isdir(path)
        backend = _expected_model_backend(model)
        role = "daily" if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b-gguf-vulkan") else "quality" if model == "qwen3-asr-1.7b" else "fast"
        model_benchmarks = {
            key: value for key, value in benchmark.items()
            if key == model or key.startswith(f"{model}::")
        }
        blocking_reason = _model_blocking_reason(model, exists, diagnostics)
        entries.append({
            "id": model,
            "name": dirname,
            "path": path,
            "exists": exists,
            "installed": exists,
            "backend": backend,
            "role": role,
            "acceleration": _default_acceleration_for_model(model),
            "download_url": MODEL_DOWNLOAD_URLS.get(model, ""),
            "modelscope_id": MODEL_MODELSCOPE_IDS.get(model, ""),
            "gpu_required_supported": not bool(blocking_reason),
            "blocking_reason": blocking_reason,
            "recommended_for": recommendation.get("recommended_for", {}).get(model, []),
            "benchmark": _normalize_benchmark(benchmark[model]) if model in benchmark else None,
            "benchmarks": model_benchmarks,
        })
    return entries


def _safe_model_target(model_id: str) -> Path:
    if model_id not in MODEL_DIR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown model")
    target = Path(resolve_model_dir(model_id)).resolve()
    allowed_roots = [Path(root).resolve() for root in model_root_candidates()]
    if not any(target == root or root in target.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Model path is outside known model roots")
    return target


def _public_model_download_job(job: dict) -> dict:
    return {
        "model": job.get("model", ""),
        "modelscope_id": job.get("modelscope_id", ""),
        "status": job.get("status", "idle"),
        "target_dir": job.get("target_dir", ""),
        "log_path": job.get("log_path", ""),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "returncode": job.get("returncode"),
        "message": job.get("message", ""),
        "error": job.get("error", ""),
    }


def _run_modelscope_download(model_id: str, job: dict):
    target_dir = Path(job["target_dir"])
    log_path = Path(job["log_path"])
    try:
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        code = (
            "import sys\n"
            "from modelscope import snapshot_download\n"
            "snapshot_download(sys.argv[1], local_dir=sys.argv[2])\n"
        )
        job["message"] = "正在从 ModelScope 下载模型"
        with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
            probe = subprocess.run(
                [sys.executable, "-c", "import modelscope"],
                cwd=BASE_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
            if probe.returncode != 0:
                job["message"] = "正在安装 ModelScope SDK"
                install_command = [sys.executable, "-m", "pip", "install", "modelscope"]
                log_file.write(f"Install command: {install_command}\n")
                log_file.flush()
                install = subprocess.run(
                    install_command,
                    cwd=BASE_DIR,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                if install.returncode != 0:
                    job["returncode"] = install.returncode
                    job["status"] = "error"
                    job["finished_at"] = time.time()
                    job["error"] = "ModelScope SDK 安装失败，请查看下载日志"
                    return

            job["message"] = "正在从 ModelScope 下载模型"
            command = [sys.executable, "-c", code, job["modelscope_id"], str(target_dir)]
            log_file.write(f"Command: {command}\n")
            log_file.flush()
            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
            job["pid"] = process.pid
            returncode = process.wait()
        job["returncode"] = returncode
        job["finished_at"] = time.time()
        if returncode == 0 and target_dir.exists() and any(target_dir.iterdir()):
            job["status"] = "done"
            job["message"] = "下载完成"
        else:
            job["status"] = "error"
            if returncode != 0:
                job["error"] = (
                    "ModelScope 下载失败。若日志提示 No module named 'modelscope'，"
                    f"请先运行：{sys.executable} -m pip install modelscope"
                )
            else:
                job["error"] = "ModelScope 下载结束，但目标目录仍为空"
    except Exception as exc:
        job["status"] = "error"
        job["finished_at"] = time.time()
        job["error"] = str(exc)


def _benchmark_path() -> str:
    return os.path.join(os.path.dirname(APP_CONFIG_FILE), "model_benchmark.json")


def _load_model_benchmark() -> dict:
    path = _benchmark_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_model_benchmark(data: dict):
    os.makedirs(os.path.dirname(_benchmark_path()), exist_ok=True)
    with open(_benchmark_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _expected_model_backend(model: str) -> str:
    if model == "qwen3-asr-1.7b-gguf-vulkan":
        return "gguf-vulkan"
    if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b"):
        return "qwen-asr"
    return "sherpa-onnx"


def _default_acceleration_for_model(model: str) -> str:
    if model == "qwen3-asr-1.7b-gguf-vulkan":
        return "gguf-vulkan"
    if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b"):
        return "pytorch-cuda"
    return "sherpa-onnx-cpu"


def _vulkan_status() -> dict:
    gguf_dir = resolve_model_dir("qwen3-asr-1.7b-gguf-vulkan")
    gguf_files = list(Path(gguf_dir).glob("*.gguf")) if os.path.isdir(gguf_dir) else []
    return {
        "available": bool(gguf_files),
        "model_dir": gguf_dir,
        "gguf_files": [str(path) for path in gguf_files],
        "error": "" if gguf_files else "Qwen3-ASR GGUF/Vulkan model/runtime is not installed",
    }


def _runtime_diagnostics() -> dict:
    torch = _torch_status()
    nvidia = _nvidia_status()
    vulkan = _vulkan_status()
    config = load_app_config().server
    blockers = []
    if config.gpu_required:
        if config.model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b") and not torch.get("cuda_available"):
            blockers.append("pytorch_cuda_unavailable")
        if config.model == "qwen3-asr-1.7b-gguf-vulkan" and not vulkan.get("available"):
            blockers.append("vulkan_backend_missing")
    return {
        "gpu_required": config.gpu_required,
        "allow_cpu_fallback": config.allow_cpu_fallback,
        "selected_model": config.model,
        "torch": torch,
        "nvidia": nvidia,
        "vulkan": vulkan,
        "blockers": blockers,
        "runtime_ready": not blockers,
    }


def _model_blocking_reason(model: str, exists: bool, diagnostics: dict) -> str:
    if not exists:
        return "model_missing"
    if model == "qwen3-asr-1.7b-gguf-vulkan":
        return "" if diagnostics["vulkan"].get("available") else "vulkan_backend_missing"
    if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b"):
        return "" if diagnostics["torch"].get("cuda_available") else "pytorch_cuda_unavailable"
    config = load_app_config().server
    if config.gpu_required and not config.allow_cpu_fallback:
        return "cpu_only_model_blocked_by_gpu_required"
    return ""


def _build_recommendation(benchmark: dict, diagnostics: dict) -> dict:
    recommended_for: dict[str, list[str]] = {}
    realtime_candidates = []
    quality_candidates = []
    for key, result in benchmark.items():
        normalized = _normalize_benchmark(result)
        model = normalized.get("model", key.split("::", 1)[0])
        if not normalized.get("ok") or not normalized.get("actual_gpu"):
            continue
        seconds = float(normalized.get("inference_seconds") or normalized.get("recognition_seconds") or 9999)
        realtime_candidates.append((seconds, model, key))
        if model.startswith("qwen3-asr"):
            quality_candidates.append((seconds, model, key))

    realtime = min(realtime_candidates, default=None)
    quality = min(quality_candidates, default=None)
    if realtime:
        recommended_for.setdefault(realtime[1], []).append("realtime")
    if quality:
        recommended_for.setdefault(quality[1], []).append("quality")
    return {
        "status": "ok" if realtime else "blocked",
        "realtime_model": realtime[1] if realtime else "",
        "quality_model": quality[1] if quality else "",
        "recommended_for": recommended_for,
        "reason": "GPU benchmark result found" if realtime else "No installed model has a successful GPU benchmark yet",
        "diagnostics": diagnostics,
    }


def _benchmark_acceleration(model: str, gpu: bool, gpu_backend: str) -> str:
    if not gpu:
        return "cpu"
    if model == "qwen3-asr-1.7b-gguf-vulkan":
        return "gguf-vulkan"
    if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b"):
        return "pytorch-cuda"
    if gpu_backend in ("vulkan", "dml", "cuda"):
        return f"sherpa-onnx-{gpu_backend}"
    return "sherpa-onnx-cpu"


def _actual_gpu_used(status: str, acceleration: str, torch_status: dict) -> bool:
    if status != "ok":
        return False
    if acceleration in {"cuda", "pytorch-cuda"}:
        return bool(torch_status.get("cuda_available"))
    return acceleration in {"vulkan", "dml", "gguf-vulkan", "sherpa-onnx-vulkan", "sherpa-onnx-dml", "sherpa-onnx-cuda"}


def _torch_status() -> dict:
    status = {"available": False, "version": "", "cuda_available": False, "cuda_version": None, "device": "", "error": ""}
    try:
        import torch
        status["available"] = True
        status["version"] = getattr(torch, "__version__", "")
        status["cuda_version"] = getattr(torch.version, "cuda", None)
        status["cuda_available"] = bool(torch.cuda.is_available())
        if status["cuda_available"]:
            status["device"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        status["error"] = str(exc)
    return status


def _nvidia_status() -> dict:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        ).strip()
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if not output:
        return {"available": False, "gpus": []}
    gpus = []
    for line in output.splitlines():
        parts = line.split(",")
        gpus.append({
            "name": parts[0].strip() if len(parts) > 0 else "",
            "memory_total_mb": int(parts[1].strip()) if len(parts) > 1 and parts[1].strip().isdigit() else None,
            "driver_version": parts[2].strip() if len(parts) > 2 else "",
        })
    first = gpus[0] if gpus else {}
    return {
        "available": True,
        "name": first.get("name", ""),
        "memory_total_mb": first.get("memory_total_mb"),
        "driver_version": first.get("driver_version", ""),
        "gpus": gpus,
    }


def _memory_gb() -> float | None:
    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        return None


def _normalize_benchmark(result: dict) -> dict:
    status = result.get("status", "")
    load_seconds = result.get("load_seconds")
    inference_seconds = result.get("inference_seconds", result.get("infer_seconds"))
    load_value = float(load_seconds or 0)
    inference_value = float(inference_seconds or 0)
    torch_status = result.get("torch") or {}
    acceleration = result.get("acceleration") or ""
    actual_gpu = bool(result.get("actual_gpu", _actual_gpu_used(status, acceleration, torch_status)))
    return {
        **result,
        "exists": status != "missing",
        "ok": status == "ok",
        "loading_seconds": result.get("load_seconds"),
        "inference_seconds": inference_seconds,
        "infer_seconds": inference_seconds,
        "recognition_seconds": inference_seconds,
        "total": round(load_value + inference_value, 2),
        "total_seconds": round(load_value + inference_value, 2),
        "cuda_available": torch_status.get("cuda_available", False),
        "actual_gpu": actual_gpu,
        "text": result.get("text", ""),
        "updated_at": result.get("timestamp"),
        "error": result.get("error") or (status if status and status != "ok" else ""),
    }


def _save_benchmark_result(result: dict) -> dict:
    result = _normalize_benchmark(result)
    benchmark = _load_model_benchmark()
    key = result.get("benchmark_id") or f"{result['model']}::{result.get('acceleration') or 'default'}"
    benchmark[key] = result
    existing = benchmark.get(result["model"])
    if not existing or _benchmark_rank(result) >= _benchmark_rank(existing):
        benchmark[result["model"]] = result
    _save_model_benchmark(benchmark)
    return result


def _benchmark_rank(result: dict) -> tuple:
    normalized = _normalize_benchmark(result)
    seconds = float(normalized.get("recognition_seconds") or normalized.get("inference_seconds") or 9999)
    status_rank = 0
    if normalized.get("ok") and normalized.get("actual_gpu"):
        status_rank = 4
    elif normalized.get("ok"):
        status_rank = 3
    elif normalized.get("exists"):
        status_rank = 2
    return (status_rank, -seconds, float(normalized.get("updated_at") or 0))


def _hotword_path(name: str) -> str:
    allowed = {"hot-zh.txt", "hot-en.txt", "hot-rule.txt"}
    if name not in allowed:
        raise HTTPException(status_code=404, detail="Unsupported hotword file")
    return os.path.join(BASE_DIR, name)


@app.get("/api/status")
async def get_status():
    server = ProcessManager.check_server_health()
    client = ProcessManager.check_client_health()
    return {"server": server, "client": client}


@app.get("/api/health")
async def get_health():
    config = load_app_config()
    server = ProcessManager.check_server_health()
    client = ProcessManager.check_client_health()
    selected_model = next((m for m in _model_entries() if m["id"] == config.server.model), None)
    diagnostics = _runtime_diagnostics()
    log_files = sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")), key=os.path.getmtime) if os.path.isdir(LOGS_DIR) else []
    recent_lines = []
    for path in log_files[-5:]:
        for line in _tail_file(path, 40):
            if _line_is_recent_issue(line):
                recent_lines.append({"file": os.path.basename(path), "line": line.strip()})
    return {
        "ok": (server["running"] or client["running"]) and diagnostics["runtime_ready"],
        "server": server,
        "client": client,
        "model": selected_model,
        "diagnostics": diagnostics,
        "config_file": APP_CONFIG_FILE,
        "recent_issues": recent_lines[-30:],
    }


@app.get("/api/config")
async def get_config():
    return app_config_to_dict(load_app_config())


@app.put("/api/config")
async def put_config(req: ConfigUpdateRequest):
    values = req.model_dump(exclude_none=True)
    if "server" in values and "model" in values["server"] and "model_dir" not in values["server"]:
        values["server"]["model_dir"] = ""
    config = update_app_config(values)
    return {"status": "saved", "config": app_config_to_dict(config)}


def _audio_device_recommendation(name: str, host_api: str, is_default: bool, sample_rate: int) -> tuple[bool, str]:
    return input_device_recommendation(name, host_api, is_default, sample_rate)


def _pyaudio_host_api(audio: Any, host_api_index: int) -> str:
    try:
        return str(audio.get_host_api_info_by_index(host_api_index).get("name") or "")
    except Exception:
        return ""


def _pyaudio_default_input_index(audio: Any) -> int:
    try:
        return int(audio.get_default_input_device_info().get("index", -1))
    except Exception:
        return -1


def _pyaudio_input_devices(audio: Any, selected_config: ClientConfig | None = None) -> list[dict]:
    devices = []
    default_index = _pyaudio_default_input_index(audio)
    for index in range(audio.get_device_count()):
        info = audio.get_device_info_by_index(index)
        max_channels = int(info.get("maxInputChannels", 0) or 0)
        if max_channels <= 0:
            continue
        name = str(info.get("name", ""))
        host_api_index = int(info.get("hostApi", -1)) if info.get("hostApi", -1) is not None else -1
        host_api = _pyaudio_host_api(audio, host_api_index)
        sample_rate = int(float(info.get("defaultSampleRate", 0) or 0))
        is_default = index == default_index
        recommended, reason = _audio_device_recommendation(name, host_api, is_default, sample_rate)
        selected = False
        if selected_config:
            selected = device_matches_selection(
                {
                    "index": index,
                    "name": name,
                    "host_api": host_api,
                    "default_sample_rate": sample_rate,
                },
                selected_config.input_device_index,
                selected_config.input_device_name,
                selected_config.input_device_host_api,
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


def _collect_audio_input_devices() -> dict:
    config = load_app_config().client
    try:
        import pyaudio
    except Exception as exc:
        return {
            "available": False,
            "devices": [],
            "default_index": -1,
            "selected_index": config.input_device_index,
            "selected_name": config.input_device_name,
            "selected_exists": False,
            "recommended_count": 0,
            "error": f"PyAudio unavailable: {exc}",
        }

    audio = pyaudio.PyAudio()
    try:
        default_index = _pyaudio_default_input_index(audio)
        devices = _pyaudio_input_devices(audio, config)
    finally:
        audio.terminate()

    selected_device = next((device for device in devices if device.get("selected")), None)
    selected_resolved_index = (
        best_input_device(
            devices,
            default_index=default_index,
            preferred_name=config.input_device_name,
            preferred_host_api=config.input_device_host_api,
            preferred_sample_rate=config.input_device_sample_rate,
        )
        if config.input_device_name
        else int(selected_device["index"]) if selected_device else None
    )
    selected_exists = config.input_device_index < 0 or bool(selected_device) or selected_resolved_index is not None
    smart_default_index = best_input_device(devices, default_index=default_index)
    smart_default = next((device for device in devices if device["index"] == smart_default_index), None)
    recommended_count = len([device for device in devices if device["recommended"] or device["selected"]])
    return {
        "available": True,
        "devices": devices,
        "default_index": default_index,
        "smart_default_index": smart_default_index if smart_default_index is not None else -1,
        "smart_default_name": smart_default.get("name", "") if smart_default else "",
        "selected_index": config.input_device_index,
        "selected_resolved_index": selected_resolved_index if selected_resolved_index is not None else -1,
        "selected_name": config.input_device_name,
        "selected_exists": selected_exists,
        "recommended_count": recommended_count,
        "error": "",
    }


@app.get("/api/audio/input-devices")
async def get_audio_input_devices():
    return _collect_audio_input_devices()


def _record_audio_test(device_index: int, seconds: float) -> dict:
    config = load_app_config().client
    seconds = max(0.5, min(float(seconds or 3.0), 5.0))
    if config.windows_voice_capture_enabled:
        device_name = config.input_device_name
        try:
            import pyaudio

            audio = pyaudio.PyAudio()
            try:
                devices = _pyaudio_input_devices(audio)
                if device_index >= 0:
                    selected = next((device for device in devices if int(device.get("index", -1)) == device_index), None)
                    if selected:
                        device_name = str(selected.get("name") or device_name)
            finally:
                audio.terminate()
        except Exception:
            pass
        try:
            probe = _run_windows_voice_probe(AudioFormatProbeRequest(
                seconds=seconds,
                device_index=device_index,
                device_name=device_name,
                run_asr=False,
            ))
            from scripts.mic_format_probe import read_wav_pcm

            normalized_audio, sample_rate, channels = read_wav_pcm(Path(str(probe["file"]["path"])))
            level = dict(probe["file"].get("audio_level") or {})
            helper = probe.get("helper") if isinstance(probe.get("helper"), dict) else {}
            helper_device = helper.get("device") if isinstance(helper.get("device"), dict) else {}
            wav_data = Path(str(probe["file"]["path"])).read_bytes()
            return {
                "ok": True,
                "message": quality_message(level),
                "has_signal": bool(level.get("has_signal")),
                "capture_backend": "windows_mediacapture",
                "device_index": device_index,
                "device_name": str(helper_device.get("name") or device_name or ""),
                "host_api": "Windows MediaCapture",
                "capture_host_api": "Windows MediaCapture",
                "sample_rate": sample_rate,
                "seconds": seconds,
                "capture_channels": channels,
                "normalized_channels": channels,
                "normalized_strategy": "windows_mediacapture",
                "normalized_channel_index": 0,
                "channel_analysis": [],
                "stereo_correlation": None,
                "source_audio_level": level,
                "processed_audio_level": level,
                "input_output_gain_ratio": 1.0,
                "gain_db": 0.0,
                "volume_policy": "windows_mediacapture_default_processing",
                "auto_gain_enabled": False,
                "windows_voice_capture_enabled": True,
                "windows_voice_capture": {
                    "media_category": probe.get("recording", {}).get("media_category", "VoiceTyping"),
                    "audio_processing": probe.get("recording", {}).get("audio_processing", "Default"),
                },
                "quality_state": level.get("quality_state"),
                "audio_wav_base64": base64.b64encode(wav_data).decode("ascii"),
                "normalized_audio": normalized_audio,
                **level,
            }
        except Exception as exc:
            logger.warning("Windows voice capture test failed, falling back to PyAudio/WASAPI: %s", exc)

    try:
        import pyaudio
    except Exception as exc:
        return {"ok": False, "message": f"PyAudio unavailable: {exc}", "has_signal": False}

    audio = pyaudio.PyAudio()
    try:
        if device_index < 0:
            devices = _pyaudio_input_devices(audio)
            best_index = best_input_device(devices, default_index=_pyaudio_default_input_index(audio))
            device_index = best_index if best_index is not None else -1
        capture = capture_input_once(
            audio,
            pyaudio,
            None if device_index < 0 else device_index,
            seconds=seconds,
            preferred_sample_rate=0,
            configured_sample_rate=48000,
            preferred_channels=2,
            auto_gain_enabled=config.auto_gain_enabled,
            logger=logger,
        )
        level = capture["audio_level"]
        wav_data = wav_bytes_from_pcm16(
            capture["normalized_audio"],
            int(capture["sample_rate"]),
            int(capture.get("normalized_channels") or 1),
        )
        return {
            "ok": True,
            "message": capture["message"],
            "has_signal": level["has_signal"],
            "capture_backend": "pyaudio_wasapi",
            "device_index": capture.get("device_index"),
            "device_name": capture.get("device_name", ""),
            "host_api": capture.get("host_api", ""),
            "capture_host_api": capture.get("host_api", ""),
            "sample_rate": capture.get("sample_rate"),
            "seconds": seconds,
            "capture_channels": capture.get("capture_channels"),
            "normalized_channels": capture.get("normalized_channels"),
            "normalized_strategy": capture.get("normalized_strategy"),
            "normalized_channel_index": capture.get("normalized_channel_index"),
            "channel_analysis": capture.get("channel_analysis", []),
            "stereo_correlation": capture.get("stereo_correlation"),
            "source_audio_level": capture.get("source_audio_level", {}),
            "processed_audio_level": capture.get("processed_audio_level", {}),
            "input_output_gain_ratio": capture.get("input_output_gain_ratio", 1.0),
            "gain_db": capture.get("gain_db", 0.0),
            "volume_policy": capture.get("volume_policy", "passthrough_no_gain"),
            "auto_gain_enabled": config.auto_gain_enabled,
            "quality_state": capture.get("quality_state"),
            "audio_wav_base64": base64.b64encode(wav_data).decode("ascii"),
            "normalized_audio": capture.get("normalized_audio", b""),
            **level,
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": f"打开或读取麦克风失败：{exc}",
            "has_signal": False,
            "device_index": device_index,
        }
    finally:
        audio.terminate()


async def _recognize_audio_preview(audio_data: bytes, sample_rate: int) -> dict:
    if not audio_data:
        return {"ok": False, "text": "", "error": "empty audio"}
    config = load_app_config().server
    uri = f"ws://127.0.0.1:{config.port}"
    task_id = f"preview-{int(time.time() * 1000)}"
    try:
        async with ws_lib.connect(uri, max_size=None, open_timeout=20, ping_interval=20, ping_timeout=10) as websocket:
            await websocket.send(json.dumps({
                "type": "audio_start",
                "task_id": task_id,
                "sample_rate": int(sample_rate),
            }, ensure_ascii=False))
            await websocket.send(audio_data)
            await websocket.send(json.dumps({
                "type": "audio_end",
                "task_id": task_id,
                "sample_rate": int(sample_rate),
            }, ensure_ascii=False))
            response = await asyncio.wait_for(websocket.recv(), timeout=90)
    except Exception as exc:
        return {"ok": False, "text": "", "error": str(exc)}
    try:
        data = json.loads(response)
    except json.JSONDecodeError:
        return {"ok": False, "text": "", "error": "invalid recognition response"}
    text = str(data.get("text") or "").strip()
    return {
        "ok": bool(text),
        "text": text,
        "error": str(data.get("error") or ""),
        "model": str(data.get("model") or ""),
    }


@app.post("/api/audio/test-input")
async def test_audio_input(req: AudioTestRequest):
    result = await asyncio.to_thread(_record_audio_test, req.device_index, req.seconds)
    normalized_audio = result.pop("normalized_audio", b"")
    if result.get("ok") and normalized_audio:
        recognition = await _recognize_audio_preview(normalized_audio, int(result.get("sample_rate") or 48000))
        result["recognized_text"] = recognition.get("text", "")
        result["recognition_ok"] = recognition.get("ok", False)
        result["recognition_error"] = recognition.get("error", "")
        result["recognition_model"] = recognition.get("model", "")
        if recognition.get("ok") and str(result.get("quality_state") or "") == "ok":
            remember_capture_profile({
                "device_name": result.get("device_name", ""),
                "host_api": result.get("capture_host_api", ""),
                "sample_rate": result.get("sample_rate", 0),
                "capture_channels": result.get("capture_channels", 1),
                "normalized_strategy": result.get("normalized_strategy", "mono"),
                "normalized_channel_index": result.get("normalized_channel_index", -1),
                "quality_state": result.get("quality_state", ""),
                "recognized_text": recognition.get("text", ""),
            }, reason="api_test_input")
    return result


def _safe_probe_output_path(run_id: str, filename: str) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise HTTPException(status_code=400, detail="Invalid probe id")
    clean_name = Path(filename).name
    if clean_name != filename or not clean_name.lower().endswith(".wav"):
        raise HTTPException(status_code=400, detail="Invalid probe file")
    from scripts.mic_format_probe import OUTPUT_ROOT

    root = OUTPUT_ROOT.resolve()
    target = (root / run_id / clean_name).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid probe path")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Probe audio not found")
    return target


def _probe_file_url(run_id: str, path: Path) -> str:
    return f"/api/audio/format-probe/{run_id}/{path.name}"


def _run_audio_format_probe_recording(req: AudioFormatProbeRequest) -> dict:
    from scripts.mic_format_probe import OUTPUT_ROOT, audio_metrics, build_outputs, record_raw, select_device

    seconds = max(0.5, min(float(req.seconds or 5.0), 20.0))
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    args = argparse.Namespace(
        seconds=seconds,
        device_index=int(req.device_index) if req.device_index is not None and int(req.device_index) >= 0 else None,
        device_name=req.device_name or "",
        output_dir=str(output_dir),
        no_asr=not req.run_asr,
    )
    device_index, device_info = select_device(args)
    raw_audio, sample_rate, channels = record_raw(device_index, device_info, seconds)
    outputs = build_outputs(raw_audio, sample_rate, channels, output_dir)
    files = {}
    for key, path in outputs.items():
        row = audio_metrics(path)
        row["filename"] = path.name
        row["url"] = _probe_file_url(run_id, path)
        files[key] = row

    server_config = load_app_config().server
    return {
        "ok": True,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "device": {
            "index": device_index,
            "name": str(device_info.get("name") or ""),
            "host_api": str(device_info.get("host_api") or ""),
            "default_sample_rate": int(float(device_info.get("defaultSampleRate", 0) or 0)),
            "max_input_channels": int(device_info.get("maxInputChannels", 0) or 0),
        },
        "recording": {
            "requested_seconds": seconds,
            "sample_rate": sample_rate,
            "channels": channels,
            "format": "PCM16/int16",
            "auto_gain": False,
            "noise_reduction": False,
            "compression": False,
        },
        "files": files,
        "asr": {
            "model": server_config.model,
            "service": f"ws://127.0.0.1:{server_config.port}",
            "results": {},
            "skipped": not req.run_asr,
        },
    }


async def _recognize_probe_files(result: dict) -> dict:
    from scripts.mic_format_probe import read_wav_pcm

    if result.get("asr", {}).get("skipped"):
        candidates = {
            key: value
            for key, value in result.get("files", {}).items()
            if key.startswith("minimal_channel") or key == "standard_asr_16k_mono"
        }
        result["asr"]["results"] = {
            key: {"skipped": True, "reason": "用户关闭了 ASR 测试"}
            for key in candidates
        }
        return result

    asr_results = {}
    for key, file_info in result.get("files", {}).items():
        if not (key.startswith("minimal_channel") or key == "standard_asr_16k_mono"):
            continue
        path = Path(str(file_info.get("path") or ""))
        audio_data, sample_rate, _channels = read_wav_pcm(path)
        started = time.time()
        recognition = await _recognize_audio_preview(audio_data, sample_rate)
        asr_results[key] = {
            "text": recognition.get("text", ""),
            "seconds": round(time.time() - started, 3),
            "sample_rate": sample_rate,
            "ok": recognition.get("ok", False),
            "error": recognition.get("error", ""),
            "model": recognition.get("model", ""),
        }
    result["asr"]["results"] = asr_results
    return result


def _write_probe_result_json(result: dict) -> None:
    output_dir = Path(str(result.get("output_dir") or ""))
    if not output_dir:
        return
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_browser_probe_label(value: str, fallback: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "").strip())
    cleaned = cleaned.strip("_")
    return cleaned[:40] or fallback


def _convert_browser_probe_upload(content: bytes, filename: str, label: str, processing: str) -> dict:
    from scripts.mic_format_probe import OUTPUT_ROOT, audio_metrics

    status = ffmpeg_status()
    ffmpeg = status.get("ffmpeg") or ""
    if not ffmpeg:
        raise RuntimeError(status.get("message") or "ffmpeg is not available")

    safe_label = _safe_browser_probe_label(label, "browser")
    safe_processing = _safe_browser_probe_label(processing, "unknown")
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    source_name = f"{safe_label}_{safe_processing}.webm"
    source_path = output_dir / source_name
    wav_path = output_dir / f"{safe_label}_{safe_processing}_16k_mono.wav"
    source_path.write_bytes(content)

    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-sample_fmt",
        "s16",
        str(wav_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "ffmpeg conversion failed").strip())

    metrics = audio_metrics(wav_path)
    metrics["filename"] = wav_path.name
    metrics["url"] = _probe_file_url(run_id, wav_path)
    result = {
        "ok": True,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "source": {
            "filename": filename,
            "stored_filename": source_name,
            "label": safe_label,
            "processing": safe_processing,
            "bytes": len(content),
        },
        "file": metrics,
        "asr": {
            "model": load_app_config().server.model,
            "results": {},
        },
    }
    return result


def _run_windows_voice_probe(req: AudioFormatProbeRequest) -> dict:
    from scripts.mic_format_probe import OUTPUT_ROOT, audio_metrics

    def repair_windows_text(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: repair_windows_text(item) for key, item in value.items()}
        if isinstance(value, list):
            return [repair_windows_text(item) for item in value]
        if not isinstance(value, str):
            return value
        if not any(marker in value for marker in ("é", "å", "è", "\x85", "\x8b", "\x8e")):
            return value
        try:
            repaired = value.encode("latin-1").decode("utf-8")
        except UnicodeError:
            return value
        original_cjk = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
        repaired_cjk = sum(1 for char in repaired if "\u4e00" <= char <= "\u9fff")
        return repaired if repaired_cjk > original_cjk else value

    seconds = max(0.5, min(float(req.seconds or 5.0), 20.0))
    run_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
    output_dir = OUTPUT_ROOT / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    wav_path = output_dir / "windows_voice_capture_16k_mono.wav"
    helper_project = Path(BASE_DIR) / "tools" / "windows_voice_capture" / "VoiceCaptureHelper.csproj"
    helper_dll = (
        Path(BASE_DIR)
        / "tools"
        / "windows_voice_capture"
        / "bin"
        / "x64"
        / "Release"
        / "net10.0-windows10.0.26100.0"
        / "VoiceCaptureHelper.dll"
    )
    if not helper_project.is_file():
        raise RuntimeError(f"Windows voice capture helper is missing: {helper_project}")

    config = load_app_config()
    device_name = req.device_name or config.client.input_device_name
    helper_args = [
        "--seconds",
        str(seconds),
        "--output",
        str(wav_path),
        "--device-name",
        device_name,
        "--category",
        "VoiceTyping",
        "--processing",
        "Default",
    ]
    if helper_dll.is_file():
        command = ["dotnet", str(helper_dll), *helper_args]
    else:
        command = ["dotnet", "run", "--project", str(helper_project), "-c", "Release", "-p:Platform=x64", "--", *helper_args]
    dotnet_home = Path(DATA_DIR) / "dotnet_home"
    dotnet_home.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["DOTNET_CLI_HOME"] = str(dotnet_home)
    env["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1"
    env["DOTNET_NOLOGO"] = "1"
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=max(150, int(seconds) + 120),
        cwd=BASE_DIR,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "Windows voice capture helper failed").strip())
    helper_info: dict[str, Any] = {}
    for line in reversed((completed.stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            helper_info = repair_windows_text(json.loads(line))
            break
        except json.JSONDecodeError:
            continue

    metrics = audio_metrics(wav_path)
    metrics["filename"] = wav_path.name
    metrics["url"] = _probe_file_url(run_id, wav_path)
    result = {
        "ok": True,
        "run_id": run_id,
        "output_dir": str(output_dir),
        "capture_backend": "windows_mediacapture",
        "helper": helper_info,
        "recording": {
            "requested_seconds": seconds,
            "sample_rate": 16000,
            "channels": 1,
            "format": "PCM16/int16",
            "media_category": str(helper_info.get("media_category") or "VoiceTyping"),
            "audio_processing": str(helper_info.get("audio_processing") or "Default"),
        },
        "file": metrics,
        "asr": {
            "model": config.server.model,
            "results": {},
        },
    }
    return result


@app.post("/api/audio/windows-voice-probe")
async def windows_voice_audio_probe(req: AudioFormatProbeRequest):
    try:
        result = await asyncio.to_thread(_run_windows_voice_probe, req)
        from scripts.mic_format_probe import read_wav_pcm

        wav_path = Path(str(result["file"]["path"]))
        audio_data, sample_rate, _channels = await asyncio.to_thread(read_wav_pcm, wav_path)
        started = time.time()
        recognition = await _recognize_audio_preview(audio_data, sample_rate)
        result["asr"]["results"] = {
            "standard_asr_16k_mono": {
                "text": recognition.get("text", ""),
                "seconds": round(time.time() - started, 3),
                "sample_rate": sample_rate,
                "ok": recognition.get("ok", False),
                "error": recognition.get("error", ""),
                "model": recognition.get("model", ""),
            }
        }
        await asyncio.to_thread(_write_probe_result_json, result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("windows voice audio probe failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/audio/browser-probe")
async def browser_audio_probe(
    file: UploadFile = File(...),
    label: str = Form("browser"),
    processing: str = Form("unknown"),
):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio is empty")
    try:
        result = await asyncio.to_thread(_convert_browser_probe_upload, content, file.filename or "recording.webm", label, processing)
        from scripts.mic_format_probe import read_wav_pcm

        wav_path = Path(str(result["file"]["path"]))
        audio_data, sample_rate, _channels = await asyncio.to_thread(read_wav_pcm, wav_path)
        started = time.time()
        recognition = await _recognize_audio_preview(audio_data, sample_rate)
        result["asr"]["results"] = {
            "standard_asr_16k_mono": {
                "text": recognition.get("text", ""),
                "seconds": round(time.time() - started, 3),
                "sample_rate": sample_rate,
                "ok": recognition.get("ok", False),
                "error": recognition.get("error", ""),
                "model": recognition.get("model", ""),
            }
        }
        await asyncio.to_thread(_write_probe_result_json, result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("browser audio probe failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/audio/format-probe")
async def audio_format_probe(req: AudioFormatProbeRequest):
    try:
        result = await asyncio.to_thread(_run_audio_format_probe_recording, req)
        result = await _recognize_probe_files(result)
        await asyncio.to_thread(_write_probe_result_json, result)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("audio format probe failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/audio/format-probe/{run_id}/{filename}")
async def get_audio_format_probe_file(run_id: str, filename: str):
    target = _safe_probe_output_path(run_id, filename)
    return FileResponse(str(target), media_type="audio/wav", filename=target.name)


def _capture_device_level(audio: Any, pyaudio_module: Any, device: dict, seconds: float, waveform_points: int) -> dict:
    try:
        config = load_app_config().client
        capture = capture_input_once(
            audio,
            pyaudio_module,
            int(device["index"]),
            seconds=seconds,
            preferred_sample_rate=int(device.get("default_sample_rate") or 0),
            configured_sample_rate=48000,
            preferred_channels=2,
            waveform_points=waveform_points,
            auto_gain_enabled=config.auto_gain_enabled,
            logger=None,
        )
        return {
            **device,
            **capture["audio_level"],
            "ok": True,
            "message": capture["message"],
            "sample_rate": capture.get("sample_rate"),
            "capture_host_api": capture.get("host_api", ""),
            "capture_channels": capture.get("capture_channels"),
            "normalized_channels": capture.get("normalized_channels"),
            "normalized_strategy": capture.get("normalized_strategy"),
            "normalized_channel_index": capture.get("normalized_channel_index"),
            "channel_analysis": capture.get("channel_analysis", []),
            "stereo_correlation": capture.get("stereo_correlation"),
            "source_audio_level": capture.get("source_audio_level", {}),
            "processed_audio_level": capture.get("processed_audio_level", {}),
            "input_output_gain_ratio": capture.get("input_output_gain_ratio", 1.0),
            "gain_db": capture.get("gain_db", 0.0),
            "volume_policy": capture.get("volume_policy", "passthrough_no_gain"),
            "auto_gain_enabled": config.auto_gain_enabled,
            "quality_state": capture.get("quality_state", ""),
            "waveform": capture.get("waveform") or [],
        }
    except Exception as exc:
        return {
            **device,
            "ok": False,
            "message": f"打开失败：{exc}",
            "has_signal": False,
            "rms": 0.0,
            "peak": 0,
            "rms_ratio": 0.0,
            "peak_ratio": 0.0,
            "quality_state": "too_quiet",
            "waveform": [0.0] * waveform_points,
        }


def _scan_audio_levels(seconds: float, include_all: bool, waveform_points: int) -> dict:
    try:
        import pyaudio
    except Exception as exc:
        return {
            "available": False,
            "devices": [],
            "error": f"PyAudio unavailable: {exc}",
        }

    inventory = _collect_audio_input_devices()
    devices = inventory.get("devices", [])
    if not include_all:
        devices = [device for device in devices if device.get("recommended") or device.get("selected") or device.get("is_default")]

    seconds = max(0.08, min(float(seconds or 0.25), 0.8))
    waveform_points = max(16, min(int(waveform_points or 64), 128))
    audio = pyaudio.PyAudio()
    started = time.time()
    try:
        rows = [
            _capture_device_level(audio, pyaudio, device, seconds, waveform_points)
            for device in devices
        ]
    finally:
        audio.terminate()

    return {
        "available": True,
        "devices": rows,
        "seconds": seconds,
        "waveform_points": waveform_points,
        "elapsed_seconds": round(time.time() - started, 3),
        "detected_count": len([device for device in rows if device.get("has_signal")]),
        "strongest": max(rows, key=lambda item: item.get("rms_ratio", 0.0), default=None),
        "error": "",
    }


@app.post("/api/audio/scan-levels")
async def scan_audio_levels(req: AudioScanRequest):
    return await asyncio.to_thread(_scan_audio_levels, req.seconds, req.include_all, req.waveform_points)


@app.get("/api/models")
async def get_models():
    config = load_app_config()
    return {
        "models": _model_entries(),
        "selected": config.server.model,
        "models_dir": MODELS_DIR,
        "model_roots": model_root_candidates(),
    }


@app.get("/api/models/{model_id}/download-modelscope")
async def get_modelscope_download(model_id: str):
    if model_id not in MODEL_DIR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown model")
    job = model_download_jobs.get(model_id)
    if job:
        return _public_model_download_job(job)
    target = _safe_model_target(model_id)
    return {
        "model": model_id,
        "modelscope_id": MODEL_MODELSCOPE_IDS.get(model_id, ""),
        "status": "installed" if target.exists() else "idle",
        "target_dir": str(target),
        "log_path": "",
        "message": "已安装" if target.exists() else "",
        "error": "",
    }


@app.post("/api/models/{model_id}/download-modelscope")
async def start_modelscope_download(model_id: str):
    if model_id not in MODEL_DIR_NAMES:
        raise HTTPException(status_code=404, detail="Unknown model")
    modelscope_id = MODEL_MODELSCOPE_IDS.get(model_id, "")
    if not modelscope_id:
        raise HTTPException(status_code=400, detail="This model has no ModelScope download mapping")

    existing = model_download_jobs.get(model_id)
    if existing and existing.get("status") == "running":
        return _public_model_download_job(existing)

    target = _safe_model_target(model_id)
    if target.exists() and any(target.iterdir()):
        job = {
            "model": model_id,
            "modelscope_id": modelscope_id,
            "status": "installed",
            "target_dir": str(target),
            "message": "模型目录已存在",
        }
        model_download_jobs[model_id] = job
        return _public_model_download_job(job)

    job = {
        "model": model_id,
        "modelscope_id": modelscope_id,
        "status": "running",
        "target_dir": str(target),
        "log_path": str(Path(LOGS_DIR, f"model_download_{model_id}.log")),
        "started_at": time.time(),
        "message": "下载任务已启动",
        "error": "",
    }
    model_download_jobs[model_id] = job
    asyncio.create_task(asyncio.to_thread(_run_modelscope_download, model_id, job))
    return _public_model_download_job(job)


@app.post("/api/models/{model_id}/open-folder")
async def open_model_folder(model_id: str):
    model_path = _safe_model_target(model_id)
    target = model_path if model_path.exists() else model_path.parent
    target.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open folder: {exc}") from exc
    return {"status": "opened", "path": str(target)}


@app.get("/api/runtime/diagnostics")
async def get_runtime_diagnostics():
    return _runtime_diagnostics()


@app.get("/api/hardware")
async def get_hardware():
    diagnostics = _runtime_diagnostics()
    torch = diagnostics["torch"]
    nvidia = diagnostics["nvidia"]
    recommendation = "检测到 NVIDIA GPU，但当前 PyTorch CUDA 不可用；Qwen safetensors 会走 CPU，延迟会明显偏高。"
    if torch["cuda_available"]:
        recommendation = "PyTorch CUDA 可用，可以继续测试 Qwen CUDA 推理耗时。"
    elif not nvidia.get("available"):
        recommendation = "未检测到 NVIDIA GPU，建议使用低延迟模型作为日用候选。"
    return {
        "cpu": os.environ.get("PROCESSOR_IDENTIFIER", ""),
        "memory_gb": _memory_gb(),
        "nvidia_gpu": bool(nvidia.get("available")),
        "gpus": nvidia.get("gpus", []),
        "torch": torch,
        "nvidia": nvidia,
        "vulkan": diagnostics["vulkan"],
        "gpu_required": diagnostics["gpu_required"],
        "allow_cpu_fallback": diagnostics["allow_cpu_fallback"],
        "blockers": diagnostics["blockers"],
        "runtime_ready": diagnostics["runtime_ready"],
        "recommendation": recommendation,
        "ports": {
            "asr": DEFAULT_ASR_PORT,
            "api": DEFAULT_API_PORT,
            "frontend": DEFAULT_FRONTEND_PORT,
        },
    }


def _default_benchmark_audio() -> str:
    candidates = sorted(Path(r"C:\Program Files\CapsWriter-Offline-Windows-64bit\2026\04\assets").glob("(20260429-200*.mp3"))
    return str(candidates[0]) if candidates else ""


def _decode_audio_for_benchmark(path: str) -> tuple[bytes, int]:
    ffmpeg = ffmpeg_status().get("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not available")
    sample_rate = 16000
    audio = subprocess.check_output(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            path,
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "pipe:1",
        ],
        cwd=BASE_DIR,
    )
    return audio, sample_rate


def _safe_history_path(path_value: str, expect_file: bool = False) -> Path:
    target = Path(path_value or "")
    if not path_value:
        raise HTTPException(status_code=404, detail="Path is empty")
    if expect_file and (not target.exists() or not target.is_file()):
        raise HTTPException(status_code=404, detail="History file not found")
    if not expect_file and (not target.exists() or not target.is_dir()):
        raise HTTPException(status_code=404, detail="History folder not found")

    config = load_app_config().client
    allowed_roots = [
        Path(path).resolve()
        for path in (config.archive_root, config.audio_dir, str(Path(BASE_DIR, "data")))
        if path
    ]
    resolved = target.resolve()
    if not any(resolved == root or root in resolved.parents for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Path is outside VoiceType data directories")
    return resolved


def _open_path_in_shell(target: Path):
    try:
        if sys.platform == "win32":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to open path: {exc}") from exc
    return {"status": "opened", "path": str(target)}


def _run_model_benchmark(model: str, audio_file: str, persist: bool = True, acceleration: Optional[str] = None) -> dict:
    model_dir = resolve_model_dir(model)
    config = load_app_config().server
    acceleration = acceleration or _benchmark_acceleration(model, config.gpu, config.gpu_backend)
    bench_gpu = acceleration not in ("cpu", "pytorch-cpu", "sherpa-onnx-cpu")
    bench_backend = config.gpu_backend
    if acceleration in ("gguf-vulkan", "sherpa-onnx-vulkan"):
        bench_backend = "vulkan"
    elif acceleration == "sherpa-onnx-dml":
        bench_backend = "dml"
    elif acceleration in ("pytorch-cuda", "sherpa-onnx-cuda"):
        bench_backend = "cuda"
    bench_gpu_required = bench_gpu and not config.allow_cpu_fallback
    torch_status = _torch_status()
    base_result = {
        "benchmark_id": f"{model}::{acceleration}",
        "model": model,
        "backend": _expected_model_backend(model),
        "acceleration": acceleration,
        "actual_gpu": False,
        "model_dir": model_dir,
        "audio_file": audio_file,
        "load_seconds": None,
        "inference_seconds": None,
        "text": "",
        "torch": torch_status,
        "timestamp": time.time(),
    }
    if not os.path.isdir(model_dir):
        result = {
            **base_result,
            "status": "missing",
            "error": "model directory is not installed",
        }
        return _save_benchmark_result(result) if persist else _normalize_benchmark(result)
    if not audio_file or not os.path.exists(audio_file):
        result = {
            **base_result,
            "status": "missing_audio",
            "error": "benchmark audio file is not available",
        }
        return _save_benchmark_result(result) if persist else _normalize_benchmark(result)

    started = time.time()
    engine = ASREngine(
        model=model,
        model_dir=model_dir,
        gpu=bench_gpu,
        gpu_backend=bench_backend,
        gpu_required=bench_gpu_required,
        allow_cpu_fallback=config.allow_cpu_fallback,
    )
    if not engine.initialize():
        result = {
            **base_result,
            "status": "init_failed",
            "load_seconds": round(time.time() - started, 2),
            "timestamp": time.time(),
            "error": engine.last_error or "ASR engine initialization failed",
        }
        return _save_benchmark_result(result) if persist else _normalize_benchmark(result)
    load_seconds = time.time() - started

    try:
        audio, sample_rate = _decode_audio_for_benchmark(audio_file)
    except Exception as exc:
        result = {
            **base_result,
            "status": "decode_failed",
            "backend": engine.backend or base_result["backend"],
            "load_seconds": round(load_seconds, 2),
            "timestamp": time.time(),
            "error": str(exc),
        }
        return _save_benchmark_result(result) if persist else _normalize_benchmark(result)

    infer_started = time.time()
    try:
        text = engine.recognize(audio, sample_rate=sample_rate) or ""
    except Exception as exc:
        result = {
            **base_result,
            "status": "infer_failed",
            "backend": engine.backend or base_result["backend"],
            "load_seconds": round(load_seconds, 2),
            "inference_seconds": round(time.time() - infer_started, 2),
            "timestamp": time.time(),
            "error": str(exc),
        }
        return _save_benchmark_result(result) if persist else _normalize_benchmark(result)
    infer_seconds = time.time() - infer_started
    status = "ok" if text else "empty"
    torch_status = _torch_status()
    result = {
        **base_result,
        "status": status,
        "backend": engine.backend,
        "acceleration": engine.acceleration or acceleration,
        "load_seconds": round(load_seconds, 2),
        "inference_seconds": round(infer_seconds, 2),
        "text": text,
        "torch": torch_status,
        "actual_gpu": engine.using_gpu,
        "timestamp": time.time(),
    }
    return _save_benchmark_result(result) if persist else _normalize_benchmark(result)


def _benchmark_models(models: Optional[list[str]] = None, audio_file: Optional[str] = None) -> dict:
    selected_models = models or list(MODEL_DIR_NAMES.keys())
    benchmark_audio = audio_file or _default_benchmark_audio()
    results = []
    for model in selected_models:
        if model not in MODEL_DIR_NAMES:
            result = {
                "model": model,
                "backend": "",
                "acceleration": "",
                "actual_gpu": False,
                "model_dir": "",
                "audio_file": benchmark_audio,
                "load_seconds": None,
                "inference_seconds": None,
                "text": "",
                "torch": _torch_status(),
                "status": "unknown_model",
                "timestamp": time.time(),
                "error": "model is not configured",
            }
            results.append(_save_benchmark_result(result))
            continue
        for acceleration in _benchmark_plan_for_model(model):
            results.append(_run_model_benchmark(model, benchmark_audio, acceleration=acceleration))
    return {
        "audio_file": benchmark_audio,
        "benchmark_file": _benchmark_path(),
        "results": results,
    }


def _benchmark_plan_for_model(model: str) -> list[str]:
    if model in ("qwen3-asr-0.6b", "qwen3-asr-1.7b"):
        return ["pytorch-cpu", "pytorch-cuda"]
    if model == "qwen3-asr-1.7b-gguf-vulkan":
        return ["gguf-vulkan"]
    if model in ("paraformer", "sensevoice"):
        return ["sherpa-onnx-cpu", "sherpa-onnx-cuda"]
    if model == "funasr-nano":
        return ["sherpa-onnx-cpu", "sherpa-onnx-dml", "sherpa-onnx-vulkan"]
    return [_default_acceleration_for_model(model)]


@app.get("/api/models/benchmark")
async def get_model_benchmark():
    return {"benchmarks": _load_model_benchmark()}


@app.get("/api/models/recommendation")
async def get_model_recommendation():
    return _build_recommendation(_load_model_benchmark(), _runtime_diagnostics())


@app.post("/api/models/benchmark")
async def post_model_benchmark(req: ModelBenchmarkRequest):
    if req.all:
        return await asyncio.to_thread(_benchmark_models, req.models, req.audio_file)
    model = req.model or load_app_config().server.model
    audio_file = req.audio_file or _default_benchmark_audio()
    return await asyncio.to_thread(_run_model_benchmark, model, audio_file, True, req.acceleration)


@app.post("/api/models/benchmark-all")
async def post_model_benchmark_all(req: ModelBenchmarkRequest):
    return await asyncio.to_thread(_benchmark_models, req.models, req.audio_file)


@app.post("/api/models/apply-recommendation")
async def apply_model_recommendation():
    recommendation = _build_recommendation(_load_model_benchmark(), _runtime_diagnostics())
    model = recommendation.get("realtime_model")
    if not model:
        raise HTTPException(status_code=409, detail=recommendation.get("reason") or "No GPU recommendation available")
    config = load_app_config()
    config.server.model = model
    config.server.model_dir = ""
    config.server.__post_init__()
    save_app_config(config)
    return {"status": "applied", "model": model, "config": app_config_to_dict(config)}


@app.post("/api/models/select")
async def select_model(req: ModelSelectRequest):
    config = load_app_config()
    config.server.model = req.model
    config.server.model_dir = req.model_dir or ""
    config.server.__post_init__()
    save_app_config(config)
    return {"status": "selected", "config": app_config_to_dict(config)}


def _launch_transcription_task(task_id: str):
    config = load_app_config().server
    transcriptions.run_task(
        task_id=task_id,
        default_model=config.model,
        default_model_dir=config.model_dir,
        gpu=config.gpu,
        gpu_backend=config.gpu_backend,
    )


@app.get("/api/ffmpeg/status")
async def get_ffmpeg_status():
    return ffmpeg_status()


@app.get("/api/llm/config")
async def get_llm_config():
    return load_llm_config(mask=True)


@app.put("/api/llm/config")
async def put_llm_config(req: LLMConfigRequest):
    return {"status": "saved", "config": save_llm_config(req.model_dump(exclude_none=True))}


@app.post("/api/transcriptions")
async def create_transcription(req: TranscriptionCreateRequest):
    try:
        task = transcriptions.create_task(req.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asyncio.create_task(asyncio.to_thread(_launch_transcription_task, task["task_id"]))
    return task


@app.post("/api/transcriptions/upload")
async def upload_transcription(
    files: list[UploadFile] = File(...),
    options: str = Form("{}"),
):
    try:
        payload = json.loads(options or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="options must be valid JSON") from exc
    saved_paths = transcriptions.save_uploaded_files(files)
    payload["input_files"] = saved_paths
    try:
        task = transcriptions.create_task(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    asyncio.create_task(asyncio.to_thread(_launch_transcription_task, task["task_id"]))
    return task


@app.get("/api/transcriptions")
async def list_transcriptions():
    return {"tasks": transcriptions.list_tasks()}


@app.get("/api/transcriptions/{task_id}")
async def get_transcription(task_id: str):
    task = transcriptions.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Transcription task not found")
    return task


@app.post("/api/transcriptions/{task_id}/cancel")
async def cancel_transcription(task_id: str):
    try:
        return transcriptions.cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Transcription task not found") from exc


@app.get("/api/transcriptions/{task_id}/outputs")
async def get_transcription_outputs(task_id: str):
    try:
        return {"outputs": transcriptions.outputs(task_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Transcription task not found") from exc


@app.get("/api/logs/recent")
async def get_recent_logs(lines: int = 120):
    lines = max(20, min(lines, 500))
    if not os.path.isdir(LOGS_DIR):
        return {"logs": []}
    log_files = sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")), key=os.path.getmtime)
    logs = []
    for path in log_files[-6:]:
        for line in _tail_file(path, lines):
            logs.append({"file": os.path.basename(path), "line": line.rstrip()})
    return {"logs": logs[-lines:]}


@app.get("/api/hotwords/{name}")
async def get_hotword_file(name: str):
    path = _hotword_path(name)
    content = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    return {"name": name, "content": content}


@app.put("/api/hotwords/{name}")
async def put_hotword_file(name: str, payload: Dict[str, str]):
    path = _hotword_path(name)
    content = payload.get("content", "")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return {"status": "saved", "name": name}


@app.post("/api/reload-hotwords")
async def reload_hotwords():
    config = load_app_config().client
    manager = HotwordManager()
    manager.load(BASE_DIR, config.hotword_files)
    return {
        "status": "validated",
        "files": config.hotword_files,
        "note": "Running client reloads hotword files automatically.",
    }


@app.post("/api/server/start")
async def api_start_server():
    return ProcessManager.start_server()


@app.post("/api/server/stop")
async def api_stop_server():
    return ProcessManager.stop_server()


@app.post("/api/client/start")
async def api_start_client():
    return ProcessManager.start_client()


@app.post("/api/client/stop")
async def api_stop_client():
    return ProcessManager.stop_client()


@app.post("/api/start-all")
async def api_start_all():
    server_result = ProcessManager.start_server()
    wait_result = await ProcessManager.wait_server_ready(timeout_seconds=180)
    if not wait_result.get("ready"):
        return {
            "server": server_result,
            "server_ready": wait_result,
            "client": {"status": "not_started", "message": "Client was not started because ASR is not ready."},
        }
    client_result = ProcessManager.start_client()
    return {"server": server_result, "server_ready": wait_result, "client": client_result}


@app.post("/api/stop-all")
async def api_stop_all():
    server_result = ProcessManager.stop_server()
    client_result = ProcessManager.stop_client()
    return {"server": server_result, "client": client_result}


@app.get("/api/history")
async def get_history(limit: int = 100, offset: int = 0):
    entries = history.get_entries(limit=limit, offset=offset)
    return {"entries": entries, "total": len(entries)}


@app.get("/api/history/{task_id}/audio")
async def get_history_audio(task_id: str):
    entries = history.get_entries(limit=1000)
    entry = next((item for item in entries if item.get("task_id") == task_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    resolved = _safe_history_path(entry.get("audio_path") or "", expect_file=True)
    return FileResponse(str(resolved), media_type="audio/wav", filename=resolved.name)


@app.post("/api/history/open-audio-root")
async def open_history_audio_root():
    root = _safe_history_path(load_app_config().client.archive_root)
    return _open_path_in_shell(root)


@app.post("/api/history/open-result-root")
async def open_history_result_root():
    root = _safe_history_path(load_app_config().client.archive_root)
    return _open_path_in_shell(root)


@app.post("/api/history/{task_id}/open-audio-folder")
async def open_history_audio_folder(task_id: str):
    entries = history.get_entries(limit=1000)
    entry = next((item for item in entries if item.get("task_id") == task_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    resolved = _safe_history_path(entry.get("audio_path") or "", expect_file=True)
    return _open_path_in_shell(resolved.parent)


@app.post("/api/history/{task_id}/open-result-folder")
async def open_history_result_folder(task_id: str):
    entries = history.get_entries(limit=1000)
    entry = next((item for item in entries if item.get("task_id") == task_id), None)
    if not entry:
        raise HTTPException(status_code=404, detail="History entry not found")
    result_path = entry.get("transcript_path") or ""
    if not result_path and entry.get("audio_path"):
        result_path = str(Path(entry["audio_path"]).with_name("result.json"))
    resolved = _safe_history_path(result_path, expect_file=True)
    return _open_path_in_shell(resolved.parent)


@app.post("/api/history/clear")
async def clear_history():
    history.clear_entries()
    return {"status": "cleared"}


@app.delete("/api/history/{task_id}")
async def delete_history_entry(task_id: str):
    deleted = history.delete_entry(task_id)
    return {"status": "deleted" if deleted else "not_found", "task_id": task_id}


@app.post("/api/error-mark")
async def add_error_mark(req: ErrorMarkRequest):
    mark = history.add_error_mark(text=req.text, marked_text=req.marked_text)
    return {"status": "added", "mark": mark}


@app.get("/api/error-marks")
async def get_error_marks():
    return {"marks": history.get_error_marks()}


@app.get("/api/stats")
async def get_stats():
    return history.get_stats()


@app.websocket("/ws/recognition")
async def ws_recognition(websocket: WebSocket):
    await websocket.accept()

    config = load_app_config().server
    asr_url = f"ws://127.0.0.1:{config.port}"

    try:
        while True:
            try:
                caps_ws = await ws_lib.connect(
                    asr_url,
                    max_size=None,
                    ping_interval=20,
                    ping_timeout=10,
                )
                await caps_ws.send(json.dumps({"type": "monitor"}))
                await websocket.send_json({"type": "connected"})
                break
            except Exception:
                await websocket.send_json({"type": "connecting"})
                await asyncio.sleep(2)

        while True:
            try:
                message = await caps_ws.recv()
                data = json.loads(message)
                if data.get("type") == "monitor_ready":
                    await websocket.send_json({"type": "monitor_ready", **data})
                    continue
                if data.get("is_final"):
                    entry = history.add_entry(
                        text=data.get("text", ""),
                        task_id=data.get("task_id", ""),
                        delay=data.get("time_complete", 0) - data.get("time_submit", 0),
                        audio_path=data.get("audio_path", ""),
                        model=data.get("model", ""),
                        transcript_path=data.get("transcript_path", ""),
                        duration_seconds=data.get("duration_seconds"),
                    )
                    await websocket.send_json({"type": "result", **entry})
                else:
                    await websocket.send_json({
                        "type": "partial",
                        "text": data.get("text", ""),
                    })
            except ws_lib.ConnectionClosed:
                await websocket.send_json({"type": "disconnected"})
                break
    except WebSocketDisconnect:
        pass


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(_health_check_loop())


async def _health_check_loop():
    while True:
        await asyncio.sleep(10)
        ProcessManager.auto_restart()


def main():
    config = load_app_config().api

    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--port="):
            config.port = int(arg.split("=", 1)[1])
        elif arg.startswith("--host="):
            config.host = arg.split("=", 1)[1]

    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
