"""Shared rate limiting utilities."""

from __future__ import annotations

import hashlib
from typing import Optional

from flask import Flask, Request, request

from .config import (
    DEFAULT_RATE_LIMIT,
    RATE_LIMIT_SALT,
    RATE_LIMIT_STORAGE,
    TRUST_PROXY_HEADERS,
)

try:
    from flask_limiter import Limiter
except ImportError: #pragma: no cover - optional depedency
    Limiter = None #type: ignore

limiter: Optional["Limiter"] = None


def _resolve_client_ip(current_request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded_for = current_request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate
        real_ip = current_request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
    return current_request.remote_addr or "0.0.0.0"


def _rate_limit_key() -> str:
    client_ip = _resolve_client_ip(request)
    seed = f"{client_ip}|{RATE_LIMIT_SALT}".encode("utf-8")
    return hashlib.blake2s(seed, digest_size=16).hexdigest()


def init_rate_limiter(app: Flask) -> None:
    global limiter

    if Limiter is None:
        limiter = None
        return

    limiter = Limiter(
        key_func=_rate_limit_key,
        default_limits=[DEFAULT_RATE_LIMIT],
        storage_uri=RATE_LIMIT_STORAGE,
        strategy="moving-window",
        headers_enabled=True,
    )
    limiter.init_app(app)


def rate_limit(limit_value: str):
    def decorator(func):
        if limiter:
            return limiter.limit(limit_value)(func)
        return func

    return decorator
