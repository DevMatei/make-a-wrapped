"""Genre lookup helpers."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from .listenbrainz import get_top_artists_payload
from .musicbrainz import extract_artist_mbid, lookup_artist_tag, search_artist_mbid

TAG_LOOKUP_CONCURRENCY = 4
# MusicBrainz throttles per IP, so every extra lookup adds real latency
GENRE_ARTIST_SAMPLE = 6


def _safe_lookup_tag(artist_mbid: str):
    try:
        return lookup_artist_tag(artist_mbid)
    except Exception:
        return None


def get_top_genre(username: str, *, range_obj=None) -> str:
    artists = get_top_artists_payload(username, GENRE_ARTIST_SAMPLE, range_obj=range_obj)
    mbids = [mbid for mbid in (extract_artist_mbid(artist) for artist in artists) if mbid]
    if not mbids:
        return "no genre"

    with ThreadPoolExecutor(max_workers=min(TAG_LOOKUP_CONCURRENCY, len(mbids))) as pool:
        tags = pool.map(_safe_lookup_tag, mbids)

    tag_counter: Counter[str] = Counter(tag for tag in tags if tag)
    if not tag_counter:
        return "no genre"
    top_tag, _ = tag_counter.most_common(1)[0]
    return top_tag


def get_genre_for_artist(artist_name: str) -> str:
    artist_mbid = search_artist_mbid(artist_name)
    if not artist_mbid:
        return "no genre"
    tag = lookup_artist_tag(artist_mbid)
    return tag.title() if tag else "no genre"
