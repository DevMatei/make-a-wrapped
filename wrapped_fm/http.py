"""HTTP client configuration and helpers."""

from __future__ import annotations

import threading
import time
from typing import Dict, Optional

import requests
from flask import abort
from requests import Response as RequestsResponse
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from .config import (
    HTTP_POOL_MAXSIZE,
    HTTP_TIMEOUT,
    LASTFM_API,
    LASTFM_USER_AGENT,
    LIBREFM_MIN_INTERVAL,
    LIBREFM_USER_AGENT,
    LISTENBRAINZ_API,
    LISTENBRAINZ_USER_AGENT,
    MUSICBRAINZ_API,
    MUSICBRAINZ_USER_AGENT,
    WIKIDATA_ENTITY_API,
)


class _RatePacer:
    """Serialises outbound requests for a session with a minimum interval."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.min_interval
        if delay:
            time.sleep(delay)


def _pace(session: requests.Session) -> None:
    pacer = getattr(session, "_upstream_pacer", None)
    if pacer is not None:
        pacer.wait()


def _retry_after_seconds(response: RequestsResponse, default: float = 5.0) -> float:
    value = response.headers.get("Retry-After", "").strip()
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return default


def _configure_session(
    session: requests.Session,
    retries: int = 3,
    pool_maxsize: int = HTTP_POOL_MAXSIZE,
) -> None:
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        status=retries,
        backoff_factor=0.5,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_maxsize,
        pool_maxsize=pool_maxsize,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)


def _configure_no_retry_session(
    session: requests.Session,
    pool_maxsize: int = HTTP_POOL_MAXSIZE,
) -> None:
    retry = Retry(total=0, raise_on_status=False)
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=pool_maxsize,
        pool_maxsize=pool_maxsize,
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)


listenbrainz_session = requests.Session()
listenbrainz_session.headers.update(
    {"User-Agent": LISTENBRAINZ_USER_AGENT, "Accept": "application/json"}
)
_configure_session(listenbrainz_session)

musicbrainz_session = requests.Session()
musicbrainz_session.headers.update(
    {"User-Agent": MUSICBRAINZ_USER_AGENT, "Accept": "application/json"}
)
_configure_session(musicbrainz_session)

cover_art_session = requests.Session()
cover_art_session.headers.update({"User-Agent": LISTENBRAINZ_USER_AGENT})
_configure_session(cover_art_session)

wikidata_session = requests.Session()
wikidata_session.headers.update(
    {"User-Agent": LISTENBRAINZ_USER_AGENT, "Accept": "application/json"}
)
_configure_session(wikidata_session)

image_session = requests.Session()
image_session.headers.update(
    {
        "User-Agent": LISTENBRAINZ_USER_AGENT,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
)
_configure_session(image_session)

lastfm_session = requests.Session()
lastfm_session.headers.update(
    {"User-Agent": LASTFM_USER_AGENT, "Accept": "application/json"}
)
_configure_session(lastfm_session)

listenbrainz_aggregate_session = requests.Session()
listenbrainz_aggregate_session.headers.update(
    {"User-Agent": LISTENBRAINZ_USER_AGENT, "Accept": "application/json"}
)
_configure_no_retry_session(listenbrainz_aggregate_session)

lastfm_aggregate_session = requests.Session()
lastfm_aggregate_session.headers.update(
    {"User-Agent": LASTFM_USER_AGENT, "Accept": "application/json"}
)
_configure_no_retry_session(lastfm_aggregate_session)

librefm_session = requests.Session()
librefm_session.headers.update(
    {"User-Agent": LIBREFM_USER_AGENT, "Accept": "application/json"}
)
librefm_session._upstream_pacer = _RatePacer(LIBREFM_MIN_INTERVAL)
_configure_session(librefm_session)

librefm_aggregate_session = requests.Session()
librefm_aggregate_session.headers.update(
    {"User-Agent": LIBREFM_USER_AGENT, "Accept": "application/json"}
)
librefm_aggregate_session._upstream_pacer = _RatePacer(LIBREFM_MIN_INTERVAL)
_configure_no_retry_session(librefm_aggregate_session)

musicbrainz_aggregate_session = requests.Session()
musicbrainz_aggregate_session.headers.update(
    {"User-Agent": MUSICBRAINZ_USER_AGENT, "Accept": "application/json"}
)
_configure_no_retry_session(musicbrainz_aggregate_session)

deezer_session = requests.Session()
deezer_session.headers.update(
    {"User-Agent": LASTFM_USER_AGENT, "Accept": "application/json"}
)
_configure_session(deezer_session)


def request_with_handling(
    session: requests.Session,
    url: str,
    *,
    params: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    allow_redirects: bool = True,
) -> RequestsResponse:
    """Perform a GET request with shared retry and error handling."""
    _pace(session)
    last_exc: Optional[Exception] = None
    attempts = 0
    while True:
        try:
            response = session.get(
                url,
                params=params,
                timeout=timeout or HTTP_TIMEOUT,
                allow_redirects=allow_redirects,
            )
        except RequestException as exc:
            last_exc = exc
            if attempts >= 2:
                abort(502, description=f"Upstream request failed: {last_exc}")
            attempts += 1
            time.sleep(0.3 * attempts)
            _pace(session)
            continue
        if response.status_code == 429 and attempts < 4:
            attempts += 1
            time.sleep(_retry_after_seconds(response))
            _pace(session)
            continue
        return response
