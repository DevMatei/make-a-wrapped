"""Legacy entrypoint for running the Make a Wrapped Flask application."""

from __future__ import annotations

import os

from wrapped_fm import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
