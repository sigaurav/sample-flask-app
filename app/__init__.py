"""
Application factory for WF Enterprise Analytics.

Usage:
    from app import create_app
    app = create_app("development")
"""

import os
import uuid
import logging
from flask import Flask, g, request

from app.config import config_map
from app.utils.logger import configure_logging


def create_app(config_name: str = "default") -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_name: One of 'development', 'production', 'testing', 'default'.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ── Configuration ─────────────────────────────────────────────────────────
    cfg_class = config_map.get(config_name, config_map["default"])
    app.config.from_object(cfg_class)

    # ── Logging ───────────────────────────────────────────────────────────────
    configure_logging(
        level        = app.config["LOG_LEVEL"],
        fmt          = app.config["LOG_FORMAT"],
        log_file     = app.config.get("LOG_FILE", ""),
        max_bytes    = app.config.get("LOG_MAX_BYTES", 10 * 1024 * 1024),
        backup_count = app.config.get("LOG_BACKUP_COUNT", 5),
    )

    # ── Per-request context stamps ────────────────────────────────────────────
    @app.before_request
    def _stamp_request_context() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]
        g.user_id    = request.headers.get("X-User-Id", "anonymous")

    # ── Ensure export directory exists ─────────────────────────────────────────
    os.makedirs(app.config["EXPORT_DIR"], exist_ok=True)

    # ── Register Blueprints ───────────────────────────────────────────────────
    from app.controllers.main_controller         import main_bp
    from app.controllers.api_controller          import api_bp
    from app.controllers.export_controller       import export_bp
    from app.controllers.async_export_controller import async_export_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp,          url_prefix="/api")
    app.register_blueprint(export_bp,       url_prefix="/api/export")
    app.register_blueprint(async_export_bp, url_prefix="/api/exports")

    # ── Global error handlers ─────────────────────────────────────────────────
    _register_error_handlers(app)

    # Only log in the child server process; the parent (reloader) runs create_app
    # too but should not emit user-facing startup messages.
    if not app.config["DEBUG"] or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        logging.getLogger(__name__).info("Application created with config: %s", config_name)
    return app


def _register_error_handlers(app: Flask) -> None:
    """Attach JSON-friendly error handlers to the application."""
    from app.utils.response_utils import error_response

    @app.errorhandler(404)
    def not_found(exc):
        return error_response("Resource not found", 404)

    @app.errorhandler(400)
    def bad_request(exc):
        return error_response("Bad request", 400)

    @app.errorhandler(500)
    def internal_error(exc):
        app.logger.exception("Unhandled server error")
        return error_response("Internal server error", 500)
