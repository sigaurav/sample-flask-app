"""
Teradata adapter — teradatasql for FR Y-14Q data.

Requires:  pip install teradatasql

Connection config keys (Flask uppercase):
    TERADATA_HOST   : Teradata server hostname / IP
    TERADATA_PORT   : DBC port (default 1025)
    TERADATA_DB     : Default database / schema name
    TERADATA_SCHEMA : Schema used for table qualification (default same as DB)

Authentication uses Kerberos / Windows SSO via TDNEGO logon mechanism.
No username or password is required or stored.

Add one entry to _QUERY_MAP per entity.  Each query must accept one
positional (?) parameter: period_dt.  Everything else — joins, CTEs,
column aliases — goes directly in the SQL.

When page/per_page are passed to fetch(), the adapter wraps the base query
in a CTE and pushes filter/sort/paginate into SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


class TeradataAdapter(BaseAdapter):

    source_type = "teradata"

    # One entry per entity.  Positional ? parameter: period_dt
    _QUERY_MAP: Dict[str, str] = {
        # "facilities": """
        #     SELECT *
        #     FROM   "SCHEMA"."H1_FACILITIES"
        #     WHERE  "PERIOD_DT" = ?
        # """,
    }

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("TERADATA_HOST", "")
        self._port   = int(config.get("TERADATA_PORT", 1025))
        self._db     = config.get("TERADATA_DB", "")
        self._schema = config.get("TERADATA_SCHEMA", "") or config.get("TERADATA_DB", "")

    def _get_connection(self):
        try:
            import teradatasql
        except ImportError:
            raise RuntimeError("teradatasql is required for Teradata: pip install teradatasql")
        return teradatasql.connect(
            host     = self._host,
            dbs_port = str(self._port),
            database = self._db,
            logmech  = "TDNEGO",
        )

    def _get_query(self, entity_type: str) -> str:
        sql = self._QUERY_MAP.get(entity_type)
        if not sql:
            raise KeyError(
                f"No query defined for '{entity_type}' in TeradataAdapter._QUERY_MAP"
            )
        return sql

    # ── SQL builder helpers ──────────────────────────────────────────────────

    def _build_where_sql(self, clauses, params):
        parts = []
        for field, op, val in clauses:
            qcol = f'"{field}"'

            if op == "eq":
                parts.append(f"{qcol} = ?")
                params.append(val)
            elif op == "contains":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR(10000))) LIKE '%' || ? || '%'")
                params.append(val.lower())
            elif op == "equals":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR(10000))) = ?")
                params.append(val.lower())
            elif op == "startsWith":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR(10000))) LIKE ? || '%'")
                params.append(val.lower())
            elif op in ("numEq", "gt", "gte", "lt", "lte"):
                sym = {"numEq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                parts.append(f"CAST({qcol} AS FLOAT) {sym} ?")
                params.append(float(val))
            elif op in ("dateEq", "dateBefore", "dateAfter"):
                sym = {"dateEq": "=", "dateBefore": "<", "dateAfter": ">"}[op]
                parts.append(f"CAST({qcol} AS DATE) {sym} ?")
                params.append(val)
            elif op == "inList":
                values = [v.strip().lower() for v in val.split(",") if v.strip()]
                if values:
                    placeholders = ", ".join("?" for _ in values)
                    parts.append(f"LOWER(CAST({qcol} AS VARCHAR(10000))) IN ({placeholders})")
                    params.extend(values)
        return parts

    def _build_order_sql(self, sort_fields):
        if not sort_fields:
            return ""
        return "ORDER BY " + ", ".join(f'"{f}" {d}' for f, d in sort_fields)

    def _build_cte_sql(self, base_sql, period_dt, clauses, sort_fields,
                       select="*", page=None, per_page=None):
        clean_base = self._strip_order_by(base_sql)
        params = [period_dt]
        where_parts = self._build_where_sql(clauses, params)
        order_by = self._build_order_sql(sort_fields)

        sql = f"WITH _base AS (\n{clean_base}\n)\nSELECT {select} FROM _base"
        if where_parts:
            sql += "\nWHERE " + " AND ".join(where_parts)
        if order_by:
            sql += f"\n{order_by}"
        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            if order_by:
                sql += f"\nOFFSET {offset} ROWS FETCH NEXT {per_page} ROWS ONLY"
            else:
                sql += f"\nORDER BY 1\nOFFSET {offset} ROWS FETCH NEXT {per_page} ROWS ONLY"

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
        filters      = dict(filters or {})
        period_dt = filters.pop("_period_dt", "")
        col_filters  = filters.get("col_filters", {})
        quick        = filters.get("quick_filter", "")
        base_sql     = self._get_query(entity_type)

        can_db_paginate = page is not None and per_page is not None and not quick

        if can_db_paginate:
            clauses = self._build_filter_clauses(col_filters, entity_key)
            sort_fields = self._build_sort_fields(sorts)
            sql, params = self._build_cte_sql(
                base_sql, period_dt, clauses, sort_fields,
                page=page, per_page=per_page,
            )
            self.log.debug("TeradataAdapter paginated SQL:\n%s\nparams=%s", sql, params)
            with self._get_connection() as con:
                df = pd.read_sql(sql, con, params=params)
        else:
            params = [period_dt]
            with self._get_connection() as con:
                df = pd.read_sql(base_sql, con, params=params)

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
            "TeradataAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def fetch_count(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
    ) -> int:
        filters      = dict(filters or {})
        period_dt = filters.pop("_period_dt", "")
        col_filters  = filters.get("col_filters", {})
        base_sql     = self._get_query(entity_type)

        clauses = self._build_filter_clauses(col_filters, entity_key)
        sql, params = self._build_cte_sql(
            base_sql, period_dt, clauses, sort_fields=[],
            select="COUNT(*) AS cnt",
        )
        with self._get_connection() as con:
            df = pd.read_sql(sql, con, params=params)
        return int(df.iloc[0, 0]) if not df.empty else 0

    def introspect_columns(self, entity_type: str) -> List[str]:
        sql = self._get_query(entity_type)
        with self._get_connection() as con:
            df = pd.read_sql(
                f"SELECT * FROM ({sql}) AS _q WHERE 1=0",
                con,
                params=[""],
            )
        return df.columns.tolist()

    def health_check(self) -> bool:
        try:
            with self._get_connection() as con:
                pd.read_sql("SELECT 1 AS ok", con)
            return True
        except Exception:
            return False
