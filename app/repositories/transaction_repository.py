"""Transaction repository — CSV data access."""

from __future__ import annotations

import pandas as pd

from app.repositories.base_repository import BaseRepository

SEARCH_COLUMNS = [
    "transaction_id", "obligor_id", "facility_id",
    "transaction_type", "status", "reference_number",
    "created_by", "approved_by",
]


class TransactionRepository(BaseRepository):
    """Data access for transactions.csv."""

    def _filename(self) -> str:
        return "transactions.csv"

    def _primary_key(self) -> str:
        return "transaction_id"

    def get_by_obligor(self, obligor_id: str) -> pd.DataFrame:
        """Return all transactions for *obligor_id*."""
        return self.filter_by("obligor_id", obligor_id)

    def get_by_facility(self, facility_id: str) -> pd.DataFrame:
        """Return all transactions belonging to *facility_id*."""
        return self.filter_by("facility_id", facility_id)

    def count_by_obligor(self, obligor_id: str) -> int:
        """Return the number of transactions for *obligor_id*."""
        return self.count_by("obligor_id", obligor_id)

    def get_counts_per_obligor(self) -> dict[str, int]:
        """
        Return a mapping of obligor_id → transaction count.

        Computed via groupby for O(n) performance.
        """
        df = self._load()
        return df.groupby("obligor_id").size().to_dict()

    def search_for_obligor(self, obligor_id: str, query: str = "") -> pd.DataFrame:
        """Return transactions for an obligor, filtered by optional *query*."""
        df = self.get_by_obligor(obligor_id)
        if not query:
            return df
        query = query.lower()
        mask = pd.Series([False] * len(df), index=df.index)
        for col in SEARCH_COLUMNS:
            if col in df.columns:
                mask = mask | df[col].str.lower().str.contains(query, na=False)
        return df.loc[mask]
