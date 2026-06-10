"""
SQL Server adapter — pyodbc / SQLAlchemy for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``sqlalchemy pyodbc`` and configure the connection keys.

Connection config keys (Flask uppercase):
    SQLSERVER_HOST   : SQL Server hostname / IP
    SQLSERVER_PORT   : TCP port (default 1433)
    SQLSERVER_DB     : Database name (e.g., 'FRY14Q')
    SQLSERVER_SCHEMA : Schema name (default 'dbo')
    SQLSERVER_DRIVER : ODBC driver string

Authentication uses SSO Windows Authentication (Trusted_Connection=yes).
No username/password required or stored.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


_TABLE_MAP: Dict[str, str] = {
    "facilities":   "h1_facilities",
    "obligors":     "h1_obligors",
    "transactions": "h1_transactions",
    "comments":     "h1_comments",
}

_PARENT_FK: Dict[str, str] = {
    "obligors":     "facility_id",
    "transactions": "obligor_id",
    "comments":     "transaction_id",
}


class SQLServerAdapter(BaseAdapter):
    """
    SQL Server adapter for FR Y-14Q regulatory reporting.

    Not available in Phase 1.  Configure SQLSERVER_HOST/SQLSERVER_DB in
    ProductionConfig and add 'sqlserver' to ENTITY_SOURCES to activate.
    Uses Windows SSO (Trusted_Connection=yes) — no credentials needed.
    """

    source_type = "sqlserver"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("SQLSERVER_HOST", "")
        self._port   = int(config.get("SQLSERVER_PORT", 1433))
        self._db     = config.get("SQLSERVER_DB", "")
        self._schema = config.get("SQLSERVER_SCHEMA", "dbo")
        self._driver = config.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")

    def _get_engine(self):
        """
        Return a SQLAlchemy engine for SQL Server using SSO Windows Authentication.

        Phase 2 implementation:
            from sqlalchemy import create_engine
            conn_str = (
                f"mssql+pyodbc://@{self._host}:{self._port}/{self._db}"
                f"?driver={self._driver.replace(' ', '+')}"
                f"&Trusted_Connection=yes"
            )
            return create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
        """
        raise NotImplementedError(
            "SQL Server adapter not configured. "
            "Set SQLSERVER_HOST/SQLSERVER_DB in config and install sqlalchemy+pyodbc."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("SQLServerAdapter is not available in Phase 1.")

    def introspect_columns(self, entity_type: str) -> List[str]:  # noqa: ARG002
        raise NotImplementedError("SQLServerAdapter.introspect_columns not available in Phase 1.")

    def health_check(self) -> bool:
        return False
