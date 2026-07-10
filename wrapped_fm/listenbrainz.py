"""ListenBrainz statistics helpers."""

from __future__ import annotations

import datetime
import logging
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from flask import abort

from .cache import TTLCache
from .config import (
    AVERAGE_TRACK_LENGTH_MINUTES,
    AVERAGE_TRACK_SAMPLE_LIMIT,
    LISTENBRAINZ_API,
    LISTENBRAINZ_CACHE_SIZE,
    LISTENBRAINZ_CACHE_TTL,
    LISTEN_RANGE,
    MAX_TOP_RESULTS,
)
from .date_range import DateRange
from .http import listenbrainz_aggregate_session, request_with_handling
from .musicbrainz import lookup_recording_length


logger = logging.getLogger("wrapped_fm")


listenbrainz_cache = TTLCache(ttl=LISTENBRAINZ_CACHE_TTL, max_size=LISTENBRAINZ_CACHE_SIZE)
aggregation_cache = TTLCache(ttl=300, max_size=256)

LISTEN_AGGREGATION_PAGE_SIZE = 1000  # API max
LISTEN_AGGREGATION_MAX_PAGES = 15
LISTEN_AGGREGATION_MAX_LISTENS = LISTEN_AGGREGATION_PAGE_SIZE * LISTEN_AGGREGATION_MAX_PAGES
LISTEN_AGGREGATION_TIMEOUT = 30  # the endpoint can take >15s for heavy users
LISTEN_AGGREGATION_BUDGET = 60


@dataclass
class _AggregatedListens:
    top_artists: List[Dict[str, object]] = field(default_factory=list)
    top_tracks: List[Dict[str, object]] = field(default_factory=list)
    top_releases: List[Dict[str, object]] = field(default_factory=list)
    total_listen_count: int = 0
    reached_limit: bool = False
    failed: bool = False


def fetch_listenbrainz(path: str, params: Optional[Dict[str, str]] = None, *, timeout: Optional[float] = None) -> Dict:
    param_items: Tuple[Tuple[str, str], ...] = tuple(sorted((params or {}).items()))
    cache_key = (path, param_items)
    return listenbrainz_cache.get_or_compute(
        cache_key, lambda: _fetch_listenbrainz_uncached(path, params, timeout)
    )


def _fetch_listenbrainz_uncached(path: str, params: Optional[Dict[str, str]], timeout: Optional[float]) -> Dict:
    url = f"{LISTENBRAINZ_API}{path}"
    response = request_with_handling(listenbrainz_aggregate_session, url, params=params, timeout=timeout or 5)

    if response.status_code == 404:
        abort(404, description="ListenBrainz user not found")
    if response.status_code >= 500:
        abort(503, description="ListenBrainz service unavailable")
    if not response.ok:
        abort(response.status_code, description="ListenBrainz request failed")

    content = response.content
    if not content.strip():
        return {}

    def _snippet() -> str:
        text = content.decode("utf-8", "replace").strip()
        return text[:200] + ("..." if len(text) > 200 else "")

    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        abort(
            502,
            description=(
                "Unexpected response from ListenBrainz "
                f"(status {response.status_code}, content-type {content_type}): {_snippet() or 'empty body'}"
            ),
        )

    try:
        data = response.json()
    except ValueError:
        abort(
            502,
            description=(
                "Unable to decode ListenBrainz response as JSON "
                f"(status {response.status_code}): {_snippet() or 'empty body'}"
            ),
        )

    payload = data.get("payload") if isinstance(data, dict) else None
    if payload is None:
        abort(502, description="Missing payload in ListenBrainz response")
    return payload


def normalise_count(value: int) -> int:
    return max(int(value), 0)


def clamp_top_number(requested: int) -> int:
    return max(1, min(int(requested), MAX_TOP_RESULTS))


def _default_range() -> DateRange:
    from .date_range import resolve_preset, PRESET_THIS_YEAR

    try:
        return resolve_preset(LISTEN_RANGE)
    except ValueError:
        return resolve_preset(PRESET_THIS_YEAR)


def _fetch_stat_payload(
    username: str,
    endpoint: str,
    key: str,
    *,
    range_obj: Optional[DateRange] = None,
    count: Optional[int] = None,
) -> Dict:
    resolved = range_obj or _default_range()
    if not resolved.lb_range:
        return _aggregate_payload_for_range(username, endpoint, resolved, count=count)

    ranges = [resolved.lb_range]
    if resolved.lb_range != "all_time":
        ranges.append("all_time")

    last_payload: Dict = {}
    for stat_range in ranges:
        params: Dict[str, str] = {"range": stat_range}
        if count is not None:
            params["count"] = str(count)
        try:
            payload = fetch_listenbrainz(f"/stats/user/{username}/{endpoint}", params)
        except Exception as exc:
            logger.warning("LB stats fetch failed for %s/%s: %s", username, stat_range, exc)
            return {}
        last_payload = payload
        if payload.get(key):
            return payload
    return last_payload


def get_top_artists_payload(username: str, count: int, *, range_obj: Optional[DateRange] = None) -> List[Dict]:
    payload = _fetch_stat_payload(username, "artists", "artists", count=count, range_obj=range_obj)
    return payload.get("artists", [])


def get_top_tracks_payload(username: str, count: int, *, range_obj: Optional[DateRange] = None) -> List[Dict]:
    payload = _fetch_stat_payload(username, "recordings", "recordings", count=count, range_obj=range_obj)
    return payload.get("recordings", [])


def get_top_releases_payload(username: str, count: int, *, range_obj: Optional[DateRange] = None) -> List[Dict]:
    payload = _fetch_stat_payload(username, "releases", "releases", count=count, range_obj=range_obj)
    return payload.get("releases", [])


def format_ranked_lines(items) -> str:
    return "<br>".join(f"{idx + 1}. {value}" for idx, value in enumerate(items))


def calculate_average_track_minutes(username: str) -> Optional[float]:
    sample_limit = max(1, min(AVERAGE_TRACK_SAMPLE_LIMIT, 20))
    recordings = get_top_tracks_payload(username, sample_limit)

    unique_mbids: List[str] = []
    for recording in recordings:
        recording_mbid = recording.get("recording_mbid")
        if recording_mbid and recording_mbid not in unique_mbids:
            unique_mbids.append(recording_mbid)
        if len(unique_mbids) >= 6:
            break

    length_map: Dict[str, int] = {}
    if unique_mbids:
        def _lookup(mbid: str) -> Tuple[str, Optional[int]]:
            try:
                return mbid, lookup_recording_length(mbid)
            except Exception:
                return mbid, None
        with ThreadPoolExecutor(max_workers=3) as pool:
            for mbid, length in pool.map(_lookup, unique_mbids):
                if length:
                    length_map[mbid] = length

    total_length_ms = 0
    total_listens = 0
    for recording in recordings:
        recording_mbid = recording.get("recording_mbid")
        listen_count = normalise_count(recording.get("listen_count", 0))
        if listen_count <= 0:
            continue
        length_ms = length_map.get(recording_mbid) if recording_mbid else None
        if not length_ms:
            continue
        total_length_ms += length_ms * listen_count
        total_listens += listen_count

    if total_listens <= 0:
        return None
    return (total_length_ms / total_listens) / 60000.0


_ACTIVITY_RANGES = ("this_year", "year", "all_time")


def _fetch_activity_items(username: str) -> List[Dict]:
    """Fetch listening-activity items from multiple LB ranges and merge them."""

    def _fetch(lb_range: str) -> List[Dict]:
        try:
            payload = fetch_listenbrainz(
                f"/stats/user/{username}/listening-activity",
                {"range": lb_range},
            )
        except Exception:
            return []
        return payload.get("listening_activity", [])

    with ThreadPoolExecutor(max_workers=len(_ACTIVITY_RANGES)) as pool:
        results = list(pool.map(_fetch, _ACTIVITY_RANGES))

    all_items: List[Dict] = []
    seen_ts: set = set()
    for items in results:
        for item in items:
            ts = item.get("from_ts")
            if ts is not None and ts not in seen_ts:
                seen_ts.add(ts)
                all_items.append(item)
    return all_items


def _count_listens_from_activity(items: List[Dict], start_ts: int, end_ts: int) -> int:
    total = 0
    for item in items:
        from_ts = item.get("from_ts")
        to_ts = item.get("to_ts")
        if from_ts is None:
            continue
        if to_ts is not None and to_ts <= start_ts:
            continue
        if from_ts >= end_ts:
            continue
        total += normalise_count(item.get("listen_count", 0))
    return total


def estimate_total_listen_minutes(username: str, *, range_obj: Optional[DateRange] = None) -> str:
    resolved = range_obj or _default_range()

    avg_pool = ThreadPoolExecutor(max_workers=1)
    avg_future = avg_pool.submit(calculate_average_track_minutes, username)
    avg_pool.shutdown(wait=False)

    if not resolved.lb_range:
        activity_items = _fetch_activity_items(username)
        if activity_items:
            total_listens = _count_listens_from_activity(activity_items, resolved.start_ts, resolved.end_ts)
        else:
            aggregated = _aggregate_listens_in_range(username, resolved)
            total_listens = aggregated.total_listen_count
    else:
        try:
            activity = fetch_listenbrainz(
                f"/stats/user/{username}/listening-activity",
                {"range": resolved.lb_range},
            )
        except Exception as exc:
            logger.warning("LB listening-activity failed for %s: %s", username, exc)
            return "0"

        activity_items = activity.get("listening_activity", [])
        if resolved.preset == "this_year":
            current_year = datetime.datetime.now(datetime.timezone.utc).year
            listen_counts = [
                normalise_count(item.get("listen_count", 0))
                for item in activity_items
                if item.get("from_ts") and datetime.datetime.fromtimestamp(item["from_ts"], tz=datetime.timezone.utc).year == current_year
            ]
        else:
            listen_counts = [
                normalise_count(item.get("listen_count", 0))
                for item in activity_items
            ]
        total_listens = sum(listen_counts)

    if total_listens <= 0:
        return "0"

    avg_minutes = avg_future.result() or AVERAGE_TRACK_LENGTH_MINUTES
    total_minutes = int(total_listens * avg_minutes)
    return f"{total_minutes:,}"


def _aggregate_payload_for_range(
    username: str,
    endpoint: str,
    range_obj: DateRange,
    *,
    count: Optional[int] = None,
) -> Dict:
    aggregated = _aggregate_listens_in_range(username, range_obj)
    attr_by_endpoint = {
        "artists": ("artists", "top_artists"),
        "recordings": ("recordings", "top_tracks"),
        "releases": ("releases", "top_releases"),
    }
    mapping = attr_by_endpoint.get(endpoint)
    if mapping is None:
        return {}
    list_key, attr_name = mapping
    items = getattr(aggregated, attr_name)
    if count is not None:
        items = items[:count]
    return {
        list_key: items,
        "range": range_obj.lb_range or range_obj.preset,
        "from_ts": range_obj.start_ts,
        "to_ts": range_obj.end_ts,
        "_meta": {
            "is_aggregated": True,
            "total_listen_count": aggregated.total_listen_count,
            "reached_limit": aggregated.reached_limit,
            "failed": aggregated.failed,
        },
    }


def _aggregation_cache_key(username: str, range_obj: DateRange) -> Tuple[str, str, int, int]:
    start = range_obj.start_ts - (range_obj.start_ts % 3600)
    end = range_obj.end_ts - (range_obj.end_ts % 3600)
    return (username, range_obj.preset, start, end)


def _aggregate_listens_in_range(username: str, range_obj: DateRange) -> _AggregatedListens:
    cache_key = _aggregation_cache_key(username, range_obj)
    return aggregation_cache.get_or_compute(
        cache_key, lambda: _aggregate_listens_uncached(username, range_obj)
    )


def _fetch_listens_page(username: str, max_ts: int) -> List[Dict]:
    try:
        response = listenbrainz_aggregate_session.get(
            f"{LISTENBRAINZ_API}/user/{username}/listens",
            params={"max_ts": str(max_ts), "count": str(LISTEN_AGGREGATION_PAGE_SIZE)},
            timeout=LISTEN_AGGREGATION_TIMEOUT,
        )
        if response.status_code == 404:
            return []
        if not response.ok:
            logger.debug("ListenBrainz listens page %s returned %s", max_ts, response.status_code)
            return []
        data = response.json()
    except Exception as exc:
        logger.debug("ListenBrainz listens page fetch failed for %s: %s", username, exc)
        return []
    payload = data.get("payload") if isinstance(data, dict) else None
    if not isinstance(payload, dict):
        return []
    listens = payload.get("listens") or []
    return listens if isinstance(listens, list) else []


def _aggregate_listens_uncached(username: str, range_obj: DateRange) -> _AggregatedListens:
    result = _AggregatedListens()
    artist_counter: Counter = Counter()
    track_counter: Counter = Counter()
    release_counter: Counter = Counter()
    listened_at_min = range_obj.start_ts
    listened_at_max = range_obj.end_ts - 1

    def parse_listens(listens: List[Dict], upper_ts: int) -> Tuple[int, int]:
        # page_oldest tracks out-of-range listens too so paging keeps moving
        page_oldest = upper_ts
        count = 0
        for entry in listens:
            listened_at = entry.get("listened_at")
            if not isinstance(listened_at, int):
                continue
            page_oldest = min(page_oldest, listened_at)
            if listened_at < listened_at_min or listened_at > listened_at_max:
                continue
            track_metadata = entry.get("track_metadata") or {}
            artist_name = (track_metadata.get("artist_name") or "").strip()
            track_name = (track_metadata.get("track_name") or "").strip()
            release_name = (track_metadata.get("release_name") or "").strip()
            additional = track_metadata.get("additional_info") or {}
            recording_mbid = additional.get("recording_mbid") or None
            release_mbid = additional.get("release_mbid") or None
            artist_mbid = additional.get("artist_mbids")
            if isinstance(artist_mbid, list) and artist_mbid:
                artist_mbid = artist_mbid[0]
            elif not isinstance(artist_mbid, str):
                artist_mbid = None

            if artist_name:
                artist_counter[(artist_name, artist_mbid)] += 1
            if track_name:
                track_counter[(track_name, artist_name, release_name, recording_mbid)] += 1
            if release_name:
                release_counter[(release_name, artist_name, release_mbid)] += 1
            count += 1
        return count, page_oldest

    # the endpoint only pages by max_ts, so the walk is sequential
    next_max_ts = listened_at_max
    try:
        deadline = time.monotonic() + LISTEN_AGGREGATION_BUDGET
        for _ in range(LISTEN_AGGREGATION_MAX_PAGES):
            if time.monotonic() >= deadline:
                break
            listens = _fetch_listens_page(username, next_max_ts)
            if not listens:
                break
            count, page_oldest = parse_listens(listens, next_max_ts)
            result.total_listen_count += count
            if result.total_listen_count >= LISTEN_AGGREGATION_MAX_LISTENS:
                result.reached_limit = True
                break
            if len(listens) < LISTEN_AGGREGATION_PAGE_SIZE:
                break
            next_ts = page_oldest - 1
            if next_ts >= next_max_ts or next_ts < listened_at_min:
                break
            next_max_ts = next_ts
    except Exception as exc:
        logger.warning("ListenBrainz aggregation failed for %s: %s", username, exc)
        result.failed = True

    result.top_artists = _format_top_artists(artist_counter, MAX_TOP_RESULTS)
    result.top_tracks = _format_top_tracks(track_counter, MAX_TOP_RESULTS)
    result.top_releases = _format_top_releases(release_counter, MAX_TOP_RESULTS)
    return result


def _format_top_artists(counter: Counter, limit: int) -> List[Dict[str, object]]:
    return [
        {"artist_name": name, "artist_mbid": mbid or None, "listen_count": count}
        for (name, mbid), count in counter.most_common(limit)
    ]


def _format_top_tracks(counter: Counter, limit: int) -> List[Dict[str, object]]:
    return [
        {
            "track_name": track_name,
            "artist_name": artist_name,
            "release_name": release_name or "",
            "recording_mbid": recording_mbid,
            "release_mbid": None,
            "listen_count": count,
        }
        for (track_name, artist_name, release_name, recording_mbid), count in counter.most_common(limit)
    ]


def _format_top_releases(counter: Counter, limit: int) -> List[Dict[str, object]]:
    return [
        {
            "release_name": release_name,
            "artist_name": artist_name,
            "release_mbid": release_mbid,
            "listen_count": count,
        }
        for (release_name, artist_name, release_mbid), count in counter.most_common(limit)
    ]
