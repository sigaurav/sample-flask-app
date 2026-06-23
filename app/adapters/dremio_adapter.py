"""
Dremio adapter — Arrow Flight query engine for FR Y-14Q data.

Requires:  pip install pyarrow

Connection config keys (Flask uppercase):
    DREMIO_HOST   : Dremio coordinator hostname
    DREMIO_PORT   : Arrow Flight port (default 32010)
    DREMIO_SOURCE : Virtual dataset source namespace (e.g. 'FR_Y14Q')

Credentials are retrieved via the injected CredentialProvider (Windows
Credential Manager / keyring).  Passwords are never stored in config or logged.

Add one entry to _QUERY_MAP per entity.  Use {sor} and {fic_mis_date} as
placeholders — Arrow Flight does not support parameterised queries so values
are interpolated at runtime.  Everything else — joins, CTEs, column aliases —
goes directly in the SQL.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


class DremioAdapter(BaseAdapter):

    source_type = "dremio"

    # One entry per entity.  Placeholder: {fic_mis_date}
    _QUERY_MAP: Dict[str, str] = {
        # "facilities": """
        #     SELECT *
        #     FROM   "FR_Y14Q"."H1_FACILITIES"
        #     WHERE  "PERIOD_DT" = '{fic_mis_date}'
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

    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        filters      = dict(filters or {})
        fic_mis_date = filters.pop("_fic_mis_date", "")

        sql = self._get_query(entity_type).format(
            fic_mis_date=fic_mis_date.replace("'", "''"),
        )
        self.log.debug("DremioAdapter SQL: %s", sql)
        df = self._execute(sql)

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
            "DremioAdapter.fetch entity=%s entity_key=%s rows=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        sql = self._get_query(entity_type).format(fic_mis_date="")
        df  = self._execute(f"SELECT * FROM ({sql}) AS _q LIMIT 0")
        return df.columns.tolist()

    def health_check(self) -> bool:
        try:
            self._get_client()
            return True
        except Exception:
            return False
