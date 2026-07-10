"""
DataService — central adapter registry for all FR Y-14Q data sources.

Reads ENABLED_DATA_SOURCES from app config and initialises only the
adapters that are configured.  Registered on the Flask app object in
create_app() so adapters are shared across requests rather than
re-created per call.

Usage (in routes / services):
    adapter = current_app.data_service.get_adapter_for_entity("facilities")
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.adapters.base_adapter       import BaseAdapter
from app.adapters.csv_adapter        import CSVAdapter
from app.adapters.dremio_adapter     import DremioAdapter
from app.adapters.sqlserver_adapter  import SQLServerAdapter
from app.adapters.teradata_adapter   import TeradataAdapter

log = logging.getLogger(__name__)

_ADAPTER_CLASSES: Dict[str, type] = {
    "csv":       CSVAdapter,
    "dremio":    DremioAdapter,
    "sqlserver": SQLServerAdapter,
    "teradata":  TeradataAdapter,
}

# Only Dremio uses a credential provider (Windows Credential Manager / keyring).
# SQL Server uses SSO Windows Authentication — no credential provider needed.
_NEEDS_CREDENTIAL_PROVIDER = {"dremio"}


class DataService:
    """
    Manages the lifecycle of all data-source adapters.

    Adapters are initialised once at app startup based on the
    ENABLED_DATA_SOURCES config list.  The first entry in that list
    is treated as the primary (default) source.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config  = config
        self.adapters: Dict[str, BaseAdapter] = {}

        # Intersect: sources declared in ENTITIES that are also in ENABLED_DATA_SOURCES.
        # ENTITIES says what source each entity *wants*; ENABLED_DATA_SOURCES gates
        # which sources are permitted to connect.  Unlisted sources are skipped.
        entities = config.get("ENTITIES", {})
        required = {v.get("source", "csv") for v in entities.values()}
        enabled  = set(config.get("ENABLED_DATA_SOURCES", ["csv"]))
        to_init  = required & enabled or {"csv"}

        cp = None
        if any(s in _NEEDS_CREDENTIAL_PROVIDER for s in to_init):
            from app.security.windows_credential_provider import WindowsCredentialProvider
            cp = WindowsCredentialProvider()

        for source in to_init:
            cls = _ADAPTER_CLASSES.get(source)
            if cls is None:
                log.warning("DataService: unknown source '%s' — skipped", source)
                continue
            try:
                if source in _NEEDS_CREDENTIAL_PROVIDER:
                    self.adapters[source] = cls(config, cp)
                else:
                    self.adapters[source] = cls(config)
                log.info("DataService: registered adapter '%s'", source)
            except Exception as exc:
                log.warning("DataService: could not init adapter '%s': %s", source, exc)

        if not self.adapters:
            log.warning("DataService: no adapters initialised — falling back to CSV")
            self.adapters["csv"] = CSVAdapter(config)

    #  Public API ─

    def get_adapter_for_entity(self, entity_type: str) -> BaseAdapter:
        """Return the adapter configured for *entity_type* in ENTITIES config."""
        source = self._config.get("ENTITIES", {}).get(entity_type, {}).get("source")
        if source and source in self.adapters:
            return self.adapters[source]
        return next(iter(self.adapters.values()))
