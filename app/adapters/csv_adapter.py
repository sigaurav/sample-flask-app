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

        fname = entity_type + ".csv"

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
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        df      = self._load(entity_type).copy()
        filters = dict(filters or {})

        fic_mis_date = filters.pop("_fic_mis_date", "")
        df = self._apply_context_filter(df, fic_mis_date)

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

        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            df = df[[c for c in cols if c in df.columns]]

        self.log.debug(
            "CSVAdapter.fetch entity=%s entity_key=%s rows_returned=%d",
            entity_type, entity_key, len(df),
        )
        return df

    def introspect_columns(self, entity_type: str) -> List[str]:
        cols = self._get_select_cols(entity_type)
        if cols != ["*"]:
            return cols
        path = os.path.join(self._data_dir, entity_type + ".csv")
        with open(path, newline="", encoding="utf-8") as f:
            return next(csv.reader(f))

    def health_check(self) -> bool:
        entities = self._config.get("ENTITIES", {})
        csv_entities = [e for e, cfg in entities.items() if cfg.get("source", "csv") == "csv"]
        return all(
            os.path.exists(os.path.join(self._data_dir, e + ".csv"))
            for e in csv_entities
        )
