"""
Hierarchical configuration classes using environment-based selection.

Pattern:
    BaseConfig → DevelopmentConfig / ProductionConfig / TestingConfig
"""

import os
from app.schemas import get_all_fields, get_pk


class BaseConfig:
    """
    Shared defaults for all environments.

    All paths are derived from the project root so the app
    can be launched from any working directory.
    """

    #  Core Flask ─
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "wf-enterprise-dev-secret-2024")
    DEBUG: bool     = False
    TESTING: bool   = False

    #  Paths 
    BASE_DIR:   str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR:   str = os.path.join(BASE_DIR, "data")
    EXPORT_DIR: str = os.path.join(BASE_DIR, "exports")
    LOG_DIR:    str = os.path.join(BASE_DIR, "logs")

    #  Logging 
    LOG_LEVEL:         str = "INFO"
    LOG_FORMAT:        str = (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "req=%(request_id)s user=%(user_id)s | %(message)s"
    )
    LOG_FILE:          str = ""
    LOG_MAX_BYTES:     int = 10 * 1024 * 1024   # 10 MB
    LOG_BACKUP_COUNT:  int = 5

    #  Pagination ─
    DEFAULT_PAGE_SIZE: int = 50
    MAX_PAGE_SIZE:     int = 100_000

    #  Async export worker 
    EXPORT_WORKER_THREADS: int = 4   # ThreadPoolExecutor max_workers

    #  Active data sources 
    # Allowlist of source types that are permitted to establish connections.
    # ENTITIES declares which source each entity *wants*; if that source is not
    # in this list no adapter is initialised and the entity falls back to CSV.
    # Valid values: "csv", "dremio", "sqlserver", "teradata"
    ENABLED_DATA_SOURCES: list = ["csv", "dremio", "sqlserver"]

    #  Entity graph ─
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
    #   fk_child    : FK column(s) on the *child* table — REQUIRED even when
    #                 names are identical to "fk"; makes the join explicit
    #   count_col   : computed count column added to this entity's rows
    #
    # To add a new entity: add one block here, create its data file and schema
    # JSON, and add a sidebar link.  No other code changes needed.
    ENTITIES: dict = {
        "facilities": {
            "source":        "csv",
            "label":         "Credit Facilities",
            "pk":            get_pk('facilities'),
            "label_field":   "OBLIGOR_NAME",
            "active_filter": {"field": "ACTIVE_FLAG", "value": "Y"},
            "columns":       get_all_fields('facilities'),
            "enable_row_action": True,
            "children": {
                "obligations": {
                    "fk":        ["LOANNUMBER"],
                    "fk_child":  ["LOAN_NUMBER"],
                    "count_col": "OBLIGATION_COUNT",
                },
                "property": {
                    "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "fk_child":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "count_col": "PROPERTY_COUNT",
                },
                "investigation_tracker": {
                    "fk": [
                        "PERIOD_DT", "FACLTY_SOR_ID", "FACLTY_BNK_NBR_ID",
                        "FACLTY_ID", "FACLTY_OBLGR_ID", "FACLTY_AU_CD",
                    ],
                    "fk_child":            ["entity_key"],
                    "concat_separator":    "|",
                    "child_static_filter": {"field": "entity_type", "value": "facilities"},
                    "count_col":           "INVESTIGATION_COUNT",
                },
            },
        },
        "obligations": {
            "source":      "csv",
            "label":       "Obligations",
            "pk":          get_pk('obligations'),
            "label_field": "OBLGN_ID",
            "columns":     get_all_fields('obligations'),
            "enable_row_action": False,
            "children": {
                "property": {
                    "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "fk_child":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                    "count_col": "PROPERTY_COUNT",
                },
                "errors": {
                    "fk": [
                        "FACLTY_BNK_NBR_ID", "OBLGN_ID", "OBLGN_OBLGR_ID",
                        "FACLTY_ID", "FACLTY_OBLGR_ID", "FACLTY_SOR_ID",
                        "OBLGN_BNK_NBR_ID", "OBLGN_SOR_ID",
                        "OBLGR_BNK_NBR_ID", "OBLGR_ID", "OBLGR_SOR_ID",
                        "OBLGN_AU_CD",
                    ],
                    "fk_child":          ["RECORD_ID"],
                    "concat_separator":  "|",
                    "count_col":         "ERROR_COUNT",
                },
            },
        },
        "property": {
            "source":      "csv",
            "label":       "Property",
            "pk":          get_pk('property'),  # property has no single PK; use all columns
            "label_field": "PRPRTY_ID",
            "columns":     get_all_fields('property'),
            "enable_row_action": False,
            "children":    {},
        },
        "errors": {
            "source":      "csv",
            "label":       "Data Load Errors",
            "pk":          ["ID"],
            "label_field": "ID",
            "columns":     get_all_fields('errors'),
            "enable_row_action": False,
            "children":    {},
        },
        "investigation_assignees":{
            "source":      "csv",
            "label":       "Investigation Assignees",
            "pk":          get_pk('investigation_assignees'),
            "label_field": "ID",
            "columns":     get_all_fields('investigation_assignees'),
            "enable_row_action": False,
            "children":    {},
        },
        "investigation_tracker":{
            "source":      "csv",
            "label":       "Investigation Tracker",
            "pk":          get_pk('investigation_tracker'),
            "label_field": "ID",
            "columns":     get_all_fields('investigation_tracker'),
            "enable_row_action": False,
            "children":    {},
        }
    }

    #    data sources 
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

    #  Jira integration ─
    JIRA_BASE_URL: str = os.environ.get("JIRA_BASE_URL", "")
    JIRA_TOKEN:    str = os.environ.get("JIRA_TOKEN", "")
    PAGE_SIZE:     int = 100


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


#  Registry ─
config_map: dict = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
    "default":     DevelopmentConfig,
}
