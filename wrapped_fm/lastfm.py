"""Last.fm statistics helpers."""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flask import abort

from .config import (
    AVERAGE_TRACK_LENGTH_MINUTES,
    DEEZER_API,
    IGNORED_TAGS,
    LASTFM_API,
    LASTFM_API_KEY,
    POPULAR_GENRES,
)
from .http import deezer_session, lastfm_session, request_with_handling

LASTFM_PERIOD = "12month"
SECONDS_PER_YEAR = 31_557_600  # 365.25 days
LASTFM_AVERAGE_SAMPLE_LIMIT = 150
MAX_TAG_RESULTS = 25


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
    node: Iterable = payload
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


def get_lastfm_top_artists(username: str, limit: int) -> List[str]:
    payload = _call_lastfm(
        "user.gettopartists",
        {
            "user": username,
            "period": LASTFM_PERIOD,
            "limit": str(limit),
        },
    )
    names = _extract_names(payload, ("topartists", "artist"))
    return names[:limit]


def get_lastfm_top_tracks(username: str, limit: int) -> List[str]:
    payload = _call_lastfm(
        "user.gettoptracks",
        {
            "user": username,
            "period": LASTFM_PERIOD,
            "limit": str(limit),
        },
    )
    names = _extract_names(payload, ("toptracks", "track"))
    return names[:limit]


def get_lastfm_top_albums(username: str, limit: int) -> List[str]:
    payload = _call_lastfm(
        "user.gettopalbums",
        {
            "user": username,
            "period": LASTFM_PERIOD,
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
    payload = _call_lastfm(
        "track.getInfo",
        {
            "artist": artist_name,
            "track": track_name,
        },
    )
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


def _calculate_lastfm_average_track_minutes(username: str) -> float:
    payload = _call_lastfm(
        "user.gettoptracks",
        {
            "user": username,
            "period": LASTFM_PERIOD,
            "limit": str(LASTFM_AVERAGE_SAMPLE_LIMIT),
        },
    )
    tracks = (payload.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    total_length_ms = 0
    total_listens = 0
    missing_duration_keys: List[Tuple[str, str]] = []
    provided_durations: Dict[Tuple[str, str], int] = {}
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


def _fetch_lastfm_total_listens(username: str) -> int:
    now = int(time.time())
    start = now - SECONDS_PER_YEAR
    payload = _call_lastfm(
        "user.getweeklytrackchart",
        {
            "user": username,
            "from": str(start),
            "to": str(now),
        },
    )
    chart = payload.get("weeklytrackchart", {})
    tracks = chart.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not isinstance(tracks, list):
        return 0
    total_listens = 0
    for entry in tracks:
        if not isinstance(entry, dict):
            continue
        try:
            plays = int(entry.get("playcount", 0))
        except (TypeError, ValueError):
            plays = 0
        if plays > 0:
            total_listens += plays
    return total_listens


def estimate_lastfm_listen_minutes(username: str) -> str:
    total_listens = _fetch_lastfm_total_listens(username)
    if total_listens <= 0:
        return "0"

    average_minutes = _calculate_lastfm_average_track_minutes(username)
    total_minutes = max(0, int(round(total_listens * average_minutes)))
    minutes = max(0, total_minutes)
    return f"{minutes:,}"


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


def get_lastfm_top_genre(username: str) -> str:
    artists = get_lastfm_top_artists(username, 10)
    if not artists:
        return "No genre"
    popular_counter: Counter[str] = Counter()
    fallback_counter: Counter[str] = Counter()
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
    popular_counter: Counter[str] = Counter()
    fallback_counter: Counter[str] = Counter()
    for tag, weight in tags:
        fallback_counter[tag] += weight
        if tag in POPULAR_GENRES:
            popular_counter[tag] += weight
    return _select_tag_from_counters(popular_counter, fallback_counter)
