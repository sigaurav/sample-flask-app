"""
Centralized logging configuration.

Called once during app factory setup; thereafter standard
logging.getLogger(__name__) calls work throughout the codebase.
"""

import logging
import sys


def configure_logging(level: str = "INFO", fmt: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s") -> None:
    """
    Configure the root logger with a stream handler pointing to stdout.

    Args:
        level: Logging level string ('DEBUG', 'INFO', 'WARNING', 'ERROR').
        fmt:   Log line format string.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any pre-existing handlers to avoid duplicate output
    root.handlers.clear()
    root.addHandler(handler)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)
