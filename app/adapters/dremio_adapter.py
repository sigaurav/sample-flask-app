"""
Dremio adapter — Arrow Flight query engine for FR Y-14Q data.

Requires:  pip install pyarrow

Connection config keys (Flask uppercase):
    DREMIO_HOST   : Dremio coordinator hostname
    DREMIO_PORT   : Arrow Flight port (default 32010)
    DREMIO_SOURCE : Virtual dataset source namespace (e.g. 'FR_Y14Q')

Credentials are retrieved via the injected CredentialProvider (Windows
Credential Manager / keyring).  Passwords are never stored in config or logged.

Add one entry to _QUERY_MAP per entity.  Use {period_dt} as the
placeholder — Arrow Flight does not support parameterised queries so the
value is interpolated at runtime.  Everything else — joins, CTEs, column
aliases — goes directly in the SQL.

When page/per_page are passed to fetch(), the adapter wraps the base query
in a CTE and pushes filter/sort/paginate into SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


def _esc(val: str) -> str:
    """Escape a string value for Dremio SQL (no parameterised queries)."""
    return str(val).replace("'", "''")


class DremioAdapter(BaseAdapter):

    source_type = "dremio"

    # One entry per entity.  Placeholder: {period_dt}
    _QUERY_MAP: Dict[str, str] = {
        # "facilities": """
        #     SELECT *
        #     FROM   "FR_Y14Q"."H1_FACILITIES"
        #     WHERE  "PERIOD_DT" = '{period_dt}'
        # """,
    }

    def __init__(self, config: Dict[str, Any], credential_provider=None) -> None:
        super().__init__(config)
        self._host                = config.get("DREMIO_HOST", "")
        self._port                = int(config.get("DREMIO_PORT", 32010))
        self._source              = config.get("DREMIO_SOURCE", "FR_Y14Q")
        self._credential_provider = credential_provider

    def _get_credentials(self) -> Tuple[str, str]:
        if self._credential_provider is None:
            raise RuntimeError("No credential provider configured for Dremio.")
        user     = self._credential_provider.get_secret("dremio_user")
        password = self._credential_provider.get_secret("dremio_password")
        return user, password

    def _get_client(self):
        try:
            from pyarrow import flight
        except ImportError:
            raise RuntimeError("pyarrow is required for Dremio: pip install pyarrow")
        location       = f"grpc+tls://{self._host}:{self._port}"
        client         = flight.FlightClient(location)
        user, password = self._get_credentials()
        bearer_token   = client.authenticate_basic_token(user, password)
        return client, flight.FlightCallOptions(headers=[bearer_token])

    def _execute(self, sql: str) -> pd.DataFrame:
        from pyarrow import flight
        import pyarrow as pa
        client, options = self._get_client()
        descriptor = flight.FlightDescriptor.for_command(sql.encode("utf-8"))
        info        = client.get_flight_info(descriptor, options)
        tables      = [client.do_get(ep.ticket, options).read_all() for ep in info.endpoints]
        return (pa.concat_tables(tables) if tables else pa.table({})).to_pandas()

    def _get_query(self, entity_type: str) -> str:
        sql = self._QUERY_MAP.get(entity_type)
        if not sql:
            raise KeyError(
                f"No query defined for '{entity_type}' in DremioAdapter._QUERY_MAP"
            )
        return sql

    # ── SQL builder helpers ──────────────────────────────────────────────────

    def _build_where_sql(self, clauses):
        parts = []
        for field, op, val in clauses:
            qcol = f'"{field}"'
            ev   = _esc(val)

            if op == "eq":
                parts.append(f"{qcol} = '{ev}'")
            elif op == "contains":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR)) LIKE '%{_esc(val.lower())}%'")
            elif op == "equals":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR)) = '{_esc(val.lower())}'")
            elif op == "startsWith":
                parts.append(f"LOWER(CAST({qcol} AS VARCHAR)) LIKE '{_esc(val.lower())}%'")
            elif op in ("numEq", "gt", "gte", "lt", "lte"):
                sym = {"numEq": "=", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
                parts.append(f"CAST({qcol} AS DOUBLE) {sym} {float(val)}")
            elif op in ("dateEq", "dateBefore", "dateAfter"):
                sym = {"dateEq": "=", "dateBefore": "<", "dateAfter": ">"}[op]
                parts.append(f"CAST({qcol} AS DATE) {sym} DATE '{ev}'")
            elif op == "inList":
                values = [f"'{_esc(v.strip().lower())}'" for v in val.split(",") if v.strip()]
                if values:
                    parts.append(f"LOWER(CAST({qcol} AS VARCHAR)) IN ({', '.join(values)})")
        return parts

    def _build_order_sql(self, sort_fields):
        if not sort_fields:
            return ""
        return "ORDER BY " + ", ".join(f'"{f}" {d}' for f, d in sort_fields)

    def _build_cte_sql(self, base_sql, period_dt, clauses, sort_fields,
                       select="*", page=None, per_page=None):
        base_rendered = base_sql.format(period_dt=_esc(period_dt))
        clean_base = self._strip_order_by(base_rendered)
        where_parts = self._build_where_sql(clauses)
        order_by = self._build_order_sql(sort_fields)

        sql = f"WITH _base AS (\n{clean_base}\n)\nSELECT {select} FROM _base"
        if where_parts:
            sql += "\nWHERE " + " AND ".join(where_parts)
        if order_by:
            sql += f"\n{order_by}"
        if page is not None and per_page is not None:
            offset = (page - 1) * per_page
            sql += f"\nLIMIT {per_page} OFFSET {offset}"

        return sql

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
            sql = self._build_cte_sql(
                base_sql, period_dt, clauses, sort_fields,
                page=page, per_page=per_page,
            )
            self.log.debug("DremioAdapter paginated SQL:\n%s", sql)
            df = self._execute(sql)
        else:
            sql = base_sql.format(period_dt=_esc(period_dt))
            self.log.debug("DremioAdapter SQL: %s", sql)
            df = self._execute(sql)

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
            "DremioAdapter.fetch entity=%s entity_key=%s rows=%d",
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
        sql = self._build_cte_sql(
            base_sql, period_dt, clauses, sort_fields=[],
            select="COUNT(*) AS cnt",
        )
        df = self._execute(sql)
        return int(df.iloc[0, 0]) if not df.empty else 0

    def introspect_columns(self, entity_type: str) -> List[str]:
        sql = self._get_query(entity_type).format(period_dt="")
        df  = self._execute(f"SELECT * FROM ({sql}) AS _q LIMIT 0")
        return df.columns.tolist()

    def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False
