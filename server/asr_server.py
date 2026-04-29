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
from config.settings import ServerConfig
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

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    audio_buffer.extend(message)
                elif isinstance(message, str):
                    try:
                        data = json.loads(message)
                        msg_type = data.get("type", "")

                        if msg_type == "audio_end":
                            time_submit = time.time()
                            result = await self._process_audio(
                                bytes(audio_buffer), task_id, time_start, time_submit
                            )
                            if result:
                                await websocket.send(json.dumps(result, ensure_ascii=False))
                            audio_buffer.clear()
                            task_id = str(uuid.uuid4())
                            time_start = time.time()

                        elif msg_type == "audio_start":
                            audio_buffer.clear()
                            task_id = data.get("task_id", str(uuid.uuid4()))
                            time_start = time.time()

                        elif msg_type == "ping":
                            await websocket.send(json.dumps({"type": "pong"}))

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
            logger.info(f"Client removed: {conn_id} (remaining: {len(self._active_connections)})")

    async def _process_audio(
        self, audio_data: bytes, task_id: str, time_start: float, time_submit: float
    ) -> Optional[dict]:
        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._engine.recognize, audio_data, 16000)

            time_complete = time.time()
            return {
                "task_id": task_id,
                "text": text or "",
                "is_final": True,
                "time_start": time_start,
                "time_submit": time_submit,
                "time_complete": time_complete,
                "model": self._engine.model_name,
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
            }


def main():
    import sys

    config = ServerConfig()

    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            config.model = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            config.port = int(arg.split("=", 1)[1])
        elif arg == "--no-gpu":
            config.gpu = False
        elif arg.startswith("--gpu-backend="):
            config.gpu_backend = arg.split("=", 1)[1]

    server = ASRServer(config)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
