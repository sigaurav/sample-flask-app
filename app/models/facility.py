"""Facility domain model."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Facility:
    """
    Represents a credit facility record.

    Maps 1-to-many with Obligor.  The *obligor_count* field is
    computed at query time by the service layer.
    """

    facility_id:           str
    facility_name:         str
    facility_type:         str
    credit_limit:          float
    currency:              str
    outstanding_balance:   float
    available_credit:      float
    utilization_pct:       float
    status:                str
    risk_rating:           str
    risk_score:            float
    relationship_manager:  str
    region:                str
    country:               str
    created_date:          str
    maturity_date:         str
    interest_rate:         float
    obligor_count:         int = field(default=0)

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary suitable for JSON serialization."""
        return {
            "facility_id":           self.facility_id,
            "facility_name":         self.facility_name,
            "facility_type":         self.facility_type,
            "credit_limit":          self.credit_limit,
            "currency":              self.currency,
            "outstanding_balance":   self.outstanding_balance,
            "available_credit":      self.available_credit,
            "utilization_pct":       self.utilization_pct,
            "status":                self.status,
            "risk_rating":           self.risk_rating,
            "risk_score":            self.risk_score,
            "relationship_manager":  self.relationship_manager,
            "region":                self.region,
            "country":               self.country,
            "created_date":          self.created_date,
            "maturity_date":         self.maturity_date,
            "interest_rate":         self.interest_rate,
            "obligor_count":         self.obligor_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Facility":
        """Construct a Facility from a raw dictionary (e.g. CSV row)."""
        return cls(
            facility_id=           str(data.get("facility_id", "")),
            facility_name=         str(data.get("facility_name", "")),
            facility_type=         str(data.get("facility_type", "")),
            credit_limit=          float(data.get("credit_limit", 0)),
            currency=              str(data.get("currency", "USD")),
            outstanding_balance=   float(data.get("outstanding_balance", 0)),
            available_credit=      float(data.get("available_credit", 0)),
            utilization_pct=       float(data.get("utilization_pct", 0)),
            status=                str(data.get("status", "")),
            risk_rating=           str(data.get("risk_rating", "")),
            risk_score=            float(data.get("risk_score", 0)),
            relationship_manager=  str(data.get("relationship_manager", "")),
            region=                str(data.get("region", "")),
            country=               str(data.get("country", "")),
            created_date=          str(data.get("created_date", "")),
            maturity_date=         str(data.get("maturity_date", "")),
            interest_rate=         float(data.get("interest_rate", 0)),
            obligor_count=         int(data.get("obligor_count", 0)),
        )
