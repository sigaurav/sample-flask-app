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

Add one entry to _QUERY_MAP per entity.  Each query must accept two
positional (?) parameters in order: SOR, fic_mis_date.  Everything else —
joins, CTEs, column aliases — goes directly in the SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


class TeradataAdapter(BaseAdapter):

    source_type = "teradata"

    # One entry per entity.  Positional ? parameter: fic_mis_date
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

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        filters      = dict(filters or {})
        fic_mis_date = filters.pop("_fic_mis_date", "")

        sql    = self._get_query(entity_type)
        params = [fic_mis_date]
        self.log.debug("TeradataAdapter SQL: %s  params=%s", sql, params)

        with self._get_connection() as con:
            df = pd.read_sql(sql, con, params=params)

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
            "TeradataAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

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
