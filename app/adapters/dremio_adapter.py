"""
Dremio adapter — Arrow Flight / REST query engine for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``pyarrow`` and configure the connection keys below.

Connection config keys:
    dremio_host     : Dremio coordinator hostname
    dremio_port     : Arrow Flight port (default 32010)
    dremio_source   : Virtual dataset source path (e.g., 'FR_Y14Q.dbo')

Credentials are retrieved via the injected ``CredentialProvider`` —
passwords are never stored in config or logged.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


_SQL_TEMPLATES: Dict[str, str] = {
    "facilities":   "SELECT * FROM {source}.h1_facilities",
    "obligors":     "SELECT * FROM {source}.h1_obligors WHERE facility_id = '{eid}'",
    "transactions": "SELECT * FROM {source}.h1_transactions WHERE obligor_id = '{eid}'",
    "comments":     "SELECT * FROM {source}.h1_comments WHERE transaction_id = '{eid}'",
}


class DremioAdapter(BaseAdapter):
    """
    Dremio Arrow Flight adapter for FR Y-14Q regulatory reporting.

    Not available in Phase 1.  Configure in ProductionConfig and set
    ``source_type='dremio'`` in export job requests to activate.
    """

    source_type = "dremio"

    def __init__(self, config: Dict[str, Any], credential_provider=None) -> None:
        super().__init__(config)
        self._host              = config.get("dremio_host", "")
        self._port              = int(config.get("dremio_port", 32010))
        self._source            = config.get("dremio_source", "FR_Y14Q")
        self._credential_provider = credential_provider

    def _get_credentials(self):
        """Retrieve user/password from the credential provider (never from config)."""
        if self._credential_provider is None:
            raise RuntimeError("No credential provider configured for Dremio.")
        user     = self._credential_provider.get_secret("dremio_user")
        password = self._credential_provider.get_secret("dremio_password")
        return user, password

    def _get_client(self):
        """
        Return an authenticated Arrow Flight client.

        Phase 2 implementation:
            from pyarrow import flight
            user, password = self._get_credentials()
            client = flight.FlightClient(f'grpc+tls://{self._host}:{self._port}')
            return client, client.authenticate_basic_token(user, password)
        """
        raise NotImplementedError(
            "Dremio adapter not configured. "
            "Set dremio_host/dremio_source in config, configure a CredentialProvider, "
            "and install pyarrow."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            "DremioAdapter is not available in Phase 1. "
            "Use source_type='csv' or 'excel' for export jobs."
        )

    def health_check(self) -> bool:
        return False
