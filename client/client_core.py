import asyncio
import json
import os
import sys
import time
import uuid
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets

from common.hotword import HotwordManager
from common.logger import setup_logger
from config.settings import ClientConfig
from client.output import type_result
from client.recorder import AudioRecorder

logger = setup_logger("client_core")


class VoiceClient:
    def __init__(self, config: ClientConfig):
        self._config = config
        self._recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
        )
        self._hotword = HotwordManager()
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._recording = False
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start(self):
        logger.info("Starting VoiceClient...")

        self._hotword.load(
            hotword_dir=".",
            files=self._config.hotword_files,
        )

        self._running = True

        keyboard_task = asyncio.create_task(self._keyboard_loop())
        ws_task = asyncio.create_task(self._recv_loop())

        await asyncio.gather(keyboard_task, ws_task)

    async def _connect(self) -> bool:
        attempt = 0
        while self._running:
            attempt += 1
            try:
                self._ws = await websockets.connect(
                    f"ws://{self._config.server_host}:{self._config.server_port}",
                    max_size=None,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                )
                logger.info(f"Connected to server (attempt {attempt})")
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
                return True
            except ConnectionRefusedError:
                logger.warning(f"Server not available, retrying... (attempt {attempt})")
            except TimeoutError:
                logger.warning(f"Connection timeout, retrying... (attempt {attempt})")
            except OSError as e:
                logger.warning(f"Connection error: {e}, retrying... (attempt {attempt})")
            except Exception as e:
                logger.error(f"Unexpected connection error: {e}, retrying... (attempt {attempt})")

            delay = min(
                self._config.reconnect_base_delay * (2 ** (min(attempt, 10) - 1)),
                self._config.reconnect_max_delay,
            )
            await asyncio.sleep(delay)

        return False

    async def _heartbeat_loop(self):
        while self._running and self._ws and not self._ws.closed:
            await asyncio.sleep(self._config.heartbeat_interval)
            if self._ws and not self._ws.closed:
                try:
                    pong = await self._ws.ping()
                    await asyncio.wait_for(pong, timeout=10.0)
                except Exception:
                    logger.warning("Heartbeat failed, connection may be lost")
                    try:
                        await self._ws.close()
                    except Exception:
                        pass
                    self._ws = None
                    return

    async def _recv_loop(self):
        while self._running:
            if not self._ws or self._ws.closed:
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None
                if not await self._connect():
                    break

            try:
                message = await self._ws.recv()
                data = json.loads(message)

                if not data.get("is_final"):
                    continue

                text = data.get("text", "")
                if not text:
                    continue

                self._hotword.maybe_reload(self._config.hotword_files)
                text = self._hotword.apply(text)

                await type_result(text, self._config)

                delay = data.get("time_complete", 0) - data.get("time_submit", 0)
                logger.info(f"Result: {text} (delay: {delay:.2f}s)")

            except websockets.ConnectionClosedError:
                logger.warning("Connection lost, reconnecting...")
                self._ws = None
            except websockets.ConnectionClosedOK:
                logger.info("Connection closed by server, reconnecting...")
                self._ws = None
            except json.JSONDecodeError as e:
                logger.warning(f"Invalid message: {e}")
            except Exception as e:
                logger.error(f"Receive error: {e}")

    async def _keyboard_loop(self):
        import keyboard as kb

        shortcut = self._config.shortcut_key
        logger.info(f"Listening for shortcut key: {shortcut}")

        pressed = False

        while self._running:
            if kb.is_pressed(shortcut) and not pressed:
                pressed = True
                await self._on_key_down()
            elif not kb.is_pressed(shortcut) and pressed:
                pressed = False
                await self._on_key_up()

            await asyncio.sleep(0.01)

    async def _on_key_down(self):
        if self._recording:
            return

        self._recording = True
        logger.info("Key pressed, starting recording")

        if not self._recorder.start():
            self._recording = False
            return

        if self._ws and not self._ws.closed:
            try:
                task_id = str(uuid.uuid4())
                await self._ws.send(json.dumps({
                    "type": "audio_start",
                    "task_id": task_id,
                }))
            except Exception as e:
                logger.error(f"Failed to send audio_start: {e}")

        asyncio.create_task(self._stream_audio())

    async def _stream_audio(self):
        while self._recording and self._recorder.is_recording:
            chunk = self._recorder.read_chunk()
            if chunk and self._ws and not self._ws.closed:
                try:
                    await self._ws.send(chunk)
                except Exception as e:
                    logger.error(f"Failed to send audio chunk: {e}")
                    break
            await asyncio.sleep(0.02)

    async def _on_key_up(self):
        if not self._recording:
            return

        self._recording = False
        logger.info("Key released, stopping recording")

        audio_data = self._recorder.stop()

        if self._ws and not self._ws.closed:
            try:
                await self._ws.send(json.dumps({"type": "audio_end"}))
            except Exception as e:
                logger.error(f"Failed to send audio_end: {e}")

        if self._config.save_audio and audio_data:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filepath = f"recordings/{timestamp}.wav"
            self._recorder.save_wav(filepath, audio_data)

    async def stop(self):
        self._running = False
        if self._recording:
            self._recorder.stop()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        logger.info("VoiceClient stopped")


def main():
    import sys

    config = ClientConfig()

    for arg in sys.argv[1:]:
        if arg.startswith("--server="):
            config.server_host = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            config.server_port = int(arg.split("=", 1)[1])
        elif arg.startswith("--output="):
            config.output_mode = arg.split("=", 1)[1]
        elif arg.startswith("--key="):
            config.shortcut_key = arg.split("=", 1)[1]

    client = VoiceClient(config)

    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        asyncio.run(client.stop())


if __name__ == "__main__":
    main()
