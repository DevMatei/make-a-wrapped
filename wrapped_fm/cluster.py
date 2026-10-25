"""Helpers for running more than one node.

Nodes talk to each other over /internal/* with a shared bearer secret. A single
node setup (no CLUSTER_SECRET) never makes any of these calls.
"""

from __future__ import annotations

import hmac
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests
from flask import Request, abort

from .config import (
    CLUSTER_PEERS,
    CLUSTER_PRIMARY,
    CLUSTER_SECRET,
    CLUSTER_STATE_DIR,
    CLUSTER_TIMEOUT,
    NODE_ID,
)

try:
    import fcntl
except ImportError:
    fcntl = None

logger = logging.getLogger("wrapped_fm")

_running: Dict[str, threading.Lock] = {}
_running_guard = threading.Lock()


class PrimaryUnavailableError(Exception):
    """Raised when the primary node can't be reached."""


class ForwardedError(Exception):
    """An error response passed back from the primary."""

    def __init__(self, status: int, description: str) -> None:
        super().__init__(description)
        self.status = status
        self.description = description


def enabled() -> bool:
    return bool(CLUSTER_SECRET and (CLUSTER_PEERS or CLUSTER_PRIMARY))


def is_replica() -> bool:
    return bool(CLUSTER_SECRET and CLUSTER_PRIMARY)


def peers():
    return list(CLUSTER_PEERS) if CLUSTER_SECRET else []


def check_secret(provided: Optional[str]) -> bool:
    if not CLUSTER_SECRET or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), CLUSTER_SECRET.encode("utf-8"))


def require_node(req: Request) -> None:
    header = req.headers.get("Authorization", "")
    if not check_secret(header[7:] if header.startswith("Bearer ") else ""):
        abort(404)


def _headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {CLUSTER_SECRET}", "X-Wrapped-Node": NODE_ID}


def peer_get(base: str, path: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", CLUSTER_TIMEOUT)
    return requests.get(f"{base}{path}", headers=_headers(), **kwargs)


def peer_post(base: str, path: str, **kwargs) -> requests.Response:
    kwargs.setdefault("timeout", CLUSTER_TIMEOUT)
    return requests.post(f"{base}{path}", headers=_headers(), **kwargs)


def fetch_from_peers(path: str) -> Optional[requests.Response]:
    """Return the first 200 response for path from any peer."""
    for base in peers():
        try:
            response = peer_get(base, path)
        except requests.RequestException as error:
            logger.warning("Peer %s unreachable for %s: %s", base, path, error)
            continue
        if response.status_code == 200:
            return response
    return None


def push_to_peers(path: str, payload: Dict[str, Any]) -> None:
    """Best effort fire and forget POST to every peer."""
    targets = peers()
    if not targets:
        return

    def run() -> None:
        for base in targets:
            try:
                peer_post(base, path, json=payload)
            except requests.RequestException as error:
                logger.warning("Push to %s%s failed: %s", base, path, error)

    threading.Thread(target=run, name="cluster-push", daemon=True).start()


def call_primary(action: str, **kwargs) -> Dict[str, Any]:
    try:
        response = peer_post(CLUSTER_PRIMARY, f"/internal/templates/{action}", **kwargs)
    except requests.RequestException as error:
        logger.warning("Primary unreachable for %s: %s", action, error)
        raise PrimaryUnavailableError from error
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 500:
        raise PrimaryUnavailableError
    if response.status_code >= 400:
        description = body.get("description") if isinstance(body, dict) else None
        raise ForwardedError(response.status_code, description or "Request failed.")
    return body if isinstance(body, dict) else {}


def _claim(key: str, interval: float) -> bool:
    """True for exactly one worker per interval across processes."""
    os.makedirs(CLUSTER_STATE_DIR, exist_ok=True)
    stamp = Path(CLUSTER_STATE_DIR) / f"{key}.stamp"
    with open(f"{stamp}.lock", "a", encoding="utf-8") as lock_file:
        if fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return False
        try:
            try:
                last = float(stamp.read_text().strip() or "0")
            except (OSError, ValueError):
                last = 0.0
            now = time.time()
            if now - last < interval:
                return False
            stamp.write_text(str(now))
            return True
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def every(key: str, interval: float, job: Callable[[], Any]) -> None:
    """Run job in the background at most once per interval across all workers."""
    with _running_guard:
        lock = _running.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        return
    try:
        claimed = _claim(key, interval)
    except OSError:
        claimed = False
    if not claimed:
        lock.release()
        return

    def run() -> None:
        try:
            job()
        except Exception:
            logger.exception("Background job %s failed", key)
        finally:
            lock.release()

    threading.Thread(target=run, name=f"cluster-{key}", daemon=True).start()
