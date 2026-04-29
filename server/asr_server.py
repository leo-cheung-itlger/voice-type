import asyncio
import json
import os
import sys
import time
import uuid
from typing import Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets

from common.logger import setup_logger
from config.settings import ServerConfig, load_app_config
from server.asr_engine import ASREngine

logger = setup_logger("asr_server")


class ASRServer:
    def __init__(self, config: ServerConfig):
        self._config = config
        self._engine = ASREngine(
            model=config.model,
            model_dir=config.model_dir,
            gpu=config.gpu,
            gpu_backend=config.gpu_backend,
        )
        self._active_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._monitor_connections: Dict[str, websockets.WebSocketServerProtocol] = {}
        self._active_tasks: Dict[str, asyncio.Task] = {}

    async def start(self):
        logger.info(f"Initializing ASR engine (model={self._config.model})...")
        if not self._engine.initialize():
            logger.error("Failed to initialize ASR engine, exiting")
            return

        logger.info(f"Starting ASR server on {self._config.host}:{self._config.port}")
        async with websockets.serve(
            self._handler,
            self._config.host,
            self._config.port,
            max_size=None,
            ping_interval=self._config.ping_interval,
            ping_timeout=self._config.ping_timeout,
            max_queue=self._config.max_connections,
        ):
            logger.info(f"ASR server running on ws://{self._config.host}:{self._config.port}")
            await asyncio.Future()

    async def _handler(self, websocket: websockets.WebSocketServerProtocol):
        conn_id = str(uuid.uuid4())[:8]
        self._active_connections[conn_id] = websocket
        logger.info(f"Client connected: {conn_id} (total: {len(self._active_connections)})")

        audio_buffer = bytearray()
        task_id = str(uuid.uuid4())
        time_start = time.time()
        time_submit = 0.0
        audio_path = ""
        sample_rate = 16000
        is_monitor = False

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    if is_monitor:
                        continue
                    audio_buffer.extend(message)
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        if msg_type == "audio_end":
                            if is_monitor:
                                continue
                            audio_path = data.get("audio_path", "")
                            sample_rate = int(data.get("sample_rate", sample_rate) or sample_rate)
                            time_submit = time.time()
                            result = await self._process_audio(
                                bytes(audio_buffer), task_id, time_start, time_submit, audio_path, sample_rate
                            )
                            if result:
                                await websocket.send(json.dumps(result, ensure_ascii=False))
                                await self._broadcast_monitor(result)
                            audio_buffer.clear()
                            task_id = str(uuid.uuid4())
                            time_start = time.time()
                            audio_path = ""
                            sample_rate = 16000

                        elif msg_type == "audio_start":
                            if is_monitor:
                                continue
                            audio_buffer.clear()
                            task_id = data.get("task_id", str(uuid.uuid4()))
                            sample_rate = int(data.get("sample_rate", sample_rate) or sample_rate)
                            time_start = time.time()

                        elif msg_type == "ping":
                            await websocket.send(json.dumps({"type": "pong"}))

                        elif msg_type == "monitor":
                            is_monitor = True
                            self._monitor_connections[conn_id] = websocket
                            await websocket.send(json.dumps({
                                "type": "monitor_ready",
                                "connections": len(self._active_connections),
                            }, ensure_ascii=False))

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON from client {conn_id}")

        except websockets.ConnectionClosedError:
            logger.info(f"Client disconnected (error): {conn_id}")
        except websockets.ConnectionClosedOK:
            logger.info(f"Client disconnected (ok): {conn_id}")
        except Exception as e:
            logger.error(f"Handler error for {conn_id}: {e}")
        finally:
            self._active_connections.pop(conn_id, None)
            self._monitor_connections.pop(conn_id, None)
            logger.info(f"Client removed: {conn_id} (remaining: {len(self._active_connections)})")

    async def _broadcast_monitor(self, result: dict):
        if not self._monitor_connections:
            return

        message = json.dumps({"type": "result", **result}, ensure_ascii=False)
        stale = []
        for conn_id, websocket in self._monitor_connections.items():
            try:
                await websocket.send(message)
            except Exception:
                stale.append(conn_id)

        for conn_id in stale:
            self._monitor_connections.pop(conn_id, None)

    async def _process_audio(
        self,
        audio_data: bytes,
        task_id: str,
        time_start: float,
        time_submit: float,
        audio_path: str = "",
        sample_rate: int = 16000,
    ) -> Optional[dict]:
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._engine.recognize, audio_data, sample_rate)

            time_complete = time.time()
            return {
                "task_id": task_id,
                "text": text or "",
                "is_final": True,
                "time_start": time_start,
                "time_submit": time_submit,
                "time_complete": time_complete,
                "model": self._engine.model_name,
                "audio_path": audio_path,
                "sample_rate": sample_rate,
            }
        except Exception as e:
            logger.error(f"Audio processing failed: {e}")
            return {
                "task_id": task_id,
                "text": "",
                "is_final": True,
                "error": str(e),
                "time_start": time_start,
                "time_submit": time_submit,
                "time_complete": time.time(),
                "audio_path": audio_path,
            }


def main():
    import sys

    config = load_app_config().server

    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            config.model = arg.split("=", 1)[1]
            config.model_dir = ""
            config.__post_init__()
        elif arg.startswith("--model-dir="):
            config.model_dir = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            config.port = int(arg.split("=", 1)[1])
        elif arg.startswith("--host="):
            config.host = arg.split("=", 1)[1]
        elif arg == "--no-gpu":
            config.gpu = False
        elif arg == "--gpu":
            config.gpu = True
        elif arg.startswith("--gpu-backend="):
            config.gpu_backend = arg.split("=", 1)[1]

    server = ASRServer(config)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
