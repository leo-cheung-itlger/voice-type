"""Cross-process leases: changing the model must never interrupt active audio work."""
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from config.settings import DATA_DIR


@contextmanager
def _guard():
    root = Path(DATA_DIR) / "activity"
    root.mkdir(parents=True, exist_ok=True)
    with (root / "guard.lock").open("a+b") as handle:
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + 5
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("操作正在进行，请稍后重试")
                time.sleep(.02)
        try:
            yield root
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _live(root):
    import psutil
    rows = []
    for path in root.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
            process = psutil.Process(row["pid"])
            if abs(process.create_time() - row["process_created"]) < 1:
                rows.append({**row, "token": path.stem})
                continue
        except (OSError, ValueError, KeyError, psutil.Error):
            pass
        path.unlink(missing_ok=True)
    return rows


def activities():
    with _guard() as root:
        return _live(root)


def acquire(kind):
    import psutil
    with _guard() as root:
        rows = _live(root)
        if any(row["kind"] == "switch" for row in rows) or (kind == "switch" and rows):
            raise RuntimeError("正在录音、识别或转录，请完成后再切换模型")
        token = uuid.uuid4().hex
        (root / f"{token}.json").write_text(json.dumps({"pid": os.getpid(), "process_created": psutil.Process().create_time(), "kind": kind}), encoding="utf-8")
        return token


def release(token):
    if token:
        with _guard() as root:
            (root / f"{token}.json").unlink(missing_ok=True)


@contextmanager
def activity(kind):
    token = acquire(kind)
    try:
        yield
    finally:
        release(token)
