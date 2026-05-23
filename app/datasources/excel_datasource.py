"""
Excel data source — reads FR Y-14Q data from a multi-sheet workbook.

Sheet layout (configurable via ``sheet_map``):
    Facilities   → h1_facilities sheet
    Obligors     → h1_obligors sheet
    Transactions → h1_transactions sheet
    Comments     → h1_comments sheet

Phase 1: functional for single-workbook scenarios.
Phase 2: extend with workbook-per-schedule support and streaming reads.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

from app.datasources.base_datasource import BaseDataSource


_DEFAULT_SHEET_MAP: Dict[str, str] = {
    "facilities":   "H1_Facilities",
    "obligors":     "H1_Obligors",
    "transactions": "H1_Transactions",
    "comments":     "H1_Comments",
}


class ExcelDataSource(BaseDataSource):
    """
    Reads FR Y-14Q data from an Excel (.xlsx) workbook.

    Configure via:
        config = {
            'excel_path': '/path/to/FR_Y14Q_Data.xlsx',
            'sheet_map':  {'facilities': 'Sheet1', ...},   # optional override
        }
    """

    source_type = "excel"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._workbook_path: str       = config.get("excel_path", "")
        self._sheet_map:     Dict[str, str] = {
            **_DEFAULT_SHEET_MAP,
            **config.get("sheet_map", {}),
        }
        self._cache: Dict[str, pd.DataFrame] = {}

    # ── Internal loader ───────────────────────────────────────────────────────

    def _load(self, entity_type: str) -> pd.DataFrame:
        if entity_type in self._cache:
            return self._cache[entity_type]

        if not self._workbook_path:
            raise ValueError("ExcelDataSource: 'excel_path' not configured.")
        if not os.path.exists(self._workbook_path):
            raise FileNotFoundError(f"Workbook not found: {self._workbook_path}")

        sheet = self._sheet_map.get(entity_type)
        if not sheet:
            raise ValueError(f"No sheet mapping for entity_type '{entity_type}'")

        df = pd.read_excel(
            self._workbook_path,
            sheet_name=sheet,
            dtype=str,
            engine="openpyxl",
        ).fillna("")

        self._cache[entity_type] = df
        self.log.debug(
            "ExcelDataSource loaded entity=%s sheet=%s rows=%d",
            entity_type, sheet, len(df),
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
        df = self._load(entity_type).copy()

        if filters:
            col_filters = filters.get("col_filters", {})
            if col_filters:
                df = self._apply_col_filters(df, col_filters)
            quick = filters.get("quick_filter", "")
            if quick:
                df = self._apply_quick_filter(df, quick)

        df = self._apply_sorts(df, sorts or [])
        return df

    def health_check(self) -> bool:
        return bool(self._workbook_path) and os.path.exists(self._workbook_path)
