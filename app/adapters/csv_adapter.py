"""
CSV adapter — reads authoritative data from the flat-file store in DATA_DIR.

This is the Phase 1 default source type used for all FR Y-14Q workflows
when Dremio or SQL Server connectivity is not configured.
"""

from __future__ import annotations

import csv
import os
from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


_ENTITY_FILES: Dict[str, str] = {
    "facilities":   "facilities.csv",
    "obligors":     "obligors.csv",
    "transactions": "transactions.csv",
    "comments":     "comments.csv",
}

_PARENT_FK: Dict[str, str] = {
    "obligors":     "facility_id",
    "transactions": "obligor_id",
    "comments":     "transaction_id",
}


class CSVAdapter(BaseAdapter):
    """
    Reads authoritative FR Y-14Q data from CSV files.

    Files are loaded once per ``CSVAdapter`` instance and cached in
    memory for the lifetime of the object.
    """

    source_type = "csv"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._data_dir: str = config["DATA_DIR"]
        self._cache: Dict[str, pd.DataFrame] = {}

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
            "CSVAdapter loaded entity=%s rows=%d path=%s",
            entity_type, len(df), path,
        )
        return df

    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        df      = self._load(entity_type).copy()
        filters = dict(filters or {})

        # Context filter runs first — narrows to the selected SOR / reporting date
        sor          = filters.pop("_sor", "")
        fic_mis_date = filters.pop("_fic_mis_date", "")
        df = self._apply_context_filter(df, sor, fic_mis_date)

        if entity_id and entity_type in _PARENT_FK:
            pk_field = _PARENT_FK[entity_type]
            df = df[df[pk_field] == str(entity_id)].reset_index(drop=True)

        col_filters = filters.get("col_filters", {})
        if col_filters:
            df = self._apply_col_filters(df, col_filters)
        quick = filters.get("quick_filter", "")
        if quick:
            df = self._apply_quick_filter(df, quick)

        df = self._apply_sorts(df, sorts or [])

        self.log.debug(
            "CSVAdapter.fetch entity=%s entity_id=%s sor=%r rows_returned=%d",
            entity_type, entity_id, sor, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        fname = _ENTITY_FILES.get(entity_type)
        if not fname:
            raise ValueError(f"Unknown entity_type '{entity_type}'")
        path = os.path.join(self._data_dir, fname)
        with open(path, newline="", encoding="utf-8") as f:
            return next(csv.reader(f))

    def health_check(self) -> bool:
        return all(
            os.path.exists(os.path.join(self._data_dir, f))
            for f in _ENTITY_FILES.values()
        )
