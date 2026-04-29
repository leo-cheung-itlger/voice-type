import os
import re
import time
from typing import Dict, List, Optional, Tuple

from common.logger import setup_logger

logger = setup_logger("hotword")


class HotwordManager:
    def __init__(self):
        self._zh_words: Dict[str, str] = {}
        self._en_words: Dict[str, str] = {}
        self._rules: List[Tuple[str, str]] = []
        self._last_load_time: float = 0
        self._load_interval: float = 5.0
        self._hotword_dir: str = ""

    def load(self, hotword_dir: str, files: List[str]):
        self._hotword_dir = hotword_dir
        self._reload_all(files)
        logger.info(f"Loaded {len(self._zh_words)} zh, {len(self._en_words)} en, {len(self._rules)} rules")

    def maybe_reload(self, files: List[str]):
        now = time.time()
        if now - self._last_load_time < self._load_interval:
            return
        self._reload_all(files)

    def _reload_all(self, files: List[str]):
        self._zh_words.clear()
        self._en_words.clear()
        self._rules.clear()

        for fname in files:
            fpath = os.path.join(self._hotword_dir, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split("->")
                        if len(parts) != 2:
                            continue
                        src = parts[0].strip()
                        dst = parts[1].strip()
                        if not src or not dst:
                            continue

                        if fname.startswith("hot-zh"):
                            self._zh_words[src] = dst
                        elif fname.startswith("hot-en"):
                            self._en_words[src.upper()] = dst
                        elif fname.startswith("hot-rule"):
                            try:
                                self._rules.append((re.compile(src), dst))
                            except re.error as e:
                                logger.warning(f"Invalid regex '{src}': {e}")
            except Exception as e:
                logger.error(f"Failed to load hotword file {fpath}: {e}")

        self._last_load_time = time.time()

    def apply(self, text: str) -> str:
        for src, dst in self._zh_words.items():
            if src in text:
                text = text.replace(src, dst)

        for src, dst in self._en_words.items():
            pattern = re.compile(r'\b' + re.escape(src) + r'\b', re.IGNORECASE)
            text = pattern.sub(dst, text)

        for pattern, dst in self._rules:
            text = pattern.sub(dst, text)

        return text
