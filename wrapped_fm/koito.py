"""Koito stats through its web api."""

from __future__ import annotations

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from flask import abort

from .cache import TTLCache
from .config import LISTENBRAINZ_USER_AGENT, MALOJA_ALLOW_PRIVATE
from .date_range import DateRange
from .maloja import _host_is_public
from .musicbrainz import lookup_artist_tag, search_artist_mbid


logger = logging.getLogger("wrapped_fm")

KOITO_TIMEOUT = 20
KOITO_MAX_BYTES = 5 * 1024 * 1024
GENRE_ARTIST_SAMPLE = 4

koito_session = requests.Session()
koito_session.headers.update({"User-Agent": LISTENBRAINZ_USER_AGENT, "Accept": "application/json"})
stats_cache = TTLCache(ttl=120, max_size=128)


def normalise_server_url(raw: Optional[str]) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        abort(400, description="Enter your Koito server url.")
    if "://" not in value:
        value = f"https://{value}"
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        abort(400, description="That Koito url doesn't look right.")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        abort(400, description="That Koito url doesn't look right.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        abort(400, description="Leave logins and query strings out of the Koito url.")
    path = parsed.path.rstrip("/")
    for suffix in ("/apis/web/v1", "/apis/listenbrainz/1", "/apis/listenbrainz"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    host = parsed.hostname
    if not MALOJA_ALLOW_PRIVATE and not _host_is_public(host, port or (443 if parsed.scheme == "https" else 80)):
        abort(400, description="That Koito server isn't reachable from here. It needs a public address.")
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc = f"{netloc}:{port}"
    return f"{parsed.scheme}://{netloc}{path}"


def _get(base: str, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict:
    url = f"{base}/apis/web/v1/{endpoint}"
    try:
        response = koito_session.get(url, params=params, timeout=KOITO_TIMEOUT, allow_redirects=False, stream=True)
    except requests.RequestException as exc:
        logger.info("koito request failed for %s: %s", base, exc)
        abort(502, description="Couldn't reach that Koito server.")
    with response:
        if response.status_code in (301, 302, 303, 307, 308):
            abort(502, description="That Koito server redirected somewhere else. Use the final url.")
        if response.status_code == 404:
            abort(404, description="That doesn't look like a Koito server (no /apis/web/v1).")
        if response.status_code in (401, 403):
            abort(403, description="That Koito server has the login gate on, so its stats aren't public.")
        if not response.ok:
            abort(502, description=f"Koito returned an error ({response.status_code}).")
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > KOITO_MAX_BYTES:
                abort(502, description="Koito sent back way too much data.")
    try:
        data = json.loads(bytes(body).decode("utf-8"))
    except ValueError:
        abort(502, description="Koito sent back something that isn't json.")
    if not isinstance(data, dict):
        abort(502, description="Koito sent back something unexpected.")
    return data


def _range_params(range_obj: Optional[DateRange]) -> Dict[str, str]:
    if range_obj is None or range_obj.preset == "all_time":
        return {"period": "all_time"}
    return {"from": str(range_obj.start_ts), "to": str(max(range_obj.start_ts, range_obj.end_ts - 1))}


def _items(data: Dict) -> List[Dict]:
    items = data.get("items")
    if not isinstance(items, list):
        return []
    rows = []
    for row in items:
        item = row.get("item") if isinstance(row, dict) else None
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _artist_names(item: Dict) -> str:
    artists = item.get("artists")
    if isinstance(artists, list):
        return ", ".join(str(a.get("name")) for a in artists if isinstance(a, dict) and a.get("name"))
    return ""


def _top_genre(artists: List[Dict]) -> str:
    def lookup(artist: Dict) -> Optional[str]:
        try:
            mbid = artist.get("musicbrainz_id") or search_artist_mbid(str(artist.get("name") or ""))
            return lookup_artist_tag(mbid) if mbid else None
        except Exception:
            return None

    sample = [artist for artist in artists if artist.get("name")][:GENRE_ARTIST_SAMPLE]
    if not sample:
        return "no genre"
    with ThreadPoolExecutor(max_workers=len(sample)) as pool:
        tags = Counter(tag for tag in pool.map(lookup, sample) if tag)
    return tags.most_common(1)[0][0] if tags else "no genre"


def fetch_koito_stats(server: str, range_obj: Optional[DateRange], count: int = 5) -> Dict:
    params = _range_params(range_obj)
    key = (server, tuple(sorted(params.items())), count)
    return stats_cache.get_or_compute(key, lambda: _fetch_uncached(server, params, count))


def _fetch_uncached(server: str, params: Dict[str, str], count: int) -> Dict:
    top_params = {**params, "limit": str(count)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        artists_future = pool.submit(_get, server, "top/artists", top_params)
        tracks_future = pool.submit(_get, server, "top/tracks", top_params)
        stats_future = pool.submit(_get, server, "stats", params)
        artist_rows = _items(artists_future.result())
        track_rows = _items(tracks_future.result())
        try:
            stats = stats_future.result()
        except Exception:
            stats = {}

    minutes = stats.get("minutes_listened")
    if not isinstance(minutes, int) or minutes < 0:
        minutes = sum(int(row.get("time_listened") or 0) for row in track_rows) // 60
    tracks = [row for row in track_rows if row.get("title")][:count]
    return {
        "artists": [str(row["name"]) for row in artist_rows if row.get("name")][:count],
        "tracks": [str(row["title"]) for row in tracks],
        "track_artists": [_artist_names(row) for row in tracks],
        "minutes": f"{minutes:,}",
        "scrobbles": stats.get("listen_count") if isinstance(stats.get("listen_count"), int) else None,
        "genre": _top_genre(artist_rows),
        "name": str(urlparse(server).hostname or "koito")[:64],
    }
