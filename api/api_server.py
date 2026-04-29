import asyncio
import glob
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import websockets as ws_lib

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

history = HistoryManager()
transcriptions = TranscriptionManager()
server_process: Optional[subprocess.Popen] = None
client_process: Optional[subprocess.Popen] = None


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


class ProcessManager:
    @staticmethod
    def _find_python() -> str:
        return sys.executable

    @staticmethod
    def _get_script_path(name: str) -> str:
        return os.path.join(BASE_DIR, name)

    @staticmethod
    def _port_open(host: str, port: int, timeout: float = 0.3) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

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
        ]
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
    def start_server() -> dict:
        global server_process
        if server_process and server_process.poll() is None:
            return {"status": "already_running", "pid": server_process.pid}

        config = load_app_config().server
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
        if server_process and server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
            pid = server_process.pid
            server_process = None
            logger.info(f"Server stopped (PID: {pid})")
            return {"status": "stopped", "pid": pid}
        return {"status": "not_running"}

    @staticmethod
    def start_client() -> dict:
        global client_process
        if client_process and client_process.poll() is None:
            return {"status": "already_running", "pid": client_process.pid}

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
        if client_process and client_process.poll() is None:
            client_process.terminate()
            try:
                client_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                client_process.kill()
            pid = client_process.pid
            client_process = None
            logger.info(f"Client stopped (PID: {pid})")
            return {"status": "stopped", "pid": pid}
        return {"status": "not_running"}

    @staticmethod
    def check_server_health() -> dict:
        config = load_app_config().server
        process_running = server_process is not None and server_process.poll() is None
        port_running = ProcessManager._port_open("127.0.0.1", config.port)
        return {
            "running": process_running or port_running,
            "managed": process_running,
            "port_open": port_running,
            "pid": server_process.pid if process_running else None,
            "port": config.port,
        }

    @staticmethod
    def check_client_health() -> dict:
        if client_process is None:
            return {"running": False, "managed": False, "pid": None}
        running = client_process.poll() is None
        return {"running": running, "managed": running, "pid": client_process.pid if running else None}

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
    for model, dirname in MODEL_DIR_NAMES.items():
        path = resolve_model_dir(model)
        exists = os.path.isdir(path)
        entries.append({
            "id": model,
            "name": dirname,
            "path": path,
            "exists": exists,
        })
    return entries


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
    log_files = sorted(glob.glob(os.path.join(LOGS_DIR, "*.log")), key=os.path.getmtime) if os.path.isdir(LOGS_DIR) else []
    recent_lines = []
    for path in log_files[-5:]:
        for line in _tail_file(path, 40):
            if _line_is_recent_issue(line):
                recent_lines.append({"file": os.path.basename(path), "line": line.strip()})
    return {
        "ok": server["running"] or client["running"],
        "server": server,
        "client": client,
        "model": selected_model,
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


@app.get("/api/models")
async def get_models():
    config = load_app_config()
    return {
        "models": _model_entries(),
        "selected": config.server.model,
        "models_dir": MODELS_DIR,
        "model_roots": model_root_candidates(),
    }


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
    await asyncio.sleep(3)
    client_result = ProcessManager.start_client()
    return {"server": server_result, "client": client_result}


@app.post("/api/stop-all")
async def api_stop_all():
    server_result = ProcessManager.stop_server()
    client_result = ProcessManager.stop_client()
    return {"server": server_result, "client": client_result}


@app.get("/api/history")
async def get_history(limit: int = 100, offset: int = 0):
    entries = history.get_entries(limit=limit, offset=offset)
    return {"entries": entries, "total": len(entries)}


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
    config = APIConfig()

    for i, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--port="):
            config.port = int(arg.split("=", 1)[1])
        elif arg.startswith("--host="):
            config.host = arg.split("=", 1)[1]

    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
