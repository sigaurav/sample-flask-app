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


class TeradataAdapter(BaseAdapter):
    """Teradata adapter using SSO Kerberos/TDNEGO authentication."""

    source_type = "teradata"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host   = config.get("TERADATA_HOST", "")
        self._port   = int(config.get("TERADATA_PORT", 1025))
        self._db     = config.get("TERADATA_DB", "")
        self._schema = config.get("TERADATA_SCHEMA", "") or config.get("TERADATA_DB", "")

    # ── Connection ────────────────────────────────────────────────────────────

    def _get_connection(self):
        try:
            import teradatasql
        except ImportError:
            raise RuntimeError(
                "teradatasql is required for Teradata: pip install teradatasql"
            )
        return teradatasql.connect(
            host     = self._host,
            dbs_port = str(self._port),
            database = self._db,
            logmech  = "TDNEGO",   # SSO — negotiates Kerberos or LDAP automatically
        )

    # ── SQL builder ───────────────────────────────────────────────────────────

    def _build_query(
        self,
        entity_type:  str,
        entity_key:   Optional[Dict[str, str]],
        sor:          str,
        fic_mis_date: str,
    ) -> Tuple[str, List]:
        """Return (sql_string, positional_params_list) for teradatasql ? binding."""
        cols   = self._get_select_cols(entity_type)
        select = "*" if cols == ["*"] else ", ".join(f'"{c}"' for c in cols)
        table  = _TABLE_MAP[entity_type]
        conditions = []
        params: List[Any] = []

        if sor:
            conditions.append('"FACLTY_SOR_ID" = ?')
            params.append(sor)
        if fic_mis_date:
            conditions.append('"PERIOD_DT" = ?')
            params.append(fic_mis_date)
        if entity_key:
            for field, val in entity_key.items():
                conditions.append(f'"{field}" = ?')
                params.append(val)

        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        sql   = f'SELECT {select} FROM "{self._schema}"."{table}"{where}'
        return sql, params

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        filters      = dict(filters or {})
        sor          = filters.pop("_sor", "")
        fic_mis_date = filters.pop("_fic_mis_date", "")

        sql, params = self._build_query(entity_type, entity_key, sor, fic_mis_date)
        self.log.debug("TeradataAdapter SQL: %s  params=%s", sql, params)

        with self._get_connection() as con:
            df = pd.read_sql(sql, con, params=params if params else None)

        col_filters = filters.get("col_filters", {})
        if col_filters:
            df = self._apply_col_filters(df, col_filters)
        quick = filters.get("quick_filter", "")
        if quick:
            df = self._apply_quick_filter(df, quick)

        df = self._apply_sorts(df, sorts or [])
        self.log.debug(
            "TeradataAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            return cols

        table = _TABLE_MAP.get(entity_type)
        if not table:
            raise ValueError(f"Unknown entity_type '{entity_type}'")

        sql = (
            "SELECT ColumnName FROM DBC.ColumnsV "
            f"WHERE DatabaseName = '{self._db}' AND TableName = '{table}' "
            "ORDER BY ColumnId"
        )
        with self._get_connection() as con:
            df = pd.read_sql(sql, con)
        return df["ColumnName"].tolist()

    def health_check(self) -> bool:
        try:
            with self._get_connection() as con:
                pd.read_sql("SELECT 1 AS ok", con)
            return True
        except Exception:
            return False
