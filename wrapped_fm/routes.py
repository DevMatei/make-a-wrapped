"""Flask routes blueprint."""

from __future__ import annotations

import io
import json
import logging
import os

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    request,
    send_file,
)

from . import templates as template_store
from .badge import badge_label, build_badge, normalise_badge_color, normalise_badge_type, render_badge_svg
from .badge_store import (
    BadgeStoreFullError,
    SnapshotInvalidError,
    fetch_snapshot,
    store_snapshot,
)
from .config import (
    BADGE_SNAPSHOT_TTL_SECONDS,
    IMAGE_RATE_LIMIT,
    SITE_URL,
    STATS_RATE_LIMIT,
    TEMPLATE_ASSET_MAX_BYTES,
    TEMPLATE_REVIEW_KEY,
    TEMP_ARTWORK_MAX_BYTES,
    TEMP_ARTWORK_TTL_SECONDS,
    TURNSTILE_ENABLED,
    TURNSTILE_SITE_KEY,
    WRAPPED_COUNT_SINCE,
)
from .date_range import (
    PRESET_ALL_TIME,
    describe_for_client,
    parse_query_params,
    resolve_preset,
)
from .genres import get_genre_for_artist, get_top_genre
from .images import (
    ImageQueueBusyError,
    ImageQueueFullError,
    ImageUnavailableError,
    fetch_top_artist_image,
)
from .listenbrainz import (
    clamp_top_number,
    format_ranked_lines,
    get_top_artists_payload,
    get_top_releases_payload,
    get_top_tracks_payload,
    estimate_total_listen_minutes,
)
from .lastfm import (
    estimate_lastfm_listen_minutes,
    get_lastfm_artist_genre,
    get_lastfm_top_albums,
    get_lastfm_top_artists,
    get_lastfm_top_genre,
    get_lastfm_top_tracks,
)
from .metrics import increment_wrapped_count, read_wrapped_count
from .rate_limiter import rate_limit
from .temp_artwork import ArtworkExpiredError, ArtworkMissingError, fetch_artwork, store_artwork
from .turnstile import require_turnstile


logger = logging.getLogger("wrapped_fm")
bp = Blueprint("wrapped_routes", __name__)
SUPPORTED_STATS_SERVICES = {"listenbrainz", "lastfm", "librefm"}
LASTFM_FAMILY_SERVICES = {"lastfm", "librefm"}
# raster only, no SVG (can carry scripts and we serve it from our origin)
ALLOWED_ARTWORK_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


BADGE_SANDBOX_POLICY = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


def _resolve_stats_service() -> str:
    service = (request.args.get("service") or "listenbrainz").strip().lower()
    if service not in SUPPORTED_STATS_SERVICES:
        return "listenbrainz"
    return service


def _resolve_date_range():
    preset = (request.args.get("range") or request.args.get("preset") or "").strip().lower()
    if not preset:
        return resolve_preset("this_year")
    try:
        return parse_query_params(request.args.items(multi=True))
    except ValueError:
        return resolve_preset("this_year")


def _range_metadata(range_obj) -> dict:
    return {
        "preset": range_obj.preset,
        "label": range_obj.label,
        "kind": range_obj.kind,
        "start_ts": range_obj.start_ts,
        "end_ts": range_obj.end_ts,
        "is_custom": range_obj.is_custom,
    }


def _set_period_header(response, range_obj) -> None:
    try:
        response.headers["X-Period"] = json.dumps(_range_metadata(range_obj))
    except Exception:
        pass


def _safe_lb_artists(username: str, number: int, range_obj):
    try:
        return get_top_artists_payload(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("LB artists failed for %s: %s", username, exc)
        return [], True


def _safe_lb_tracks(username: str, number: int, range_obj):
    try:
        return get_top_tracks_payload(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("LB tracks failed for %s: %s", username, exc)
        return [], True


def _safe_lb_releases(username: str, number: int, range_obj):
    try:
        return get_top_releases_payload(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("LB releases failed for %s: %s", username, exc)
        return [], True


def _safe_lb_minutes(username: str, range_obj):
    try:
        return estimate_total_listen_minutes(username, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("LB minutes failed for %s: %s", username, exc)
        return "0", True


def _safe_lb_genre(username: str, range_obj):
    try:
        return get_top_genre(username, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("LB genre failed for %s: %s", username, exc)
        return "No genre", True


def _safe_lastfm_artists(username: str, number: int, range_obj, service: str = "lastfm"):
    try:
        return get_lastfm_top_artists(username, number, range_obj=range_obj, service=service), False
    except Exception as exc:
        logger.warning("music service artists failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_tracks(username: str, number: int, range_obj, service: str = "lastfm"):
    try:
        return get_lastfm_top_tracks(username, number, range_obj=range_obj, service=service), False
    except Exception as exc:
        logger.warning("music service tracks failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_albums(username: str, number: int, range_obj, service: str = "lastfm"):
    try:
        return get_lastfm_top_albums(username, number, range_obj=range_obj, service=service), False
    except Exception as exc:
        logger.warning("music service albums failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_minutes(username: str, range_obj, service: str = "lastfm"):
    try:
        return estimate_lastfm_listen_minutes(username, range_obj=range_obj, service=service), False
    except Exception as exc:
        logger.warning("music service minutes failed for %s: %s", username, exc)
        return "0", True


def _safe_lastfm_genre(username: str, range_obj, service: str = "lastfm"):
    try:
        return get_lastfm_top_genre(username, range_obj=range_obj, service=service), False
    except Exception as exc:
        logger.warning("music service genre failed for %s: %s", username, exc)
        return "No genre", True


def _is_lastfm_family(service: str) -> bool:
    return service in LASTFM_FAMILY_SERVICES


def _all_time_fallback_range():
    return resolve_preset(PRESET_ALL_TIME)


@bp.route("/")
def root() -> Response:
    return current_app.send_static_file("index.html")


@bp.route("/templates")
def templates_page() -> Response:
    return current_app.send_static_file("templates.html")


@bp.route("/marketplace")
def marketplace_page() -> Response:
    page_path = os.path.join(str(current_app.static_folder), "marketplace.html")
    try:
        with open(page_path, "r", encoding="utf-8") as handle:
            html = handle.read()
    except OSError:
        return current_app.send_static_file("marketplace.html")
    try:
        templates = template_store.list_templates()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Template list failed for marketplace SEO: %s", exc)
        templates = []
    items = [
        {
            "@type": "ListItem",
            "position": index + 1,
            "item": {
                "@type": "CreativeWork",
                "name": template.get("name") or "Untitled",
                "alternateName": template.get("slug"),
                "url": f"{SITE_URL}/?template={template['slug']}",
                "author": {
                    "@type": "Person",
                    "name": (template.get("creator") or {}).get("name") or "Make a Wrapped",
                },
                "isAccessibleForFree": True,
            },
        }
        for index, template in enumerate(templates)
        if template.get("slug")
    ]
    seo = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "Make a Wrapped template library",
        "url": f"{SITE_URL}/marketplace",
        "description": "Official and community templates for your ListenBrainz, Last.fm, Libre.fm, or Navidrome wrapped. Pick one or make your own.",
        "isAccessibleForFree": True,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(items),
            "itemListElement": items,
        },
    }
    json_ld = f'<script type="application/ld+json">\n{json.dumps(seo)}\n</script>'
    html = html.replace("<!--MARKETPLACE_SEO-->", json_ld)
    response = current_app.response_class(html, mimetype="text/html")
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@bp.route("/editor")
def editor_page() -> Response:
    return current_app.send_static_file("editor.html")


@bp.route("/admin")
def admin_page() -> Response:
    return current_app.send_static_file("admin.html")


@bp.route("/api/templates", methods=["GET"])
def list_templates_api() -> Response:
    try:
        templates = template_store.list_templates()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Template listing failed: %s", exc)
        templates = []
    response = jsonify({"templates": templates})
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@bp.route("/api/templates/<slug>", methods=["GET"])
def get_template_api(slug: str) -> Response:
    try:
        template = template_store.get_template(slug)
    except template_store.TemplateUnavailableError:
        abort(404, description="Template not found.")
    response = jsonify({"template": template})
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@bp.route("/api/templates/<slug>/use", methods=["POST"])
@rate_limit(STATS_RATE_LIMIT)
def record_template_use_api(slug: str) -> Response:
    if not template_store.resolve_template_exists(slug):
        abort(404, description="Template not found.")
    count = template_store.record_template_use(slug)
    return jsonify({"ok": True, "uses": count})


@bp.route("/api/templates/submit", methods=["POST"])
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def submit_template_api() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        submission = template_store.submit_template(payload)
    except template_store.TemplateInvalidError as exc:
        abort(400, description=str(exc))
    except template_store.CreatorInvalidError as exc:
        abort(400, description=str(exc))
    return jsonify({
        "ok": True,
        "submission_id": submission["submission_id"],
        "status": submission["status"],
    })


@bp.route("/api/templates/asset", methods=["POST"])
@require_turnstile
@rate_limit(IMAGE_RATE_LIMIT)
def upload_template_asset_api() -> Response:
    slug = (request.form.get("slug") or "").strip().lower()
    uploaded_file = request.files.get("asset")
    if uploaded_file is None or uploaded_file.filename == "":
        abort(400, description="Missing asset file")
    data = uploaded_file.read()
    if not data:
        abort(400, description="Empty asset file")
    if len(data) > TEMPLATE_ASSET_MAX_BYTES:
        abort(413, description="Asset exceeds the size limit")
    content_type = (uploaded_file.mimetype or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_ARTWORK_TYPES:
        abort(400, description="Asset must be a PNG, JPEG, WebP, or GIF image")
    try:
        result = template_store.store_template_asset(slug, uploaded_file.filename, data)
    except template_store.TemplateInvalidError as exc:
        abort(400, description=str(exc))
    return jsonify({"ok": True, "url": result["filename"]})


@bp.route("/template-assets/<path:rel_path>", methods=["GET"])
def fetch_template_asset(rel_path: str) -> Response:
    absolute_path = template_store.resolve_template_asset_path(f"/template-assets/{rel_path}")
    if not absolute_path or not os.path.isfile(absolute_path):
        abort(404, description="Asset not found.")
    content_type = "image/png"
    if rel_path.endswith(".jpg"):
        content_type = "image/jpeg"
    elif rel_path.endswith(".webp"):
        content_type = "image/webp"
    try:
        with open(absolute_path, "rb") as handle:
            data = handle.read()
    except OSError:
        abort(404, description="Asset not found.")
    response = send_file(
        io.BytesIO(data),
        mimetype=content_type,
        as_attachment=False,
        download_name=os.path.basename(rel_path),
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _require_reviewer() -> None:
    if not TEMPLATE_REVIEW_KEY:
        abort(404, description="Template review is disabled.")
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.startswith("Bearer ") else ""
    if not token or token != TEMPLATE_REVIEW_KEY:
        abort(401, description="Review key is required.")


@bp.route("/api/templates/review", methods=["POST"])
@rate_limit(STATS_RATE_LIMIT)
def review_templates_api() -> Response:
    _require_reviewer()
    payload = request.get_json(silent=True) or {}
    action = (payload.get("action") or "list").strip().lower()
    if action == "list":
        return jsonify({"pending": template_store.get_pending_submissions()})
    submission_id = payload.get("submission_id") or ""
    if action == "approve":
        try:
            template_store.approve_submission(submission_id)
        except template_store.TemplateUnavailableError as exc:
            abort(404, description=str(exc))
        except template_store.TemplateInvalidError as exc:
            abort(400, description=str(exc))
        return jsonify({"ok": True, "action": "approved"})
    if action == "reject":
        try:
            template_store.reject_submission(submission_id)
        except template_store.TemplateUnavailableError as exc:
            abort(404, description=str(exc))
        return jsonify({"ok": True, "action": "rejected"})
    abort(400, description="Unknown review action.")


@bp.route("/lastfm-wrapped")
def lastfm_landing() -> Response:
    return current_app.send_static_file("lastfm-wrapped.html")


@bp.route("/navidrome-wrapped")
def navidrome_landing() -> Response:
    return current_app.send_static_file("navidrome-wrapped.html")


def _client_config_payload() -> dict:
    return {
        "turnstileEnabled": bool(TURNSTILE_ENABLED),
        "turnstileSiteKey": TURNSTILE_SITE_KEY or "",
    }


@bp.route("/api/client-config", methods=["GET"])
def client_config_api() -> Response:
    payload = _client_config_payload()
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/client-config.js", methods=["GET"])
def client_config_module() -> Response:
    payload = _client_config_payload()
    content = "\n".join(
        [
            "// Runtime config",
            f"export const TURNSTILE_ENABLED = {json.dumps(payload['turnstileEnabled'])};",
            f"export const TURNSTILE_SITE_KEY = {json.dumps(payload['turnstileSiteKey'])};",
        ]
    )
    response = current_app.response_class(f"{content}\n", mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/api/period-options", methods=["GET"])
def period_options_api() -> Response:
    payload = describe_for_client()
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/badge/<username>")
@rate_limit(STATS_RATE_LIMIT)
def get_badge(username: str) -> Response:
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    badge_type = normalise_badge_type(request.args.get("type"))
    color = normalise_badge_color(request.args.get("color"))
    svg = build_badge(service, username, badge_type, color, range_obj)
    response = current_app.response_class(svg, mimetype="image/svg+xml")
    response.headers["Cache-Control"] = "public, max-age=3600"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = BADGE_SANDBOX_POLICY
    return response


@bp.route("/api/badge/publish", methods=["POST"])
@rate_limit(IMAGE_RATE_LIMIT)
def publish_badge_snapshot() -> Response:
    payload = request.get_json(silent=True) or {}
    try:
        badge_id = store_snapshot(payload.get("secret"), payload.get("values"))
    except SnapshotInvalidError as exc:
        abort(400, description=str(exc))
    except BadgeStoreFullError:
        abort(503, description="Badge storage is full, try again later.")
    return jsonify({"badge_id": badge_id, "expires_in": BADGE_SNAPSHOT_TTL_SECONDS})


@bp.route("/badge/nv/<badge_id>")
@rate_limit(STATS_RATE_LIMIT)
def get_navidrome_badge(badge_id: str) -> Response:
    badge_type = normalise_badge_type(request.args.get("type"))
    color = normalise_badge_color(request.args.get("color"))
    snapshot = fetch_snapshot(badge_id)
    if snapshot is None:
        svg = render_badge_svg(badge_label(badge_type), "expired", "9f9f9f")
        max_age = 300
    else:
        value = snapshot.get(badge_type) or "unavailable"
        svg = render_badge_svg(badge_label(badge_type), value, color)
        max_age = 3600
    response = current_app.response_class(svg, mimetype="image/svg+xml")
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = BADGE_SANDBOX_POLICY
    return response


@bp.route("/metrics/wrapped", methods=["GET"])
def get_wrapped_metric() -> Response:
    return jsonify({"count": read_wrapped_count(), "since": WRAPPED_COUNT_SINCE})


@bp.route("/metrics/wrapped", methods=["POST"])
@rate_limit(STATS_RATE_LIMIT)
def increment_wrapped_metric() -> Response:
    count = increment_wrapped_count()
    return jsonify({"count": count, "since": WRAPPED_COUNT_SINCE})


@bp.route("/artwork/upload", methods=["POST"])
@require_turnstile
@rate_limit(IMAGE_RATE_LIMIT)
def upload_custom_artwork() -> Response:
    uploaded_file = request.files.get("artwork")
    if uploaded_file is None or uploaded_file.filename == "":
        abort(400, description="Missing artwork file")
    data = uploaded_file.read()
    if not data:
        abort(400, description="Empty artwork file")
    if len(data) > TEMP_ARTWORK_MAX_BYTES:
        abort(413, description="Artwork exceeds size limit")
    content_type = (uploaded_file.mimetype or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_ARTWORK_TYPES:
        abort(400, description="Artwork must be a PNG, JPEG, WebP, or GIF image")
    token = store_artwork(data, content_type)
    return jsonify({"token": token, "expires_in": TEMP_ARTWORK_TTL_SECONDS})


@bp.route("/artwork/<token>", methods=["GET"])
def fetch_custom_artwork(token: str) -> Response:
    try:
        data, content_type = fetch_artwork(token)
    except ArtworkMissingError:
        abort(404, description="Artwork expired")
    except ArtworkExpiredError:
        abort(410, description="Artwork expired")
    if content_type not in ALLOWED_ARTWORK_TYPES:
        content_type = "application/octet-stream"
    response = send_file(
        io.BytesIO(data),
        mimetype=content_type,
        as_attachment=False,
        download_name=f"artwork-{token}.img",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/top/albums/<username>/<int:number>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_albums(username: str, number: int) -> str:
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        names, _ = _safe_lastfm_albums(username, number, range_obj, service=service)
    else:
        releases, _ = _safe_lb_releases(username, number, range_obj)
        names = [release.get("release_name", "Unknown Release") for release in releases]
    response = current_app.response_class(format_ranked_lines(names), mimetype="text/plain")
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/artists/<username>/<int:number>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_artists(username: str, number: int):
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        names, _ = _safe_lastfm_artists(username, number, range_obj, service=service)
    else:
        artists, _ = _safe_lb_artists(username, number, range_obj)
        names = [artist.get("artist_name", "Unknown artist") for artist in artists]
    response = jsonify({"artists": names, "period": _range_metadata(range_obj)})
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/artists/<username>/<int:number>/formatted")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_artists_formatted(username: str, number: int) -> str:
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        names, _ = _safe_lastfm_artists(username, number, range_obj, service=service)
    else:
        artists, _ = _safe_lb_artists(username, number, range_obj)
        names = [artist.get("artist_name", "Unknown artist") for artist in artists]
    response = current_app.response_class(format_ranked_lines(names), mimetype="text/plain")
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/tracks/<username>/<int:number>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_tracks(username: str, number: int):
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        names, _ = _safe_lastfm_tracks(username, number, range_obj, service=service)
    else:
        tracks, _ = _safe_lb_tracks(username, number, range_obj)
        names = [track.get("track_name", "Unknown track") for track in tracks]
    response = jsonify({"tracks": names, "period": _range_metadata(range_obj)})
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/tracks/<username>/<int:number>/formatted")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_tracks_formatted(username: str, number: int) -> str:
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        names, _ = _safe_lastfm_tracks(username, number, range_obj, service=service)
    else:
        tracks, _ = _safe_lb_tracks(username, number, range_obj)
        names = [track.get("track_name", "Unknown track") for track in tracks]
    response = current_app.response_class(format_ranked_lines(names), mimetype="text/plain")
    _set_period_header(response, range_obj)
    return response


@bp.route("/time/total/<username>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_listen_time(username: str) -> str:
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        minutes, _ = _safe_lastfm_minutes(username, range_obj, service=service)
    else:
        minutes, _ = _safe_lb_minutes(username, range_obj)
    response = current_app.response_class(minutes, mimetype="text/plain")
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/genre/user/<username>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_genre_user(username: str) -> str:
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if _is_lastfm_family(service):
        genre, _ = _safe_lastfm_genre(username, range_obj, service=service)
    else:
        genre, _ = _safe_lb_genre(username, range_obj)
    response = current_app.response_class(genre, mimetype="text/plain")
    _set_period_header(response, range_obj)
    return response


@bp.route("/top/genre/artist/<artist_name>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_genre_artist(artist_name: str) -> str:
    service = _resolve_stats_service()
    if _is_lastfm_family(service):
        genre = get_lastfm_artist_genre(artist_name, service=service)
    else:
        genre = get_genre_for_artist(artist_name)
    return current_app.response_class(genre, mimetype="text/plain")


@bp.route("/top/img/<username>")
@require_turnstile
@rate_limit(IMAGE_RATE_LIMIT)
def get_top_artist_img(username: str) -> Response:
    service = _resolve_stats_service()
    source = request.args.get("source", "artist").strip().lower() or "artist"
    if source not in {"artist", "release"}:
        source = "artist"
    range_obj = _resolve_date_range()
    try:
        image_result = fetch_top_artist_image(username, preferred_source=source, service=service, range_obj=range_obj)
        content_type = (image_result.content_type or "").split(";")[0].strip().lower()
        if content_type not in ALLOWED_ARTWORK_TYPES:
            raise ImageUnavailableError
    except ImageQueueFullError:
        abort(429, description="Image queue is full, try again in a moment.")
    except ImageQueueBusyError:
        abort(429, description="Image queue is busy, please retry shortly.")
    except ImageUnavailableError:
        fallback_path = current_app.static_folder + "/img/black.png"
        try:
            with open(fallback_path, "rb") as f:
                fallback_data = f.read()
        except Exception:
            abort(404, description="Artist image unavailable")
        response = Response(fallback_data, content_type="image/png")
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["X-Image-Fallback"] = "true"
        _set_period_header(response, range_obj)
        return response

    response = Response(image_result.content, content_type=content_type or "image/jpeg")
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Image-Queue-Position"] = str(image_result.queue_position)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Security-Policy"] = BADGE_SANDBOX_POLICY
    _set_period_header(response, range_obj)
    return response
