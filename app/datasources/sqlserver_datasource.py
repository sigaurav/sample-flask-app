"""
SQL Server data source — pyodbc / SQLAlchemy for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``sqlalchemy pyodbc`` and configure the connection keys.

Connection config keys:
    sqlserver_host     : SQL Server hostname / IP
    sqlserver_port     : TCP port (default 1433)
    sqlserver_db       : Database name (e.g., 'FRY14Q')
    sqlserver_user     : Service account username
    sqlserver_password : Service account password
    sqlserver_schema   : Schema name (default 'dbo')
    sqlserver_driver   : ODBC driver string (default 'ODBC Driver 18 for SQL Server')

Table mapping (fully qualified):
    facilities   → {db}.{schema}.h1_facilities
    obligors     → {db}.{schema}.h1_obligors
    transactions → {db}.{schema}.h1_transactions
    comments     → {db}.{schema}.h1_comments

Phase 2 implementation notes:
    pip install sqlalchemy pyodbc
    from sqlalchemy import create_engine, text
    import pandas as pd
    conn_str = (
        f"mssql+pyodbc://{user}:{password}@{host}:{port}/{db}"
        f"?driver={driver.replace(' ', '+')}"
    )
    engine = create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
    with engine.connect() as conn:
        df = pd.read_sql(text(query), conn)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.datasources.base_datasource import BaseDataSource


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


class SQLServerDataSource(BaseDataSource):
    """
    SQL Server data source for FR Y-14Q regulatory reporting.

    Not available in Phase 1.  Configure in ProductionConfig and set
    ``source_type='sqlserver'`` in export job requests to activate.
    """

    source_type = "sqlserver"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host     = config.get("sqlserver_host", "")
        self._port     = int(config.get("sqlserver_port", 1433))
        self._db       = config.get("sqlserver_db", "")
        self._user     = config.get("sqlserver_user", "")
        self._password = config.get("sqlserver_password", "")
        self._schema   = config.get("sqlserver_schema", "dbo")
        self._driver   = config.get("sqlserver_driver", "ODBC Driver 18 for SQL Server")

    def _get_engine(self):
        """
        Return a SQLAlchemy engine for SQL Server.

        Phase 2 implementation:
            from sqlalchemy import create_engine
            conn_str = (
                f"mssql+pyodbc://{self._user}:{self._password}"
                f"@{self._host}:{self._port}/{self._db}"
                f"?driver={self._driver.replace(' ', '+')}"
            )
            return create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
        """
        raise NotImplementedError(
            "SQL Server source not configured. "
            "Set sqlserver_host/user/password/db in config and install sqlalchemy+pyodbc."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "SQLServerDataSource is not available in Phase 1. "
            "Use source_type='csv' or 'excel' for export jobs."
        )

    def health_check(self) -> bool:
        return False
