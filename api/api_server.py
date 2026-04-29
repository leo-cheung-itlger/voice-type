import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import websockets as ws_lib

from common.history import HistoryManager
from common.logger import setup_logger
from config.settings import APIConfig, ServerConfig

logger = setup_logger("api_server")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="VoiceType API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

history = HistoryManager()
server_process: Optional[subprocess.Popen] = None
client_process: Optional[subprocess.Popen] = None


class ErrorMarkRequest(BaseModel):
    text: str
    marked_text: str


class ProcessManager:
    @staticmethod
    def _find_python() -> str:
        return sys.executable

    @staticmethod
    def _get_script_path(name: str) -> str:
        return os.path.join(BASE_DIR, name)

    @staticmethod
    def start_server() -> dict:
        global server_process
        if server_process and server_process.poll() is None:
            return {"status": "already_running", "pid": server_process.pid}

        python = ProcessManager._find_python()
        script = ProcessManager._get_script_path("server/asr_server.py")
        server_process = subprocess.Popen(
            [python, script],
            cwd=BASE_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
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
        client_process = subprocess.Popen(
            [python, script],
            cwd=BASE_DIR,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
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
        if server_process is None:
            return {"running": False}
        running = server_process.poll() is None
        return {"running": running, "pid": server_process.pid if running else None}

    @staticmethod
    def check_client_health() -> dict:
        if client_process is None:
            return {"running": False}
        running = client_process.poll() is None
        return {"running": running, "pid": client_process.pid if running else None}

    @staticmethod
    def auto_restart():
        if server_process and server_process.poll() is not None:
            logger.warning("Server process died, auto-restarting...")
            ProcessManager.start_server()

        if client_process and client_process.poll() is not None:
            logger.warning("Client process died, auto-restarting...")
            ProcessManager.start_client()


@app.get("/api/status")
async def get_status():
    server = ProcessManager.check_server_health()
    client = ProcessManager.check_client_health()
    return {"server": server, "client": client}


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

    config = ServerConfig()
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
                await websocket.send_json({"type": "connected"})
                break
            except Exception:
                await websocket.send_json({"type": "connecting"})
                await asyncio.sleep(2)

        while True:
            try:
                message = await caps_ws.recv()
                data = json.loads(message)
                if data.get("is_final"):
                    entry = history.add_entry(
                        text=data.get("text", ""),
                        task_id=data.get("task_id", ""),
                        delay=data.get("time_complete", 0) - data.get("time_submit", 0),
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
