"""Last.fm statistics helpers."""

from __future__ import annotations

import datetime
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from flask import abort

from .config import (
    AVERAGE_TRACK_LENGTH_MINUTES,
    DEEZER_API,
    IGNORED_TAGS,
    LASTFM_API,
    LASTFM_API_KEY,
    POPULAR_GENRES,
)
from .date_range import DateRange
from .http import deezer_session, lastfm_aggregate_session, lastfm_session, request_with_handling


logger = logging.getLogger("wrapped_fm")


DEFAULT_LASTFM_PERIOD = "12month"
LASTFM_AVERAGE_SAMPLE_LIMIT = 150
MAX_TAG_RESULTS = 25

RECENTTRACKS_PAGE_SIZE = 200
RECENTTRACKS_MAX_PAGES = 6
RECENTTRACKS_MAX_LISTENS = RECENTTRACKS_PAGE_SIZE * RECENTTRACKS_MAX_PAGES
RECENTTRACKS_CONCURRENCY = 2
RECENTTRACKS_TIMEOUT = 3
RECENTTRACKS_BUDGET = 12

recenttracks_cache: Dict[Tuple[str, int, int], Tuple[float, "_AggregatedRecent"]] = {}
RECENTTRACKS_CACHE_TTL = 300
RECENTTRACKS_CACHE_SIZE = 256


@dataclass
class _AggregatedRecent:
    top_artists: List[Tuple[str, int]] = field(default_factory=list)
    top_tracks: List[Tuple[str, int]] = field(default_factory=list)
    top_albums: List[Tuple[str, int]] = field(default_factory=list)
    total_listen_count: int = 0
    reached_limit: bool = False
    failed: bool = False


def _ensure_lastfm_ready() -> None:
    if not LASTFM_API_KEY:
        abort(503, description="Last.fm support is not configured on this server.")


def _call_lastfm(method: str, params: Optional[Dict[str, str]] = None) -> Dict:
    _ensure_lastfm_ready()
    query = {
        "method": method,
        "api_key": LASTFM_API_KEY,
        "format": "json",
    }
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    response = request_with_handling(lastfm_session, LASTFM_API, params=query)
    try:
        data = response.json()
    except ValueError:
        abort(502, description="Invalid response from Last.fm")
    error_code = data.get("error")
    if error_code:
        message = data.get("message", "Last.fm request failed")
        if error_code in {6, 7, 29}:
            abort(404, description=message)
        abort(502, description=message)
    return data


def _call_deezer(path: str, params: Optional[Dict[str, str]] = None) -> Dict:
    response = request_with_handling(
        deezer_session,
        f"{DEEZER_API.rstrip('/')}/{path.lstrip('/')}",
        params=params,
        timeout=8,
    )
    try:
        return response.json()
    except ValueError:
        return {}


def _extract_names(payload: Dict, path: Sequence[str]) -> List[str]:
    node = payload
    for key in path:
        if isinstance(node, dict):
            node = node.get(key) or []
        else:
            return []
    if not isinstance(node, list):
        return []
    names: List[str] = []
    for entry in node:
        if isinstance(entry, dict):
            value = entry.get("name")
            if isinstance(value, str) and value.strip():
                names.append(value.strip())
    return names


def _resolve_lastfm_period(range_obj: Optional[DateRange]) -> str:
    if range_obj and range_obj.lastfm_period:
        return range_obj.lastfm_period
    return DEFAULT_LASTFM_PERIOD


def _top_artist_names(aggregated: _AggregatedRecent, limit: int) -> List[str]:
    return [name for name, _ in aggregated.top_artists[:limit]]


def _top_track_names(aggregated: _AggregatedRecent, limit: int) -> List[str]:
    return [name for name, _ in aggregated.top_tracks[:limit]]


def _top_album_names(aggregated: _AggregatedRecent, limit: int) -> List[str]:
    return [name for name, _ in aggregated.top_albums[:limit]]


def get_lastfm_top_artists(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
) -> List[str]:
    if range_obj and (range_obj.is_custom or not range_obj.lastfm_period):
        aggregated = _aggregate_recent_in_range(username, range_obj)
        return _top_artist_names(aggregated, limit)

    payload = _call_lastfm(
        "user.gettopartists",
        {
            "user": username,
            "period": _resolve_lastfm_period(range_obj),
            "limit": str(limit),
        },
    )
    names = _extract_names(payload, ("topartists", "artist"))
    return names[:limit]


def get_lastfm_top_tracks(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
) -> List[str]:
    if range_obj and (range_obj.is_custom or not range_obj.lastfm_period):
        aggregated = _aggregate_recent_in_range(username, range_obj)
        return _top_track_names(aggregated, limit)

    payload = _call_lastfm(
        "user.gettoptracks",
        {
            "user": username,
            "period": _resolve_lastfm_period(range_obj),
            "limit": str(limit),
        },
    )
    names = _extract_names(payload, ("toptracks", "track"))
    return names[:limit]


def get_lastfm_top_albums(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
) -> List[str]:
    if range_obj and (range_obj.is_custom or not range_obj.lastfm_period):
        aggregated = _aggregate_recent_in_range(username, range_obj)
        return _top_album_names(aggregated, limit)

    payload = _call_lastfm(
        "user.gettopalbums",
        {
            "user": username,
            "period": _resolve_lastfm_period(range_obj),
            "limit": str(limit),
        },
    )
    names = _extract_names(payload, ("topalbums", "album"))
    return names[:limit]


def _normalise_duration(value: Optional[str]) -> int:
    if not value:
        return int(AVERAGE_TRACK_LENGTH_MINUTES * 60000)
    try:
        duration = int(value)
        if duration <= 0:
            raise ValueError
        if duration < 1000:
            duration *= 1000
    except (TypeError, ValueError):
        duration = int(AVERAGE_TRACK_LENGTH_MINUTES * 60000)
    return duration


@lru_cache(maxsize=2048)
def _fetch_track_duration(artist_name: str, track_name: str) -> int:
    try:
        payload = _call_lastfm(
            "track.getInfo",
            {
                "artist": artist_name,
                "track": track_name,
            },
        )
    except Exception:
        payload = None
    track_info = payload.get("track") if isinstance(payload, dict) else None
    duration = None
    if isinstance(track_info, dict):
        duration = track_info.get("duration")
    resolved = _normalise_duration(duration if isinstance(duration, str) else str(duration or ""))
    if resolved and resolved != int(AVERAGE_TRACK_LENGTH_MINUTES * 60000):
        return resolved
    query = _call_deezer(
        "search",
        {
            "q": f'artist:"{artist_name}" track:"{track_name}"',
            "limit": "1",
        },
    )
    data = query.get("data")
    if isinstance(data, dict):
        data = [data]
    if isinstance(data, list) and data:
        entry = data[0]
        try:
            seconds = int(entry.get("duration", 0))
        except (TypeError, ValueError):
            seconds = 0
        if seconds > 0:
            return seconds * 1000
    return resolved


def _calculate_lastfm_average_track_minutes(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
) -> float:
    period = _resolve_lastfm_period(range_obj)
    if range_obj and (range_obj.is_custom or not range_obj.lastfm_period):
        aggregated = _aggregate_recent_in_range(username, range_obj)
        if not aggregated.top_tracks:
            return AVERAGE_TRACK_LENGTH_MINUTES
        total_length_ms = 0
        total_listens = 0
        for name, plays in aggregated.top_tracks[:LASTFM_AVERAGE_SAMPLE_LIMIT]:
            if " - " in name:
                artist_name, track_name = name.split(" - ", 1)
            else:
                artist_name, track_name = "", name
            duration = _fetch_track_duration(artist_name, track_name) if artist_name else int(AVERAGE_TRACK_LENGTH_MINUTES * 60000)
            total_length_ms += duration * plays
            total_listens += plays
        if total_listens <= 0 or total_length_ms <= 0:
            return AVERAGE_TRACK_LENGTH_MINUTES
        return (total_length_ms / total_listens) / 60000.0

    payload = _call_lastfm(
        "user.gettoptracks",
        {
            "user": username,
            "period": period,
            "limit": str(LASTFM_AVERAGE_SAMPLE_LIMIT),
        },
    )
    tracks = (payload.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    total_length_ms = 0
    total_listens = 0
    missing_duration_keys: List[Tuple[str, str]] = []
    provided_durations: Dict[Tuple[str, int], int] = {}
    plays_by_key: Dict[Tuple[str, str], int] = {}

    for entry in tracks[:LASTFM_AVERAGE_SAMPLE_LIMIT]:
        if not isinstance(entry, dict):
            continue
        track_name = entry.get("name")
        artist_info = entry.get("artist") or {}
        artist_name = None
        if isinstance(artist_info, dict):
            artist_name = artist_info.get("name")
        if not artist_name or not track_name:
            continue
        try:
            plays = int(entry.get("playcount", 0))
        except (TypeError, ValueError):
            plays = 0
        if plays <= 0:
            continue
        duration = entry.get("duration")
        key = (artist_name, track_name)
        plays_by_key[key] = plays
        if duration not in {None, "", "0"}:
            provided_durations[key] = _normalise_duration(str(duration))
        else:
            missing_duration_keys.append(key)
        total_listens += plays

    if missing_duration_keys:
        def _lookup(args: Tuple[str, str]) -> int:
            return _fetch_track_duration(args[0], args[1])

        with ThreadPoolExecutor(max_workers=6) as pool:
            for key, duration in zip(missing_duration_keys, pool.map(_lookup, missing_duration_keys)):
                provided_durations[key] = duration

    for key, duration in provided_durations.items():
        plays = plays_by_key.get(key, 0)
        if plays <= 0:
            continue
        total_length_ms += duration * plays

    if total_listens <= 0 or total_length_ms <= 0:
        return AVERAGE_TRACK_LENGTH_MINUTES
    return (total_length_ms / total_listens) / 60000.0


def _fetch_lastfm_total_listens(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
) -> int:
    if range_obj:
        start = range_obj.start_ts
        end = range_obj.end_ts - 1
    else:
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        start_dt = datetime.datetime(now_dt.year, 1, 1, tzinfo=datetime.timezone.utc)
        end = int(time.time())
        start = int(start_dt.timestamp())
    payload = _call_lastfm(
        "user.getrecenttracks",
        {
            "user": username,
            "from": str(start),
            "to": str(end),
            "limit": "1",
        },
    )
    recenttracks = payload.get("recenttracks", {})
    if not isinstance(recenttracks, dict):
        return 0
    attr = recenttracks.get("@attr", {})
    if not isinstance(attr, dict):
        return 0
    try:
        total_listens = int(attr.get("total", 0))
    except (TypeError, ValueError):
        total_listens = 0
    return total_listens


def estimate_lastfm_listen_minutes(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
) -> str:
    total_listens = _fetch_lastfm_total_listens(username, range_obj=range_obj)
    if total_listens <= 0:
        return "0"

    average_minutes = _calculate_lastfm_average_track_minutes(username, range_obj=range_obj)
    total_minutes = max(0, int(round(total_listens * average_minutes)))
    minutes = max(0, total_minutes)
    return f"{minutes:,}"


def _aggregate_recent_in_range(username: str, range_obj: DateRange) -> _AggregatedRecent:
    cache_key = (username, range_obj.start_ts, range_obj.end_ts)
    now = time.time()
    cached = recenttracks_cache.get(cache_key)
    if cached and now - cached[0] < RECENTTRACKS_CACHE_TTL:
        return cached[1]

    result = _AggregatedRecent()
    artist_counter: Counter = Counter()
    track_counter: Counter = Counter()
    album_counter: Counter = Counter()

    end_ts = range_obj.end_ts - 1
    start_ts = range_obj.start_ts
    pending: List[int] = [end_ts]

    def fetch_page(page_to: int) -> List[Dict]:
        try:
            response = lastfm_aggregate_session.get(
                LASTFM_API,
                params={
                    "method": "user.getrecenttracks",
                    "api_key": LASTFM_API_KEY,
                    "format": "json",
                    "user": username,
                    "from": str(start_ts),
                    "to": str(page_to),
                    "limit": str(RECENTTRACKS_PAGE_SIZE),
                },
                timeout=RECENTTRACKS_TIMEOUT,
            )
            if not response.ok:
                return []
            try:
                data = response.json()
            except ValueError:
                return []
        except Exception as exc:
            logger.debug("Last.fm recenttracks fetch failed for %s: %s", username, exc)
            return []
        if not isinstance(data, dict):
            return []
        recenttracks = data.get("recenttracks", {})
        tracks = recenttracks.get("track") if isinstance(recenttracks, dict) else []
        if isinstance(tracks, dict):
            tracks = [tracks]
        return tracks or []

    def parse_tracks(tracks: List[Dict], page_to: int) -> Tuple[int, int]:
        page_oldest = page_to
        count = 0
        for entry in tracks:
            if not isinstance(entry, dict):
                continue
            uts_value = entry.get("date")
            uts = None
            if isinstance(uts_value, dict):
                try:
                    uts = int(uts_value.get("uts", 0))
                except (TypeError, ValueError):
                    uts = None
            if uts is None or uts < start_ts or uts > end_ts:
                continue
            page_oldest = min(page_oldest, uts)
            artist_info = entry.get("artist") or {}
            artist_name = (artist_info.get("#text") or "").strip() if isinstance(artist_info, dict) else ""
            album_info = entry.get("album") or {}
            album_name = (album_info.get("#text") or "").strip() if isinstance(album_info, dict) else ""
            track_name = (entry.get("name") or "").strip()
            if artist_name:
                artist_counter[artist_name] += 1
            if track_name and artist_name:
                track_counter[track_name] += 1
            if album_name and artist_name:
                album_counter[f"{artist_name} - {album_name}"] += 1
            count += 1
        return count, page_oldest

    try:
        deadline = time.monotonic() + RECENTTRACKS_BUDGET
        with ThreadPoolExecutor(max_workers=RECENTTRACKS_CONCURRENCY) as pool:
            for _ in range(RECENTTRACKS_MAX_PAGES):
                if result.total_listen_count >= RECENTTRACKS_MAX_LISTENS:
                    result.reached_limit = True
                    break
                if not pending:
                    break
                if time.monotonic() >= deadline:
                    break
                batch = pending[:RECENTTRACKS_CONCURRENCY]
                pending = pending[RECENTTRACKS_CONCURRENCY:]
                page_results = list(pool.map(fetch_page, batch))
                any_full = False
                for page_to, tracks in zip(batch, page_results):
                    if not tracks:
                        continue
                    count, page_oldest = parse_tracks(tracks, page_to)
                    result.total_listen_count += count
                    if len(tracks) >= RECENTTRACKS_PAGE_SIZE:
                        any_full = True
                        next_to = page_oldest - 1
                        if next_to < page_to and next_to >= start_ts:
                            pending.append(next_to)
                if not any_full:
                    break
    except Exception as exc:
        logger.warning("Last.fm aggregation failed for %s: %s", username, exc)
        result.failed = True

    result.top_artists = artist_counter.most_common(50)
    result.top_tracks = track_counter.most_common(50)
    result.top_albums = album_counter.most_common(50)

    recenttracks_cache[cache_key] = (now, result)
    if len(recenttracks_cache) > RECENTTRACKS_CACHE_SIZE:
        oldest_key = min(recenttracks_cache.items(), key=lambda item: item[1][0])[0]
        recenttracks_cache.pop(oldest_key, None)

    return result


def _normalise_tag(name: str) -> str:
    normalised = name.strip().lower()
    if not normalised:
        return ""
    return normalised


@lru_cache(maxsize=512)
def _fetch_artist_tags(artist_name: str) -> List[Tuple[str, int]]:
    payload = _call_lastfm(
        "artist.getTopTags",
        {
            "artist": artist_name,
        },
    )
    tags = payload.get("toptags", {}).get("tag") or []
    if not isinstance(tags, list):
        return []
    results: List[Tuple[str, int]] = []
    for tag in tags[:MAX_TAG_RESULTS]:
        if not isinstance(tag, dict):
            continue
        name = tag.get("name")
        if not isinstance(name, str):
            continue
        normalised = _normalise_tag(name)
        if not normalised or normalised in IGNORED_TAGS:
            continue
        try:
            weight = int(tag.get("count", 0))
        except (TypeError, ValueError):
            weight = 0
        if weight <= 0:
            weight = 1
        results.append((normalised, weight))
    return results


def _select_tag_from_counters(preferred: Counter, fallback: Counter) -> str:
    counter = preferred if preferred else fallback
    if not counter:
        return "No genre"
    tag, _ = counter.most_common(1)[0]
    return tag.title()


def get_lastfm_top_genre(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
) -> str:
    artists = get_lastfm_top_artists(username, 10, range_obj=range_obj)
    if not artists:
        return "No genre"
    popular_counter: Counter = Counter()
    fallback_counter: Counter = Counter()
    for artist in artists:
        for tag, weight in _fetch_artist_tags(artist):
            fallback_counter[tag] += weight
            if tag in POPULAR_GENRES:
                popular_counter[tag] += weight
    return _select_tag_from_counters(popular_counter, fallback_counter)


def get_lastfm_artist_genre(artist_name: str) -> str:
    tags = _fetch_artist_tags(artist_name)
    if not tags:
        return "No genre"
    popular_counter: Counter = Counter()
    fallback_counter: Counter = Counter()
    for tag, weight in tags:
        fallback_counter[tag] += weight
        if tag in POPULAR_GENRES:
            popular_counter[tag] += weight
    return _select_tag_from_counters(popular_counter, fallback_counter)
