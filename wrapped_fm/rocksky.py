"""Rocksky stats through its public xrpc api."""

from __future__ import annotations

import datetime
import logging
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from flask import abort

from .cache import TTLCache
from .config import AVERAGE_TRACK_LENGTH_MINUTES, ROCKSKY_API
from .date_range import DateRange
from .http import listenbrainz_session, request_with_handling
from .musicbrainz import lookup_artist_tag, search_artist_mbid


logger = logging.getLogger("wrapped_fm")

GENRE_ARTIST_SAMPLE = 4
DURATION_SAMPLE = 50
# atproto handle or did
_HANDLE_RE = re.compile(r"^(did:[a-z]+:[A-Za-z0-9._:%-]{1,200}|[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?)$")

stats_cache = TTLCache(ttl=120, max_size=128)


def normalise_handle(raw: Optional[str]) -> str:
    value = (raw or "").strip().lstrip("@")
    if not value:
        abort(400, description="Enter your Rocksky handle.")
    if not _HANDLE_RE.match(value):
        abort(400, description="That Rocksky handle doesn't look right.")
    return value.lower() if not value.startswith("did:") else value


def _get(method: str, params: Dict[str, str]) -> Dict:
    response = request_with_handling(listenbrainz_session, f"{ROCKSKY_API}/{method}", params=params, timeout=15)
    if response.status_code in (400, 404):
        abort(404, description="Rocksky user not found")
    if not response.ok:
        abort(502, description=f"Rocksky returned an error ({response.status_code}).")
    try:
        data = response.json()
    except ValueError:
        abort(502, description="Rocksky sent back something that isn't json.")
    if not isinstance(data, dict):
        abort(502, description="Rocksky sent back something unexpected.")
    return data


def _iso(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(ts: int) -> str:
    return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc).strftime("%Y-%m-%d")


def _is_all_time(range_obj: Optional[DateRange]) -> bool:
    return range_obj is None or range_obj.preset == "all_time"


def _range_params(range_obj: Optional[DateRange]) -> Dict[str, str]:
    if _is_all_time(range_obj):
        return {}
    return {"startDate": _iso(range_obj.start_ts), "endDate": _iso(range_obj.end_ts)}


def _scrobble_count(handle: str, range_obj: Optional[DateRange]) -> Optional[int]:
    try:
        if _is_all_time(range_obj):
            value = _get("app.rocksky.stats.getStats", {"did": handle}).get("scrobbles")
            return value if isinstance(value, int) else None
        end = max(range_obj.start_ts, range_obj.end_ts - 1)
        days = _get(
            "app.rocksky.charts.getScrobblesChart",
            {"did": handle, "from": _day(range_obj.start_ts), "to": _day(end)},
        ).get("scrobbles")
    except Exception as exc:
        logger.info("rocksky scrobble count failed for %s: %s", handle, exc)
        return None
    if not isinstance(days, list):
        return None
    return sum(int(day.get("count") or 0) for day in days if isinstance(day, dict))


def _top_genre(artists: List[Dict]) -> str:
    def lookup(artist: Dict) -> Optional[str]:
        tags = artist.get("tags")
        if isinstance(tags, list) and tags and isinstance(tags[0], str):
            return tags[0]
        try:
            mbid = search_artist_mbid(str(artist.get("name") or ""))
            return lookup_artist_tag(mbid) if mbid else None
        except Exception:
            return None

    sample = [artist for artist in artists if artist.get("name")][:GENRE_ARTIST_SAMPLE]
    if not sample:
        return "no genre"
    with ThreadPoolExecutor(max_workers=len(sample)) as pool:
        tags = Counter(tag for tag in pool.map(lookup, sample) if tag)
    return tags.most_common(1)[0][0] if tags else "no genre"


def fetch_rocksky_stats(handle: str, range_obj: Optional[DateRange], count: int = 5) -> Dict:
    params = _range_params(range_obj)
    key = (handle, tuple(sorted(params.items())), count)
    return stats_cache.get_or_compute(key, lambda: _fetch_uncached(handle, range_obj, params, count))


def _fetch_uncached(handle: str, range_obj: Optional[DateRange], params: Dict[str, str], count: int) -> Dict:
    with ThreadPoolExecutor(max_workers=3) as pool:
        artists_future = pool.submit(_get, "app.rocksky.actor.getActorArtists", {"did": handle, "limit": str(count), **params})
        songs_future = pool.submit(_get, "app.rocksky.actor.getActorSongs", {"did": handle, "limit": str(DURATION_SAMPLE), **params})
        total_future = pool.submit(_scrobble_count, handle, range_obj)
        artists = [a for a in artists_future.result().get("artists") or [] if isinstance(a, dict)]
        songs = [s for s in songs_future.result().get("tracks") or [] if isinstance(s, dict)]
        total = total_future.result()

    known_ms = 0
    known_plays = 0
    sampled_plays = 0
    for song in songs:
        plays = song.get("playCount")
        plays = plays if isinstance(plays, int) and plays > 0 else 0
        sampled_plays += plays
        duration = song.get("duration")
        if isinstance(duration, (int, float)) and duration > 0 and plays:
            known_ms += duration * plays
            known_plays += plays
    avg_minutes = (known_ms / known_plays / 60000.0) if known_plays else AVERAGE_TRACK_LENGTH_MINUTES
    scrobbles = total if isinstance(total, int) and total >= 0 else sampled_plays
    minutes = int(scrobbles * avg_minutes)

    tracks = [song for song in songs if song.get("title")][:count]
    return {
        "artists": [str(a["name"]) for a in artists if a.get("name")][:count],
        "tracks": [str(song["title"]) for song in tracks],
        "track_artists": [str(song.get("artist") or "") for song in tracks],
        "minutes": f"{minutes:,}",
        "scrobbles": scrobbles,
        "genre": _top_genre(artists),
        "name": handle[:64],
    }
