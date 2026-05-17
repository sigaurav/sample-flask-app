"""
Application entry point.

Usage:
    python run.py
    FLASK_ENV=production python run.py
"""

import os
import sys
import logging

# ── ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app


def main() -> None:
    """Bootstrap and run the Flask development server."""
    env = os.getenv("FLASK_ENV", "development")
    app = create_app(env)

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 5000))

    debug = app.config["DEBUG"]

    # Werkzeug reloader forks a parent process (file watcher) and a child process
    # (real server). WERKZEUG_RUN_MAIN=true is set only in the child, so guard the
    # startup log here to avoid printing it twice.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        display_host = "localhost" if host == "0.0.0.0" else host
        logging.getLogger(__name__).info(
            "Starting WF Enterprise Analytics on http://%s:%s [%s]", display_host, port, env
        )

    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
