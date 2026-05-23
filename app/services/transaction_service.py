"""
Transaction service — business logic for transaction queries.

Enriches transaction records with comment counts to enable
the deepest level of drill-down.
"""

from __future__ import annotations

from typing import Any

from app.models.transaction                  import Transaction
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.comment_repository     import CommentRepository
from app.services.base_service               import BaseService


class TransactionService(BaseService):
    """Business logic for transaction-level operations."""

    def __init__(self, data_dir: str) -> None:
        super().__init__(data_dir)
        self._transaction_repo = TransactionRepository(data_dir)
        self._comment_repo     = CommentRepository(data_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_transactions_for_obligor(
        self,
        obligor_id: str,
        search:     str = "",
        page:       int = 1,
        per_page:   int = 50,
    ) -> dict[str, Any]:
        """
        Return paginated, enriched transactions for *obligor_id*.

        Enrichment adds *comment_count* per transaction.
        """
        df = self._transaction_repo.search_for_obligor(obligor_id, search)

        comment_counts = self._comment_repo.get_counts_per_transaction()
        df = df.copy()
        df["comment_count"] = (
            df["transaction_id"].map(comment_counts).fillna(0).astype(int)
        )

        total   = len(df)
        df_page = self._transaction_repo.paginate(df, page, per_page)

        records = [
            Transaction.from_dict(self._coerce_numerics(row)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]

        self.log.debug(
            "get_transactions_for_obligor(%s) -> %d/%d records",
            obligor_id, len(records), total,
        )
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_all_transactions(
        self,
        search:   str = "",
        page:     int = 1,
        per_page: int = 50,
    ) -> dict[str, Any]:
        """Return paginated, enriched transactions across all obligors."""
        from app.repositories.transaction_repository import SEARCH_COLUMNS
        df = self._transaction_repo.search(search, SEARCH_COLUMNS)

        comment_counts = self._comment_repo.get_counts_per_transaction()
        df["comment_count"] = df["transaction_id"].map(comment_counts).fillna(0).astype(int)

        total   = len(df)
        df_page = self._transaction_repo.paginate(df, page, per_page)
        records = [
            Transaction.from_dict(self._coerce_numerics(row)).to_dict()
            for row in df_page.to_dict(orient="records")
        ]
        return {"records": records, "total": total, "page": page, "per_page": per_page}

    def get_comments_for_transaction(
        self,
        transaction_id: str,
        search:         str = "",
        page:           int = 1,
        per_page:       int = 50,
    ) -> dict[str, Any]:
        """Return paginated comments for *transaction_id*."""
        from app.models.comment import Comment

        df = self._comment_repo.search_for_transaction(transaction_id, search)

        total   = len(df)
        df_page = self._comment_repo.paginate(df, page, per_page)

        records = [
            Comment.from_dict(row).to_dict()
            for row in df_page.to_dict(orient="records")
        ]

        return {"records": records, "total": total, "page": page, "per_page": per_page}

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coerce_numerics(row: dict) -> dict:
        if "amount" in row:
            try:
                row["amount"] = float(row["amount"])
            except (ValueError, TypeError):
                row["amount"] = 0.0
        return row
