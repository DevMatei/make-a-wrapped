"""Genre lookup helpers."""

from __future__ import annotations

from collections import Counter

from .listenbrainz import get_top_artists_payload
from .musicbrainz import extract_artist_mbid, lookup_artist_tag, search_artist_mbid


def get_top_genre(username: str, *, range_obj=None) -> str:
    artists = get_top_artists_payload(username, 10, range_obj=range_obj)
    tag_counter: Counter[str] = Counter()

    for artist in artists:
        artist_mbid = extract_artist_mbid(artist)
        if not artist_mbid:
            continue
        tag = lookup_artist_tag(artist_mbid)
        if tag:
            tag_counter[tag] += 1

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
