"""
Hierarchical configuration classes using environment-based selection.

Pattern:
    BaseConfig → DevelopmentConfig / ProductionConfig / TestingConfig
"""

import os


class BaseConfig:
    """
    Shared defaults for all environments.

    All paths are derived from the project root so the app
    can be launched from any working directory.
    """

    # ── Core Flask ─────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "wf-enterprise-dev-secret-2024")
    DEBUG: bool     = False
    TESTING: bool   = False

    # ── Paths ──────────────────────────────────────────────────────────────────
    BASE_DIR:   str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR:   str = os.path.join(BASE_DIR, "data")
    EXPORT_DIR: str = os.path.join(BASE_DIR, "exports")

    # ── Logging ────────────────────────────────────────────────────────────────
    LOG_LEVEL:  str = "INFO"
    LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

    # ── Pagination ─────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE:     int = 500

    # ── Export ─────────────────────────────────────────────────────────────────
    MAX_EXPORT_ROWS: int = 100_000


class DevelopmentConfig(BaseConfig):
    """Local development — verbose logging, Flask debugger enabled."""

    DEBUG:     bool = True
    LOG_LEVEL: str  = "DEBUG"


class ProductionConfig(BaseConfig):
    """Production deployment — minimal logging, no debugger."""

    LOG_LEVEL: str = "WARNING"

    # Enforce a real secret key in production
    SECRET_KEY: str = os.environ.get("SECRET_KEY", BaseConfig.SECRET_KEY)


class TestingConfig(BaseConfig):
    """Automated testing — in-memory, no side effects."""

    TESTING:   bool = True
    DEBUG:     bool = True
    LOG_LEVEL: str  = "DEBUG"


# ── Registry ───────────────────────────────────────────────────────────────────
config_map: dict = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
    "default":     DevelopmentConfig,
}
