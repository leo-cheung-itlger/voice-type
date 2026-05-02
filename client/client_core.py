import asyncio
import json
import os
import sys
import time
import uuid
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import websockets

from common.hotword import HotwordManager
from common.logger import setup_logger
from config.settings import ClientConfig, load_app_config
from client.notifier import RecordingNotifier
from client.output import type_result
from client.recorder import AudioRecorder

logger = setup_logger("client_core")


KEY_ALIASES = {
    "caps lock": "caps_lock",
    "caps_lock": "caps_lock",
    "capslock": "caps_lock",
    "shift": "shift",
    "left shift": "left_shift",
    "left_shift": "left_shift",
    "right shift": "right_shift",
    "right_shift": "right_shift",
    "ctrl": "ctrl",
    "control": "ctrl",
    "left ctrl": "left_ctrl",
    "left_ctrl": "left_ctrl",
    "right ctrl": "right_ctrl",
    "right_ctrl": "right_ctrl",
    "alt": "alt",
    "left alt": "left_alt",
    "left_alt": "left_alt",
    "right alt": "right_alt",
    "right_alt": "right_alt",
}

SCAN_CODE_KEYS = {
    42: "left_shift",
    54: "right_shift",
    29: "left_ctrl",
    97: "right_ctrl",
    56: "left_alt",
    100: "right_alt",
    58: "caps_lock",
}


def normalize_shortcut_key(key: str) -> str:
    normalized = (key or "").strip().lower().replace("-", "_")
    normalized = " ".join(normalized.replace("_", " ").split())
    alias = KEY_ALIASES.get(normalized)
    if alias:
        return alias
    return normalized.replace(" ", "_")


def normalize_keyboard_event_key(name: str, scan_code: Optional[int] = None) -> str:
    if scan_code in SCAN_CODE_KEYS:
        return SCAN_CODE_KEYS[scan_code]
    return normalize_shortcut_key(name)


def shortcut_matches(configured: str, event_key: str) -> bool:
    shortcut = normalize_shortcut_key(configured)
    key = normalize_shortcut_key(event_key)
    if shortcut == key:
        return True
    if shortcut == "shift" and key in ("left_shift", "right_shift"):
        return True
    if shortcut == "ctrl" and key in ("left_ctrl", "right_ctrl"):
        return True
    if shortcut == "alt" and key in ("left_alt", "right_alt"):
        return True
    return False


def display_shortcut_key(key: str) -> str:
    return normalize_shortcut_key(key).replace("_", " ")


class VoiceClient:
    def __init__(self, config: ClientConfig):
        self._config = config
        self._recorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            input_device_index=config.input_device_index,
            input_device_name=config.input_device_name,
        )
        self._notifier = RecordingNotifier(
            enabled=config.notification_enabled,
            sound_enabled=config.notification_sound,
        )
        self._hotword = HotwordManager()
        self._ws: Optional[Any] = None
        self._running = False
        self._recording = False
        self._processing = False
        self._key_down_at = 0.0
        self._pressed_shortcut = False
        self._keyboard_hook = None
        self._send_queue: "asyncio.Queue[dict]" = asyncio.Queue()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def start(self):
        logger.info("Starting VoiceClient...")

        self._hotword.load(
            hotword_dir=".",
            files=self._config.hotword_files,
        )

        self._running = True

        keyboard_task = asyncio.create_task(self._keyboard_loop())
        worker_task = asyncio.create_task(self._request_worker())

        await asyncio.gather(keyboard_task, worker_task)

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

    def _ws_is_open(self) -> bool:
        if not self._ws:
            return False

        closed = getattr(self._ws, "closed", None)
        if closed is not None:
            return not closed

        close_code = getattr(self._ws, "close_code", None)
        if close_code is not None:
            return False

        state = getattr(self._ws, "state", None)
        if state is None:
            return True

        state_name = getattr(state, "name", "").upper()
        if state_name:
            return state_name == "OPEN"

        try:
            return int(state) == 1
        except Exception:
            return True

    async def _heartbeat_loop(self):
        while self._running and self._ws_is_open():
            await asyncio.sleep(self._config.heartbeat_interval)
            if self._ws_is_open():
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
            if not self._ws_is_open():
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

        loop = asyncio.get_running_loop()
        shortcut = normalize_shortcut_key(self._config.shortcut_key)
        logger.info(
            "Listening for shortcut key via global hook: raw=%s normalized=%s",
            self._config.shortcut_key,
            shortcut,
        )

        def schedule(callback):
            if not self._running:
                return
            loop.call_soon_threadsafe(lambda: asyncio.create_task(callback()))

        def on_keyboard_event(event):
            event_key = normalize_keyboard_event_key(
                getattr(event, "name", "") or "",
                getattr(event, "scan_code", None),
            )
            if not shortcut_matches(shortcut, event_key):
                return
            event_type = getattr(event, "event_type", "")
            if event_type == "down" and not self._pressed_shortcut:
                self._pressed_shortcut = True
                logger.info("Shortcut down: configured=%s event=%s", shortcut, event_key)
                schedule(self._on_key_down)
            elif event_type == "up" and self._pressed_shortcut:
                self._pressed_shortcut = False
                logger.info("Shortcut up: configured=%s event=%s", shortcut, event_key)
                schedule(self._on_key_up)

        try:
            self._keyboard_hook = kb.hook(on_keyboard_event, suppress=False)
            logger.info("Global keyboard hook started")
            while self._running:
                await asyncio.sleep(0.2)
        except Exception as e:
            logger.error(f"Global keyboard hook failed: {e}")
            self._notifier.output_failed("快捷键监听失败，可能需要管理员权限")
            while self._running:
                await asyncio.sleep(1)
        finally:
            if self._keyboard_hook is not None:
                try:
                    kb.unhook(self._keyboard_hook)
                except Exception:
                    pass
                self._keyboard_hook = None
            logger.info("Global keyboard hook stopped")

    async def _on_key_down(self):
        if self._recording:
            return

        self._recording = True
        self._key_down_at = time.monotonic()
        logger.info("Key pressed, starting recording")

        if not self._recorder.start():
            self._recording = False
            return

        self._notifier.recording_started()

        asyncio.create_task(self._drain_recording())

    async def _drain_recording(self):
        while self._recording and self._recorder.is_recording:
            self._recorder.read_chunk()
            await asyncio.sleep(0.02)

    async def _on_key_up(self):
        if not self._recording:
            return

        self._recording = False
        logger.info("Key released, stopping recording")

        audio_data = self._recorder.stop()
        held_seconds = max(time.monotonic() - self._key_down_at, 0.0)
        min_press_seconds = max(float(self._config.min_press_seconds or 0), 0.0)
        if held_seconds < min_press_seconds:
            logger.info(
                "Shortcut press ignored as too short: %.3fs < %.3fs",
                held_seconds,
                min_press_seconds,
            )
            self._notifier.ignored_short_press(held_seconds)
            return

        self._notifier.recording_finished()

        if not audio_data:
            self._notifier.output_failed("没有录到音频")
            return

        task_id = str(uuid.uuid4())
        archive_dir = self._archive_dir(task_id)
        audio_path = ""
        transcript_path = os.path.join(archive_dir, "result.json")

        if self._config.save_audio:
            audio_path = os.path.join(archive_dir, "recording.wav")
            self._recorder.save_wav(audio_path, audio_data)

        queued_count = self._send_queue.qsize() + (1 if self._processing else 0)
        if queued_count:
            self._notifier.queued(queued_count + 1)

        await self._send_queue.put({
            "task_id": task_id,
            "audio_data": audio_data,
            "audio_path": audio_path,
            "transcript_path": transcript_path,
            "sample_rate": self._config.sample_rate,
        })

    def _archive_dir(self, task_id: str) -> str:
        now = time.localtime()
        timestamp = time.strftime("%H%M%S", now)
        short_id = task_id.split("-", 1)[0]
        path = os.path.join(
            self._config.archive_root,
            time.strftime("%Y", now),
            time.strftime("%m", now),
            time.strftime("%d", now),
            f"{timestamp}_{short_id}",
        )
        os.makedirs(path, exist_ok=True)
        return path

    async def _request_worker(self):
        while self._running:
            item = await self._send_queue.get()
            self._processing = True
            ticker: Optional[asyncio.Task] = None
            try:
                self._notifier.analysis_started()
                ticker = asyncio.create_task(self._analysis_ticker())
                result = await self._recognize_item(item)
                text = result.get("text", "")
                if not text:
                    error = result.get("error") or "识别结果为空"
                    logger.warning(f"Recognition failed or empty: {error}")
                    self._notifier.output_failed(error)
                    continue

                self._hotword.maybe_reload(self._config.hotword_files)
                text = self._hotword.apply(text)
                await type_result(text, self._config)

                delay = result.get("time_complete", 0) - result.get("time_submit", 0)
                logger.info(f"Result: {text} (delay: {delay:.2f}s)")
                self._write_result_json(item, result, text, delay)
                self._notifier.output_success_with_duration(delay)
            except Exception as e:
                logger.error(f"Recognition request failed: {e}")
                self._notifier.output_failed("识别失败")
            finally:
                if ticker:
                    ticker.cancel()
                self._processing = False
                self._send_queue.task_done()

    async def _analysis_ticker(self):
        started = time.time()
        while True:
            await asyncio.sleep(1)
            seconds = int(time.time() - started)
            if seconds >= 3:
                self._notifier.analysis_tick(seconds)

    def _write_result_json(self, item: dict, result: dict, text: str, delay: float):
        transcript_path = item.get("transcript_path") or ""
        if not transcript_path:
            return
        try:
            os.makedirs(os.path.dirname(transcript_path), exist_ok=True)
            payload = {
                "task_id": item.get("task_id", ""),
                "text": text,
                "duration_seconds": round(delay, 3),
                "audio_path": item.get("audio_path", ""),
                "transcript_path": transcript_path,
                "model": result.get("model", ""),
                "output_mode": self._config.output_mode,
                "sample_rate": item.get("sample_rate", self._config.sample_rate),
                "time_start": result.get("time_start"),
                "time_submit": result.get("time_submit"),
                "time_complete": result.get("time_complete"),
            }
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write transcript result JSON: {e}")

    async def _recognize_item(self, item: dict) -> dict:
        async with websockets.connect(
            f"ws://{self._config.server_host}:{self._config.server_port}",
            max_size=None,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            await ws.send(json.dumps({
                "type": "audio_start",
                "task_id": item["task_id"],
                "sample_rate": item["sample_rate"],
            }))
            audio_data = item["audio_data"]
            chunk_size = 32_000
            for index in range(0, len(audio_data), chunk_size):
                await ws.send(audio_data[index:index + chunk_size])
            time_submit = time.time()
            await ws.send(json.dumps({
                "type": "audio_end",
                "audio_path": item["audio_path"],
                "transcript_path": item.get("transcript_path", ""),
                "sample_rate": item["sample_rate"],
            }, ensure_ascii=False))
            message = await ws.recv()
            data = json.loads(message)
            data.setdefault("time_submit", time_submit)
            data.setdefault("time_complete", time.time())
            return data

    async def stop(self):
        self._running = False
        if self._recording:
            self._recorder.stop()
        if self._ws_is_open():
            await self._ws.close()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        self._pressed_shortcut = False
        self._notifier.shutdown()
        logger.info("VoiceClient stopped")


def main():
    import sys

    config = load_app_config().client

    for arg in sys.argv[1:]:
        if arg.startswith("--server="):
            config.server_host = arg.split("=", 1)[1]
        elif arg.startswith("--port="):
            config.server_port = int(arg.split("=", 1)[1])
        elif arg.startswith("--output="):
            config.output_mode = arg.split("=", 1)[1]
        elif arg.startswith("--key="):
            config.shortcut_key = normalize_shortcut_key(arg.split("=", 1)[1])
        elif arg.startswith("--audio-dir="):
            config.audio_dir = arg.split("=", 1)[1]
        elif arg.startswith("--archive-root="):
            config.archive_root = arg.split("=", 1)[1]
        elif arg.startswith("--input-device-index="):
            config.input_device_index = int(arg.split("=", 1)[1])
        elif arg.startswith("--input-device-name="):
            config.input_device_name = arg.split("=", 1)[1]
        elif arg.startswith("--min-press-seconds="):
            config.min_press_seconds = float(arg.split("=", 1)[1])
        elif arg == "--save-audio":
            config.save_audio = True
        elif arg == "--no-save-audio":
            config.save_audio = False
        elif arg == "--notify":
            config.notification_enabled = True
        elif arg == "--no-notify":
            config.notification_enabled = False
        elif arg == "--sound":
            config.notification_sound = True
        elif arg == "--no-sound":
            config.notification_sound = False

    client = VoiceClient(config)

    try:
        asyncio.run(client.start())
    except KeyboardInterrupt:
        asyncio.run(client.stop())


if __name__ == "__main__":
    main()
