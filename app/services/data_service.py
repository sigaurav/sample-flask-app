"""
DataService — central adapter registry for all FR Y-14Q data sources.

Reads ENABLED_DATA_SOURCES from app config and initialises only the
adapters that are configured.  Registered on the Flask app object in
create_app() so adapters are shared across requests rather than
re-created per call.

Usage (in routes):
    from flask import current_app
    adapter = current_app.data_service.get_adapter()
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.adapters.csv_adapter       import CSVAdapter
from app.adapters.dremio_adapter    import DremioAdapter
from app.adapters.excel_adapter     import ExcelAdapter
from app.adapters.sqlserver_adapter import SQLServerAdapter
from app.adapters.base_adapter      import BaseAdapter

log = logging.getLogger(__name__)

_ADAPTER_CLASSES: Dict[str, type] = {
    "csv":       CSVAdapter,
    "dremio":    DremioAdapter,
    "sqlserver": SQLServerAdapter,
    "excel":     ExcelAdapter,
}

_NEEDS_CREDENTIAL_PROVIDER = {"dremio", "sqlserver"}


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

        # Credential provider is only needed for Dremio / SQL Server.
        # Lazy-import so keyring is not required when only CSV is active.
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
                ds_cfg = self._build_adapter_config(source)
                if source in _NEEDS_CREDENTIAL_PROVIDER:
                    self.adapters[source] = cls(ds_cfg, cp)
                else:
                    self.adapters[source] = cls(ds_cfg)
                log.info("DataService: registered adapter '%s'", source)
            except Exception as exc:
                log.warning("DataService: could not init adapter '%s': %s", source, exc)

        if not self.adapters:
            log.warning("DataService: no adapters initialised — falling back to CSV")
            self.adapters["csv"] = CSVAdapter(self._build_adapter_config("csv"))

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_adapter(self, source_type: Optional[str] = None) -> BaseAdapter:
        """
        Return the adapter for *source_type*, or the primary adapter when
        *source_type* is None.

        Raises ValueError if the requested source is not configured.
        """
        if source_type:
            adapter = self.adapters.get(source_type)
            if adapter is None:
                raise ValueError(
                    f"Adapter '{source_type}' is not configured. "
                    f"Enabled sources: {list(self.adapters)}"
                )
            return adapter
        return next(iter(self.adapters.values()))

    def health(self) -> Dict[str, bool]:
        """Return a health-check result for every registered adapter."""
        return {name: adapter.health_check() for name, adapter in self.adapters.items()}

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build_adapter_config(self, source_type: str) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {"data_dir": self._config.get("DATA_DIR", "")}

        if source_type == "dremio":
            cfg.update({
                "dremio_host":   self._config.get("DREMIO_HOST", ""),
                "dremio_port":   self._config.get("DREMIO_PORT", 32010),
                "dremio_source": self._config.get("DREMIO_SOURCE", "FR_Y14Q"),
            })
        elif source_type == "sqlserver":
            cfg.update({
                "sqlserver_host":   self._config.get("SQLSERVER_HOST", ""),
                "sqlserver_port":   self._config.get("SQLSERVER_PORT", 1433),
                "sqlserver_db":     self._config.get("SQLSERVER_DB", ""),
                "sqlserver_schema": self._config.get("SQLSERVER_SCHEMA", "dbo"),
                "sqlserver_driver": self._config.get(
                    "SQLSERVER_DRIVER", "ODBC Driver 18 for SQL Server"
                ),
            })
        elif source_type == "excel":
            cfg["excel_path"] = self._config.get("EXCEL_DATA_PATH", "")

        return cfg
