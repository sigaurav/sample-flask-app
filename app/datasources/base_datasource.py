"""
Abstract base class for all FR Y-14Q data sources.

Concrete implementations must override ``fetch`` and ``health_check``.
Shared pandas filtering utilities live here so every source benefits
without duplicating logic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd


class BaseDataSource(ABC):
    """
    Unified data retrieval interface.

    Each subclass targets one physical source (CSV, Excel, Dremio,
    SQL Server).  Controllers and services depend only on this interface,
    keeping source mechanics encapsulated.
    """

    #: Identifies the source type in export job records and log output.
    source_type: str = "base"

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def fetch(
        self,
        entity_type: str,
        entity_id:   Optional[str]  = None,
        filters:     Optional[Dict] = None,
        sorts:       Optional[List] = None,
    ) -> pd.DataFrame:
        """
        Retrieve data for *entity_type*, optionally scoped and filtered.

        Args:
            entity_type: One of ``facilities``, ``obligors``,
                         ``transactions``, ``comments``.
            entity_id:   Parent entity ID (e.g., facility_id when fetching
                         obligors for a specific facility).
            filters:     Dict with keys ``col_filters`` (field→{op,val})
                         and ``quick_filter`` (plain text search).
            sorts:       List of ``{field, dir}`` dicts, in priority order.

        Returns:
            DataFrame with raw string columns matching the CSV schema.
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the underlying source is reachable."""

    # ── Shared pandas helpers (available to all subclasses) ───────────────────

    def _apply_col_filters(self, df: pd.DataFrame, col_filters: Dict) -> pd.DataFrame:
        """Apply per-column filter specs (mirrors frontend _applyFilters logic)."""
        for field, spec in col_filters.items():
            if field not in df.columns:
                continue
            op  = spec.get("op", "contains")
            val = str(spec.get("val", "")).strip()
            if not val:
                continue

            if op == "contains":
                mask = df[field].astype(str).str.lower().str.contains(val.lower(), na=False)
            elif op == "equals":
                mask = df[field].astype(str).str.lower() == val.lower()
            elif op == "startsWith":
                mask = df[field].astype(str).str.lower().str.startswith(val.lower(), na=False)
            elif op in ("numEq", "gt", "gte", "lt", "lte"):
                nums = pd.to_numeric(df[field], errors="coerce")
                v    = float(val)
                ops  = {"numEq": nums == v, "gt": nums > v, "gte": nums >= v,
                        "lt": nums < v, "lte": nums <= v}
                mask = ops[op]
            elif op in ("dateEq", "dateBefore", "dateAfter"):
                dates = pd.to_datetime(df[field], errors="coerce")
                ref   = pd.to_datetime(val, errors="coerce")
                if pd.isna(ref):
                    continue
                if op == "dateEq":
                    mask = dates.dt.date == ref.date()
                elif op == "dateBefore":
                    mask = dates < ref
                else:
                    mask = dates > ref
            elif op == "inList":
                # Categorical: val is comma-separated list of accepted values
                accepted = {v.strip().lower() for v in val.split(",")}
                mask = df[field].astype(str).str.lower().isin(accepted)
            else:
                continue

            df = df[mask].reset_index(drop=True)

        return df

    def _apply_quick_filter(
        self, df: pd.DataFrame, quick: str,
        cols: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Case-insensitive substring search across *cols* (defaults to all)."""
        if not quick or df.empty:
            return df
        q    = quick.strip().lower()
        cols = cols or list(df.columns)
        mask = df[cols].apply(
            lambda c: c.astype(str).str.lower().str.contains(q, na=False)
        ).any(axis=1)
        return df[mask].reset_index(drop=True)

    def _apply_sorts(self, df: pd.DataFrame, sorts: List[Dict]) -> pd.DataFrame:
        """Apply a multi-column sort spec from the frontend sort state."""
        if not sorts or df.empty:
            return df
        fields     = [s["field"]             for s in sorts if s.get("field") in df.columns]
        ascending  = [s.get("dir", "asc") == "asc" for s in sorts if s.get("field") in df.columns]
        if fields:
            df = df.sort_values(by=fields, ascending=ascending, ignore_index=True)
        return df
