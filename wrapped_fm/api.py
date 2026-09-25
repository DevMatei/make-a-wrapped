"""Versioned API for server-rendered Wrapped posters."""

from __future__ import annotations

import base64
import copy
import json
import logging
import re
import struct
import subprocess
import threading
from pathlib import Path

from flask import Blueprint, Response, abort, current_app, jsonify, request
from werkzeug.exceptions import HTTPException

from . import templates as template_store
from .config import (
    API_RENDER_CONCURRENCY,
    API_RENDER_QUEUE_LIMIT,
    API_RENDER_QUEUE_TIMEOUT,
    IMAGE_RATE_LIMIT,
    TEMPLATE_ASSET_DIR,
    TEMPLATE_ASSET_MAX_BYTES,
)
from .date_range import resolve_preset
from .genres import get_top_genre
from .lastfm import (
    estimate_lastfm_listen_minutes,
    get_lastfm_top_artists,
    get_lastfm_top_genre,
    get_lastfm_top_tracks,
)
from .listenbrainz import (
    clamp_top_number,
    estimate_total_listen_minutes,
    get_top_artists_payload,
    get_top_tracks_payload,
)
from .images import (
    ImageQueueBusyError,
    ImageQueueFullError,
    ImageUnavailableError,
    fetch_top_artist_image,
)
from .rate_limiter import rate_limit
from .metrics import increment_wrapped_count

logger = logging.getLogger("wrapped_fm.api")
bp = Blueprint("wrapped_api_v1", __name__, url_prefix="/api/v1")

MAX_API_REQUEST_BYTES = 64 * 1024
MAX_CUSTOM_ARTWORK_BYTES = 32 * 1024
MAX_PROVIDER_ARTWORK_BYTES = 6 * 1024 * 1024
MAX_SOURCE_IMAGE_PIXELS = 16_000_000
MAX_CANVAS_PIXELS = 2_500_000
MAX_RANKED_ITEMS = 10
DEFAULT_PROVIDER_ITEM_COUNT = 5
MAX_TEXT_LENGTH = 120
PROVIDER_SERVICES = {"listenbrainz", "lastfm", "librefm"}
CUSTOM_FIELDS = {"artists", "tracks", "minutes", "genre", "period", "artwork"}
_render_slots = threading.BoundedSemaphore(API_RENDER_CONCURRENCY)
_render_waiters = threading.BoundedSemaphore(API_RENDER_QUEUE_LIMIT)


def _acquire_render_slot() -> bool:
    if _render_slots.acquire(blocking=False):
        return True
    if not _render_waiters.acquire(blocking=False):
        return False
    try:
        return _render_slots.acquire(timeout=API_RENDER_QUEUE_TIMEOUT)
    finally:
        _render_waiters.release()


@bp.errorhandler(HTTPException)
def handle_http_error(error: HTTPException):
    return api_http_error_response(error)


def api_http_error_response(error: HTTPException) -> Response:
    response = jsonify({
        "error": {
            "code": error.name.lower().replace(" ", "_"),
            "message": error.description,
        }
    })
    response.status_code = error.code or 500
    original_response = error.get_response()
    if original_response.headers.get("Retry-After"):
        response.headers["Retry-After"] = original_response.headers["Retry-After"]
    elif response.status_code == 503:
        response.headers["Retry-After"] = "2"
    _add_api_cors_headers(response)
    return response


@bp.errorhandler(Exception)
def handle_unexpected_error(error: Exception):
    return api_internal_error_response(error)


def api_internal_error_response(error: Exception) -> Response:
    logger.exception("Unhandled API error", exc_info=error)
    response = jsonify({
        "error": {
            "code": "internal_error",
            "message": "The request could not be completed.",
        }
    })
    response.status_code = 500
    _add_api_cors_headers(response)
    return response


def _add_api_cors_headers(response: Response) -> Response:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Max-Age"] = "600"
    return response


@bp.after_request
def add_cors_headers(response: Response) -> Response:
    return _add_api_cors_headers(response)


def _clean_text(value, field: str, *, required: bool = True) -> str:
    if not isinstance(value, str):
        abort(400, description=f"{field} must be a string.")
    cleaned = " ".join(value.split())
    if required and not cleaned:
        abort(400, description=f"{field} must not be empty.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        abort(400, description=f"{field} must be at most {MAX_TEXT_LENGTH} characters.")
    if any(not character.isprintable() for character in cleaned):
        abort(400, description=f"{field} contains unsupported characters.")
    return cleaned


def _ranked_items(value, field: str) -> list[str]:
    if not isinstance(value, list):
        abort(400, description=f"{field} must be an array of strings.")
    if len(value) > MAX_RANKED_ITEMS:
        abort(400, description=f"{field} may contain at most {MAX_RANKED_ITEMS} items.")
    return [_clean_text(item, f"{field}[{index}]") for index, item in enumerate(value)]


def _decode_data_image(value, field: str, max_bytes: int) -> bytes:
    if not isinstance(value, str):
        abort(400, description=f"{field} must be a base64 PNG, JPEG, or WebP data URL.")
    match = re.fullmatch(r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})", value, re.IGNORECASE)
    if not match:
        abort(400, description=f"{field} must be a base64 PNG, JPEG, or WebP data URL.")
    try:
        image_data = base64.b64decode(match.group(2), validate=True)
    except ValueError:
        abort(400, description=f"{field} contains invalid base64 data.")
    if not image_data or len(image_data) > max_bytes:
        abort(400, description=f"{field} exceeds its {max_bytes}-byte image limit.")
    return image_data


def _image_dimensions(image_data: bytes) -> tuple[int, int] | None:
    if image_data.startswith(b"\x89PNG\r\n\x1a\n") and len(image_data) >= 24:
        return struct.unpack(">II", image_data[16:24])
    if image_data[:3] == b"GIF" and len(image_data) >= 10:
        return struct.unpack("<HH", image_data[6:10])
    if image_data[:4] == b"RIFF" and image_data[8:12] == b"WEBP" and len(image_data) >= 25:
        chunk = image_data[12:16]
        if chunk == b"VP8X" and len(image_data) >= 30:
            width = int.from_bytes(image_data[24:27], "little") + 1
            height = int.from_bytes(image_data[27:30], "little") + 1
            return width, height
        if chunk == b"VP8 " and len(image_data) >= 30 and image_data[23:26] == b"\x9d\x01\x2a":
            width, height = struct.unpack("<HH", image_data[26:30])
            return width & 0x3FFF, height & 0x3FFF
        if chunk == b"VP8L" and len(image_data) >= 25 and image_data[20] == 0x2F:
            width = 1 + image_data[21] + ((image_data[22] & 0x3F) << 8)
            height = 1 + ((image_data[22] & 0xC0) >> 6) + (image_data[23] << 2) + ((image_data[24] & 0x0F) << 10)
            return width, height
    if image_data[:2] == b"\xff\xd8":
        index = 2
        while index + 4 <= len(image_data):
            if image_data[index] != 0xFF:
                index += 1
                continue
            while index < len(image_data) and image_data[index] == 0xFF:
                index += 1
            if index >= len(image_data):
                break
            marker = image_data[index]
            index += 1
            if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
                continue
            if index + 2 > len(image_data):
                break
            segment_size = int.from_bytes(image_data[index:index + 2], "big")
            if segment_size < 2 or index + segment_size > len(image_data):
                break
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height, width = struct.unpack(">HH", image_data[index + 3:index + 7])
                return width, height
            index += segment_size
    return None


def _validate_image_dimensions(image_data: bytes, field: str) -> bool:
    dimensions = _image_dimensions(image_data)
    if not dimensions or min(dimensions) < 1:
        abort(400, description=f"{field} must be a valid PNG, JPEG, WebP, or GIF image.")
    if dimensions[0] * dimensions[1] > MAX_SOURCE_IMAGE_PIXELS:
        abort(400, description=f"{field} exceeds the {MAX_SOURCE_IMAGE_PIXELS}-pixel image limit.")
    return True


def _custom_data(raw: dict) -> tuple[dict, bytes | None]:
    if not isinstance(raw, dict):
        abort(400, description="data must be an object.")
    unknown = set(raw) - CUSTOM_FIELDS
    if unknown:
        abort(400, description=f"Unsupported data fields: {', '.join(sorted(unknown))}.")

    artists = _ranked_items(raw.get("artists", []), "data.artists")
    tracks = _ranked_items(raw.get("tracks", []), "data.tracks")
    if not artists and not tracks:
        abort(400, description="data must include at least one artist or track.")

    minutes_value = raw.get("minutes", "0")
    if isinstance(minutes_value, bool) or not isinstance(minutes_value, (str, int)):
        abort(400, description="data.minutes must be a string or non-negative integer.")
    minutes = str(minutes_value) if isinstance(minutes_value, int) else _clean_text(
        minutes_value,
        "data.minutes",
        required=False,
    )
    if (
        len(minutes) > MAX_TEXT_LENGTH
        or (isinstance(minutes_value, int) and minutes_value < 0)
        or (minutes.startswith("-") and minutes[1:].replace(",", "").replace(".", "").isdigit())
    ):
        abort(400, description="data.minutes must be a non-negative value of at most 120 characters.")

    genre = _clean_text(raw.get("genre", "No genre"), "data.genre")
    period = raw.get("period")
    if period is not None:
        if not isinstance(period, dict) or set(period) - {"label"}:
            abort(400, description="data.period may contain only a label string.")
        period = {"label": _clean_text(period.get("label"), "data.period.label")}

    artwork = raw.get("artwork")
    artwork_data = _decode_data_image(artwork, "data.artwork", MAX_CUSTOM_ARTWORK_BYTES) if artwork is not None else None
    if artwork_data:
        _validate_image_dimensions(artwork_data, "data.artwork")
    data = {"artists": artists, "tracks": tracks, "minutes": minutes, "genre": genre, "period": period}
    return data, artwork_data


def _provider_data(source: dict) -> tuple[dict, dict, object]:
    service = source.get("provider")
    if not isinstance(service, str):
        abort(400, description="source.provider must be a string.")
    unknown = set(source) - {"type", "provider", "username", "range", "limit"}
    if unknown:
        abort(400, description=f"Unsupported provider source fields: {', '.join(sorted(unknown))}.")
    if service not in PROVIDER_SERVICES:
        if service == "navidrome":
            abort(400, description="Navidrome is browser-only in this project; use custom data with this API.")
        abort(400, description="source.provider must be listenbrainz, lastfm, or librefm.")

    username = _clean_text(source.get("username"), "source.username")
    selected_range = source.get("range", {"preset": "this_year"})
    if not isinstance(selected_range, dict) or set(selected_range) - {"preset", "month", "year"}:
        abort(400, description="source.range must contain preset and optional month and year.")
    preset = selected_range.get("preset", "this_year")
    if not isinstance(preset, str):
        abort(400, description="source.range.preset must be a string.")
    if preset == "specific_month":
        if (
            isinstance(selected_range.get("month"), bool)
            or not isinstance(selected_range.get("month"), int)
            or isinstance(selected_range.get("year"), bool)
            or not isinstance(selected_range.get("year"), int)
        ):
            abort(400, description="specific_month needs integer month and year values.")
    elif "month" in selected_range or "year" in selected_range:
        abort(400, description="month and year are only accepted with the specific_month period.")
    try:
        range_obj = resolve_preset(
            preset,
            month=selected_range.get("month"),
            year=selected_range.get("year"),
        )
    except (TypeError, ValueError):
        abort(400, description="source.range is not a valid period.")

    item_count = source.get("limit", DEFAULT_PROVIDER_ITEM_COUNT)
    if type(item_count) is not int or not 1 <= item_count <= MAX_RANKED_ITEMS:
        abort(400, description=f"source.limit must be an integer from 1 to {MAX_RANKED_ITEMS}.")
    count = clamp_top_number(item_count)
    try:
        if service == "listenbrainz":
            artists = [item.get("artist_name", "Unknown artist") for item in get_top_artists_payload(username, count, range_obj=range_obj)]
            tracks = [item.get("track_name", "Unknown track") for item in get_top_tracks_payload(username, count, range_obj=range_obj)]
            minutes = estimate_total_listen_minutes(username, range_obj=range_obj)
            genre = get_top_genre(username, range_obj=range_obj)
        else:
            artists = get_lastfm_top_artists(username, count, range_obj=range_obj, service=service)
            tracks = get_lastfm_top_tracks(username, count, range_obj=range_obj, service=service)
            minutes = estimate_lastfm_listen_minutes(username, range_obj=range_obj, service=service)
            genre = get_lastfm_top_genre(username, range_obj=range_obj, service=service)
    except Exception:
        logger.exception("Provider lookup failed for %s", service)
        abort(502, description="The selected music provider could not return Wrapped data.")

    data = {
        "artists": [_clean_text(value, "provider artist") for value in artists[:count]],
        "tracks": [_clean_text(value, "provider track") for value in tracks[:count]],
        "minutes": str(minutes),
        "genre": _clean_text(genre or "No genre", "provider genre"),
        "period": {
            "preset": range_obj.preset,
            "label": range_obj.label,
            "kind": range_obj.kind,
            "start_ts": range_obj.start_ts,
            "end_ts": range_obj.end_ts,
            "is_custom": range_obj.is_custom,
        },
    }
    return data, {"type": "provider", "provider": service, "username": username}, range_obj


def _read_payload() -> dict:
    if request.mimetype != "application/json":
        abort(415, description="Content-Type must be application/json.")
    if request.content_length is not None and request.content_length > MAX_API_REQUEST_BYTES:
        abort(413, description="Request body exceeds the 64 KiB API limit.")
    raw = request.get_data(cache=True)
    if len(raw) > MAX_API_REQUEST_BYTES:
        abort(413, description="Request body exceeds the 64 KiB API limit.")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        abort(400, description="Request body must contain valid JSON.")
    if not isinstance(payload, dict):
        abort(400, description="Request body must be a JSON object.")
    return payload


def _template_background_bytes(template: dict) -> bytes | None:
    background = template.get("background") or {}
    if not isinstance(background, dict):
        abort(422, description="Selected template has an invalid background.")
    if background.get("type") != "image":
        return None
    source = background.get("src", "")
    if isinstance(source, str) and source.startswith("data:image/"):
        image_data = _decode_data_image(source, "template background", TEMPLATE_ASSET_MAX_BYTES)
        dimensions = _image_dimensions(image_data)
        if not dimensions or min(dimensions) < 1 or dimensions[0] * dimensions[1] > MAX_SOURCE_IMAGE_PIXELS:
            abort(422, description="Selected template background is invalid or too large to render.")
        return image_data

    if not isinstance(source, str) or not source.startswith("/"):
        abort(422, description="Selected template has an unsupported image background.")
    if source.startswith("/template-assets/"):
        asset_root = Path(TEMPLATE_ASSET_DIR).resolve()
        resolved = template_store.resolve_template_asset_path(source)
        if not resolved:
            abort(422, description="Selected template background is unavailable.")
        path = Path(resolved).resolve()
    else:
        asset_root = Path(current_app.static_folder).resolve()
        path = (asset_root / source.lstrip("/")).resolve()
    if not path.is_relative_to(asset_root) or not path.is_file():
        abort(422, description="Selected template background is unavailable.")
    try:
        image_data = path.read_bytes()
    except OSError:
        abort(422, description="Selected template background is unavailable.")
    if len(image_data) > TEMPLATE_ASSET_MAX_BYTES:
        abort(422, description="Selected template background exceeds the render limit.")
    dimensions = _image_dimensions(image_data)
    if not dimensions or min(dimensions) < 1 or dimensions[0] * dimensions[1] > MAX_SOURCE_IMAGE_PIXELS:
        abort(422, description="Selected template background is invalid or too large to render.")
    return image_data


def _provider_artwork(source_info: dict, range_obj) -> bytes | None:
    try:
        image = fetch_top_artist_image(
            source_info["username"],
            preferred_source=source_info.get("source", "artist"),
            service=source_info["provider"],
            range_obj=range_obj,
        )
    except (ImageUnavailableError, ImageQueueBusyError):
        return None
    except ImageQueueFullError:
        abort(429, description="Artwork service is busy. Retry shortly.")
    except Exception:
        logger.exception("Provider artwork lookup failed for %s", source_info["provider"])
        return None
    if len(image.content) > MAX_PROVIDER_ARTWORK_BYTES:
        logger.warning("Skipping provider artwork above the API size limit")
        return None
    dimensions = _image_dimensions(image.content)
    if not dimensions:
        logger.warning("Skipping provider artwork with an unsupported image format")
        return None
    if min(dimensions) < 1 or dimensions[0] * dimensions[1] > MAX_SOURCE_IMAGE_PIXELS:
        logger.warning("Skipping provider artwork above the image dimension limit")
        return None
    return image.content


def _artwork_options(value, source_info: dict | None, range_obj) -> tuple[dict, object] | None:
    if value is None:
        if source_info:
            return {**source_info, "source": "artist"}, range_obj
        return None
    if not isinstance(value, dict) or set(value) - {"provider", "username", "source", "range", "enabled", "fit"}:
        abort(400, description="artwork may contain provider, username, source, range, enabled, and fit.")
    if not source_info and set(value) == {"fit"}:
        if not isinstance(value["fit"], str) or value["fit"] not in {"cover", "contain"}:
            abort(400, description="artwork.fit must be cover or contain.")
        return None
    if value.get("enabled", True) is False:
        return None
    if value.get("enabled", True) is not True:
        abort(400, description="artwork.enabled must be a boolean.")

    provider = value.get("provider", source_info.get("provider") if source_info else None)
    if not isinstance(provider, str) or provider not in PROVIDER_SERVICES:
        abort(400, description="artwork.provider must be listenbrainz, lastfm, or librefm.")
    username = value.get("username", source_info.get("username") if source_info else None)
    username = _clean_text(username, "artwork.username")
    art_source = value.get("source", "artist")
    if not isinstance(art_source, str) or art_source not in {"artist", "release"}:
        abort(400, description="artwork.source must be artist or release.")
    fit = value.get("fit", "cover")
    if not isinstance(fit, str) or fit not in {"cover", "contain"}:
        abort(400, description="artwork.fit must be cover or contain.")

    selected_range = value.get("range")
    if selected_range is None:
        selected_range_obj = range_obj or resolve_preset("this_year")
    else:
        if not isinstance(selected_range, dict) or set(selected_range) - {"preset", "month", "year"}:
            abort(400, description="artwork.range must contain preset and optional month and year.")
        preset = selected_range.get("preset", "this_year")
        if not isinstance(preset, str):
            abort(400, description="artwork.range.preset must be a string.")
        if preset == "specific_month":
            month = selected_range.get("month")
            year = selected_range.get("year")
            if type(month) is not int or type(year) is not int:
                abort(400, description="artwork.range specific_month needs integer month and year values.")
        elif "month" in selected_range or "year" in selected_range:
            abort(400, description="artwork.range month and year are only accepted with specific_month.")
        try:
            selected_range_obj = resolve_preset(
                preset,
                month=selected_range.get("month"),
                year=selected_range.get("year"),
            )
        except (TypeError, ValueError):
            abort(400, description="artwork.range is not a valid period.")
    return {"type": "provider", "provider": provider, "username": username, "source": art_source}, selected_range_obj


def _render_image(template: dict, data: dict, image_data: bytes | None, output_format: str) -> bytes:
    canvas = template.get("canvas")
    if not isinstance(canvas, dict):
        abort(422, description="Selected template has an invalid canvas size.")
    width = canvas.get("width")
    height = canvas.get("height")
    if (
        type(width) is not int
        or type(height) is not int
        or width < 1
        or height < 1
        or width * height > MAX_CANVAS_PIXELS
    ):
        abort(422, description="Selected template canvas exceeds the render size limit.")

    assets = {}
    background = _template_background_bytes(template)
    if background:
        assets["background"] = base64.b64encode(background).decode("ascii")
    if image_data:
        assets["artwork"] = base64.b64encode(image_data).decode("ascii")
    payload = json.dumps({
        "template": template,
        "data": data,
        "assets": assets,
        "format": output_format,
    }).encode("utf-8")
    project_root = Path(__file__).resolve().parent.parent
    renderer = project_root / "scripts" / "render-wrapped.mjs"
    try:
        result = subprocess.run(
            ["node", "--max-old-space-size=128", str(renderer)],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=project_root,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        abort(503, description="The renderer timed out. Retry shortly.")
    except OSError:
        logger.exception("Node Canvas renderer could not be started")
        abort(503, description="The image renderer is unavailable.")
    if result.returncode:
        error_text = result.stderr.decode("utf-8", errors="replace")[:1000]
        if "exceeds the output size limit" in error_text:
            abort(413, description="Generated image exceeds the 12 MiB output limit.")
        logger.error("Canvas render failed: %s", error_text)
        abort(500, description="The Wrapped image could not be rendered.")
    if not result.stdout:
        logger.error("Canvas renderer returned an empty image")
        abort(500, description="The Wrapped image could not be rendered.")
    return result.stdout


@bp.route("/wrapped", methods=["POST", "OPTIONS"])
@rate_limit(IMAGE_RATE_LIMIT)
def generate_wrapped_api() -> Response:
    if request.method == "OPTIONS":
        return current_app.response_class(status=204)
    payload = _read_payload()
    unknown = set(payload) - {"source", "data", "template", "format", "artwork"}
    if unknown:
        abort(400, description=f"Unsupported request fields: {', '.join(sorted(unknown))}.")
    output_format = payload.get("format", "png")
    if not isinstance(output_format, str) or output_format not in {"png", "svg"}:
        abort(400, description="format must be png or svg.")
    if ("source" in payload) == ("data" in payload):
        abort(400, description="Provide either data or source, but not both.")
    template_slug = payload.get("template", "black")
    if not isinstance(template_slug, str) or len(template_slug) > 48:
        abort(400, description="template must be a template slug string.")
    try:
        selected_template = template_store.get_template(template_slug)
    except template_store.TemplateUnavailableError:
        abort(404, description="Template not found.")

    if not _acquire_render_slot():
        abort(503, description="The render queue is full or timed out. Retry shortly.")
    try:
        range_obj = None
        source_info = None
        image_data = None
        if "source" in payload:
            source = payload["source"]
            if not isinstance(source, dict) or source.get("type") != "provider":
                abort(400, description="source.type must be provider.")
            data, source_info, range_obj = _provider_data(source)
        else:
            data, image_data = _custom_data(payload["data"])
            artwork_options_raw = payload.get("artwork")
            if image_data and isinstance(artwork_options_raw, dict) and set(artwork_options_raw) - {"fit"}:
                abort(400, description="Choose either data.artwork or an artwork provider source.")

        artwork_options = _artwork_options(payload.get("artwork"), source_info, range_obj)
        artwork_fit = payload.get("artwork", {}).get("fit", "cover") if isinstance(payload.get("artwork"), dict) else "cover"
        if artwork_options:
            artwork_source, artwork_range = artwork_options
            if selected_template.get("artwork", {}).get("enabled", True) and not image_data:
                image_data = _provider_artwork(artwork_source, artwork_range)

        render_template = copy.deepcopy(selected_template)
        if image_data and isinstance(render_template.get("artwork"), dict):
            render_template["artwork"]["contain"] = artwork_fit == "contain"
        image_bytes = _render_image(render_template, data, image_data, output_format)
    finally:
        _render_slots.release()

    try:
        increment_wrapped_count()
        template_store.record_template_use(selected_template["slug"])
    except Exception:
        logger.exception("Could not record API Wrapped generation")

    content_type = "image/png" if output_format == "png" else "image/svg+xml"
    filename = f"wrapped-{selected_template['slug']}.{output_format}"
    response = current_app.response_class(image_bytes, mimetype=content_type)
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
