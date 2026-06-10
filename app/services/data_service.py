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
from typing import Any, Dict, Optional

from app.adapters.base_adapter      import BaseAdapter
from app.adapters.csv_adapter       import CSVAdapter
from app.adapters.dremio_adapter    import DremioAdapter
from app.adapters.excel_adapter     import ExcelAdapter
from app.adapters.sqlserver_adapter import SQLServerAdapter

log = logging.getLogger(__name__)

_ADAPTER_CLASSES: Dict[str, type] = {
    "csv":       CSVAdapter,
    "dremio":    DremioAdapter,
    "sqlserver": SQLServerAdapter,
    "excel":     ExcelAdapter,
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

        enabled = config.get("ENABLED_DATA_SOURCES", ["csv"])

        # Lazy-import keyring only when Dremio is actually enabled.
        cp = None
        if any(s in _NEEDS_CREDENTIAL_PROVIDER for s in enabled):
            from app.security.windows_credential_provider import WindowsCredentialProvider
            cp = WindowsCredentialProvider()

        for source in enabled:
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

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_adapter(self, source_type: Optional[str] = None) -> BaseAdapter:
        """Return the adapter for *source_type*, or the primary adapter."""
        if source_type:
            adapter = self.adapters.get(source_type)
            if adapter is None:
                raise ValueError(
                    f"Adapter '{source_type}' is not configured. "
                    f"Enabled sources: {list(self.adapters)}"
                )
            return adapter
        return next(iter(self.adapters.values()))

    def get_adapter_for_entity(self, entity_type: str) -> BaseAdapter:
        """
        Return the adapter designated for *entity_type* via ENTITY_SOURCES config.

        Falls back to the primary adapter when no specific routing is configured
        or the designated source is not currently enabled.
        """
        entity_sources: Dict[str, str] = self._config.get("ENTITY_SOURCES", {})
        source = entity_sources.get(entity_type)
        if source and source in self.adapters:
            return self.adapters[source]
        # Fallback to primary
        return next(iter(self.adapters.values()))

    def health(self) -> Dict[str, bool]:
        """Return a health-check result for every registered adapter."""
        return {name: adapter.health_check() for name, adapter in self.adapters.items()}
