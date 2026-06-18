"""
SQL Server adapter — SQLAlchemy + pyodbc for FR Y-14Q data.

Requires:  pip install sqlalchemy pyodbc

Connection config keys (Flask uppercase):
    SQLSERVER_HOST   : SQL Server hostname / IP
    SQLSERVER_PORT   : TCP port (default 1433)
    SQLSERVER_DB     : Database name
    SQLSERVER_SCHEMA : Schema name (default 'dbo')
    SQLSERVER_DRIVER : ODBC driver string

Authentication uses SSO Windows Authentication (Trusted_Connection=yes).
No username or password is required or stored.

Add one entry to _QUERY_MAP per entity.  Each query must accept two named
parameters: :sor and :fic_mis_date.  Everything else — joins, CTEs,
column aliases — goes directly in the SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


class SQLServerAdapter(BaseAdapter):

    source_type = "sqlserver"

    # One entry per entity.  Parameter: :fic_mis_date
    _QUERY_MAP: Dict[str, str] = {
        # "facilities": """
        #     SELECT *
        #     FROM   [dbo].[H1_FACILITIES]
        #     WHERE  [PERIOD_DT] = :fic_mis_date
        # """,
    }

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("SQLSERVER_HOST", "")
        self._port   = int(config.get("SQLSERVER_PORT", 1433))
        self._db     = config.get("SQLSERVER_DB", "")
        self._schema = config.get("SQLSERVER_SCHEMA", "dbo")
        self._driver = config.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
        self._engine = None

    def _get_engine(self):
        if self._engine is not None:
            return self._engine
        try:
            from sqlalchemy import create_engine
        except ImportError:
            raise RuntimeError(
                "sqlalchemy and pyodbc are required for SQL Server: "
                "pip install sqlalchemy pyodbc"
            )
        conn_str = (
            f"mssql+pyodbc://@{self._host}:{self._port}/{self._db}"
            f"?driver={self._driver.replace(' ', '+')}"
            f"&Trusted_Connection=yes"
        )
        self._engine = create_engine(conn_str, fast_executemany=True, pool_pre_ping=True)
        return self._engine

    def _get_query(self, entity_type: str) -> str:
        sql = self._QUERY_MAP.get(entity_type)
        if not sql:
            raise KeyError(
                f"No query defined for '{entity_type}' in SQLServerAdapter._QUERY_MAP"
            )
        return sql

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        from sqlalchemy import text

        filters      = dict(filters or {})
        fic_mis_date = filters.pop("_fic_mis_date", "")
        filters.pop("_sor", None)

        sql    = self._get_query(entity_type)
        params = {"fic_mis_date": fic_mis_date}
        self.log.debug("SQLServerAdapter SQL: %s  params=%s", sql, params)

        engine = self._get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)

        if entity_key:
            for field, val in entity_key.items():
                if field in df.columns:
                    df = df[df[field] == str(val)].reset_index(drop=True)

        col_filters = filters.get("col_filters", {})
        if col_filters:
            df = self._apply_col_filters(df, col_filters)
        quick = filters.get("quick_filter", "")
        if quick:
            df = self._apply_quick_filter(df, quick)

        df = self._apply_sorts(df, sorts or [])
        self.log.debug(
            "SQLServerAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        from sqlalchemy import text

        sql    = self._get_query(entity_type)
        params = {"fic_mis_date": ""}

        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text(f"SELECT TOP 0 * FROM ({sql}) AS _q"),
                params,
            )
            return list(result.keys())

    def health_check(self) -> bool:
        try:
            from sqlalchemy import text
            with self._get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
