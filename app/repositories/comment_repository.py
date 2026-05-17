"""Comment repository — CSV data access."""

from __future__ import annotations

import pandas as pd

from app.repositories.base_repository import BaseRepository

SEARCH_COLUMNS = [
    "comment_id", "transaction_id", "obligor_id",
    "comment_type", "author", "department", "status", "priority",
]


class CommentRepository(BaseRepository):
    """Data access for comments.csv."""

    def _filename(self) -> str:
        return "comments.csv"

    def _primary_key(self) -> str:
        return "comment_id"

    def get_by_transaction(self, transaction_id: str) -> pd.DataFrame:
        """Return all comments for *transaction_id*."""
        return self.filter_by("transaction_id", transaction_id)

    def count_by_transaction(self, transaction_id: str) -> int:
        """Return the number of comments for *transaction_id*."""
        return self.count_by("transaction_id", transaction_id)

    def get_counts_per_transaction(self) -> dict[str, int]:
        """Return a mapping of transaction_id → comment count."""
        df = self._load()
        return df.groupby("transaction_id").size().to_dict()

    def search_for_transaction(self, transaction_id: str, query: str = "") -> pd.DataFrame:
        """Return comments for a transaction, filtered by optional *query*."""
        df = self.get_by_transaction(transaction_id)
        if not query:
            return df
        query = query.lower()
        mask = pd.Series([False] * len(df), index=df.index)
        for col in SEARCH_COLUMNS:
            if col in df.columns:
                mask = mask | df[col].str.lower().str.contains(query, na=False)
        return df.loc[mask]
