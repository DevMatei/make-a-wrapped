"""Maloja stats through its native mlj_1 api."""

from __future__ import annotations

import datetime
import ipaddress
import json
import logging
import socket
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from flask import abort

from .cache import TTLCache
from .config import AVERAGE_TRACK_LENGTH_MINUTES, LISTENBRAINZ_USER_AGENT, MALOJA_ALLOW_PRIVATE
from .date_range import DateRange
from .musicbrainz import lookup_artist_tag, search_artist_mbid


logger = logging.getLogger("wrapped_fm")

MALOJA_TIMEOUT = 20
MALOJA_MAX_BYTES = 20 * 1024 * 1024
GENRE_ARTIST_SAMPLE = 4

maloja_session = requests.Session()
maloja_session.headers.update({"User-Agent": LISTENBRAINZ_USER_AGENT, "Accept": "application/json"})
stats_cache = TTLCache(ttl=120, max_size=128)


def _host_is_public(host: str, port: int) -> bool:
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (OSError, UnicodeError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def normalise_server_url(raw: Optional[str]) -> str:
    value = (raw or "").strip().rstrip("/")
    if not value:
        abort(400, description="Enter your Maloja server url.")
    if "://" not in value:
        value = f"https://{value}"
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        abort(400, description="That Maloja url doesn't look right.")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        abort(400, description="That Maloja url doesn't look right.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        abort(400, description="Leave logins and query strings out of the Maloja url.")
    path = parsed.path.rstrip("/")
    for suffix in ("/apis/mlj_1", "/apis/listenbrainz/1", "/apis/listenbrainz"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
    host = parsed.hostname
    if not MALOJA_ALLOW_PRIVATE and not _host_is_public(host, port or (443 if parsed.scheme == "https" else 80)):
        abort(400, description="That Maloja server isn't reachable from here. It needs a public address.")
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc = f"{netloc}:{port}"
    return f"{parsed.scheme}://{netloc}{path}"


def _get(base: str, endpoint: str, params: Optional[Dict[str, str]] = None) -> Dict:
    url = f"{base}/apis/mlj_1/{endpoint}"
    try:
        response = maloja_session.get(url, params=params, timeout=MALOJA_TIMEOUT, allow_redirects=False, stream=True)
    except requests.RequestException as exc:
        logger.info("maloja request failed for %s: %s", base, exc)
        abort(502, description="Couldn't reach that Maloja server.")
    with response:
        if response.status_code in (301, 302, 303, 307, 308):
            abort(502, description="That Maloja server redirected somewhere else. Use the final url.")
        if response.status_code == 404:
            abort(404, description="That doesn't look like a Maloja server (no /apis/mlj_1).")
        if response.status_code in (401, 403):
            abort(403, description="That Maloja server doesn't allow public reads.")
        if not response.ok:
            abort(502, description=f"Maloja returned an error ({response.status_code}).")
        body = bytearray()
        for chunk in response.iter_content(65536):
            body.extend(chunk)
            if len(body) > MALOJA_MAX_BYTES:
                abort(502, description="Maloja sent back way too much data.")
    try:
        data = json.loads(bytes(body).decode("utf-8"))
    except ValueError:
        abort(502, description="Maloja sent back something that isn't json.")
    if not isinstance(data, dict):
        abort(502, description="Maloja sent back something unexpected.")
    return data


def _range_params(range_obj: Optional[DateRange]) -> Dict[str, str]:
    if range_obj is None or range_obj.preset == "all_time":
        return {}
    start = datetime.datetime.fromtimestamp(range_obj.start_ts, tz=datetime.timezone.utc).date()
    # maloja's "to" day is inclusive
    end = datetime.datetime.fromtimestamp(max(range_obj.start_ts, range_obj.end_ts - 1), tz=datetime.timezone.utc).date()
    return {"from": start.strftime("%Y/%m/%d"), "to": end.strftime("%Y/%m/%d")}


def _list(data: Dict) -> List[Dict]:
    items = data.get("list")
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _track_artists(track: Dict) -> str:
    artists = track.get("artists")
    if isinstance(artists, list):
        return ", ".join(str(a) for a in artists if a)
    return ""


def _top_genre(artist_names: List[str]) -> str:
    def lookup(name: str) -> Optional[str]:
        try:
            mbid = search_artist_mbid(name)
            return lookup_artist_tag(mbid) if mbid else None
        except Exception:
            return None

    sample = artist_names[:GENRE_ARTIST_SAMPLE]
    if not sample:
        return "no genre"
    with ThreadPoolExecutor(max_workers=len(sample)) as pool:
        tags = Counter(tag for tag in pool.map(lookup, sample) if tag)
    return tags.most_common(1)[0][0] if tags else "no genre"


def summarise(artist_rows: List[Dict], track_rows: List[Dict], total: Optional[int], count: int) -> Dict:
    artists = [str(row.get("artist")) for row in artist_rows if row.get("artist")]

    tracks: List[Tuple[str, str]] = []
    known_ms = 0
    known_plays = 0
    total_plays = 0
    for row in track_rows:
        track = row.get("track") if isinstance(row.get("track"), dict) else {}
        plays = row.get("scrobbles")
        plays = plays if isinstance(plays, int) and plays > 0 else 0
        total_plays += plays
        title = track.get("title")
        if title and len(tracks) < count:
            tracks.append((str(title), _track_artists(track)))
        length = track.get("length")
        if isinstance(length, (int, float)) and length > 0 and plays:
            known_ms += length * 1000 * plays
            known_plays += plays

    scrobbles = total if isinstance(total, int) and total >= 0 else total_plays
    avg_minutes = (known_ms / known_plays / 60000.0) if known_plays else AVERAGE_TRACK_LENGTH_MINUTES
    minutes = int(scrobbles * avg_minutes)
    return {
        "artists": artists[:count],
        "tracks": [title for title, _ in tracks],
        "track_artists": [artist for _, artist in tracks],
        "minutes": f"{minutes:,}",
        "scrobbles": scrobbles,
    }


def fetch_maloja_stats(server: str, range_obj: Optional[DateRange], count: int = 5) -> Dict:
    params = _range_params(range_obj)
    key = (server, tuple(sorted(params.items())), count)
    return stats_cache.get_or_compute(key, lambda: _fetch_uncached(server, params, count))


def _fetch_uncached(server: str, params: Dict[str, str], count: int) -> Dict:
    with ThreadPoolExecutor(max_workers=4) as pool:
        info_future = pool.submit(_get, server, "serverinfo")
        artists_future = pool.submit(_get, server, "charts/artists", params)
        tracks_future = pool.submit(_get, server, "charts/tracks", params)
        total_future = pool.submit(_get, server, "numscrobbles", params)
        try:
            info = info_future.result()
        except Exception:
            info = {}
        artist_rows = _list(artists_future.result())
        track_rows = _list(tracks_future.result())
        try:
            total = total_future.result().get("amount")
        except Exception:
            total = None

    result = summarise(artist_rows, track_rows, total, count)
    all_artists = [str(row.get("artist")) for row in artist_rows if row.get("artist")]
    result["genre"] = _top_genre(all_artists)
    result["name"] = str(info.get("name") or urlparse(server).hostname or "maloja")[:64]
    return result
