"""Wrapped counter persistence helpers."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from .config import WRAPPED_COUNT_FILE

wrapped_count_lock = threading.Lock()

try:
    import fcntl
except ImportError:
    fcntl = None


def _ensure_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text("0")


def _read_wrapped_count_unlocked() -> int:
    try:
        return int(WRAPPED_COUNT_FILE.read_text().strip() or "0")
    except FileNotFoundError:
        _ensure_file(WRAPPED_COUNT_FILE)
        return 0
    except ValueError:
        WRAPPED_COUNT_FILE.write_text("0")
        return 0


def read_wrapped_count() -> int:
    with wrapped_count_lock:
        return _read_wrapped_count_unlocked()


def _increment_with_file_lock(delta: int) -> int:
    with open(WRAPPED_COUNT_FILE, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            raw = handle.read().strip()
            try:
                count = int(raw or "0")
            except ValueError:
                count = 0
            count += delta
            handle.seek(0)
            handle.truncate()
            handle.write(str(count))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return count


def increment_wrapped_count(delta: int = 1) -> int:
    with wrapped_count_lock:
        _ensure_file(WRAPPED_COUNT_FILE)
        step = max(delta, 0)
        if fcntl is not None:
            try:
                return _increment_with_file_lock(step)
            except OSError:
                pass
        count = _read_wrapped_count_unlocked() + step
        tmp_path = Path(f"{WRAPPED_COUNT_FILE}.{os.getpid()}.tmp")
        tmp_path.write_text(str(count))
        os.replace(tmp_path, WRAPPED_COUNT_FILE)
        return count
