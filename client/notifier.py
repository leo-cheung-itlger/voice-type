import queue
import sys
import threading
from typing import Optional

from common.logger import setup_logger

logger = setup_logger("notifier")


class RecordingNotifier:
    def __init__(self, enabled: bool = True, sound_enabled: bool = True):
        self._enabled = enabled
        self._sound_enabled = sound_enabled
        self._queue: "queue.Queue[str]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._ready = False

    def configure(self, enabled: bool = True, sound_enabled: bool = True):
        self._enabled = bool(enabled)
        self._sound_enabled = bool(sound_enabled)

    def recording_started(self):
        self._beep(start=True)
        self._send("start")

    def recording_finished(self):
        self._beep(start=False)
        self._send("finish")

    def analysis_started(self):
        self._send("analysis")

    def analysis_tick(self, seconds: int):
        self._send(f"analysis:{seconds}")

    def queued(self, count: int):
        self._send(f"queued:{count}")

    def output_success(self):
        self._send("success")

    def output_success_with_duration(self, seconds: float):
        self._send(f"success:{seconds:.1f}")

    def output_failed(self, message: str = ""):
        self._send(f"failed:{message[:40]}")

    def ignored_short_press(self, seconds: float):
        self._send(f"ignored:{seconds:.2f}")

    def shutdown(self):
        self._send("quit")

    def _send(self, event: str):
        if not self._enabled:
            return
        self._ensure_thread()
        if self._ready:
            self._queue.put(event)

    def _ensure_thread(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_tk, daemon=True)
        self._thread.start()

    def _beep(self, start: bool):
        if not self._sound_enabled or sys.platform != "win32":
            return
        frequency = 880 if start else 660
        duration = 85
        threading.Thread(target=self._play_beep, args=(frequency, duration), daemon=True).start()

    @staticmethod
    def _play_beep(frequency: int, duration: int):
        try:
            import winsound

            winsound.Beep(frequency, duration)
        except Exception:
            try:
                import winsound

                winsound.MessageBeep()
            except Exception:
                pass

    def _run_tk(self):
        try:
            import tkinter as tk
        except Exception as e:
            logger.warning(f"Desktop notification unavailable: {e}")
            return

        try:
            root = tk.Tk()
            root.withdraw()
            root.overrideredirect(True)
            root.attributes("-topmost", True)

            width = 230
            height = 54
            x = max(root.winfo_screenwidth() - width - 24, 0)
            y = 24

            root.geometry(f"{width}x{height}+{x}+{y}")
            root.configure(bg="#0f172a")

            label = tk.Label(
                root,
                text="",
                bg="#0f172a",
                fg="#f8fafc",
                font=("Microsoft YaHei UI", 11),
                padx=16,
                pady=12,
                anchor="w",
            )
            label.pack(fill="both", expand=True)

            self._ready = True

            def show(text: str, bg: str):
                root.configure(bg=bg)
                label.configure(text=text, bg=bg)
                root.deiconify()
                root.lift()
                root.attributes("-topmost", True)

            def hide_later():
                root.after(750, root.withdraw)

            def poll():
                try:
                    while True:
                        event = self._queue.get_nowait()
                        if event == "start":
                            show("VoiceType 正在录音", "#14532d")
                        elif event == "finish":
                            show("录音已保存", "#1f2937")
                            hide_later()
                        elif event == "analysis":
                            show("正在分析音频", "#1d4ed8")
                        elif event.startswith("analysis:"):
                            seconds = event.split(":", 1)[1]
                            show(f"正在分析 {seconds}s", "#1d4ed8")
                        elif event.startswith("queued:"):
                            count = event.split(":", 1)[1]
                            show(f"录音已排队（{count}）", "#78350f")
                        elif event == "success":
                            show("识别已输出", "#14532d")
                            hide_later()
                        elif event.startswith("success:"):
                            seconds = event.split(":", 1)[1]
                            show(f"识别已输出 {seconds}s", "#14532d")
                            hide_later()
                        elif event.startswith("failed:"):
                            message = event.split(":", 1)[1] or "识别失败"
                            show(message, "#7f1d1d")
                            hide_later()
                        elif event.startswith("ignored:"):
                            seconds = event.split(":", 1)[1]
                            show(f"已忽略短按 {seconds}s", "#374151")
                            hide_later()
                        elif event == "quit":
                            root.destroy()
                            return
                except queue.Empty:
                    pass
                root.after(50, poll)

            root.after(50, poll)
            root.mainloop()
        except Exception as e:
            self._ready = False
            logger.warning(f"Desktop notification failed: {e}")
