"""
Dremio data source — Arrow Flight / REST query engine for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``pyarrow`` and configure the connection keys below.

Connection config keys:
    dremio_host     : Dremio coordinator hostname
    dremio_port     : Arrow Flight port (default 32010)
    dremio_user     : Service account username
    dremio_password : Service account password (or PAT token)
    dremio_source   : Virtual dataset source path (e.g., 'FR_Y14Q.dbo')

SQL table paths (Dremio VDS namespace):
    facilities   → {source}.h1_facilities
    obligors     → {source}.h1_obligors
    transactions → {source}.h1_transactions
    comments     → {source}.h1_comments

Phase 2 implementation notes:
    pip install pyarrow
    from pyarrow import flight
    client = flight.FlightClient(f'grpc+tls://{host}:{port}')
    token_pair = client.authenticate_basic_token(user, password)
    headers = [token_pair]
    descriptor = flight.FlightDescriptor.for_command(sql_query.encode())
    info = client.get_flight_info(descriptor, flight.FlightCallOptions(headers=headers))
    reader = client.do_get(info.endpoints[0].ticket, ...)
    df = reader.read_pandas()
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.datasources.base_datasource import BaseDataSource


# SQL templates — safe for string interpolation only with validated entity names.
_SQL_TEMPLATES: Dict[str, str] = {
    "facilities":   "SELECT * FROM {source}.h1_facilities",
    "obligors":     "SELECT * FROM {source}.h1_obligors WHERE facility_id = '{eid}'",
    "transactions": "SELECT * FROM {source}.h1_transactions WHERE obligor_id = '{eid}'",
    "comments":     "SELECT * FROM {source}.h1_comments WHERE transaction_id = '{eid}'",
}


class DremioDataSource(BaseDataSource):
    """
    Dremio Arrow Flight data source for FR Y-14Q regulatory reporting.

    Not available in Phase 1.  Configure in ProductionConfig and set
    ``source_type='dremio'`` in export job requests to activate.
    """

    source_type = "dremio"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._host     = config.get("dremio_host", "")
        self._port     = int(config.get("dremio_port", 32010))
        self._user     = config.get("dremio_user", "")
        self._password = config.get("dremio_password", "")
        self._source   = config.get("dremio_source", "FR_Y14Q")

    def _get_client(self):
        """
        Return an authenticated Arrow Flight client.

        Phase 2 implementation:
            from pyarrow import flight
            client = flight.FlightClient(f'grpc+tls://{self._host}:{self._port}')
            return client, client.authenticate_basic_token(self._user, self._password)
        """
        raise NotImplementedError(
            "Dremio source not configured. "
            "Set dremio_host/dremio_user/dremio_password in config and install pyarrow."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "DremioDataSource is not available in Phase 1. "
            "Use source_type='csv' or 'excel' for export jobs."
        )

    def health_check(self) -> bool:
        return False
