"""
Dremio adapter — Arrow Flight / REST query engine for FR Y-14Q data.

Phase 1: Stub — raises ``NotImplementedError`` at runtime.
Phase 2: Install ``pyarrow`` and configure the connection keys below.

Connection config keys (Flask uppercase):
    DREMIO_HOST   : Dremio coordinator hostname
    DREMIO_PORT   : Arrow Flight port (default 32010)
    DREMIO_SOURCE : Virtual dataset source path (e.g., 'FR_Y14Q.dbo')

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

    Not available in Phase 1.  Configure DREMIO_HOST/DREMIO_SOURCE in
    ProductionConfig and add 'dremio' to ENTITY_SOURCES to activate.
    """

    source_type = "dremio"

    def __init__(self, config: Dict[str, Any], credential_provider=None) -> None:
        super().__init__(config)
        self._host               = config.get("DREMIO_HOST", "")
        self._port               = int(config.get("DREMIO_PORT", 32010))
        self._source             = config.get("DREMIO_SOURCE", "FR_Y14Q")
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
            "Set DREMIO_HOST/DREMIO_SOURCE in config, configure a CredentialProvider, "
            "and install pyarrow."
        )

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        raise NotImplementedError("DremioAdapter is not available in Phase 1.")

    def introspect_columns(self, entity_type: str) -> List[str]:  # noqa: ARG002
        raise NotImplementedError("DremioAdapter.introspect_columns not available in Phase 1.")

    def health_check(self) -> bool:
        return False
