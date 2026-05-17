"""Obligor repository — CSV data access."""

from __future__ import annotations

import pandas as pd

from app.repositories.base_repository import BaseRepository

SEARCH_COLUMNS = [
    "obligor_id", "obligor_name", "obligor_type",
    "tin", "industry", "sub_industry", "country",
    "status", "risk_grade",
]


class ObligorRepository(BaseRepository):
    """Data access for obligors.csv."""

    def _filename(self) -> str:
        return "obligors.csv"

    def _primary_key(self) -> str:
        return "obligor_id"

    def get_by_facility(self, facility_id: str) -> pd.DataFrame:
        """Return all obligors belonging to *facility_id*."""
        return self.filter_by("facility_id", facility_id)

    def count_by_facility(self, facility_id: str) -> int:
        """Return the number of obligors in *facility_id*."""
        return self.count_by("facility_id", facility_id)

    def get_counts_per_facility(self) -> dict[str, int]:
        """
        Return a mapping of facility_id → obligor count.

        Computed once using pandas groupby for O(n) performance.
        """
        df = self._load()
        counts = df.groupby("facility_id").size()
        return counts.to_dict()

    def search_for_facility(self, facility_id: str, query: str = "") -> pd.DataFrame:
        """Return obligors for a facility, filtered by optional search *query*."""
        df = self.get_by_facility(facility_id)
        if not query:
            return df
        query = query.lower()
        mask = pd.Series([False] * len(df), index=df.index)
        for col in SEARCH_COLUMNS:
            if col in df.columns:
                mask = mask | df[col].str.lower().str.contains(query, na=False)
        return df.loc[mask]
