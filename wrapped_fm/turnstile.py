"""Cloudflare Turnstile helpers."""

from __future__ import annotations

import threading
import time
from functools import wraps
from typing import Dict, Optional

import requests
from flask import abort, current_app, request
from requests import RequestException

from .config import (
    TURNSTILE_CACHE_TTL,
    TURNSTILE_ENABLED,
    TURNSTILE_SECRET_KEY,
    TURNSTILE_TIMEOUT,
    TURNSTILE_VERIFY_URL,
)
from .rate_limiter import resolve_client_ip

TURNSTILE_HEADER = "X-Turnstile-Token"

_token_cache: Dict[str, float] = {}
_cache_lock = threading.Lock()


def _client_ip() -> str:
    return resolve_client_ip(request)


def _extract_turnstile_token() -> Optional[str]:
    header_token = (request.headers.get(TURNSTILE_HEADER) or "").strip()
    if header_token:
        return header_token

    if request.is_json:
        payload = request.get_json(silent=True) or {}
        candidate = (payload.get("cf-turnstile-response") or "").strip()
        if candidate:
            return candidate

    if request.form:
        candidate = (request.form.get("cf-turnstile-response") or "").strip()
        if candidate:
            return candidate

    query_token = (request.args.get("cf-turnstile-response") or "").strip()
    if query_token:
        return query_token

    return None


def _prune_cache(now: float) -> None:
    expired = [token for token, expiry in _token_cache.items() if expiry <= now]
    for token in expired:
        _token_cache.pop(token, None)


def _verify_with_cloudflare(token: str) -> bool:
    payload = {
        "secret": TURNSTILE_SECRET_KEY,
        "response": token,
        "remoteip": _client_ip(),
    }
    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data=payload,
            timeout=TURNSTILE_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (RequestException, ValueError) as exc:
        current_app.logger.warning("Turnstile verification failed: %s", exc)
        abort(502, description="Unable to verify human check. Please retry.")
    success = bool(data.get("success"))
    if not success:
        current_app.logger.info(
            "Turnstile rejected request. Errors: %s",
            data.get("error-codes"),
        )
    return success


def verify_turnstile_token(token: str) -> bool:
    if not TURNSTILE_ENABLED:
        return True
    if not token:
        return False
    now = time.monotonic()
    with _cache_lock:
        expiry = _token_cache.get(token)
        if expiry and expiry > now:
            return True
        _prune_cache(now)
    success = _verify_with_cloudflare(token)
    if success:
        with _cache_lock:
            _token_cache[token] = now + TURNSTILE_CACHE_TTL
    return success


def require_turnstile(func):
    """Decorator enforcing Turnstile when enabled."""

    if not TURNSTILE_ENABLED:
        return func

    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _extract_turnstile_token()
        if not token:
            abort(400, description="Human verification required.")
        if not verify_turnstile_token(token):
            abort(400, description="Human verification expired. Please retry.")
        return func(*args, **kwargs)

    return wrapper


__all__ = ["require_turnstile", "verify_turnstile_token", "TURNSTILE_HEADER"]
