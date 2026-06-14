"""
Dremio adapter — Arrow Flight query engine for FR Y-14Q data.

Requires:  pip install pyarrow

Connection config keys (Flask uppercase):
    DREMIO_HOST   : Dremio coordinator hostname
    DREMIO_PORT   : Arrow Flight port (default 32010)
    DREMIO_SOURCE : Virtual dataset source namespace (e.g. 'FR_Y14Q')

Credentials are retrieved via the injected CredentialProvider (Windows
Credential Manager / keyring).  Passwords are never stored in config or logged.
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


class DremioAdapter(BaseAdapter):
    """Arrow Flight adapter for Dremio FR Y-14Q regulatory data."""

    source_type = "dremio"

    def __init__(self, config: Dict[str, Any], credential_provider=None) -> None:
        super().__init__(config)
        self._host               = config.get("DREMIO_HOST", "")
        self._port               = int(config.get("DREMIO_PORT", 32010))
        self._source             = config.get("DREMIO_SOURCE", "FR_Y14Q")
        self._credential_provider = credential_provider

    # ── Connection ────────────────────────────────────────────────────────────

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
            raise RuntimeError(
                "pyarrow is required for Dremio: pip install pyarrow"
            )
        location = f"grpc+tls://{self._host}:{self._port}"
        client   = flight.FlightClient(location)
        user, password = self._get_credentials()
        bearer_token   = client.authenticate_basic_token(user, password)
        options = flight.FlightCallOptions(headers=[bearer_token])
        return client, options

    # ── SQL builder ───────────────────────────────────────────────────────────

    def _build_sql(
        self,
        entity_type:  str,
        entity_key:   Optional[Dict[str, str]],
        sor:          str,
        fic_mis_date: str,
    ) -> str:
        cols   = self._get_select_cols(entity_type)
        select = "*" if cols == ["*"] else ", ".join(f'"{c}"' for c in cols)
        table  = _TABLE_MAP[entity_type]
        conditions = []
        if sor:
            conditions.append(f'"FACLTY_SOR_ID" = \'{sor}\'')
        if fic_mis_date:
            conditions.append(f'"PERIOD_DT" = \'{fic_mis_date}\'')
        if entity_key:
            for field, val in entity_key.items():
                conditions.append(f'"{field}" = \'{val}\'')
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return f'SELECT {select} FROM "{self._source}"."{table}"{where}'

    # ── Public interface ──────────────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        from pyarrow import flight, concat_tables  # import here for lazy dependency

        filters      = dict(filters or {})
        sor          = filters.pop("_sor", "")
        fic_mis_date = filters.pop("_fic_mis_date", "")

        sql = self._build_sql(entity_type, entity_key, sor, fic_mis_date)
        self.log.debug("DremioAdapter SQL: %s", sql)

        client, options = self._get_client()
        descriptor = flight.FlightDescriptor.for_command(sql.encode("utf-8"))
        info       = client.get_flight_info(descriptor, options)

        tables = []
        for endpoint in info.endpoints:
            reader = client.do_get(endpoint.ticket, options)
            tables.append(reader.read_all())

        import pyarrow as pa
        table = concat_tables(tables) if tables else pa.table({})
        df    = table.to_pandas()

        col_filters = filters.get("col_filters", {})
        if col_filters:
            df = self._apply_col_filters(df, col_filters)
        quick = filters.get("quick_filter", "")
        if quick:
            df = self._apply_quick_filter(df, quick)

        df = self._apply_sorts(df, sorts or [])
        self.log.debug(
            "DremioAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            return cols

        from pyarrow import flight

        table = _TABLE_MAP.get(entity_type)
        if not table:
            raise ValueError(f"Unknown entity_type '{entity_type}'")

        sql = (
            f"SELECT COLUMN_NAME "
            f"FROM INFORMATION_SCHEMA.\"COLUMNS\" "
            f"WHERE TABLE_SCHEMA = '{self._source}' "
            f"AND TABLE_NAME = '{table}' "
            f"ORDER BY ORDINAL_POSITION"
        )
        client, options = self._get_client()
        descriptor = flight.FlightDescriptor.for_command(sql.encode("utf-8"))
        info       = client.get_flight_info(descriptor, options)
        reader     = client.do_get(info.endpoints[0].ticket, options)
        return reader.read_all().to_pandas()["COLUMN_NAME"].tolist()

    def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False
