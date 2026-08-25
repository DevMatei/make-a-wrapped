"""MusicBrainz/Wikidata helpers."""

from __future__ import annotations

import time
from functools import lru_cache
from typing import Dict, List, Optional

from .config import (
    IGNORED_TAGS,
    MUSICBRAINZ_API,
    POPULAR_GENRES,
    WIKIDATA_ENTITY_API,
)
from .http import musicbrainz_session, request_with_handling, wikidata_session


def fetch_musicbrainz(path: str, params: Optional[Dict[str, str]] = None, *, timeout: Optional[float] = None) -> Dict:
    url = f"{MUSICBRAINZ_API}{path}"
    response = request_with_handling(musicbrainz_session, url, params=params, timeout=timeout)

    if response.status_code == 503:
        time.sleep(1.0)
        response = request_with_handling(musicbrainz_session, url, params=params, timeout=timeout)
    if not response.ok:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def extract_artist_mbid(artist: Dict) -> Optional[str]:
    mbid = artist.get("artist_mbid")
    if mbid:
        return mbid
    mbids = artist.get("artist_mbids")
    if isinstance(mbids, list) and mbids:
        return mbids[0]
    return None


@lru_cache(maxsize=256)
def fetch_artist_details(artist_mbid: str) -> Dict:
    if not artist_mbid:
        return {}
    return fetch_musicbrainz(
        f"/artist/{artist_mbid}",
        {"fmt": "json", "inc": "tags+genres+url-rels"},
    )


@lru_cache(maxsize=256)
def lookup_artist_tag(artist_mbid: str) -> Optional[str]:
    if not artist_mbid:
        return None

    data = fetch_artist_details(artist_mbid)
    genres = data.get("genres") or []
    if genres:
        sorted_genres = sorted(
            genres,
            key=lambda value: value.get("count", 0),
            reverse=True,
        )
        for genre in sorted_genres:
            name = (genre.get("name") or "").strip()
            if not name:
                continue
            lower_name = name.lower()
            if lower_name in POPULAR_GENRES:
                return name.title()
            if any(lower_name.endswith(f" {suffix}") for suffix in ("pop", "rock", "metal", "jazz")):
                return name.title()

    tags = data.get("tags") or []
    if not tags:
        return None

    for tag in sorted(tags, key=lambda value: value.get("count", 0), reverse=True):
        tag_name = (tag.get("name") or "").strip().lower()
        if tag_name and tag_name not in IGNORED_TAGS:
            if tag_name in POPULAR_GENRES:
                return tag_name.title()
            if any(
                tag_name.endswith(suffix)
                for suffix in ("pop", "rock", "metal", "jazz", "folk", "house", "core")
            ):
                return tag_name.title()
    return None


def search_artist_mbid(artist_name: str) -> Optional[str]:
    if not artist_name:
        return None
    params = {"fmt": "json", "limit": "1", "query": f'artist:"{artist_name}"'}
    data = fetch_musicbrainz("/artist/", params)
    artists = data.get("artists") or []
    if not artists:
        return None
    return artists[0].get("id")


def commons_file_url(filename: str, width: int = 2048) -> Optional[str]:
    if not filename:
        return None
    from urllib.parse import quote

    safe_name = quote(filename.replace(" ", "_"))
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{safe_name}?width={width}"


def normalise_image_resource(resource: str) -> Optional[str]:
    if not resource:
        return None
    lowered = resource.lower()
    if lowered.startswith("https://commons.wikimedia.org/wiki/file:"):
        filename = resource.split("/File:", 1)[1]
        return commons_file_url(filename)
    if lowered.startswith("https://commons.wikimedia.org/wiki/special:filepath/"):
        if "width=" not in lowered:
            return f"{resource}?width=1200"
        return resource
    if lowered.startswith("https://upload.wikimedia.org/"):
        return resource
    return None


def extract_wikidata_qid(relations: List[Dict]) -> Optional[str]:
    for relation in relations or []:
        if relation.get("type") == "wikidata":
            resource = relation.get("url", {}).get("resource", "")
            if resource:
                return resource.rsplit("/", 1)[-1]
    return None


@lru_cache(maxsize=256)
def lookup_wikidata_image(qid: str) -> Optional[str]:
    if not qid:
        return None

    response = request_with_handling(
        wikidata_session,
        f"{WIKIDATA_ENTITY_API}/{qid}.json",
    )
    if not response.ok:
        return None

    try:
        data = response.json()
    except ValueError:
        return None

    entity = (data.get("entities") or {}).get(qid) or {}
    claims = entity.get("claims") or {}
    images = claims.get("P18") or []
    for claim in images:
        mainsnak = claim.get("mainsnak") or {}
        datavalue = mainsnak.get("datavalue") or {}
        value = datavalue.get("value")
        if isinstance(value, str) and value:
            return commons_file_url(value)
    return None


@lru_cache(maxsize=512)
def lookup_recording_length(recording_mbid: str) -> Optional[int]:
    if not recording_mbid:
        return None
    from .http import musicbrainz_aggregate_session, request_with_handling
    url = f"{MUSICBRAINZ_API}/recording/{recording_mbid}"
    try:
        response = request_with_handling(musicbrainz_aggregate_session, url, params={"fmt": "json"}, timeout=3)
    except Exception:
        return None
    if not response.ok:
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    length = data.get("length")
    try:
        return int(length)
    except (TypeError, ValueError):
        return None
