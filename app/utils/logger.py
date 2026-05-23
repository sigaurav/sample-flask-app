"""
Centralized logging configuration.

Called once during app factory setup; thereafter standard
logging.getLogger(__name__) calls work throughout the codebase.

Features
--------
RequestContextFilter
    Injects ``request_id`` and ``user_id`` into every LogRecord.
    Values are pulled from Flask's ``g`` proxy when inside a request
    context; both fall back to ``"-"`` for startup and background tasks.

StreamHandler
    Always-on console output to stdout.

RotatingFileHandler
    Optional; activated when *log_file* is a non-empty path.
    Rotates at *max_bytes* and keeps *backup_count* archived copies.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

try:
    from flask import g, has_request_context
    _FLASK = True
except ImportError:           # non-Flask usage or import before app is created
    _FLASK = False


class RequestContextFilter(logging.Filter):
    """
    Stamp ``request_id`` and ``user_id`` onto every LogRecord.

    When emitted outside a Flask request context (e.g. app startup,
    background threads) both fields are set to ``"-"`` so format strings
    that reference them never raise KeyError.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if _FLASK and has_request_context():
            record.request_id = getattr(g, "request_id", "-")
            record.user_id    = getattr(g, "user_id",    "-")
        else:
            record.request_id = "-"
            record.user_id    = "-"
        return True


def configure_logging(
    level:        str = "INFO",
    fmt:          str = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "req=%(request_id)s user=%(user_id)s | %(message)s"
    ),
    log_file:     str = "",
    max_bytes:    int = 10 * 1024 * 1024,   # 10 MB per file
    backup_count: int = 5,
) -> None:
    """
    Configure the root logger.

    A StreamHandler (stdout) is always added.  A RotatingFileHandler is
    added only when *log_file* is a non-empty path.  Both handlers share
    the same formatter and RequestContextFilter instance.

    Args:
        level:        Logging level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        fmt:          Format string.  Should include ``%(request_id)s`` and
                      ``%(user_id)s`` to surface the enriched fields.
        log_file:     Absolute or relative path for the rotating log file.
                      Leave empty (default) for console-only output.
        max_bytes:    Bytes at which the log file is rotated.  Default 10 MB.
        backup_count: Number of rotated files to keep.  Default 5.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    formatter     = logging.Formatter(fmt)
    ctx_filter    = RequestContextFilter()

    # ── Console handler ────────────────────────────────────────────────────────
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(numeric_level)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(ctx_filter)

    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.handlers.clear()
    root.addHandler(stream_handler)

    # ── Rotating file handler (opt-in) ─────────────────────────────────────────
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ctx_filter)
        root.addHandler(file_handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
