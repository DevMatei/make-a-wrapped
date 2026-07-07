"""ListenBrainz statistics helpers."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Iterable, List, Optional, Tuple

from flask import abort

from .config import (
    AVERAGE_TRACK_LENGTH_MINUTES,
    AVERAGE_TRACK_SAMPLE_LIMIT,
    LISTENBRAINZ_API,
    LISTENBRAINZ_CACHE_SIZE,
    LISTENBRAINZ_CACHE_TTL,
    LISTEN_RANGE,
    MAX_TOP_RESULTS,
)
from .http import listenbrainz_session, request_with_handling
from .musicbrainz import lookup_recording_length


listenbrainz_cache: Dict[
    Tuple[str, Tuple[Tuple[str, str], ...]], Tuple[float, Dict]
] = {}


def fetch_listenbrainz(path: str, params: Optional[Dict[str, str]] = None) -> Dict:
    url = f"{LISTENBRAINZ_API}{path}"
    param_items: Tuple[Tuple[str, str], ...] = tuple(sorted((params or {}).items()))
    cache_key = (path, param_items)
    now = time.time()
    cached = listenbrainz_cache.get(cache_key)
    if cached and now - cached[0] < LISTENBRAINZ_CACHE_TTL:
        return cached[1]

    response = request_with_handling(listenbrainz_session, url, params=params)

    if response.status_code == 404:
        abort(404, description="ListenBrainz user not found")
    if response.status_code >= 500:
        abort(503, description="ListenBrainz service unavailable")
    if not response.ok:
        abort(response.status_code, description="ListenBrainz request failed")

    content = response.content
    if not content.strip():
        return {}

    content_type = response.headers.get("Content-Type", "")
    if "application/json" not in content_type:
        snippet = content.decode("utf-8", "replace").strip()
        snippet = snippet[:200] + ("..." if len(snippet) > 200 else "")
        abort(
            502,
            description=(
                "Unexpected response from ListenBrainz "
                f"(status {response.status_code}, content-type {content_type}): {snippet or 'empty body'}"
            ),
        )

    try:
        data = response.json()
    except ValueError:  # pragma: no cover - malformed payload
        snippet = content.decode("utf-8", "replace").strip()
        snippet = snippet[:200] + ("..." if len(snippet) > 200 else "")
        abort(
            502,
            description=(
                "Unable to decode ListenBrainz response as JSON "
                f"(status {response.status_code}): {snippet or 'empty body'}"
            ),
        )

    payload = data.get("payload") if isinstance(data, dict) else None
    if payload is None:
        abort(502, description="Missing payload in ListenBrainz response")

    listenbrainz_cache[cache_key] = (now, payload)
    if len(listenbrainz_cache) > LISTENBRAINZ_CACHE_SIZE:
        oldest_key = min(listenbrainz_cache.items(), key=lambda item: item[1][0])[0]
        listenbrainz_cache.pop(oldest_key, None)
    return payload


def normalise_count(value: int) -> int:
    return max(int(value), 0)


def clamp_top_number(requested: int) -> int:
    return max(1, min(int(requested), MAX_TOP_RESULTS))


def _fetch_stat_payload(
    username: str,
    endpoint: str,
    key: str,
    *,
    count: Optional[int] = None,
) -> Dict:
    ranges = [LISTEN_RANGE]
    if LISTEN_RANGE != "all_time":
        ranges.append("all_time")

    last_payload: Dict = {}
    for stat_range in ranges:
        params: Dict[str, str] = {"range": stat_range}
        if count is not None:
            params["count"] = str(count)
        payload = fetch_listenbrainz(f"/stats/user/{username}/{endpoint}", params)
        last_payload = payload
        if payload.get(key):
            return payload
    return last_payload


def get_top_artists_payload(username: str, count: int) -> List[Dict]:
    payload = _fetch_stat_payload(username, "artists", "artists", count=count)
    return payload.get("artists", [])


def get_top_tracks_payload(username: str, count: int) -> List[Dict]:
    payload = _fetch_stat_payload(username, "recordings", "recordings", count=count)
    return payload.get("recordings", [])


def get_top_releases_payload(username: str, count: int) -> List[Dict]:
    payload = _fetch_stat_payload(username, "releases", "releases", count=count)
    return payload.get("releases", [])


def format_ranked_lines(items: Iterable[str]) -> str:
    return "<br>".join(f"{idx + 1}. {value}" for idx, value in enumerate(items))


def calculate_average_track_minutes(username: str) -> Optional[float]:
    sample_limit = max(1, min(AVERAGE_TRACK_SAMPLE_LIMIT, 200))
    recordings = get_top_tracks_payload(username, sample_limit)

    unique_mbids: List[str] = []
    for recording in recordings:
        recording_mbid = recording.get("recording_mbid")
        if recording_mbid and recording_mbid not in unique_mbids:
            unique_mbids.append(recording_mbid)

    length_map: Dict[str, Optional[int]] = {}
    if unique_mbids:
        with ThreadPoolExecutor(max_workers=6) as pool:
            for mbid, length in zip(unique_mbids, pool.map(lookup_recording_length, unique_mbids)):
                if length:
                    length_map[mbid] = length

    total_length_ms = 0
    total_listens = 0
    for recording in recordings:
        recording_mbid = recording.get("recording_mbid")
        listen_count = normalise_count(recording.get("listen_count", 0))
        if listen_count <= 0:
            continue
        length_ms = None
        if recording_mbid:
            length_ms = length_map.get(recording_mbid)
            if length_ms is None:
                length_ms = lookup_recording_length(recording_mbid or "")
                if length_ms:
                    length_map[recording_mbid] = length_ms
        if not length_ms:
            continue
        total_length_ms += length_ms * listen_count
        total_listens += listen_count

    if total_listens <= 0:
        return None
    return (total_length_ms / total_listens) / 60000.0


def estimate_total_listen_minutes(username: str) -> str:
    import datetime

    activity = fetch_listenbrainz(
        f"/stats/user/{username}/listening-activity",
        {"range": LISTEN_RANGE},
    )

    current_year = datetime.datetime.now(datetime.timezone.utc).year
    listen_counts = [
        normalise_count(item.get("listen_count", 0))
        for item in activity.get("listening_activity", [])
        if item.get("from_ts") and datetime.datetime.fromtimestamp(item["from_ts"], tz=datetime.timezone.utc).year == current_year
    ]
    total_listens = sum(listen_counts)
    if total_listens <= 0:
        return "0"

    avg_minutes = calculate_average_track_minutes(username) or AVERAGE_TRACK_LENGTH_MINUTES
    total_minutes = int(total_listens * avg_minutes)
    return f"{total_minutes:,}"
