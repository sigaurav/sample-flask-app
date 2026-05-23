"""
CSV data source — reads authoritative data from the flat-file store in DATA_DIR.

This is the Phase 1 default source type used for all FR Y-14Q workflows
when Dremio or SQL Server connectivity is not configured.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

from app.datasources.base_datasource import BaseDataSource


# ── Entity → file mapping ─────────────────────────────────────────────────────

_ENTITY_FILES: Dict[str, str] = {
    "facilities":   "facilities.csv",
    "obligors":     "obligors.csv",
    "transactions": "transactions.csv",
    "comments":     "comments.csv",
}

# Maps each child entity to the parent-FK field used for scoping.
_PARENT_FK: Dict[str, str] = {
    "obligors":     "facility_id",
    "transactions": "obligor_id",
    "comments":     "transaction_id",
}


class CSVDataSource(BaseDataSource):
    """
    Reads authoritative FR Y-14Q data from CSV files.

    Files are loaded once per ``CSVDataSource`` instance and cached in
    memory for the lifetime of the object.  The export worker creates a
    fresh instance per job, so the cache does not persist across requests.
    """

    source_type = "csv"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._data_dir: str = config["data_dir"]
        self._cache: Dict[str, pd.DataFrame] = {}

    # ── Internal loader ───────────────────────────────────────────────────────

    def _load(self, entity_type: str) -> pd.DataFrame:
        if entity_type in self._cache:
            return self._cache[entity_type]

        fname = _ENTITY_FILES.get(entity_type)
        if not fname:
            raise ValueError(f"Unknown entity_type '{entity_type}'. "
                             f"Valid: {sorted(_ENTITY_FILES)}")

        path = os.path.join(self._data_dir, fname)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Data file not found: {path}")

        df = pd.read_csv(path, dtype=str).fillna("")
        self._cache[entity_type] = df
        self.log.debug(
            "CSVDataSource loaded entity=%s rows=%d path=%s",
            entity_type, len(df), path,
        )
        return df

    # ── BaseDataSource interface ──────────────────────────────────────────────

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        """
        Fetch entity data with optional parent-scoping, filtering, and sorting.

        For ``export_type=full`` callers pass ``filters=None, sorts=None``;
        for ``partial`` exports the frontend filter/sort state is forwarded.
        """
        df = self._load(entity_type).copy()

        # ── Scope to parent entity ────────────────────────────────────────────
        if entity_id and entity_type in _PARENT_FK:
            pk_field = _PARENT_FK[entity_type]
            df = df[df[pk_field] == str(entity_id)].reset_index(drop=True)

        # ── Column filters ────────────────────────────────────────────────────
        if filters:
            col_filters = filters.get("col_filters", {})
            if col_filters:
                df = self._apply_col_filters(df, col_filters)

            quick = filters.get("quick_filter", "")
            if quick:
                df = self._apply_quick_filter(df, quick)

        # ── Sort ──────────────────────────────────────────────────────────────
        df = self._apply_sorts(df, sorts or [])

        self.log.debug(
            "CSVDataSource.fetch entity=%s entity_id=%s rows_returned=%d",
            entity_type, entity_id, len(df),
        )
        return df

    def health_check(self) -> bool:
        return all(
            os.path.exists(os.path.join(self._data_dir, f))
            for f in _ENTITY_FILES.values()
        )
