"""
Facility service — business logic for facility queries.

Orchestrates FacilityRepository + ObligorRepository to enrich
facility records with computed obligor counts before returning them.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.models.facility                    import Facility
from app.repositories.facility_repository   import FacilityRepository
from app.repositories.obligor_repository    import ObligorRepository
from app.services.base_service              import BaseService


class FacilityService(BaseService):
    """Business logic for facility-level operations."""

    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir)
        self._facility_repo = FacilityRepository(data_dir)
        self._obligor_repo  = ObligorRepository(data_dir)

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_facilities(
        self,
        search:   str = "",
        page:     int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """
        Return a paginated, enriched list of facilities.

        Enrichment adds *obligor_count* to each facility record so the
        frontend can render it as a drill-down trigger without a second
        round-trip.

        Args:
            search:   Optional text to filter by (name, ID, RM, region …).
            page:     1-based page number.
            per_page: Rows per page.

        Returns:
            Dict with keys 'records' (list of dicts), 'total', 'page', 'per_page'.
        """
        df = self._facility_repo.get_all_searchable(search)

        # Build obligor-count lookup once (O(n) groupby)
        obligor_counts = self._obligor_repo.get_counts_per_facility()

        # Inject the count column before pagination
        df["obligor_count"] = df["facility_id"].map(obligor_counts).fillna(0).astype(int)

        total = len(df)

        # Paginate
        df_page = self._facility_repo.paginate(df, page, per_page)

        records = [
            Facility.from_dict(self._coerce_numerics(row)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]

        self.log.debug("get_facilities -> %d/%d records (page %d)", len(records), total, page)
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_facility_by_id(self, facility_id: str) -> Facility | None:
        """
        Return a single enriched Facility, or None if not found.

        Args:
            facility_id: The facility identifier (e.g. 'FAC-0042').
        """
        raw = self._facility_repo.get_by_id(facility_id)
        if raw is None:
            return None
        raw["obligor_count"] = self._obligor_repo.count_by_facility(facility_id)
        return Facility.from_dict(self._coerce_numerics(raw))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_numerics(row: dict) -> dict:
        """
        Convert string columns that are stored as str (from CSV) to their
        proper numeric types so Facility.from_dict() receives correct types.
        """
        numeric_fields = [
            "credit_limit", "outstanding_balance", "available_credit",
            "utilization_pct", "risk_score", "interest_rate",
        ]
        for field in numeric_fields:
            if field in row:
                try:
                    row[field] = float(row[field])
                except (ValueError, TypeError):
                    row[field] = 0.0
        return row
