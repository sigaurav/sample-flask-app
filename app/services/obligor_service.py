"""
Obligor service — business logic for obligor queries.

Enriches obligor records with transaction counts to enable
the next level of drill-down from the obligor modal.
"""

from __future__ import annotations

from typing import Any

from app.models.obligor                      import Obligor
from app.repositories.obligor_repository     import ObligorRepository
from app.repositories.transaction_repository import TransactionRepository
from app.services.base_service               import BaseService


class ObligorService(BaseService):
    """Business logic for obligor-level operations."""

    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir)
        self._obligor_repo      = ObligorRepository(data_dir)
        self._transaction_repo  = TransactionRepository(data_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_obligors_for_facility(
        self,
        facility_id: str,
        search:      str = "",
        page:        int = 1,
        per_page:    int = 50,
    ) -> dict[str, Any]:
        """
        Return paginated, enriched obligors for *facility_id*.

        Enrichment adds *transaction_count* per obligor.

        Args:
            facility_id: Parent facility identifier.
            search:      Optional text filter.
            page:        1-based page number.
            per_page:    Rows per page.
        """
        df = self._obligor_repo.search_for_facility(facility_id, search)

        # Transaction-count lookup
        txn_counts = self._transaction_repo.get_counts_per_obligor()
        df = df.copy()
        df["transaction_count"] = (
            df["obligor_id"].map(txn_counts).fillna(0).astype(int)
        )

        total   = len(df)
        df_page = self._obligor_repo.paginate(df, page, per_page)

        records = [
            Obligor.from_dict(self._coerce_numerics(row)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]

        self.log.debug(
            "get_obligors_for_facility(%s) → %d/%d records",
            facility_id, len(records), total,
        )
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_all_obligors(
        self,
        search:   str = "",
        page:     int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """Return paginated, enriched obligors across all facilities."""
        from app.repositories.obligor_repository import SEARCH_COLUMNS
        df = self._obligor_repo.search(search, SEARCH_COLUMNS)

        txn_counts = self._transaction_repo.get_counts_per_obligor()
        df["transaction_count"] = df["obligor_id"].map(txn_counts).fillna(0).astype(int)

        total   = len(df)
        df_page = self._obligor_repo.paginate(df, page, per_page)
        records = [
            Obligor.from_dict(self._coerce_numerics(row)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_obligor_by_id(self, obligor_id: str) -> Obligor | None:
        """Return a single enriched Obligor or None."""
        raw = self._obligor_repo.get_by_id(obligor_id)
        if raw is None:
            return None
        raw["transaction_count"] = self._transaction_repo.count_by_obligor(obligor_id)
        return Obligor.from_dict(self._coerce_numerics(raw))

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_numerics(row: dict) -> dict:
        for field in ("credit_score", "exposure_amount", "outstanding_amount"):
            if field in row:
                try:
                    row[field] = float(row[field])
                except (ValueError, TypeError):
                    row[field] = 0.0
        return row
