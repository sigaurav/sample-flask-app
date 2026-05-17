"""
Abstract base repository.

Subclasses only need to supply:
  - _filename()     → str  (CSV filename inside DATA_DIR)
  - _primary_key()  → str  (column name of the unique row identifier)

All filtering, searching, and pagination helpers are inherited.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Optional

import pandas as pd

log = logging.getLogger(__name__)


class BaseRepository(ABC):
    """
    Generic CSV-backed repository with in-memory caching.

    The DataFrame is loaded once on first access and kept in memory
    for the lifetime of the process.  For a production DB-backed
    implementation, override _load() to issue SQL queries instead.
    """

    def __init__(self, data_dir: str) -> None:
        """
        Args:
            data_dir: Absolute path to the directory containing CSV files.
        """
        self._data_dir: str             = data_dir
        self._df:       pd.DataFrame | None = None

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def _filename(self) -> str:
        """Return the CSV filename (not full path) for this repository."""

    @abstractmethod
    def _primary_key(self) -> str:
        """Return the column name that uniquely identifies a row."""

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load(self) -> pd.DataFrame:
        """Lazy-load and cache the CSV into a DataFrame."""
        if self._df is None:
            path = os.path.join(self._data_dir, self._filename())
            if not os.path.exists(path):
                raise FileNotFoundError(
                    f"Data file not found: {path}. "
                    "Run 'python generate_data.py' first."
                )
            self._df = pd.read_csv(path, dtype=str)
            log.debug("Loaded %d rows from %s", len(self._df), self._filename())
        return self._df

    def invalidate_cache(self) -> None:
        """Force a reload on the next access (useful in tests)."""
        self._df = None

    # ── Public CRUD helpers ───────────────────────────────────────────────────

    def get_all(self) -> pd.DataFrame:
        """Return a defensive copy of the full dataset."""
        return self._load().copy()

    def get_by_id(self, id_value: str) -> Optional[dict]:
        """
        Return a single record as a dict, or None if not found.

        Args:
            id_value: Value to match against the primary-key column.
        """
        df     = self._load()
        pk_col = self._primary_key()
        mask   = df[pk_col] == str(id_value)
        result = df.loc[mask]
        if result.empty:
            return None
        return result.iloc[0].to_dict()

    def filter_by(self, column: str, value: Any) -> pd.DataFrame:
        """
        Return rows where *column* equals *value*.

        Args:
            column: DataFrame column name.
            value:  Value to match (coerced to str for CSV-backed repos).
        """
        df = self._load()
        if column not in df.columns:
            log.warning("filter_by: column '%s' not found in %s", column, self._filename())
            return df.iloc[0:0]
        return df.loc[df[column] == str(value)].copy()

    def count(self) -> int:
        """Return total number of rows."""
        return len(self._load())

    def count_by(self, column: str, value: Any) -> int:
        """Return the number of rows where *column* equals *value*."""
        return len(self.filter_by(column, value))

    # ── Search / pagination helpers ───────────────────────────────────────────

    def search(self, query: str, columns: list[str]) -> pd.DataFrame:
        """
        Case-insensitive substring search across the given *columns*.

        Args:
            query:   Search string.
            columns: List of column names to search within.
        """
        if not query:
            return self.get_all()

        df    = self._load()
        query = query.lower()

        mask  = pd.Series([False] * len(df), index=df.index)
        for col in columns:
            if col in df.columns:
                mask = mask | df[col].str.lower().str.contains(query, na=False)

        return df.loc[mask].copy()

    @staticmethod
    def paginate(df: pd.DataFrame, page: int, per_page: int) -> pd.DataFrame:
        """
        Slice *df* to the requested page.

        Args:
            df:       DataFrame to paginate (already filtered/sorted).
            page:     1-based page number.
            per_page: Rows per page.
        """
        page     = max(1, page)
        per_page = max(1, per_page)
        start    = (page - 1) * per_page
        return df.iloc[start : start + per_page]
