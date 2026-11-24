"""Small in-memory TTL cache with in-flight request coalescing."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Hashable, Optional, Tuple

_MISS = object()


class TTLCache:
    """Thread-safe TTL cache. get_or_compute runs one compute per missing key;
    concurrent callers for the same key wait for that result."""

    def __init__(
        self,
        ttl: float,
        max_size: int,
        *,
        max_bytes: Optional[int] = None,
        sizeof: Optional[Callable[[Any], int]] = None,
    ) -> None:
        self.ttl = ttl
        self.max_size = max_size
        self.max_bytes = max_bytes
        self._sizeof = sizeof
        self._bytes = 0
        # insertion ordered, oldest first
        self._data: Dict[Hashable, Tuple[float, Any, int]] = {}
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

    def pop(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            entry = self._data.pop(key, None)
            self._inflight.pop(key, None)
            if entry is not None:
                self._bytes -= entry[2]
        if entry is None:
            return default
        return entry[1]

    def set(self, key: Hashable, value: Any) -> None:
        size = self._sizeof(value) if self._sizeof else 0
        if self.max_bytes is not None and size > self.max_bytes:
            return
        with self._lock:
            previous = self._data.pop(key, None)
            if previous is not None:
                self._bytes -= previous[2]
            self._data[key] = (time.time(), value, size)
            self._bytes += size
            while self._data and (
                len(self._data) > self.max_size
                or (self.max_bytes is not None and self._bytes > self.max_bytes)
            ):
                oldest = next(iter(self._data))
                self._bytes -= self._data.pop(oldest)[2]

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
            self._bytes = 0
