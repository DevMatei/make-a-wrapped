"""HTTP client configuration and helpers."""

from __future__ import annotations

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
    LISTENBRAINZ_API,
    LISTENBRAINZ_USER_AGENT,
    MUSICBRAINZ_API,
    MUSICBRAINZ_USER_AGENT,
    WIKIDATA_ENTITY_API,
)


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
) -> RequestsResponse:
    """Perform a GET request with shared retry and error handling."""
    last_exc: Optional[Exception] = None
    for attempt in range(3):
        try:
            response = session.get(url, params=params, timeout=timeout or HTTP_TIMEOUT)
            return response
        except RequestException as exc:
            last_exc = exc
            time.sleep(0.3 * (attempt + 1))
    abort(502, description=f"Upstream request failed: {last_exc}")
