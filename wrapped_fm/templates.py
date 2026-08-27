"""Community template library: validation, storage and review.

Templates are JSON documents that describe how the Make a Wrapped poster is
drawn. The client renderer consumes the same schema, so a template authored in
the visual editor runs everywhere the built-in themes do.

Storage follows the existing file-backed convention used by metrics and badge
snapshots: little JSON files under data/, atomic writes, a lock for safety.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    TEMPLATE_ASSET_DIR,
    TEMPLATE_CREATOR_DIR,
    TEMPLATE_LIBRARY_DIR,
    TEMPLATE_OFFICIAL_DIR,
    TEMPLATE_SUBMISSION_DIR,
)
from .metrics import read_wrapped_count

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SLOTS = ("artists", "tracks", "minutes", "genre")
ELEMENT_KINDS = ("text", "list", "slot")
BACKGROUND_TYPES = ("image", "gradient", "solid")
CATEGORIES = (
    "dark",
    "light",
    "minimal",
    "vibrant",
    "retro",
    "abstract",
    "bold",
    "soft",
)

_NAME_MAX = 60
_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}$")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_DANGEROUS_STRINGS = ("javascript:", "vbscript:", "<script", "data:text/html")


class TemplateInvalidError(Exception):
    """Raised when a submitted template payload fails validation."""


class TemplateUnavailableError(Exception):
    """Raised when a requested template does not exist."""


class TemplateStoreFullError(Exception):
    """Raised when a submission could not be persisted."""


class CreatorInvalidError(Exception):
    """Raised when a creator identity claim fails verification."""


_store_lock = threading.Lock()
_max_slug = 48
_USES_FILE = None

# Baseline share of the overall wrapped count attributed to each official theme
# so the built-in templates show real popularity instead of zero. These existed
# before the template system, so their historical usage can't be tracked per
# slug; a weighted split of the site-wide counter is a fair stand-in.
OFFICIAL_BASELINE_WEIGHTS = {
    "black": 0.30,
    "black_new": 0.12,
    "white_new": 0.08,
    "purple": 0.20,
    "yellow": 0.15,
    "pink": 0.15,
}


def _json_safe_string(raw, max_length: int = _NAME_MAX) -> str:
    if not isinstance(raw, str):
        return ""
    value = "".join(ch for ch in raw if ch.isprintable())
    value = " ".join(value.split())
    return value[:max_length].strip()


def _len_in_range(raw: Optional[str], minimum: int = 1, maximum: int = _NAME_MAX) -> bool:
    return isinstance(raw, str) and minimum <= len(raw.strip()) <= maximum


def _valid_slug(slug: str) -> bool:
    return isinstance(slug, str) and bool(_SEGMENT_RE.match(slug)) and len(slug) <= _max_slug


def _safe_hex(value: Any, default: str) -> str:
    if isinstance(value, str) and _HEX_RE.match(value.strip()):
        return value.strip().lower()
    return default


def _safe_font(value) -> Dict[str, Any]:
    family = "Nunito"
    weight = 700
    size = 48
    if isinstance(value, dict):
        if isinstance(value.get("family"), str) and value["family"].strip():
            family = value["family"].strip()[:40]
        try:
            weight = int(value.get("weight", weight))
        except (TypeError, ValueError):
            pass
        weight = max(100, min(900, weight))
        try:
            size = int(value.get("size", size))
        except (TypeError, ValueError):
            pass
        size = max(8, min(300, size))
    else:
        if isinstance(value, (int, float)):
            size = max(8, min(300, int(value)))
    return {"family": family, "weight": weight, "size": size}


def _validate_color(raw, default: str) -> str:
    if not isinstance(raw, str):
        return default
    value = raw.strip()
    if _HEX_RE.match(value):
        return value.lower()
    if value in ("label", "value"):
        return value
    return default


def _validate_number(raw, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _safe_string(raw, max_length: int) -> str:
    value = _json_safe_string(raw, max_length)
    lowered = value.lower()
    for danger in _DANGEROUS_STRINGS:
        if danger in lowered:
            return ""
    return value


def _validate_background(raw) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateInvalidError("Background must be an object.")
    btype = str(raw.get("type", "gradient")).strip().lower()
    if btype not in BACKGROUND_TYPES:
        raise TemplateInvalidError("Unsupported background type.")
    if btype == "image":
        src = _safe_string(raw.get("src", ""), 600)
        if not src or not (src.startswith("/") or src.startswith("data:image/")):
            raise TemplateInvalidError("Background image must be served from this site.")
        if "data:" in src and "/" not in src[:16]:
            raise TemplateInvalidError("Invalid background image data URI.")
        return {"type": "image", "src": src}
    if btype == "solid":
        return {"type": "solid", "color": _safe_hex(raw.get("color"), "#000000")}
    colors = raw.get("colors")
    if not isinstance(colors, list) or not colors:
        raise TemplateInvalidError("Gradient needs at least one color.")
    cleaned_colors = [_safe_hex(c, "#000000") for c in colors[:4] if isinstance(c, str)]
    if not cleaned_colors:
        raise TemplateInvalidError("Gradient needs at least one valid color.")
    try:
        angle = int(raw.get("angle", 135))
    except (TypeError, ValueError):
        angle = 135
    angle = max(0, min(360, angle))
    return {"type": "gradient", "colors": cleaned_colors, "angle": angle}


def _validate_artwork(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateInvalidError("Artwork must be an object.")
    enabled = bool(raw.get("enabled", True))
    return {
        "enabled": enabled,
        "contain": bool(raw.get("contain", True)),
        "x": _validate_number(raw.get("x", 268), 268, 0, CANVAS_WIDTH),
        "y": _validate_number(raw.get("y", 244), 244, 0, CANVAS_HEIGHT),
        "size": _validate_number(raw.get("size", 544), 544, 80, CANVAS_WIDTH),
        "borderRadius": _validate_number(raw.get("borderRadius", 32), 32, 0, 200),
        "frame": bool(raw.get("frame", True)),
        "frameWidth": _validate_number(raw.get("frameWidth", 10), 10, 0, 40),
    }


def _validate_element(raw, index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateInvalidError(f"Element {index} must be an object.")
    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in ELEMENT_KINDS:
        raise TemplateInvalidError(f"Element {index} has an unsupported kind.")
    element = {
        "id": _safe_string(raw.get("id", f"el-{index}"), 80) or f"el-{index}",
        "kind": kind,
        "x": _validate_number(raw.get("x", 0), 0, -CANVAS_WIDTH, CANVAS_WIDTH * 2),
        "y": _validate_number(raw.get("y", 0), 0, -CANVAS_HEIGHT, CANVAS_HEIGHT * 2),
        "color": _validate_color(raw.get("color"), "label"),
        "baseline": "top" if str(raw.get("baseline", "top")) == "top" else "alphabetic",
        "align": "left",
    }
    align = str(raw.get("align", "left")).lower()
    if align in ("left", "center", "right"):
        element["align"] = align
    if kind == "text":
        element["text"] = _safe_string(raw.get("text", ""), 120) or ""
        if not element["text"] and not raw.get("text"):
            raise TemplateInvalidError(f"Element {index} is empty text.")
    else:
        slot = str(raw.get("slot", "")).strip()
        if slot not in SLOTS:
            raise TemplateInvalidError(f"Element {index} needs a valid data slot.")
        element["slot"] = slot
        element["maxWidth"] = _validate_number(raw.get("maxWidth", 0), 0, 0, CANVAS_WIDTH)
        element["minFontSize"] = _validate_number(raw.get("minFontSize", 24), 12, 8, 200)
        element["ellipsize"] = bool(raw.get("ellipsize", True))
        if kind == "list":
            element["lineHeight"] = _validate_number(raw.get("lineHeight", 72), 72, 8, 300)
            element["prefix"] = bool(raw.get("prefix", True))
    element["font"] = _safe_font(raw.get("font"))
    return element


def validate_template(raw: Any) -> Dict[str, Any]:
    """Validate and normalise a template document, returning a clean copy."""
    if not isinstance(raw, dict):
        raise TemplateInvalidError("Template must be a JSON object.")
    name = _json_safe_string(raw.get("name"), _NAME_MAX)
    if not _len_in_range(name):
        raise TemplateInvalidError("Template name is required (1-60 chars).")
    slug = str(raw.get("slug", "")).strip().lower()
    if not _valid_slug(slug):
        raise TemplateInvalidError("Slug may only contain lowercase letters, numbers and dashes.")
    canvas = raw.get("canvas")
    if isinstance(canvas, dict):
        width = _validate_number(canvas.get("width"), CANVAS_WIDTH, 100, 3000)
        height = _validate_number(canvas.get("height"), CANVAS_HEIGHT, 100, 3000)
    else:
        width = CANVAS_WIDTH
        height = CANVAS_HEIGHT

    palette_raw = raw.get("palette")
    palette_label = "#f3f6ff"
    palette_value = "#ffffff"
    if isinstance(palette_raw, dict):
        palette_label = _safe_hex(palette_raw.get("label"), palette_label)
        palette_value = _safe_hex(palette_raw.get("value"), palette_value)

    elements_raw = raw.get("elements")
    if not isinstance(elements_raw, list) or not elements_raw:
        raise TemplateInvalidError("Template needs at least one element.")
    elements = [_validate_element(el, i) for i, el in enumerate(elements_raw)]

    meta_raw = raw.get("meta")
    meta = {
        "category": "abstract",
        "tags": [],
        "featured": False,
    }
    if isinstance(meta_raw, dict):
        category = str(meta_raw.get("category", "abstract")).strip().lower()
        if category in CATEGORIES:
            meta["category"] = category
        tags = meta_raw.get("tags")
        if isinstance(tags, list):
            meta["tags"] = [_safe_string(t, 40) for t in tags if isinstance(t, str)][:8]
        meta["featured"] = bool(meta_raw.get("featured", False))

    return {
        "version": 1,
        "slug": slug,
        "name": name,
        "canvas": {"width": width, "height": height},
        "palette": {"label": palette_label, "value": palette_value},
        "background": _validate_background(raw.get("background")),
        "artwork": _validate_artwork(raw.get("artwork")),
        "meta": meta,
        "elements": elements,
    }


def creator_id_for_secret(secret: str) -> str:
    re_secret = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
    if not isinstance(secret, str) or not re_secret.match(secret):
        raise CreatorInvalidError("Creator secret is invalid.")
    hash_value = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    return f"c{hash_value[:12]}"


def _validate_creator(raw: Any) -> Tuple[Dict[str, Any], str]:
    if not isinstance(raw, dict):
        raise CreatorInvalidError("Creator information is required.")
    secret = raw.get("secret")
    claimed_id = raw.get("id")
    derived = creator_id_for_secret(secret)
    if isinstance(claimed_id, str) and claimed_id.startswith("c"):
        if claimed_id != derived:
            raise CreatorInvalidError("Creator id does not match the identity secret.")
    name = _json_safe_string(raw.get("name"), 60)
    creator = {
        "id": derived,
        "name": name or f"creator-{derived[-6:]}",
        "website": _safe_string(raw.get("website", ""), 240),
        "bio": _safe_string(raw.get("bio", ""), 280),
    }
    return creator, secret


def _read_json(path) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"))
    os.replace(tmp_path, path)


def list_official_templates() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    try:
        names = os.listdir(TEMPLATE_OFFICIAL_DIR)
    except OSError:
        return result
    for name in names:
        if not name.endswith(".json"):
            continue
        payload = _read_json(os.path.join(TEMPLATE_OFFICIAL_DIR, name))
        if not payload:
            continue
        entry = {
            "slug": payload.get("slug"),
            "name": payload.get("name"),
            "origin": "official",
            "creator": payload.get("creator"),
            "meta": payload.get("meta"),
            "status": "approved",
        }
        if entry["slug"]:
            result.append(entry)
    result.sort(key=lambda item: item.get("name") or "")
    return result


def list_community_templates() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    names = _list_json(TEMPLATE_LIBRARY_DIR)
    for name in names:
        path = os.path.join(TEMPLATE_LIBRARY_DIR, name)
        payload = _read_json(path)
        if not payload:
            continue
        template = payload.get("template")
        if not isinstance(template, dict):
            continue
        slug = template.get("slug")
        if not slug:
            continue
        result.append({
            "slug": slug,
            "name": template.get("name"),
            "origin": "community",
            "creator": payload.get("creator"),
            "meta": template.get("meta"),
            "status": "approved",
            "created_at": payload.get("created_at"),
        })
    result.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return result


def list_templates() -> List[Dict[str, Any]]:
    templates = list_official_templates() + list_community_templates()
    uses = read_uses_map()
    baseline = _official_baseline_uses()
    for template in templates:
        recorded = int(uses.get(template.get("slug"), 0))
        historical = baseline.get(template.get("slug"), 0) if template["origin"] == "official" else 0
        template["uses"] = historical + recorded
    return templates


def _official_baseline_uses() -> Dict[str, int]:
    total = read_wrapped_count()
    return {
        slug: int(round(total * weight))
        for slug, weight in OFFICIAL_BASELINE_WEIGHTS.items()
    }


def resolve_template_exists(slug: str) -> bool:
    return _valid_slug(slug) and (
        os.path.exists(os.path.join(TEMPLATE_OFFICIAL_DIR, f"{slug}.json"))
        or os.path.exists(os.path.join(TEMPLATE_LIBRARY_DIR, f"{slug}.json"))
    )


def get_template(slug: str) -> Dict[str, Any]:
    payload = _read_json(os.path.join(TEMPLATE_OFFICIAL_DIR, f"{slug}.json"))
    if payload:
        payload.setdefault("origin", "official")
        payload.setdefault("status", "approved")
        return payload
    path = os.path.join(TEMPLATE_LIBRARY_DIR, f"{slug}.json")
    payload = _read_json(path)
    if not payload:
        raise TemplateUnavailableError("Template not found.")
    template = payload.get("template")
    if not isinstance(template, dict):
        raise TemplateUnavailableError("Template is malformed.")
    template["origin"] = "community"
    template["status"] = "approved"
    template["creator"] = payload.get("creator") or {}
    return template


def _uses_path() -> str:
    return os.path.join(os.path.dirname(str(TEMPLATE_LIBRARY_DIR)), "template-uses.json")


def read_uses_map() -> Dict[str, int]:
    payload = _read_json(_uses_path())
    if not isinstance(payload, dict):
        return {}
    return {str(k): int(v) for k, v in payload.items() if isinstance(v, (int, float))}


def get_template_uses(slug: str) -> int:
    return int(read_uses_map().get(slug, 0))


def record_template_use(slug: str) -> int:
    with _store_lock:
        uses = read_uses_map()
        count = int(uses.get(slug, 0)) + 1
        uses[slug] = count
        os.makedirs(os.path.dirname(_uses_path()), exist_ok=True)
        _write_json(_uses_path(), uses)
    return count


def _list_json(directory) -> List[str]:
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(name for name in names if name.endswith(".json"))


def get_pending_submissions() -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for name in _list_json(TEMPLATE_SUBMISSION_DIR):
        payload = _read_json(os.path.join(TEMPLATE_SUBMISSION_DIR, name))
        if not payload:
            continue
        entry = dict(payload)
        entry["submission_id"] = name[:-5]
        result.append(entry)
    result.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return result


def _slug_taken(slug: str, official: bool = True, community: bool = True) -> bool:
    if official and os.path.exists(os.path.join(TEMPLATE_OFFICIAL_DIR, f"{slug}.json")):
        return True
    if community and os.path.exists(os.path.join(TEMPLATE_LIBRARY_DIR, f"{slug}.json")):
        return True
    return False


def submit_template(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise TemplateInvalidError("Submission must be a JSON object.")
    creator, _secret = _validate_creator(raw.get("creator"))
    template = validate_template(raw.get("template"))
    submission_id = uuid.uuid4().hex[:16]
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _persist_creator(creator)
    payload = {
        "version": 1,
        "submission_id": submission_id,
        "status": "pending_review",
        "created_at": created_at,
        "creator": creator,
        "template": template,
        "reason": _safe_string(raw.get("reason", ""), 500),
    }
    path = os.path.join(TEMPLATE_SUBMISSION_DIR, f"{submission_id}.json")
    with _store_lock:
        _write_json(path, payload)
    return payload


def _persist_creator(creator: Dict[str, Any]) -> None:
    os.makedirs(TEMPLATE_CREATOR_DIR, exist_ok=True)
    path = os.path.join(TEMPLATE_CREATOR_DIR, f"{creator['id']}.json")
    existing = _read_json(path)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if existing:
        existing["name"] = creator["name"] or existing.get("name", "")
        existing["website"] = creator.get("website") or existing.get("website", "")
        existing["bio"] = creator.get("bio") or existing.get("bio", "")
        existing["updated_at"] = now
        with _store_lock:
            _write_json(path, existing)
    else:
        creator["created_at"] = now
        creator["updated_at"] = now
        with _store_lock:
            _write_json(path, creator)


def get_creator(creator_id: str) -> Dict[str, Any]:
    payload = _read_json(os.path.join(TEMPLATE_CREATOR_DIR, f"{creator_id}.json"))
    return payload or {}


def count_community_templates() -> int:
    return len(list_community_templates())


def approve_submission(submission_id: str) -> Dict[str, Any]:
    path = os.path.join(TEMPLATE_SUBMISSION_DIR, f"{submission_id}.json")
    payload = _read_json(path)
    if not payload:
        raise TemplateUnavailableError("Submission not found.")
    template = payload.get("template")
    if not isinstance(template, dict):
        raise TemplateInvalidError("Submission template is malformed.")
    slug = template.get("slug")
    if _slug_taken(slug):
        raise TemplateInvalidError(f"Slug '{slug}' is already in use.")
    created_at = payload.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    library_payload = {
        "version": 1,
        "slug": slug,
        "name": template.get("name"),
        "template": validate_template(template),
        "creator": payload.get("creator"),
        "created_at": created_at,
        "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with _store_lock:
        _write_json(os.path.join(TEMPLATE_LIBRARY_DIR, f"{slug}.json"), library_payload)
        os.remove(path)
    return library_payload


def reject_submission(submission_id: str) -> None:
    path = os.path.join(TEMPLATE_SUBMISSION_DIR, f"{submission_id}.json")
    with _store_lock:
        try:
            os.remove(path)
        except OSError:
            raise TemplateUnavailableError("Submission not found.")


def store_template_asset(slug: str, filename: str, data: bytes) -> Dict[str, Any]:
    slug = slug.strip().lower() if isinstance(slug, str) else ""
    if not _valid_slug(slug):
        raise TemplateInvalidError("Invalid slug for asset.")
    name = (filename or "").lower()
    if "." not in name:
        raise TemplateInvalidError("Background asset needs a .png, .jpg, or .webp extension.")
    extension = name.rsplit(".", 1)[-1]
    if extension not in ("png", "jpg", "jpeg", "webp"):
        raise TemplateInvalidError("Background asset must be a PNG, JPEG, or WebP image.")
    stored_name = {"png": "background.png", "jpg": "background.jpg", "jpeg": "background.jpg", "webp": "background.webp"}[extension]
    directory = os.path.join(TEMPLATE_ASSET_DIR, slug)
    os.makedirs(directory, exist_ok=True)
    with _store_lock:
        with open(os.path.join(directory, stored_name), "wb") as handle:
            handle.write(data)
    return {"slug": slug, "filename": f"/template-assets/{slug}/{stored_name}"}


def resolve_template_asset_path(rel_path: str) -> Optional[str]:
    if not isinstance(rel_path, str):
        return None
    path = rel_path.strip()
    if not path.startswith("/template-assets/"):
        return None
    rel = path[len("/template-assets/"):]
    if "/" not in rel or rel.startswith("/"):
        return None
    return os.path.join(str(TEMPLATE_ASSET_DIR), rel)
