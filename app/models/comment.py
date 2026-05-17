"""Comment domain model."""

from dataclasses import dataclass


@dataclass
class Comment:
    """Analyst/operations comment attached to a transaction."""

    comment_id:     str
    transaction_id: str
    obligor_id:     str
    comment_text:   str
    comment_type:   str
    author:         str
    department:     str
    created_date:   str
    status:         str
    priority:       str

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "comment_id":     self.comment_id,
            "transaction_id": self.transaction_id,
            "obligor_id":     self.obligor_id,
            "comment_text":   self.comment_text,
            "comment_type":   self.comment_type,
            "author":         self.author,
            "department":     self.department,
            "created_date":   self.created_date,
            "status":         self.status,
            "priority":       self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Comment":
        """Construct a Comment from a raw dictionary."""
        return cls(
            comment_id=     str(data.get("comment_id", "")),
            transaction_id= str(data.get("transaction_id", "")),
            obligor_id=     str(data.get("obligor_id", "")),
            comment_text=   str(data.get("comment_text", "")),
            comment_type=   str(data.get("comment_type", "")),
            author=         str(data.get("author", "")),
            department=     str(data.get("department", "")),
            created_date=   str(data.get("created_date", "")),
            status=         str(data.get("status", "")),
            priority=       str(data.get("priority", "")),
        )
