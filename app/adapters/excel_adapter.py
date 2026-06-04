"""
Excel adapter — reads FR Y-14Q data from a multi-sheet workbook.

Sheet layout (configurable via ``sheet_map``):
    Facilities   → H1_Facilities
    Obligors     → H1_Obligors
    Transactions → H1_Transactions
    Comments     → H1_Comments
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

from app.adapters.base_adapter import BaseAdapter


_DEFAULT_SHEET_MAP: Dict[str, str] = {
    "facilities":   "H1_Facilities",
    "obligors":     "H1_Obligors",
    "transactions": "H1_Transactions",
    "comments":     "H1_Comments",
}


class ExcelAdapter(BaseAdapter):
    """Reads FR Y-14Q data from an Excel (.xlsx) workbook."""

    source_type = "excel"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self._workbook_path: str = config.get("excel_path", "")
        self._sheet_map: Dict[str, str] = {
            **_DEFAULT_SHEET_MAP,
            **config.get("sheet_map", {}),
        }
        self._cache: Dict[str, pd.DataFrame] = {}

    def _load(self, entity_type: str) -> pd.DataFrame:
        if entity_type in self._cache:
            return self._cache[entity_type]

        if not self._workbook_path:
            raise ValueError("ExcelAdapter: 'excel_path' not configured.")
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
            "ExcelAdapter loaded entity=%s sheet=%s rows=%d",
            entity_type, sheet, len(df),
        )
        return df

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
