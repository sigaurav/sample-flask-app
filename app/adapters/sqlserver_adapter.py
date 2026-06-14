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
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


_TABLE_MAP: Dict[str, str] = {
    "facilities":  "h1_facilities",
    "obligations": "h1_obligations",
    "property":    "h1_property",
}


class SQLServerAdapter(BaseAdapter):
    """SQL Server adapter using SSO Windows Authentication."""

    source_type = "sqlserver"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("SQLSERVER_HOST", "")
        self._port   = int(config.get("SQLSERVER_PORT", 1433))
        self._db     = config.get("SQLSERVER_DB", "")
        self._schema = config.get("SQLSERVER_SCHEMA", "dbo")
        self._driver = config.get("SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server")
        self._engine = None   # lazy — created on first use

    # ── Connection ────────────────────────────────────────────────────────────

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
        self._engine = create_engine(
            conn_str, fast_executemany=True, pool_pre_ping=True
        )
        return self._engine

    # ── SQL builder ───────────────────────────────────────────────────────────

    def _build_query(
        self,
        entity_type:  str,
        entity_key:   Optional[Dict[str, str]],
        sor:          str,
        fic_mis_date: str,
    ) -> Tuple[str, Dict]:
        """Return (sql_string, params_dict) using SQLAlchemy named parameters."""
        cols   = self._get_select_cols(entity_type)
        select = "*" if cols == ["*"] else ", ".join(f"[{c}]" for c in cols)
        table  = _TABLE_MAP[entity_type]
        conditions = []
        params: Dict[str, Any] = {}

        if sor:
            conditions.append("[FACLTY_SOR_ID] = :sor")
            params["sor"] = sor
        if fic_mis_date:
            conditions.append("[PERIOD_DT] = :fic_mis_date")
            params["fic_mis_date"] = fic_mis_date
        if entity_key:
            for i, (field, val) in enumerate(entity_key.items()):
                p = f"ek_{i}"
                conditions.append(f"[{field}] = :{p}")
                params[p] = val

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql   = f"SELECT {select} FROM [{self._schema}].[{table}]{where}"
        return sql, params

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        from sqlalchemy import text

        filters      = dict(filters or {})
        sor          = filters.pop("_sor", "")
        fic_mis_date = filters.pop("_fic_mis_date", "")

        sql, params = self._build_query(entity_type, entity_key, sor, fic_mis_date)
        self.log.debug("SQLServerAdapter SQL: %s  params=%s", sql, params)

        engine = self._get_engine()
        with engine.connect() as conn:
            df = pd.read_sql(text(sql), conn, params=params)

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
        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            return cols

        from sqlalchemy import text

        table = _TABLE_MAP.get(entity_type)
        if not table:
            raise ValueError(f"Unknown entity_type '{entity_type}'")

        sql = text("""
            SELECT COLUMN_NAME
            FROM   INFORMATION_SCHEMA.COLUMNS
            WHERE  TABLE_SCHEMA = :schema
            AND    TABLE_NAME   = :table
            ORDER  BY ORDINAL_POSITION
        """)
        engine = self._get_engine()
        with engine.connect() as conn:
            result = conn.execute(sql, {"schema": self._schema, "table": table})
            return [row[0] for row in result]

    def health_check(self) -> bool:
        try:
            from sqlalchemy import text
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
