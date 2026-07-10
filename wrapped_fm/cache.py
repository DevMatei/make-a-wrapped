"""Small in-memory TTL cache with in-flight request coalescing."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Hashable, Tuple

_MISS = object()


class TTLCache:
    """Thread-safe TTL cache. get_or_compute runs one compute per missing key;
    concurrent callers for the same key wait for that result."""

    def __init__(self, ttl: float, max_size: int) -> None:
        self.ttl = ttl
        self.max_size = max_size
        self._data: Dict[Hashable, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._inflight: Dict[Hashable, threading.Lock] = {}

    def _lookup(self, key: Hashable) -> Any:
        with self._lock:
            entry = self._data.get(key)
            if entry and time.time() - entry[0] < self.ttl:
                return entry[1]
        return _MISS

    def get(self, key: Hashable, default: Any = None) -> Any:
        value = self._lookup(key)
        return default if value is _MISS else value

    def set(self, key: Hashable, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.time(), value)
            while len(self._data) > self.max_size:
                oldest = min(self._data.items(), key=lambda item: item[1][0])[0]
                self._data.pop(oldest, None)

    def get_or_compute(self, key: Hashable, compute: Callable[[], Any]) -> Any:
        value = self._lookup(key)
        if value is not _MISS:
            return value
        with self._lock:
            gate = self._inflight.setdefault(key, threading.Lock())
        try:
            with gate:
                value = self._lookup(key)
                if value is _MISS:
                    value = compute()
                    self.set(key, value)
                return value
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
