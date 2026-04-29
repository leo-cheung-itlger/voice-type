import json
import os
import time
from typing import Any, Dict, List, Optional

from common.logger import setup_logger

logger = setup_logger("history")

HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "history.json",
)


class HistoryManager:
    def __init__(self, filepath: Optional[str] = None):
        self._filepath = filepath or HISTORY_FILE
        self._entries: List[Dict[str, Any]] = []
        self._error_marks: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        try:
            if os.path.exists(self._filepath):
                with open(self._filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._entries = data.get("entries", [])
                    self._error_marks = data.get("error_marks", [])
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self._entries[-1000:], "error_marks": self._error_marks},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add_entry(self, text: str, task_id: str, delay: float, audio_path: str = ""):
        entry = {
            "text": text,
            "task_id": task_id,
            "timestamp": time.time(),
            "delay": round(delay, 3),
            "audio_path": audio_path,
        }
        self._entries.append(entry)
        self._save()
        return entry

    def get_entries(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        return self._entries[-(offset + limit) : -offset] if offset else self._entries[-limit:]

    def clear_entries(self):
        self._entries.clear()
        self._save()

    def add_error_mark(self, text: str, marked_text: str):
        mark = {
            "text": text,
            "marked_text": marked_text,
            "timestamp": time.time(),
        }
        self._error_marks.append(mark)
        self._save()
        return mark

    def get_error_marks(self) -> List[Dict]:
        return self._error_marks

    def get_stats(self) -> Dict[str, Any]:
        from collections import Counter

        word_counter = Counter()
        for entry in self._entries:
            text = entry.get("text", "")
            for i in range(len(text)):
                for length in range(2, min(6, len(text) - i + 1)):
                    word_counter[text[i : i + length]] += 1

        return {
            "total_entries": len(self._entries),
            "top_words": [
                {"word": w, "count": c} for w, c in word_counter.most_common(50)
            ],
        }
