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

Add one entry to _QUERY_MAP per entity.  Each query must accept one named
parameter: :fic_mis_date.  Everything else — joins, CTEs, column aliases —
goes directly in the SQL.

When page/per_page are passed to fetch(), the adapter wraps the base query
in a CTE and pushes filter/sort/paginate into SQL so the database engine
handles it — only the requested page is transferred to Python.
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

    # ── SQL builder helpers ──────────────────────────────────────────────────

    def _build_where_sql(self, clauses, params, param_offset=0):
        parts = []
        idx = param_offset
        for field, op, val in clauses:
            qcol = f"[{field}]"
            pname = f"_f{idx}"

            if op == "eq":
                parts.append(f"{qcol} = :{pname}")
                params[pname] = val
            elif op == "contains":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) LIKE '%' + :{pname} + '%'")
                params[pname] = val.lower()
            elif op == "equals":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) = :{pname}")
                params[pname] = val.lower()
            elif op == "startsWith":
                parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) LIKE :{pname} + '%'")
                params[pname] = val.lower()
            elif op in ("numEq", "gt", "gte", "lt", "lte"):
                sym = {"numEq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                parts.append(f"TRY_CAST({qcol} AS FLOAT) {sym} :{pname}")
                params[pname] = float(val)
            elif op in ("dateEq", "dateBefore", "dateAfter"):
                sym = {"dateEq": "=", "dateBefore": "<", "dateAfter": ">"}[op]
                parts.append(f"TRY_CAST({qcol} AS DATE) {sym} :{pname}")
                params[pname] = val
            elif op == "inList":
                values = [v.strip().lower() for v in val.split(",") if v.strip()]
                in_names = []
                for v in values:
                    pn = f"_f{idx}"
                    in_names.append(f":{pn}")
                    params[pn] = v
                    idx += 1
                if in_names:
                    parts.append(f"LOWER(CAST({qcol} AS NVARCHAR(MAX))) IN ({', '.join(in_names)})")
                continue

            idx += 1
        return parts

    def _build_order_sql(self, sort_fields):
        if not sort_fields:
            return "ORDER BY (SELECT NULL)"
        return "ORDER BY " + ", ".join(f"[{f}] {d}" for f, d in sort_fields)

    def _build_cte_sql(self, base_sql, fic_mis_date, clauses, sort_fields,
                       select="*", page=None, per_page=None):
        params = {"fic_mis_date": fic_mis_date}
        where_parts = self._build_where_sql(clauses, params)
        order_by = self._build_order_sql(sort_fields)

        clean_base = self._strip_order_by(base_sql)
        sql = f"WITH _base AS (\n{clean_base}\n)\nSELECT {select} FROM _base"
        if where_parts:
            sql += "\nWHERE " + " AND ".join(where_parts)
        sql += f"\n{order_by}"
        if page is not None and per_page is not None:
            params["_offset"] = (page - 1) * per_page
            params["_limit"] = per_page
            sql += "\nOFFSET :_offset ROWS FETCH NEXT :_limit ROWS ONLY"

        return sql, params

    # ── Public interface ─────────────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
        page:        Optional[int]            = None,
        per_page:    Optional[int]            = None,
    ) -> pd.DataFrame:
        from sqlalchemy import text

        filters      = dict(filters or {})
        fic_mis_date = filters.pop("_fic_mis_date", "")
        col_filters  = filters.get("col_filters", {})
        quick        = filters.get("quick_filter", "")
        base_sql     = self._get_query(entity_type)

        can_db_paginate = page is not None and per_page is not None and not quick

        if can_db_paginate:
            clauses = self._build_filter_clauses(col_filters, entity_key)
            sort_fields = self._build_sort_fields(sorts)
            sql, params = self._build_cte_sql(
                base_sql, fic_mis_date, clauses, sort_fields,
                page=page, per_page=per_page,
            )
            self.log.debug("SQLServerAdapter paginated SQL:\n%s\nparams=%s", sql, params)
            engine = self._get_engine()
            with engine.connect() as conn:
                df = pd.read_sql(text(sql), conn, params=params)
        else:
            params = {"fic_mis_date": fic_mis_date}
            engine = self._get_engine()
            with engine.connect() as conn:
                df = pd.read_sql(text(base_sql), conn, params=params)

            if entity_key:
                for field, val in entity_key.items():
                    if field in df.columns:
                        df = df[df[field] == str(val)].reset_index(drop=True)
            if col_filters:
                df = self._apply_col_filters(df, col_filters)
            if quick:
                df = self._apply_quick_filter(df, quick)
            df = self._apply_sorts(df, sorts or [])

        self.log.debug(
            "SQLServerAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def fetch_count(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
    ) -> int:
        from sqlalchemy import text

        filters      = dict(filters or {})
        fic_mis_date = filters.pop("_fic_mis_date", "")
        col_filters  = filters.get("col_filters", {})
        base_sql     = self._get_query(entity_type)

        clauses = self._build_filter_clauses(col_filters, entity_key)
        sql, params = self._build_cte_sql(
            base_sql, fic_mis_date, clauses, sort_fields=[],
            select="COUNT(*) AS cnt",
        )
        engine = self._get_engine()
        with engine.connect() as conn:
            row = conn.execute(text(sql), params).fetchone()
        return row[0] if row else 0

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
