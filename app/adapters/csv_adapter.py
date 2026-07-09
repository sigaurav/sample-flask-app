"""
CSV adapter — reads authoritative data from the flat-file store in DATA_DIR.

This is the Phase 1 default source type used for all FR Y-14Q workflows
when Dremio or SQL Server connectivity is not configured.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

        period_dt = filters.pop("_period_dt", "")
        df = self._apply_context_filter(df, period_dt)

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
    

    # Rolando's addition
    def fetch_lookup(self, entity_type: str, required_cols: Optional[List[str]] = None) -> pd.DataFrame:
        """
        Load a simple lookup CSV from DATA_DIR without schema/date/context logic.

        Example:
            Investigation_assignees.csv
            
        """
        df = self._load(entity_type).copy()
        required_cols = required_cols or []
        if required_cols is None:
            raise ValueError("Required columns cannot be None")
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Lookup field '{col}' not found in entity '{entity_type}'")
        return df[required_cols].drop_duplicates().reset_index(drop=True)

    def push(self, entity_type: str, data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> int:
        """
        Append record(s) to entity_type's CSV file (and update the in-memory
        cache).  Returns the number of rows written.
        """
        if not data:
            return 0

        rows = data if isinstance(data, list) else [data]
        if not rows:
            return 0

        df = self._load(entity_type)
        new_rows = pd.DataFrame(rows)
        for col in df.columns:
            if col not in new_rows.columns:
                new_rows[col] = ""
        new_rows = new_rows[list(df.columns)].astype(str)

        combined = pd.concat([df, new_rows], ignore_index=True)
        self._cache[entity_type] = combined

        path = os.path.join(self._data_dir, entity_type + ".csv")
        combined.to_csv(path, index=False)

        return len(new_rows)

    def export_reference_records_to_csv(
        self,
        entity_type: str,
        records: List[dict],
        origin_pk_columns: List[str],
        reference_pk_columns: List[str],
        output_file: str,
        selected_columns: Optional[List[str]] = None,
        export_folder: Optional[str] = None,
    ) -> str:
        """
        Export rows from entity_type's CSV whose reference_pk_columns values
        match the origin_pk_columns values found in the incoming records.
        """
        if not records:
            raise ValueError("No records provided for export.")
        if not origin_pk_columns or not reference_pk_columns:
            raise ValueError("Origin and reference PK columns must be provided.")
        if len(origin_pk_columns) != len(reference_pk_columns):
            raise ValueError("origin_pk_columns and reference_pk_columns must be the same length.")

        df = self._load(entity_type).copy()
        if selected_columns:
            missing = [c for c in selected_columns if c not in df.columns]
            if missing:
                raise ValueError(f"Unknown columns for entity '{entity_type}': {missing}")
            df = df[selected_columns]

        missing_ref = [c for c in reference_pk_columns if c not in df.columns]
        if missing_ref:
            raise ValueError(f"Reference PK column(s) not found on '{entity_type}': {missing_ref}")

        seen_keys = set()
        key_tuples = []
        for record in records:
            row_key = tuple(str(record.get(col, "")).strip() for col in origin_pk_columns)
            if all(row_key) and row_key not in seen_keys:
                seen_keys.add(row_key)
                key_tuples.append(row_key)

        if not key_tuples:
            raise ValueError("No valid PK records found.")

        mask = df[reference_pk_columns].astype(str).apply(tuple, axis=1).isin(key_tuples)
        matched = df[mask]

        export_dir = Path(export_folder or self._config.get("EXPORT_DIR", "exports"))
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_stem = Path(output_file).stem
        file_suffix = Path(output_file).suffix or ".csv"
        output_path = export_dir / f"{file_stem}_{timestamp}{file_suffix}"
        matched.to_csv(output_path, index=False)
        return str(output_path.resolve())

