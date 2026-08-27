"""Shields-style SVG badges for embedding in READMEs and profiles."""

from __future__ import annotations

import logging
import re
from typing import Optional
from xml.sax.saxutils import escape

from .cache import TTLCache
from .config import BADGE_CACHE_SIZE, BADGE_CACHE_TTL
from .date_range import DateRange
from .genres import get_top_genre
from .lastfm import (
    estimate_lastfm_listen_minutes,
    get_lastfm_top_artists,
    get_lastfm_top_genre,
    get_lastfm_top_tracks,
)
from .listenbrainz import (
    estimate_total_listen_minutes,
    get_top_artists_payload,
    get_top_tracks_payload,
)

logger = logging.getLogger("wrapped_fm")

BADGE_TYPES = {"artist", "track", "genre", "minutes"}
DEFAULT_BADGE_COLOR = "c084fc"
MAX_VALUE_LENGTH = 40

_badge_cache = TTLCache(ttl=BADGE_CACHE_TTL, max_size=BADGE_CACHE_SIZE)

_HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
_NARROW_CHARS = set("iljtfr1!.,;:'\"()[]| ")
_WIDE_CHARS = set("mwMW@%&")

_BADGE_LABELS = {
    "artist": "top artist",
    "track": "top track",
    "genre": "top genre",
    "minutes": "minutes listened",
}

_XML_ESCAPE_ENTITIES = {'"': "&quot;", "'": "&apos;"}


def _escape_xml(text: str) -> str:
    return escape(text, _XML_ESCAPE_ENTITIES)


def normalise_badge_type(raw: Optional[str]) -> str:
    value = (raw or "artist").strip().lower()
    return value if value in BADGE_TYPES else "artist"


def normalise_badge_color(raw: Optional[str]) -> str:
    value = (raw or "").strip().lstrip("#")
    return value.lower() if _HEX_COLOR.match(value) else DEFAULT_BADGE_COLOR


def _measure(text: str) -> float:
    width = 0.0
    for ch in text:
        if ch in _NARROW_CHARS:
            width += 3.6
        elif ch in _WIDE_CHARS:
            width += 9.7
        elif ch.isupper():
            width += 7.6
        elif ch.isdigit():
            width += 6.4
        else:
            width += 6.2
    return width


def _truncate(value: str) -> str:
    value = value.strip()
    if len(value) <= MAX_VALUE_LENGTH:
        return value
    return value[: MAX_VALUE_LENGTH - 1].rstrip() + "…"


def _format_minutes(raw: str) -> str:
    try:
        return f"{int(str(raw).replace(',', '').strip()):,}"
    except (TypeError, ValueError):
        return str(raw)


def _fetch_value(service: str, username: str, badge_type: str, range_obj: DateRange) -> str:
    is_lastfm_family = service in ("lastfm", "librefm")
    if badge_type == "minutes":
        if is_lastfm_family:
            return _format_minutes(estimate_lastfm_listen_minutes(username, range_obj=range_obj, service=service))
        return _format_minutes(estimate_total_listen_minutes(username, range_obj=range_obj))
    if badge_type == "genre":
        if is_lastfm_family:
            return get_lastfm_top_genre(username, range_obj=range_obj, service=service)
        return get_top_genre(username, range_obj=range_obj)
    if badge_type == "track":
        if is_lastfm_family:
            names = get_lastfm_top_tracks(username, 1, range_obj=range_obj, service=service)
            return names[0] if names else "no listens yet"
        tracks = get_top_tracks_payload(username, 1, range_obj=range_obj)
        return tracks[0].get("track_name", "no listens yet") if tracks else "no listens yet"
    if is_lastfm_family:
        names = get_lastfm_top_artists(username, 1, range_obj=range_obj, service=service)
        return names[0] if names else "no listens yet"
    artists = get_top_artists_payload(username, 1, range_obj=range_obj)
    return artists[0].get("artist_name", "no listens yet") if artists else "no listens yet"


def get_badge_value(service: str, username: str, badge_type: str, range_obj: DateRange) -> str:
    key = (service, username.lower(), badge_type, range_obj.preset, range_obj.start_ts, range_obj.end_ts)

    def compute() -> str:
        try:
            return _truncate(_fetch_value(service, username, badge_type, range_obj))
        except Exception as exc:
            logger.warning("Badge value failed for %s/%s: %s", service, username, exc)
            return "unavailable"

    value = _badge_cache.get_or_compute(key, compute)
    # don't cache transient upstream failures or empty fallbacks, or one flaky
    # upstream response (very common on libre.fm) poisons the badge for the TTL
    if value in {"unavailable"} or value == "no listens yet":
        _badge_cache.pop(key, None)
    return value


def _is_light_color(color: str) -> bool:
    r, g, b = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.55


def render_badge_svg(label: str, value: str, color: str) -> str:
    height = 28
    icon_zone = 26
    left_width = icon_zone + round(_measure(label)) + 9
    right_width = round(_measure(value)) + 20
    total_width = left_width + right_width
    label_x = (icon_zone + (left_width - icon_zone - 9) / 2) * 10
    value_x = (left_width + right_width / 2) * 10
    esc_label = _escape_xml(label)
    esc_value = _escape_xml(value)
    aria = _escape_xml(f"{label}: {value}")
    value_fill = "#1e1b2e" if _is_light_color(color) else "#ffffff"
    label_shadow = (
        f'<text x="{label_x}" y="192" transform="scale(.1)" fill="#0b0817" fill-opacity=".45" '
        f'textLength="{(left_width - icon_zone - 9) * 10}">{esc_label}</text>'
    )
    value_shadow = ""
    if value_fill == "#ffffff":
        value_shadow = (
            f'<text x="{value_x}" y="192" transform="scale(.1)" fill="#0b0817" fill-opacity=".4" '
            f'textLength="{(right_width - 18) * 10}">{esc_value}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{height}" '
        f'role="img" aria-label="{aria}">'
        f"<title>{aria}</title>"
        '<linearGradient id="g" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#fff" stop-opacity=".09"/>'
        '<stop offset="1" stop-color="#000" stop-opacity=".12"/>'
        "</linearGradient>"
        f'<clipPath id="r"><rect width="{total_width}" height="{height}" rx="7"/></clipPath>'
        '<g clip-path="url(#r)">'
        f'<rect width="{left_width}" height="{height}" fill="#2a2438"/>'
        f'<rect x="{left_width}" width="{right_width}" height="{height}" fill="#{color}"/>'
        f'<rect width="{total_width}" height="{height}" fill="url(#g)"/>'
        "</g>"
        f'<rect width="{total_width - 1}" height="{height - 1}" x=".5" y=".5" rx="6.5" '
        'fill="none" stroke="#fff" stroke-opacity=".12"/>'
        f'<g fill="#{color}" transform="translate(8,7)">'
        '<circle cx="4" cy="11" r="2.6"/>'
        '<rect x="5.4" y="1.6" width="1.5" height="9.6" rx=".7"/>'
        '<path d="M6.9 1.6c2.7.8 3.7 2.6 3 5-.7-1.4-1.6-2.1-3-2.4z"/>'
        "</g>"
        '<g text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        'font-size="110" text-rendering="geometricPrecision">'
        f"{label_shadow}"
        f'<text x="{label_x}" y="182" transform="scale(.1)" fill="#d6d0e4" '
        f'textLength="{(left_width - icon_zone - 9) * 10}">{esc_label}</text>'
        f"{value_shadow}"
        f'<text x="{value_x}" y="182" transform="scale(.1)" fill="{value_fill}" font-weight="bold" '
        f'textLength="{(right_width - 18) * 10}">{esc_value}</text>'
        "</g>"
        "</svg>"
    )


def badge_label(badge_type: str) -> str:
    return _BADGE_LABELS.get(badge_type, _BADGE_LABELS["artist"])


def build_badge(service: str, username: str, badge_type: str, color: str, range_obj: DateRange) -> str:
    value = get_badge_value(service, username, badge_type, range_obj)
    return render_badge_svg(_BADGE_LABELS[badge_type], value, color)
