"""Last.fm statistics helpers."""

from __future__ import annotations

import datetime
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from flask import abort

from .cache import TTLCache
from .config import (
    AVERAGE_TRACK_LENGTH_MINUTES,
    DEEZER_API,
    IGNORED_TAGS,
    LASTFM_API,
    LASTFM_API_KEY,
    LIBREFM_API,
    LIBREFM_API_KEY,
    LIBREFM_DURATION_LOOKUP_LIMIT,
    POPULAR_GENRES,
)
from .date_range import DateRange
from .http import (
    _pace,
    deezer_session,
    lastfm_aggregate_session,
    lastfm_session,
    librefm_aggregate_session,
    librefm_session,
    request_with_handling,
)


logger = logging.getLogger("wrapped_fm")


@dataclass(frozen=True)
class _Provider:
    api: str
    api_key: str
    session: object
    aggregate_session: object


AUDIOSCROBBLER_PROVIDERS = {
    "lastfm": _Provider(
        api=LASTFM_API,
        api_key=LASTFM_API_KEY or "",
        session=lastfm_session,
        aggregate_session=lastfm_aggregate_session,
    ),
    "librefm": _Provider(
        api=LIBREFM_API,
        api_key=LIBREFM_API_KEY,
        session=librefm_session,
        aggregate_session=librefm_aggregate_session,
    ),
}
AUDIOSCROBBLER_SERVICES = tuple(AUDIOSCROBBLER_PROVIDERS)


def _resolve_provider(service: Optional[str]) -> _Provider:
    return AUDIOSCROBBLER_PROVIDERS.get(service or "lastfm", AUDIOSCROBBLER_PROVIDERS["lastfm"])


DEFAULT_LASTFM_PERIOD = "12month"
LASTFM_AVERAGE_SAMPLE_LIMIT = 150
DURATION_LOOKUP_LIMIT = 30
GENRE_ARTIST_SAMPLE = 6
MAX_TAG_RESULTS = 25
DURATION_LOOKUP_CONCURRENCY = 8
TAG_LOOKUP_CONCURRENCY = 10

RECENTTRACKS_PAGE_SIZE = 200
RECENTTRACKS_MAX_PAGES = 6
RECENTTRACKS_CONCURRENCY = 5
RECENTTRACKS_TIMEOUT = 3

recenttracks_cache = TTLCache(ttl=300, max_size=256)


@dataclass
class _AggregatedRecent:
    top_artists: List[Tuple[str, int]] = field(default_factory=list)
    top_tracks: List[Tuple[str, str, int]] = field(default_factory=list)  # (track, artist, plays)
    top_albums: List[Tuple[str, int]] = field(default_factory=list)
    total_listen_count: int = 0
    reached_limit: bool = False
    failed: bool = False


def _ensure_provider_ready(service: Optional[str]) -> None:
    provider = _resolve_provider(service)
    if not provider.api_key:
        abort(503, description="This service is not configured on this server.")


def _call_lastfm(method: str, params: Optional[Dict[str, str]] = None, service: Optional[str] = None) -> Dict:
    provider = _resolve_provider(service)
    _ensure_provider_ready(service)
    query = {
        "method": method,
        "api_key": provider.api_key,
        "format": "json",
    }
    if params:
        query.update({k: v for k, v in params.items() if v is not None})
    response = request_with_handling(provider.session, provider.api, params=query)
    try:
        data = response.json()
    except ValueError:
        abort(502, description="Invalid response from music service")
    error_code = data.get("error")
    if error_code:
        message = data.get("message", "Music service request failed")
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


def _needs_aggregation(range_obj: Optional[DateRange]) -> bool:
    return bool(range_obj and (range_obj.is_custom or not range_obj.lastfm_period))


def _fetch_top_names(username: str, method: str, path: Sequence[str], limit: int, range_obj: Optional[DateRange], service: Optional[str] = None) -> List[str]:
    payload = _call_lastfm(
        method,
        {
            "user": username,
            "period": _resolve_lastfm_period(range_obj),
            "limit": str(limit),
        },
        service=service,
    )
    return _extract_names(payload, path)[:limit]


def get_lastfm_top_artists(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> List[str]:
    if _needs_aggregation(range_obj):
        aggregated = _aggregate_recent_in_range(username, range_obj, service=service)
        return [name for name, _ in aggregated.top_artists[:limit]]
    return _fetch_top_names(username, "user.gettopartists", ("topartists", "artist"), limit, range_obj, service=service)


def get_lastfm_top_tracks(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> List[str]:
    if _needs_aggregation(range_obj):
        aggregated = _aggregate_recent_in_range(username, range_obj, service=service)
        return [track for track, _artist, _plays in aggregated.top_tracks[:limit]]
    return _fetch_top_names(username, "user.gettoptracks", ("toptracks", "track"), limit, range_obj, service=service)


def get_lastfm_top_albums(
    username: str,
    limit: int,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> List[str]:
    if _needs_aggregation(range_obj):
        aggregated = _aggregate_recent_in_range(username, range_obj, service=service)
        return [name for name, _ in aggregated.top_albums[:limit]]
    return _fetch_top_names(username, "user.gettopalbums", ("topalbums", "album"), limit, range_obj, service=service)


def _default_duration_ms() -> int:
    return int(AVERAGE_TRACK_LENGTH_MINUTES * 60000)


def _normalise_duration(value: Optional[str]) -> int:
    if not value:
        return _default_duration_ms()
    try:
        duration = int(value)
        if duration <= 0:
            raise ValueError
        if duration < 1000:
            duration *= 1000
    except (TypeError, ValueError):
        duration = _default_duration_ms()
    return duration


@lru_cache(maxsize=2048)
def _fetch_track_duration(artist_name: str, track_name: str, service: str = "lastfm") -> int:
    try:
        payload = _call_lastfm(
            "track.getInfo",
            {
                "artist": artist_name,
                "track": track_name,
            },
            service=service,
        )
    except Exception:
        payload = None
    track_info = payload.get("track") if isinstance(payload, dict) else None
    duration = None
    if isinstance(track_info, dict):
        duration = track_info.get("duration")
    resolved = _normalise_duration(str(duration) if duration not in {None, ""} else None)
    if resolved and resolved != _default_duration_ms():
        return resolved
    try:
        query = _call_deezer(
            "search",
            {
                "q": f'artist:"{artist_name}" track:"{track_name}"',
                "limit": "1",
            },
        )
    except Exception:
        return resolved
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


def _resolve_durations(keys: Sequence[Tuple[str, str]], service: Optional[str] = None) -> Dict[Tuple[str, str], int]:
    """Look up durations for (artist, track) pairs concurrently."""
    if not keys:
        return {}
    workers = min(DURATION_LOOKUP_CONCURRENCY, len(keys))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        durations = pool.map(lambda key: _fetch_track_duration(key[0], key[1], service or "lastfm"), keys)
        return dict(zip(keys, durations))


def _average_minutes(total_length_ms: int, total_listens: int) -> float:
    if total_listens <= 0 or total_length_ms <= 0:
        return AVERAGE_TRACK_LENGTH_MINUTES
    return (total_length_ms / total_listens) / 60000.0


def _duration_lookup_limit(service: Optional[str]) -> int:
    if service == "librefm":
        return max(1, LIBREFM_DURATION_LOOKUP_LIMIT)
    return DURATION_LOOKUP_LIMIT


def _calculate_lastfm_average_track_minutes(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> float:
    if _needs_aggregation(range_obj):
        aggregated = _aggregate_recent_in_range(username, range_obj, service=service)
        sample = aggregated.top_tracks[:_duration_lookup_limit(service)]
        if not sample:
            return AVERAGE_TRACK_LENGTH_MINUTES
        keys = list(dict.fromkeys((artist, track) for track, artist, _ in sample if artist))
        durations = _resolve_durations(keys, service=service)
        total_length_ms = 0
        total_listens = 0
        for track_name, artist_name, plays in sample:
            duration = durations.get((artist_name, track_name), _default_duration_ms())
            total_length_ms += duration * plays
            total_listens += plays
        return _average_minutes(total_length_ms, total_listens)

    payload = _call_lastfm(
        "user.gettoptracks",
        {
            "user": username,
            "period": _resolve_lastfm_period(range_obj),
            "limit": str(LASTFM_AVERAGE_SAMPLE_LIMIT),
        },
        service=service,
    )
    tracks = (payload.get("toptracks") or {}).get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    durations: Dict[Tuple[str, str], int] = {}
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
            durations[key] = _normalise_duration(str(duration))

    # entries are ordered by playcount, so capped lookups cover the tracks that matter most
    missing = [key for key in plays_by_key if key not in durations]
    durations.update(_resolve_durations(missing[:_duration_lookup_limit(service)], service=service))

    total_length_ms = 0
    total_listens = 0
    for key, duration in durations.items():
        plays = plays_by_key.get(key, 0)
        if plays > 0:
            total_length_ms += duration * plays
            total_listens += plays

    return _average_minutes(total_length_ms, total_listens)


def _fetch_lastfm_total_listens(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
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
        service=service,
    )
    recenttracks = payload.get("recenttracks", {})
    if not isinstance(recenttracks, dict):
        return 0
    attr = recenttracks.get("@attr", {})
    if not isinstance(attr, dict):
        return 0
    total = _attr_int(attr, "total")
    if total > 0:
        return total
    total_pages = _attr_int(attr, "totalPages")
    if total_pages <= 0:
        return 0
    # some audioscrobbler-compatible APIs (libre.fm) omit the total count, so
    # reconstruct it from the pagination metadata. we request limit=1 above, so
    # every page holds one listen and totalPages equals the listen count.
    per_page = _attr_int(attr, "perPage")
    return total_pages * max(per_page, 1)


def estimate_lastfm_listen_minutes(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> str:
    avg_pool = ThreadPoolExecutor(max_workers=1)
    avg_future = avg_pool.submit(_calculate_lastfm_average_track_minutes, username, range_obj=range_obj, service=service)
    avg_pool.shutdown(wait=False)

    total_listens = _fetch_lastfm_total_listens(username, range_obj=range_obj, service=service)
    if total_listens <= 0:
        return "0"

    average_minutes = avg_future.result()
    total_minutes = max(0, int(round(total_listens * average_minutes)))
    return f"{total_minutes:,}"


def _fetch_recent_page(username: str, start_ts: int, end_ts: int, page: int, service: Optional[str] = None) -> Tuple[List[Dict], Dict]:
    """Fetch one page of recenttracks within [start_ts, end_ts]. Returns (tracks, @attr)."""
    provider = _resolve_provider(service)
    try:
        _pace(provider.aggregate_session)
        response = provider.aggregate_session.get(
            provider.api,
            params={
                "method": "user.getrecenttracks",
                "api_key": provider.api_key,
                "format": "json",
                "user": username,
                "from": str(start_ts),
                "to": str(end_ts),
                "limit": str(RECENTTRACKS_PAGE_SIZE),
                "page": str(page),
            },
            timeout=RECENTTRACKS_TIMEOUT,
        )
        if not response.ok:
            return [], {}
        data = response.json()
    except Exception as exc:
        logger.debug("recenttracks page %s failed for %s: %s", page, username, exc)
        return [], {}
    if not isinstance(data, dict):
        return [], {}
    recenttracks = data.get("recenttracks")
    if not isinstance(recenttracks, dict):
        return [], {}
    tracks = recenttracks.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not isinstance(tracks, list):
        tracks = []
    attr = recenttracks.get("@attr")
    return tracks, attr if isinstance(attr, dict) else {}


def _attr_int(attr: Dict, key: str) -> int:
    try:
        return int(attr.get(key, 0))
    except (TypeError, ValueError):
        return 0


def _aggregate_recent_in_range(username: str, range_obj: DateRange, service: Optional[str] = None) -> _AggregatedRecent:
    cache_key = (username, range_obj.start_ts, range_obj.end_ts, service)
    return recenttracks_cache.get_or_compute(
        cache_key, lambda: _aggregate_recent_uncached(username, range_obj, service=service)
    )


def _aggregate_recent_uncached(username: str, range_obj: DateRange, service: Optional[str] = None) -> _AggregatedRecent:
    result = _AggregatedRecent()
    artist_counter: Counter = Counter()
    track_counter: Counter = Counter()
    album_counter: Counter = Counter()

    start_ts = range_obj.start_ts
    end_ts = range_obj.end_ts - 1

    def parse_tracks(tracks: List[Dict]) -> int:
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
            artist_info = entry.get("artist") or {}
            artist_name = (artist_info.get("#text") or "").strip() if isinstance(artist_info, dict) else ""
            album_info = entry.get("album") or {}
            album_name = (album_info.get("#text") or "").strip() if isinstance(album_info, dict) else ""
            track_name = (entry.get("name") or "").strip()
            if artist_name:
                artist_counter[artist_name] += 1
            if track_name and artist_name:
                track_counter[(track_name, artist_name)] += 1
            if album_name and artist_name:
                album_counter[f"{artist_name} - {album_name}"] += 1
            count += 1
        return count

    try:
        tracks, attr = _fetch_recent_page(username, start_ts, end_ts, 1, service=service)
        result.total_listen_count += parse_tracks(tracks)
        total_pages = _attr_int(attr, "totalPages")
        attr_total = _attr_int(attr, "total")

        if total_pages > 1:
            page_cap = min(total_pages, RECENTTRACKS_MAX_PAGES)
            result.reached_limit = total_pages > RECENTTRACKS_MAX_PAGES
            pages = list(range(2, page_cap + 1))
            workers = min(RECENTTRACKS_CONCURRENCY, len(pages))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for page_tracks, _ in pool.map(
                    lambda page: _fetch_recent_page(username, start_ts, end_ts, page, service=service), pages
                ):
                    result.total_listen_count += parse_tracks(page_tracks)
        elif not total_pages and len(tracks) >= RECENTTRACKS_PAGE_SIZE:
            for page in range(2, RECENTTRACKS_MAX_PAGES + 1):
                page_tracks, _ = _fetch_recent_page(username, start_ts, end_ts, page, service=service)
                result.total_listen_count += parse_tracks(page_tracks)
                if len(page_tracks) < RECENTTRACKS_PAGE_SIZE:
                    break
            else:
                result.reached_limit = True

        # attr total counts listens past the page cap too
        if attr_total > result.total_listen_count:
            result.total_listen_count = attr_total
    except Exception as exc:
        logger.warning("recenttracks aggregation failed for %s: %s", username, exc)
        result.failed = True

    result.top_artists = artist_counter.most_common(50)
    result.top_tracks = [
        (track, artist, plays)
        for (track, artist), plays in track_counter.most_common(50)
    ]
    result.top_albums = album_counter.most_common(50)
    return result


def _normalise_tag(name: str) -> str:
    return name.strip().lower()


@lru_cache(maxsize=512)
def _fetch_artist_tags(artist_name: str, service: str = "lastfm") -> List[Tuple[str, int]]:
    payload = _call_lastfm(
        "artist.getTopTags",
        {
            "artist": artist_name,
        },
        service=service,
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
        results.append((normalised, max(weight, 1)))
    return results


def _pick_genre(tag_weights: Iterable[Tuple[str, int]]) -> str:
    popular_counter: Counter = Counter()
    fallback_counter: Counter = Counter()
    for tag, weight in tag_weights:
        fallback_counter[tag] += weight
        if tag in POPULAR_GENRES:
            popular_counter[tag] += weight
    counter = popular_counter or fallback_counter
    if not counter:
        return "No genre"
    tag, _ = counter.most_common(1)[0]
    return tag.title()


def get_lastfm_top_genre(
    username: str,
    *,
    range_obj: Optional[DateRange] = None,
    service: Optional[str] = None,
) -> str:
    artists = get_lastfm_top_artists(username, GENRE_ARTIST_SAMPLE, range_obj=range_obj, service=service)
    if not artists:
        return "No genre"
    workers = min(TAG_LOOKUP_CONCURRENCY, len(artists))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tag_lists = list(pool.map(lambda artist: _fetch_artist_tags(artist, service or "lastfm"), artists))
    return _pick_genre(tag for tags in tag_lists for tag in tags)


def get_lastfm_artist_genre(artist_name: str, service: Optional[str] = None) -> str:
    return _pick_genre(_fetch_artist_tags(artist_name, service or "lastfm"))
