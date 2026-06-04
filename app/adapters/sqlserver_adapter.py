"""
SQL Server adapter — pyodbc / SQLAlchemy for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``sqlalchemy pyodbc`` and configure the connection keys.

Connection config keys:
    sqlserver_host   : SQL Server hostname / IP
    sqlserver_port   : TCP port (default 1433)
    sqlserver_db     : Database name (e.g., 'FRY14Q')
    sqlserver_schema : Schema name (default 'dbo')
    sqlserver_driver : ODBC driver string

Credentials are retrieved via the injected ``CredentialProvider`` —
passwords are never stored in config or logged.
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

    Not available in Phase 1.  Configure in ProductionConfig and set
    ``source_type='sqlserver'`` in export job requests to activate.
    """

    source_type = "sqlserver"

    def __init__(self, config: Dict[str, Any], credential_provider=None) -> None:
        super().__init__(config)
        self._host               = config.get("sqlserver_host", "")
        self._port               = int(config.get("sqlserver_port", 1433))
        self._db                 = config.get("sqlserver_db", "")
        self._schema             = config.get("sqlserver_schema", "dbo")
        self._driver             = config.get("sqlserver_driver", "ODBC Driver 18 for SQL Server")
        self._credential_provider = credential_provider

    def _get_credentials(self):
        """Retrieve user/password from the credential provider (never from config)."""
        if self._credential_provider is None:
            raise RuntimeError("No credential provider configured for SQL Server.")
        user     = self._credential_provider.get_secret("sqlserver_user")
        password = self._credential_provider.get_secret("sqlserver_password")
        return user, password

    def _get_engine(self):
        """
        Return a SQLAlchemy engine for SQL Server.

        Phase 2 implementation:
            from sqlalchemy import create_engine
            user, password = self._get_credentials()
            conn_str = (
                f"mssql+pyodbc://{user}:{password}"
                f"@{self._host}:{self._port}/{self._db}"
                f"?driver={self._driver.replace(' ', '+')}"
            )
            return create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
        """
        raise NotImplementedError(
            "SQL Server adapter not configured. "
            "Set sqlserver_host/db in config, configure a CredentialProvider, "
            "and install sqlalchemy+pyodbc."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "SQLServerAdapter is not available in Phase 1. "
            "Use source_type='csv' or 'excel' for export jobs."
        )

    def health_check(self) -> bool:
        return False
