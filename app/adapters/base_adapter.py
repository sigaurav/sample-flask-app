"""
Abstract base class for all FR Y-14Q data adapters.

Concrete implementations must override ``fetch`` and ``health_check``.
Shared pandas filtering utilities live here so every adapter benefits
without duplicating logic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import pandas as pd


class BaseAdapter(ABC):
    """
    Unified data retrieval interface.

    Each subclass targets one physical source (CSV, Dremio,
    SQL Server, Teradata).  Controllers and services depend only on this interface,
    keeping source mechanics encapsulated.
    """

    #: Identifies the source type in export job records and log output.
    source_type: str = "base"

    def __init__(self, config: Dict[str, Any]) -> None:
        self._config = config
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def _get_select_cols(self, entity_type: str) -> List[str]:
        """Return the configured column list, or ['*'] when none is set."""
        return self._config.get("ENTITIES", {}).get(entity_type, {}).get("columns", ["*"])

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def fetch(
        self,
        entity_type: str,
        entity_key:  Optional[Dict[str, str]] = None,
        filters:     Optional[Dict]           = None,
        sorts:       Optional[List]           = None,
    ) -> pd.DataFrame:
        """Retrieve data for *entity_type*, optionally scoped and filtered.

        *entity_key* is a field→value dict identifying the parent scope, e.g.
        ``{"facility_id": "FAC001"}`` for child entities or a composite key
        ``{"facility_id": "FAC001", "region_code": "US"}``.  Pass ``None``
        to fetch all rows (subject to context filters).
        """

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if the underlying source is reachable."""

    @abstractmethod
    def introspect_columns(self, entity_type: str) -> List[str]:
        """Return all column names present in the source for *entity_type*.

        Used exclusively by ``scripts/refresh_schema.py`` to detect drift
        between the live source and the JSON schema files.

        Implementation guide per source type:
        - CSVAdapter    → read the header row of the entity's CSV file.
        - DremioAdapter → execute:
            SELECT COLUMN_NAME
            FROM   INFORMATION_SCHEMA."COLUMNS"
            WHERE  TABLE_SCHEMA = '<schema>'
            AND    TABLE_NAME   = '<table>'
            ORDER  BY ORDINAL_POSITION
        - SQLServerAdapter → execute:
            SELECT COLUMN_NAME
            FROM   INFORMATION_SCHEMA.COLUMNS
            WHERE  TABLE_SCHEMA = '<schema>'
            AND    TABLE_NAME   = '<table>'
            ORDER  BY ORDINAL_POSITION
        """

    # ── Shared pandas helpers ─────────────────────────────────────────────────

    def _apply_col_filters(self, df: pd.DataFrame, col_filters: Dict) -> pd.DataFrame:
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
        if not quick or df.empty:
            return df
        q    = quick.strip().lower()
        cols = cols or list(df.columns)
        mask = df[cols].apply(
            lambda c: c.astype(str).str.lower().str.contains(q, na=False)
        ).any(axis=1)
        return df[mask].reset_index(drop=True)

    def _apply_context_filter(
        self, df: pd.DataFrame, sor: str, fic_mis_date: str
    ) -> pd.DataFrame:
        # SOR column is FACLTY_SOR_ID; match case-insensitively in case source differs
        sor_col = next((c for c in df.columns if c.upper() == "FACLTY_SOR_ID"), None)
        if sor and sor_col:
            df = df[df[sor_col] == sor].reset_index(drop=True)
        # Date column is PERIOD_DT (lowercase period_dt in obligations table)
        date_col = next((c for c in df.columns if c.upper() == "PERIOD_DT"), None)
        if fic_mis_date and date_col:
            try:
                target = pd.to_datetime(fic_mis_date).date()
                parsed = pd.to_datetime(df[date_col], errors="coerce").dt.date
                df = df[parsed == target].reset_index(drop=True)
            except Exception:
                df = df[df[date_col] == fic_mis_date].reset_index(drop=True)
        return df

    def _apply_sorts(self, df: pd.DataFrame, sorts: List[Dict]) -> pd.DataFrame:
        if not sorts or df.empty:
            return df
        fields    = [s["field"]                    for s in sorts if s.get("field") in df.columns]
        ascending = [s.get("dir", "asc") == "asc"  for s in sorts if s.get("field") in df.columns]
        if fields:
            df = df.sort_values(by=fields, ascending=ascending, ignore_index=True)
        return df
