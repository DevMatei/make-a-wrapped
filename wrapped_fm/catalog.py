"""Public, paginated view of the template library for API consumers."""

from __future__ import annotations

import base64
import binascii
import calendar
import hashlib
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from . import templates as template_store
from .config import SITE_URL, TEMPLATE_CATALOG_TTL

SORTS = ("popular", "newest", "name")
ORIGINS = ("official", "community")
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
MAX_QUERY_LENGTH = 60
PREVIEW_SIZES = {"sm": 360, "md": 540, "lg": 1080}
PREVIEW_RENDER_VERSION = "1"

_cache_lock = threading.Lock()
_cache: Dict[str, Any] = {"expires": 0.0, "entries": None}


class CatalogQueryError(ValueError):
    """Raised when catalog query parameters are invalid."""


def template_fingerprint(template: Dict[str, Any]) -> str:
    """Stable hash of everything that affects how a template is drawn."""
    drawn = {key: value for key, value in template.items() if key not in {"origin", "status", "creator", "meta"}}
    encoded = json.dumps(drawn, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded + PREVIEW_RENDER_VERSION.encode("ascii")).hexdigest()[:16]


def _created_epoch(value: Any) -> int:
    if not isinstance(value, str):
        return 0
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return 0


def _public_creator(raw: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw, dict) or not raw.get("name"):
        return None
    creator = {"name": str(raw.get("name"))}
    if raw.get("id"):
        creator["id"] = str(raw["id"])
    website = raw.get("website")
    if isinstance(website, str) and website.startswith(("https://", "http://")):
        creator["website"] = website
    return creator


def _build_entry(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    slug = summary.get("slug")
    try:
        template = template_store.get_template(slug)
    except template_store.TemplateUnavailableError:
        return None
    canvas = template.get("canvas") if isinstance(template.get("canvas"), dict) else {}
    meta = summary.get("meta") if isinstance(summary.get("meta"), dict) else {}
    tags = [tag for tag in meta.get("tags") or [] if isinstance(tag, str) and tag]
    fingerprint = template_fingerprint(template)
    return {
        "slug": slug,
        "name": summary.get("name") or slug,
        "origin": summary.get("origin"),
        "category": meta.get("category") or "abstract",
        "tags": tags,
        "featured": bool(meta.get("featured")),
        "uses": int(summary.get("uses") or 0),
        "created_at": summary.get("created_at"),
        "creator": _public_creator(summary.get("creator")),
        "canvas": {"width": canvas.get("width"), "height": canvas.get("height")},
        "version": fingerprint,
        "links": {
            "self": f"{SITE_URL}/api/v1/templates/{slug}",
            "preview": f"{SITE_URL}/api/v1/templates/{slug}/preview.png?v={fingerprint}",
            "use": f"{SITE_URL}/?template={slug}",
        },
    }


def catalog_entries() -> List[Dict[str, Any]]:
    """Every approved template as a public entry, cached for a short time."""
    now = time.monotonic()
    with _cache_lock:
        if _cache["entries"] is not None and now < _cache["expires"]:
            return _cache["entries"]
    entries = [entry for entry in map(_build_entry, template_store.list_templates()) if entry]
    with _cache_lock:
        _cache["entries"] = entries
        _cache["expires"] = time.monotonic() + TEMPLATE_CATALOG_TTL
    return entries


def clear_cache() -> None:
    with _cache_lock:
        _cache["entries"] = None
        _cache["expires"] = 0.0


def find_entry(slug: str) -> Optional[Dict[str, Any]]:
    for entry in catalog_entries():
        if entry["slug"] == slug:
            return entry
    if not template_store.resolve_template_exists(slug):
        return None
    for summary in template_store.list_templates():
        if summary.get("slug") == slug:
            return _build_entry(summary)
    return None


def _sort_key(sort: str, entry: Dict[str, Any]) -> Tuple:
    if sort == "popular":
        return (-entry["uses"], entry["slug"])
    if sort == "newest":
        return (-_created_epoch(entry["created_at"]), entry["slug"])
    return ((entry["name"] or "").casefold(), entry["slug"])


def _matches(entry: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    if filters.get("origin") and entry["origin"] != filters["origin"]:
        return False
    if filters.get("category") and entry["category"] != filters["category"]:
        return False
    if filters.get("featured") is not None and entry["featured"] != filters["featured"]:
        return False
    query = filters.get("q")
    if query:
        creator_name = (entry["creator"] or {}).get("name", "")
        haystack = " ".join([entry["name"], entry["slug"], creator_name, *entry["tags"]]).casefold()
        return all(word in haystack for word in query.casefold().split())
    return True


def _encode_cursor(sort: str, filters_hash: str, key: Tuple) -> str:
    raw = json.dumps({"s": sort, "f": filters_hash, "k": list(key)}, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str, sort: str, filters_hash: str) -> Tuple:
    if len(cursor) > 512:
        raise CatalogQueryError("cursor is invalid.")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (ValueError, binascii.Error, UnicodeError):
        raise CatalogQueryError("cursor is invalid.")
    if not isinstance(payload, dict) or not isinstance(payload.get("k"), list) or len(payload["k"]) != 2:
        raise CatalogQueryError("cursor is invalid.")
    if payload.get("s") != sort or payload.get("f") != filters_hash:
        raise CatalogQueryError("cursor belongs to a different query. Start again without a cursor.")
    first, second = payload["k"]
    expected = str if sort == "name" else int
    if type(first) is not expected or not isinstance(second, str):
        raise CatalogQueryError("cursor is invalid.")
    return (first, second)


def parse_query(args) -> Dict[str, Any]:
    allowed = {"limit", "cursor", "sort", "origin", "category", "featured", "q"}
    unknown = set(args) - allowed
    if unknown:
        raise CatalogQueryError(f"Unsupported query parameters: {', '.join(sorted(unknown))}.")

    limit_raw = args.get("limit", str(DEFAULT_PAGE_SIZE))
    if not limit_raw.isdigit() or not 1 <= int(limit_raw) <= MAX_PAGE_SIZE:
        raise CatalogQueryError(f"limit must be an integer from 1 to {MAX_PAGE_SIZE}.")
    sort = args.get("sort", "popular")
    if sort not in SORTS:
        raise CatalogQueryError("sort must be popular, newest, or name.")
    origin = args.get("origin") or None
    if origin is not None and origin not in ORIGINS:
        raise CatalogQueryError("origin must be official or community.")
    category = args.get("category") or None
    if category is not None and category not in template_store.CATEGORIES:
        raise CatalogQueryError(f"category must be one of: {', '.join(template_store.CATEGORIES)}.")
    featured_raw = args.get("featured")
    if featured_raw is None or featured_raw == "":
        featured = None
    elif featured_raw in {"true", "false"}:
        featured = featured_raw == "true"
    else:
        raise CatalogQueryError("featured must be true or false.")
    q = " ".join((args.get("q") or "").split())
    if len(q) > MAX_QUERY_LENGTH:
        raise CatalogQueryError(f"q must be at most {MAX_QUERY_LENGTH} characters.")
    if any(not character.isprintable() for character in q):
        raise CatalogQueryError("q contains unsupported characters.")

    return {
        "limit": int(limit_raw),
        "cursor": args.get("cursor") or None,
        "sort": sort,
        "filters": {"origin": origin, "category": category, "featured": featured, "q": q or None},
    }


def page(query: Dict[str, Any]) -> Dict[str, Any]:
    sort = query["sort"]
    filters = query["filters"]
    filters_hash = hashlib.sha256(json.dumps(filters, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    matching = sorted(
        (entry for entry in catalog_entries() if _matches(entry, filters)),
        key=lambda entry: _sort_key(sort, entry),
    )
    remaining = matching
    if query["cursor"]:
        after = _decode_cursor(query["cursor"], sort, filters_hash)
        remaining = [entry for entry in matching if _sort_key(sort, entry) > after]

    items = remaining[:query["limit"]]
    has_more = len(remaining) > len(items)
    next_cursor = _encode_cursor(sort, filters_hash, _sort_key(sort, items[-1])) if has_more else None
    return {
        "templates": items,
        "page": {
            "limit": query["limit"],
            "count": len(items),
            "total": len(matching),
            "has_more": has_more,
            "next_cursor": next_cursor,
        },
        "query": {"sort": sort, **{key: value for key, value in filters.items() if value is not None}},
    }
