"""
ReportingService — single data-access facade for all FR Y-14Q entities.

Follows the SantoshReference pattern:
  - Receives DataService (adapter registry) in __init__
  - Calls DataService.get_adapter() for every query — no direct CSV/DB reads here
  - Handles enrichment (cross-entity counts), coercion, and pagination in one place

Routes access this via current_app.reporting_service (registered in create_app).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from app.services.data_service  import DataService
from app.repositories.base_repository import BaseRepository
from app.models.facility    import Facility
from app.models.obligor     import Obligor
from app.models.transaction import Transaction
from app.models.comment     import Comment

log = logging.getLogger(__name__)

# ── Numeric fields per entity — coerced from CSV strings to float ─────────────
_FACILITY_NUMERIC    = ["credit_limit", "outstanding_balance", "available_credit",
                        "utilization_pct", "risk_score", "interest_rate"]
_OBLIGOR_NUMERIC     = ["credit_score", "exposure_amount", "outstanding_amount"]
_TRANSACTION_NUMERIC = ["amount"]


def _coerce(row: dict, numeric_fields: list[str]) -> dict:
    for f in numeric_fields:
        if f in row:
            try:
                row[f] = float(row[f])
            except (ValueError, TypeError):
                row[f] = 0.0
    return row


class ReportingService:
    """
    Single entry point for all read-oriented reporting queries.

    Uses DataService.get_adapter() for every data access so that
    the active source (csv / dremio / sqlserver) is transparent to callers.
    """

    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        log.info(
            "ReportingService initialised (primary adapter: %s)",
            next(iter(data_service.adapters), "none"),
        )

    # ── Facilities ─────────────────────────────────────────────────────────────

    def get_facilities(
        self, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch("facilities", filters={"quick_filter": search})

        # Enrich: obligor counts per facility
        obl_df = adapter.fetch("obligors")
        if not obl_df.empty:
            counts = obl_df.groupby("facility_id").size()
            df["obligor_count"] = df["facility_id"].map(counts).fillna(0).astype(int)
        else:
            df["obligor_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Facility.from_dict(_coerce(row, _FACILITY_NUMERIC)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        log.debug("get_facilities search=%r -> %d/%d", search, len(records), total)
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_facility_by_id(self, facility_id: str) -> Optional[Facility]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch("facilities")
        mask    = df["facility_id"] == str(facility_id)
        if not mask.any():
            return None
        row = df.loc[mask].iloc[0].to_dict()

        obl_df = adapter.fetch("obligors", entity_id=facility_id)
        row["obligor_count"] = len(obl_df)

        return Facility.from_dict(_coerce(row, _FACILITY_NUMERIC))

    # ── Obligors ───────────────────────────────────────────────────────────────

    def get_all_obligors(
        self, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch("obligors", filters={"quick_filter": search})

        # Enrich: transaction counts per obligor
        txn_df = adapter.fetch("transactions")
        if not txn_df.empty:
            counts = txn_df.groupby("obligor_id").size()
            df["transaction_count"] = df["obligor_id"].map(counts).fillna(0).astype(int)
        else:
            df["transaction_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Obligor.from_dict(_coerce(row, _OBLIGOR_NUMERIC)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_obligors_for_facility(
        self, facility_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch(
            "obligors",
            entity_id=facility_id,
            filters={"quick_filter": search},
        )

        txn_df = adapter.fetch("transactions")
        if not txn_df.empty:
            counts = txn_df.groupby("obligor_id").size()
            df["transaction_count"] = df["obligor_id"].map(counts).fillna(0).astype(int)
        else:
            df["transaction_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Obligor.from_dict(_coerce(row, _OBLIGOR_NUMERIC)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_obligor_by_id(self, obligor_id: str) -> Optional[Obligor]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch("obligors")
        mask    = df["obligor_id"] == str(obligor_id)
        if not mask.any():
            return None
        row = df.loc[mask].iloc[0].to_dict()

        txn_df = adapter.fetch("transactions", entity_id=obligor_id)
        row["transaction_count"] = len(txn_df)

        return Obligor.from_dict(_coerce(row, _OBLIGOR_NUMERIC))

    # ── Transactions ───────────────────────────────────────────────────────────

    def get_all_transactions(
        self, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch("transactions", filters={"quick_filter": search})

        cmt_df = adapter.fetch("comments")
        if not cmt_df.empty:
            counts = cmt_df.groupby("transaction_id").size()
            df["comment_count"] = df["transaction_id"].map(counts).fillna(0).astype(int)
        else:
            df["comment_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Transaction.from_dict(_coerce(row, _TRANSACTION_NUMERIC)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_transactions_for_obligor(
        self, obligor_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch(
            "transactions",
            entity_id=obligor_id,
            filters={"quick_filter": search},
        )

        cmt_df = adapter.fetch("comments")
        if not cmt_df.empty:
            counts = cmt_df.groupby("transaction_id").size()
            df["comment_count"] = df["transaction_id"].map(counts).fillna(0).astype(int)
        else:
            df["comment_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Transaction.from_dict(_coerce(row, _TRANSACTION_NUMERIC)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_comments_for_transaction(
        self, transaction_id: str, search: str = "", page: int = 1, per_page: int = 50
    ) -> dict[str, Any]:
        adapter = self._data_service.get_adapter()
        df      = adapter.fetch(
            "comments",
            entity_id=transaction_id,
            filters={"quick_filter": search},
        )

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = [
            Comment.from_dict(row).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}
