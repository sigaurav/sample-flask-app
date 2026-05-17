"""
Export service — generates CSV, Excel, and Parquet downloads.

All export methods return an (io.BytesIO, mimetype, filename) tuple
so that controllers can call flask.send_file() directly.
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import pandas as pd

from app.repositories.facility_repository    import FacilityRepository
from app.repositories.obligor_repository     import ObligorRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.comment_repository     import CommentRepository
from app.services.base_service               import BaseService

log = logging.getLogger(__name__)

# MIME types
_MIME = {
    "csv":     "text/csv",
    "excel":   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "parquet": "application/octet-stream",
}

# File extensions
_EXT = {"csv": ".csv", "excel": ".xlsx", "parquet": ".parquet"}


class ExportService(BaseService):
    """
    Produces downloadable exports for every drill-down level.

    Supports three output formats:
        'csv'     → comma-separated values
        'excel'   → Excel workbook (.xlsx via openpyxl)
        'parquet' → Apache Parquet binary (.parquet via pyarrow)
    """

    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir)
        self._facility_repo    = FacilityRepository(data_dir)
        self._obligor_repo     = ObligorRepository(data_dir)
        self._transaction_repo = TransactionRepository(data_dir)
        self._comment_repo     = CommentRepository(data_dir)

    # ── Public export methods ─────────────────────────────────────────────────

    def export_facilities(self, fmt: str = "csv") -> tuple[io.BytesIO, str, str]:
        """Export the full facilities dataset."""
        df = self._facility_repo.get_all()
        return self._build(df, fmt, "facilities")

    def export_all_obligors(self, fmt: str = "csv") -> tuple[io.BytesIO, str, str]:
        """Export the full obligors dataset."""
        df = self._obligor_repo.get_all()
        return self._build(df, fmt, "obligors")

    def export_all_transactions(self, fmt: str = "csv") -> tuple[io.BytesIO, str, str]:
        """Export the full transactions dataset."""
        df = self._transaction_repo.get_all()
        return self._build(df, fmt, "transactions")

    def export_obligors_for_facility(
        self, facility_id: str, fmt: str = "csv"
    ) -> tuple[io.BytesIO, str, str]:
        """Export obligors belonging to *facility_id*."""
        df = self._obligor_repo.get_by_facility(facility_id)
        return self._build(df, fmt, f"obligors_{facility_id}")

    def export_transactions_for_obligor(
        self, obligor_id: str, fmt: str = "csv"
    ) -> tuple[io.BytesIO, str, str]:
        """Export transactions belonging to *obligor_id*."""
        df = self._transaction_repo.get_by_obligor(obligor_id)
        return self._build(df, fmt, f"transactions_{obligor_id}")

    def export_comments_for_transaction(
        self, transaction_id: str, fmt: str = "csv"
    ) -> tuple[io.BytesIO, str, str]:
        """Export comments belonging to *transaction_id*."""
        df = self._comment_repo.get_by_transaction(transaction_id)
        return self._build(df, fmt, f"comments_{transaction_id}")

    # ── Private helpers ────────────────────────────────────────────────────────

    def _build(
        self, df: pd.DataFrame, fmt: str, stem: str
    ) -> tuple[io.BytesIO, str, str]:
        """
        Serialize *df* into *fmt* and return (buffer, mimetype, filename).

        Args:
            df:   DataFrame to export.
            fmt:  One of 'csv', 'excel', 'parquet'.
            stem: Base name for the download file (without extension).
        """
        fmt = fmt.lower()
        if fmt not in _MIME:
            raise ValueError(f"Unsupported export format '{fmt}'. Choose: csv, excel, parquet")

        buf = io.BytesIO()

        if fmt == "csv":
            csv_bytes = df.to_csv(index=False).encode("utf-8")
            buf.write(csv_bytes)

        elif fmt == "excel":
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="Data")

        elif fmt == "parquet":
            df.to_parquet(buf, index=False, engine="pyarrow")

        buf.seek(0)
        filename = stem + _EXT[fmt]
        log.info("Exported %d rows as %s → %s", len(df), fmt.upper(), filename)
        return buf, _MIME[fmt], filename
