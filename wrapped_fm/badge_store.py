"""File-backed storage for client-published badge snapshots."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Dict, Optional

from .config import (
    BADGE_SNAPSHOT_DIR,
    BADGE_SNAPSHOT_MAX_COUNT,
    BADGE_SNAPSHOT_TTL_SECONDS,
)

SNAPSHOT_FIELDS = ("artist", "track", "genre", "minutes")
MAX_VALUE_LENGTH = 60

_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_PUBLIC_ID_RE = re.compile(r"^[a-f0-9]{24}$")
_store_lock = threading.Lock()


class SnapshotInvalidError(Exception):
    """Raised when a publish payload fails validation."""


class BadgeStoreFullError(Exception):
    """Raised when the snapshot store hit its size cap."""


def public_id_for_secret(secret: str) -> str:
    if not isinstance(secret, str) or not _SECRET_RE.match(secret):
        raise SnapshotInvalidError("Invalid badge secret.")
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:24]


def _clean_value(raw) -> str:
    if not isinstance(raw, str):
        return ""
    cleaned = "".join(ch for ch in raw if ch.isprintable())
    cleaned = " ".join(cleaned.split())
    return cleaned[:MAX_VALUE_LENGTH]


def _sanitise_values(values) -> Dict[str, str]:
    if not isinstance(values, dict):
        raise SnapshotInvalidError("Missing badge values.")
    cleaned = {field: _clean_value(values.get(field)) for field in SNAPSHOT_FIELDS}
    if not any(cleaned.values()):
        raise SnapshotInvalidError("Badge values are empty.")
    return cleaned


def _snapshot_path(public_id: str) -> str:
    return os.path.join(BADGE_SNAPSHOT_DIR, f"{public_id}.json")


def _prune_expired_locked() -> None:
    cutoff = time.time() - BADGE_SNAPSHOT_TTL_SECONDS
    try:
        names = os.listdir(BADGE_SNAPSHOT_DIR)
    except FileNotFoundError:
        return
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(BADGE_SNAPSHOT_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
        except OSError:
            continue


def _count_snapshots() -> int:
    try:
        return sum(1 for name in os.listdir(BADGE_SNAPSHOT_DIR) if name.endswith(".json"))
    except FileNotFoundError:
        return 0


def store_snapshot(secret: str, values) -> str:
    public_id = public_id_for_secret(secret)
    cleaned = _sanitise_values(values)
    os.makedirs(BADGE_SNAPSHOT_DIR, exist_ok=True)
    path = _snapshot_path(public_id)
    with _store_lock:
        if not os.path.exists(path) and _count_snapshots() >= BADGE_SNAPSHOT_MAX_COUNT:
            _prune_expired_locked()
            if _count_snapshots() >= BADGE_SNAPSHOT_MAX_COUNT:
                raise BadgeStoreFullError
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump({"values": cleaned, "updated_at": time.time()}, handle)
        os.replace(tmp_path, path)
    return public_id


def fetch_snapshot(public_id: str) -> Optional[Dict[str, str]]:
    if not isinstance(public_id, str) or not _PUBLIC_ID_RE.match(public_id):
        return None
    path = _snapshot_path(public_id)
    try:
        if os.path.getmtime(path) < time.time() - BADGE_SNAPSHOT_TTL_SECONDS:
            return None
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    values = payload.get("values")
    if not isinstance(values, dict):
        return None
    return {field: _clean_value(values.get(field)) for field in SNAPSHOT_FIELDS}
