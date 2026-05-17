"""Obligor domain model."""

from dataclasses import dataclass, field


@dataclass
class Obligor:
    """
    Represents an obligor (borrower/counterparty) linked to a facility.

    The *transaction_count* field is computed by the service layer.
    """

    obligor_id:         str
    facility_id:        str
    obligor_name:       str
    obligor_type:       str
    tin:                str
    industry:           str
    sub_industry:       str
    country:            str
    credit_score:       int
    exposure_amount:    float
    outstanding_amount: float
    status:             str
    risk_grade:         str
    created_date:       str
    review_date:        str
    transaction_count:  int = field(default=0)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "obligor_id":         self.obligor_id,
            "facility_id":        self.facility_id,
            "obligor_name":       self.obligor_name,
            "obligor_type":       self.obligor_type,
            "tin":                self.tin,
            "industry":           self.industry,
            "sub_industry":       self.sub_industry,
            "country":            self.country,
            "credit_score":       self.credit_score,
            "exposure_amount":    self.exposure_amount,
            "outstanding_amount": self.outstanding_amount,
            "status":             self.status,
            "risk_grade":         self.risk_grade,
            "created_date":       self.created_date,
            "review_date":        self.review_date,
            "transaction_count":  self.transaction_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Obligor":
        """Construct an Obligor from a raw dictionary."""
        return cls(
            obligor_id=         str(data.get("obligor_id", "")),
            facility_id=        str(data.get("facility_id", "")),
            obligor_name=       str(data.get("obligor_name", "")),
            obligor_type=       str(data.get("obligor_type", "")),
            tin=                str(data.get("tin", "")),
            industry=           str(data.get("industry", "")),
            sub_industry=       str(data.get("sub_industry", "")),
            country=            str(data.get("country", "")),
            credit_score=       int(data.get("credit_score", 0)),
            exposure_amount=    float(data.get("exposure_amount", 0)),
            outstanding_amount= float(data.get("outstanding_amount", 0)),
            status=             str(data.get("status", "")),
            risk_grade=         str(data.get("risk_grade", "")),
            created_date=       str(data.get("created_date", "")),
            review_date=        str(data.get("review_date", "")),
            transaction_count=  int(data.get("transaction_count", 0)),
        )
