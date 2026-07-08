"""Flask routes blueprint."""

from __future__ import annotations

import io
import json
import logging

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    request,
    send_file,
)

from .config import (
    IMAGE_RATE_LIMIT,
    STATS_RATE_LIMIT,
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
SUPPORTED_STATS_SERVICES = {"listenbrainz", "lastfm"}


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


def _safe_lastfm_artists(username: str, number: int, range_obj):
    try:
        return get_lastfm_top_artists(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("Last.fm artists failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_tracks(username: str, number: int, range_obj):
    try:
        return get_lastfm_top_tracks(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("Last.fm tracks failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_albums(username: str, number: int, range_obj):
    try:
        return get_lastfm_top_albums(username, number, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("Last.fm albums failed for %s: %s", username, exc)
        return [], True


def _safe_lastfm_minutes(username: str, range_obj):
    try:
        return estimate_lastfm_listen_minutes(username, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("Last.fm minutes failed for %s: %s", username, exc)
        return "0", True


def _safe_lastfm_genre(username: str, range_obj):
    try:
        return get_lastfm_top_genre(username, range_obj=range_obj), False
    except Exception as exc:
        logger.warning("Last.fm genre failed for %s: %s", username, exc)
        return "No genre", True


def _all_time_fallback_range():
    return resolve_preset(PRESET_ALL_TIME)


@bp.route("/")
def root() -> Response:
    return current_app.send_static_file("index.html")


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


@bp.route("/metrics/wrapped", methods=["GET"])
def get_wrapped_metric() -> Response:
    return jsonify({"count": read_wrapped_count(), "since": WRAPPED_COUNT_SINCE})


@bp.route("/metrics/wrapped", methods=["POST"])
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
    content_type = uploaded_file.mimetype or "application/octet-stream"
    if "image" not in content_type.lower():
        abort(400, description="Artwork must be an image")
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
    response = send_file(
        io.BytesIO(data),
        mimetype=content_type,
        as_attachment=False,
        download_name=f"artwork-{token}.img",
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/top/albums/<username>/<int:number>")
@require_turnstile
@rate_limit(STATS_RATE_LIMIT)
def get_top_albums(username: str, number: int) -> str:
    number = clamp_top_number(number)
    service = _resolve_stats_service()
    range_obj = _resolve_date_range()
    if service == "lastfm":
        names, _ = _safe_lastfm_albums(username, number, range_obj)
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
    if service == "lastfm":
        names, _ = _safe_lastfm_artists(username, number, range_obj)
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
    if service == "lastfm":
        names, _ = _safe_lastfm_artists(username, number, range_obj)
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
    if service == "lastfm":
        names, _ = _safe_lastfm_tracks(username, number, range_obj)
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
    if service == "lastfm":
        names, _ = _safe_lastfm_tracks(username, number, range_obj)
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
    if service == "lastfm":
        minutes, _ = _safe_lastfm_minutes(username, range_obj)
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
    if service == "lastfm":
        genre, _ = _safe_lastfm_genre(username, range_obj)
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
    if service == "lastfm":
        genre = get_lastfm_artist_genre(artist_name)
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

    response = Response(image_result.content, content_type=image_result.content_type or "image/jpeg")
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["X-Image-Queue-Position"] = str(image_result.queue_position)
    _set_period_header(response, range_obj)
    return response
