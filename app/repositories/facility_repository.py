"""Facility repository — CSV data access."""

from __future__ import annotations

import pandas as pd

from app.repositories.base_repository import BaseRepository

SEARCH_COLUMNS = [
    "facility_id", "facility_name", "facility_type",
    "status", "risk_rating", "relationship_manager", "region", "country",
]


class FacilityRepository(BaseRepository):
    """Data access for facilities.csv."""

    def _filename(self) -> str:
        return "facilities.csv"

    def _primary_key(self) -> str:
        return "facility_id"

    def get_all_searchable(self, query: str = "") -> pd.DataFrame:
        """
        Return all facilities optionally filtered by *query*.

        Searches across: ID, name, type, status, rating, RM, region, country.
        """
        return self.search(query, SEARCH_COLUMNS)

    def get_facility_ids(self) -> list[str]:
        """Return a sorted list of all facility IDs."""
        return sorted(self._load()["facility_id"].tolist())
