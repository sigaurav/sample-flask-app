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
    LOG_DIR:    str = os.path.join(BASE_DIR, "logs")

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
    MAX_PAGE_SIZE:     int = 100_000

    # ── Async export worker ────────────────────────────────────────────────────
    EXPORT_WORKER_THREADS: int = 4   # ThreadPoolExecutor max_workers

    # ── Active data sources ────────────────────────────────────────────────────
    # Allowlist of source types that are permitted to establish connections.
    # ENTITIES declares which source each entity *wants*; if that source is not
    # in this list no adapter is initialised and the entity falls back to CSV.
    # Valid values: "csv", "dremio", "sqlserver", "teradata"
    ENABLED_DATA_SOURCES: list = ["csv", "dremio", "sqlserver"]

    # ── Query context ──────────────────────────────────────────────────────────
    # SOR column in source tables: FACLTY_SOR_ID
    # Date column in source tables: PERIOD_DT  (lowercase period_dt in obligations)
    # Add new SOR values here; the frontend dropdown auto-populates from this list.
    ENABLED_SORS: list = ["1SOR", "2SOR", "3SOR"]

    # ── Entity graph ───────────────────────────────────────────────────────────
    # Single source of truth for all entity configuration.
    #
    # source        : adapter that owns this entity's data
    #                 ("csv", "dremio", "sqlserver", "teradata")
    #                 DB adapters resolve the SQL from their _QUERY_MAP; CSV
    #                 reads <entity_type>.csv from DATA_DIR.
    # pk            : primary-key column(s) for this entity
    # label_field   : column used as the human-readable label in breadcrumbs
    # active_filter : optional {"field": col, "value": val} for the KPI strip
    # columns       : column selection for the adapter fallback (ignored when
    #                 "query" is set); ["*"] fetches all
    # children      : dict of child-entity -> relationship config
    #   fk          : FK column(s) on the *parent* table — used as URL params
    #                 and for the parent-side groupby when computing counts
    #   child_fk    : FK column(s) on the *child* table — REQUIRED even when
    #                 names are identical to "fk"; makes the join explicit
    #   count_col   : computed count column added to this entity's rows
    #
    # To add a new entity: add one block here, create its data file and schema
    # JSON, and add a sidebar link.  No other code changes needed.
    ENTITIES: dict = {
        "facilities": {
            "source":        "csv",
            "label":         "Credit Facilities",
            "pk":            ["FACLTY_ID", "FACLTY_OBLGR_ID"],
            "label_field":   "OBLIGOR_NAME",
            "active_filter": {"field": "ACTIVE_FLAG", "value": "Y"},
            "columns":       ["*"],
            "children": {
                "obligations": {
                    "fk":        ["LOANNUMBER"],
                    "child_fk":  ["LOAN_NUMBER"],
                    "count_col": "OBLIGATION_COUNT",
                },
                "property": {
                    "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "child_fk":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "count_col": "PROPERTY_COUNT",
                },
            },
        },
        "obligations": {
            "source":      "csv",
            "label":       "Obligations",
            "pk":          ["OBLGN_ID"],
            "label_field": "OBLGN_ID",
            "columns":     ["*"],
            "children": {
                "property": {
                    "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "child_fk":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "count_col": "PROPERTY_COUNT",
                },
            },
        },
        "property": {
            "source":      "csv",
            "label":       "Property",
            "pk":          ["PRPRTY_ID"],
            "label_field": "PRPRTY_ID",
            "columns":     ["*"],
            "children":    {},
        },
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

    TERADATA_HOST:   str = ""
    TERADATA_PORT:   int = 1025
    TERADATA_DB:     str = ""
    TERADATA_SCHEMA: str = ""


class DevelopmentConfig(BaseConfig):
    """Local development — verbose logging, Flask debugger enabled."""

    DEBUG:     bool = True
    LOG_LEVEL: str  = "DEBUG"
    LOG_FILE:  str  = os.path.join(BaseConfig.LOG_DIR, "wf_analytics.log")


class ProductionConfig(BaseConfig):
    """Production deployment — minimal logging, no debugger."""

    LOG_LEVEL: str = "WARNING"
    LOG_FILE:  str = os.path.join(BaseConfig.LOG_DIR, "wf_analytics.log")

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
