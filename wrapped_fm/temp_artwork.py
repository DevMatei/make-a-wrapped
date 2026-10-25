"""Temporary custom artwork storage.

Uploads go to disk so every worker can serve them. If a token isn't here the
upload probably landed on another node, so we ask the peers and keep a copy.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from secrets import token_urlsafe
from typing import Optional, Tuple

from . import cluster
from .config import TEMP_ARTWORK_DIR, TEMP_ARTWORK_TTL_SECONDS

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}
_TYPES = {ext: content_type for content_type, ext in _EXTENSIONS.items()}


class ArtworkMissingError(Exception):
    """Raised when a requested artwork token does not exist."""


class ArtworkExpiredError(Exception):
    """Raised when a requested artwork has expired."""


def _directory() -> Path:
    path = Path(TEMP_ARTWORK_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup() -> None:
    cutoff = time.time() - TEMP_ARTWORK_TTL_SECONDS
    for entry in _directory().iterdir():
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink()
        except OSError:
            continue


def _write(token: str, data: bytes, content_type: str) -> None:
    extension = _EXTENSIONS.get(content_type, "bin")
    path = _directory() / f"{token}.{extension}"
    tmp_path = path.with_suffix(f".{os.getpid()}.tmp")
    tmp_path.write_bytes(data)
    os.replace(tmp_path, path)


def _find_local(token: str) -> Optional[Path]:
    for extension in (*_TYPES, "bin"):
        path = _directory() / f"{token}.{extension}"
        if path.is_file():
            return path
    return None


def store_artwork(data: bytes, content_type: str) -> str:
    """Persist temporary artwork bytes and return a retrieval token."""
    _cleanup()
    token = token_urlsafe(12)
    _write(token, data, content_type)
    return token


def fetch_local_artwork(token: str) -> Tuple[bytes, str]:
    if not isinstance(token, str) or not _TOKEN_RE.match(token):
        raise ArtworkMissingError
    path = _find_local(token)
    if path is None:
        raise ArtworkMissingError
    if time.time() - path.stat().st_mtime > TEMP_ARTWORK_TTL_SECONDS:
        path.unlink(missing_ok=True)
        raise ArtworkExpiredError
    content_type = _TYPES.get(path.suffix[1:], "application/octet-stream")
    return path.read_bytes(), content_type


def fetch_artwork(token: str) -> Tuple[bytes, str]:
    """Return artwork bytes and mime type or raise if unavailable."""
    try:
        return fetch_local_artwork(token)
    except ArtworkMissingError:
        if not _TOKEN_RE.match(token or ""):
            raise
    response = cluster.fetch_from_peers(f"/internal/artwork/{token}")
    if response is None:
        raise ArtworkMissingError
    content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if content_type not in _EXTENSIONS:
        raise ArtworkMissingError
    _write(token, response.content, content_type)
    return response.content, content_type
