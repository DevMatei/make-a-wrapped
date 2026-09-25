"""Application factory."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from flask import Flask, request
from werkzeug.exceptions import HTTPException

from .config import TEMP_ARTWORK_MAX_BYTES
from .rate_limiter import apply_registered_limits, init_rate_limiter
from .api import api_http_error_response, bp as api_v1_bp
from .routes import bp as routes_bp

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"


def create_app() -> Flask:
    app = Flask(__name__, static_url_path="", static_folder=str(STATIC_DIR))
    app.config["MAX_CONTENT_LENGTH"] = TEMP_ARTWORK_MAX_BYTES + (1024 * 1024)
    app.register_blueprint(routes_bp)
    app.register_blueprint(api_v1_bp)
    init_rate_limiter(app)
    apply_registered_limits(app)

    @app.errorhandler(404)
    def page_not_found(e):
        if request.path.startswith("/api/v1/"):
            return api_http_error_response(e)
        return app.send_static_file('404.html'), 404

    @app.errorhandler(HTTPException)
    def handle_api_http_error(e):
        if request.path.startswith("/api/v1/"):
            return api_http_error_response(e)
        return e.get_response()

    return app
