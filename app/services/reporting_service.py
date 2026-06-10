"""
ReportingService — single data-access facade for all FR Y-14Q entities.

Follows the SantoshReference pattern:
  - Receives DataService (adapter registry) in __init__
  - Calls DataService.get_adapter_for_entity() for every query so that each
    entity type can route to its own source (csv / dremio / sqlserver)
  - Uses app/schemas/ as single source of truth for field selection and coercion

Routes access this via current_app.reporting_service (registered in create_app).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import pandas as pd

from app.services.data_service        import DataService
from app.repositories.base_repository import BaseRepository
from app.schemas                       import get_api_fields, get_numeric_fields

log = logging.getLogger(__name__)


def _schema_coerce_records(df: pd.DataFrame, entity_type: str) -> list[dict]:
    """
    Filter DataFrame to schema-declared fields and coerce numeric columns to float.

    Fields in the DataFrame but not in the schema are silently dropped (this is
    intentional — it excludes SOR, FIC_MIS_DATE, and any source columns not yet
    promoted to the schema).  Schema fields absent from the DataFrame are also
    silently skipped (graceful — handles computed fields added downstream).
    """
    api_fields     = get_api_fields(entity_type)
    numeric_fields = set(get_numeric_fields(entity_type))
    present        = [f for f in api_fields if f in df.columns]
    records        = []
    for row in df[present].to_dict(orient="records"):
        for f in numeric_fields:
            if f in row:
                try:
                    row[f] = float(row[f])
                except (ValueError, TypeError):
                    row[f] = 0.0
        records.append(row)
    return records


class ReportingService:
    """
    Single entry point for all read-oriented reporting queries.

    Each entity resolves its own adapter via DataService.get_adapter_for_entity()
    so that different tables can live on different sources transparently.
    """

    def __init__(self, data_service: DataService) -> None:
        self._data_service = data_service
        log.info(
            "ReportingService initialised (primary adapter: %s)",
            next(iter(data_service.adapters), "none"),
        )

    # ── Facilities ─────────────────────────────────────────────────────────────

    def get_facilities(
        self, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        fac_adapter = self._data_service.get_adapter_for_entity("facilities")
        obl_adapter = self._data_service.get_adapter_for_entity("obligors")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = fac_adapter.fetch("facilities", filters={"quick_filter": search, **ctx})

        obl_df = obl_adapter.fetch("obligors", filters=ctx)
        if not obl_df.empty:
            counts = obl_df.groupby("facility_id").size()
            df["obligor_count"] = df["facility_id"].map(counts).fillna(0).astype(int)
        else:
            df["obligor_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "facilities")
        log.debug("get_facilities search=%r sor=%r -> %d/%d", search, sor, len(records), total)
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_facility_by_id(
        self, facility_id: str, sor: str = "", fic_mis_date: str = ""
    ) -> Optional[dict]:
        fac_adapter = self._data_service.get_adapter_for_entity("facilities")
        obl_adapter = self._data_service.get_adapter_for_entity("obligors")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = fac_adapter.fetch("facilities", filters=ctx)
        mask = df["facility_id"] == str(facility_id)
        if not mask.any():
            return None

        row_df = df.loc[mask].copy()
        obl_df = obl_adapter.fetch("obligors", entity_id=facility_id, filters=ctx)
        row_df["obligor_count"] = len(obl_df)

        records = _schema_coerce_records(row_df, "facilities")
        return records[0] if records else None

    # ── Obligors ───────────────────────────────────────────────────────────────

    def get_all_obligors(
        self, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        obl_adapter = self._data_service.get_adapter_for_entity("obligors")
        txn_adapter = self._data_service.get_adapter_for_entity("transactions")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = obl_adapter.fetch("obligors", filters={"quick_filter": search, **ctx})

        txn_df = txn_adapter.fetch("transactions", filters=ctx)
        if not txn_df.empty:
            counts = txn_df.groupby("obligor_id").size()
            df["transaction_count"] = df["obligor_id"].map(counts).fillna(0).astype(int)
        else:
            df["transaction_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "obligors")
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_obligors_for_facility(
        self, facility_id: str, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        obl_adapter = self._data_service.get_adapter_for_entity("obligors")
        txn_adapter = self._data_service.get_adapter_for_entity("transactions")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = obl_adapter.fetch(
            "obligors",
            entity_id=facility_id,
            filters={"quick_filter": search, **ctx},
        )

        txn_df = txn_adapter.fetch("transactions", filters=ctx)
        if not txn_df.empty:
            counts = txn_df.groupby("obligor_id").size()
            df["transaction_count"] = df["obligor_id"].map(counts).fillna(0).astype(int)
        else:
            df["transaction_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "obligors")
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_obligor_by_id(
        self, obligor_id: str, sor: str = "", fic_mis_date: str = ""
    ) -> Optional[dict]:
        obl_adapter = self._data_service.get_adapter_for_entity("obligors")
        txn_adapter = self._data_service.get_adapter_for_entity("transactions")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = obl_adapter.fetch("obligors", filters=ctx)
        mask = df["obligor_id"] == str(obligor_id)
        if not mask.any():
            return None

        row_df = df.loc[mask].copy()
        txn_df = txn_adapter.fetch("transactions", entity_id=obligor_id, filters=ctx)
        row_df["transaction_count"] = len(txn_df)

        records = _schema_coerce_records(row_df, "obligors")
        return records[0] if records else None

    # ── Transactions ───────────────────────────────────────────────────────────

    def get_all_transactions(
        self, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        txn_adapter = self._data_service.get_adapter_for_entity("transactions")
        cmt_adapter = self._data_service.get_adapter_for_entity("comments")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = txn_adapter.fetch("transactions", filters={"quick_filter": search, **ctx})

        cmt_df = cmt_adapter.fetch("comments", filters=ctx)
        if not cmt_df.empty:
            counts = cmt_df.groupby("transaction_id").size()
            df["comment_count"] = df["transaction_id"].map(counts).fillna(0).astype(int)
        else:
            df["comment_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "transactions")
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_transactions_for_obligor(
        self, obligor_id: str, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        txn_adapter = self._data_service.get_adapter_for_entity("transactions")
        cmt_adapter = self._data_service.get_adapter_for_entity("comments")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = txn_adapter.fetch(
            "transactions",
            entity_id=obligor_id,
            filters={"quick_filter": search, **ctx},
        )

        cmt_df = cmt_adapter.fetch("comments", filters=ctx)
        if not cmt_df.empty:
            counts = cmt_df.groupby("transaction_id").size()
            df["comment_count"] = df["transaction_id"].map(counts).fillna(0).astype(int)
        else:
            df["comment_count"] = 0

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "transactions")
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_comments_for_transaction(
        self, transaction_id: str, search: str = "", page: int = 1, per_page: int = 50,
        sor: str = "", fic_mis_date: str = "",
    ) -> dict[str, Any]:
        cmt_adapter = self._data_service.get_adapter_for_entity("comments")
        ctx  = {"_sor": sor, "_fic_mis_date": fic_mis_date}
        df   = cmt_adapter.fetch(
            "comments",
            entity_id=transaction_id,
            filters={"quick_filter": search, **ctx},
        )

        total   = len(df)
        df_page = BaseRepository.paginate(df, page, per_page)
        records = _schema_coerce_records(df_page, "comments")
        return {"records": records, "total": total, "page": page, "per_page": per_page}
