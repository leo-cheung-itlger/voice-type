import json
import os
import time
from typing import Any, Dict, List, Optional

from common.logger import setup_logger
from config.settings import DATA_DIR

logger = setup_logger("history")

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


class HistoryManager:
    def __init__(self, filepath: Optional[str] = None):
        self._filepath = filepath or HISTORY_FILE
        self._entries: List[Dict[str, Any]] = []
        self._error_marks: List[Dict[str, Any]] = []
        self._stats_cache = None
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
        self._stats_cache = None
        try:
            os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
            with open(self._filepath, "w", encoding="utf-8") as f:
                json.dump(
                    {"entries": self._entries, "error_marks": self._error_marks},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add_entry(
        self,
        text: str,
        task_id: str,
        delay: float,
        audio_path: str = "",
        model: str = "",
        transcript_path: str = "",
        duration_seconds: Optional[float] = None,
    ):
        if task_id:
            existing = next((row for row in self._entries if row.get("task_id") == task_id), None)
            if existing:
                return existing
        duration = round(float(duration_seconds if duration_seconds is not None else delay), 3)
        if not transcript_path and audio_path and os.path.basename(audio_path).lower() == "recording.wav":
            transcript_path = os.path.join(os.path.dirname(audio_path), "result.json")
        entry = {
            "text": text,
            "task_id": task_id,
            "timestamp": time.time(),
            "delay": duration,
            "duration_seconds": duration,
            "audio_path": audio_path,
            "transcript_path": transcript_path,
            "model": model,
        }
        self._entries.append(entry)
        self._save()
        return entry

    def get_entries(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        limit = max(1, min(1000, limit))
        offset = max(0, offset)
        return self._entries[-(offset + limit) : -offset] if offset else self._entries[-limit:]

    def clear_entries(self):
        self._entries.clear()
        self._save()

    def delete_entry(self, task_id: str) -> bool:
        before = len(self._entries)
        self._entries = [entry for entry in self._entries if entry.get("task_id") != task_id]
        changed = len(self._entries) != before
        if changed:
            self._save()
        return changed

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
        if self._stats_cache is not None:
            return self._stats_cache
        word_counter = Counter()
        for entry in self._entries:
            text = entry.get("text", "")
            for i in range(len(text)):
                for length in range(2, min(6, len(text) - i + 1)):
                    word_counter[text[i : i + length]] += 1

        self._stats_cache = {
            "total_entries": len(self._entries),
            "top_words": [
                {"word": w, "count": c} for w, c in word_counter.most_common(50)
            ],
        }
        return self._stats_cache
