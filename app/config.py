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
    LOG_LEVEL:         str = "INFO"
    LOG_FORMAT:        str = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "req=%(request_id)s user=%(user_id)s | %(message)s"
    )
    LOG_FILE:          str = ""
    LOG_MAX_BYTES:     int = 10 * 1024 * 1024   # 10 MB
    LOG_BACKUP_COUNT:  int = 5

    # ── Pagination ─────────────────────────────────────────────────────────────
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE:     int = 500

    # ── Async export worker ────────────────────────────────────────────────────
    EXPORT_WORKER_THREADS: int = 4   # ThreadPoolExecutor max_workers

    # ── Active data sources ────────────────────────────────────────────────────
    # First entry is the primary source used by ReportingService.
    # Valid values: "csv", "dremio", "sqlserver", "excel"
    ENABLED_DATA_SOURCES: list = ["csv", "dremio", "sqlserver", "excel"]

    # ── Query context ──────────────────────────────────────────────────────────
    # All rows must carry SOR and FIC_MIS_DATE columns in source tables.
    # Add new SOR values here; the frontend dropdown auto-populates from this list.
    ENABLED_SORS: list = ["1SOR", "2SOR", "3SOR"]

    # ── Per-entity source routing ──────────────────────────────────────────────
    # Maps each entity to its owning data source.  Must be a value in
    # ENABLED_DATA_SOURCES; falls back to the primary adapter otherwise.
    ENTITY_SOURCES: dict = {
        "facilities":   "csv",
        "obligors":     "csv",
        "transactions": "csv",
        "comments":     "csv",
    }

    # ── External data sources ──────────────────────────────────────────────────
    DREMIO_HOST:   str = ""
    DREMIO_PORT:   int = 32010
    DREMIO_SOURCE: str = "FR_Y14Q"

    SQLSERVER_HOST:   str = ""
    SQLSERVER_PORT:   int = 1433
    SQLSERVER_DB:     str = ""
    SQLSERVER_SCHEMA: str = "dbo"
    SQLSERVER_DRIVER: str = "ODBC Driver 18 for SQL Server"

    EXCEL_DATA_PATH: str = ""


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
