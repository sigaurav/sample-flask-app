"""Transaction domain model."""

from dataclasses import dataclass, field


@dataclass
class Transaction:
    """
    Represents a single financial transaction under a facility/obligor.

    The *comment_count* field is computed by the service layer.
    """

    transaction_id:   str
    obligor_id:       str
    facility_id:      str
    transaction_type: str
    amount:           float
    currency:         str
    transaction_date: str
    value_date:       str
    status:           str
    reference_number: str
    description:      str
    created_by:       str
    approved_by:      str
    comment_count:    int = field(default=0)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "transaction_id":   self.transaction_id,
            "obligor_id":       self.obligor_id,
            "facility_id":      self.facility_id,
            "transaction_type": self.transaction_type,
            "amount":           self.amount,
            "currency":         self.currency,
            "transaction_date": self.transaction_date,
            "value_date":       self.value_date,
            "status":           self.status,
            "reference_number": self.reference_number,
            "description":      self.description,
            "created_by":       self.created_by,
            "approved_by":      self.approved_by,
            "comment_count":    self.comment_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transaction":
        """Construct a Transaction from a raw dictionary."""
        return cls(
            transaction_id=   str(data.get("transaction_id", "")),
            obligor_id=       str(data.get("obligor_id", "")),
            facility_id=      str(data.get("facility_id", "")),
            transaction_type= str(data.get("transaction_type", "")),
            amount=           float(data.get("amount", 0)),
            currency=         str(data.get("currency", "USD")),
            transaction_date= str(data.get("transaction_date", "")),
            value_date=       str(data.get("value_date", "")),
            status=           str(data.get("status", "")),
            reference_number= str(data.get("reference_number", "")),
            description=      str(data.get("description", "")),
            created_by=       str(data.get("created_by", "")),
            approved_by=      str(data.get("approved_by", "")),
            comment_count=    int(data.get("comment_count", 0)),
        )
