"""
Synthetic data generator for the WF Enterprise Analytics platform.

Generates realistic, relational CSV datasets:
  - 100 facilities
  - 500 obligors
  - 5 000 transactions
  - ~2 000 comments

Run once before starting the application:
    python generate_data.py
"""

import csv
import os
import random
from datetime import date, timedelta


# ── Configuration ─────────────────────────────────────────────────────────────

SEED = 42
NUM_FACILITIES    = 100
NUM_OBLIGORS      = 500
NUM_TRANSACTIONS  = 5_000
NUM_COMMENTS      = 2_000
DATA_DIR          = os.path.join(os.path.dirname(__file__), "data")

random.seed(SEED)

# ── Reference data pools ──────────────────────────────────────────────────────

FACILITY_TYPES = [
    "Revolving Credit Facility",
    "Term Loan",
    "Bridge Loan",
    "Syndicated Credit Facility",
    "Asset-Based Lending",
    "Standby Letter of Credit",
    "Construction Loan",
    "Acquisition Facility",
    "Trade Finance Facility",
    "Leveraged Buyout Facility",
]

# Borrower name pool — deliberately small (15 names) so each borrower appears
# multiple times across different facility types, giving secondary/tertiary
# sort keys visible groups to work within.
FACILITY_BORROWERS = [
    "Apex Capital Corp.",
    "Atlantic Finance Group",
    "Bilateral Holdings Ltd.",
    "Continental Partners LLC",
    "Enhanced Capital Inc.",
    "Global Ventures Corp.",
    "Horizon Credit Group",
    "Meridian Finance Corp.",
    "National Holdings Inc.",
    "Pacific Capital Group",
    "Premier Partners LLC",
    "Secured Finance Corp.",
    "Strategic Holdings Ltd.",
    "Summit Capital Group",
    "United Ventures LLC",
]

RISK_RATINGS = ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-",
                 "BBB+", "BBB", "BBB-", "BB+", "BB", "BB-", "B+", "B"]

RELATIONSHIP_MANAGERS = [
    "Sarah Mitchell",     "James Thornton",    "Rebecca Lawson",
    "David Harrington",   "Natalie Forsythe",  "Michael Pemberton",
    "Christine Wallace",  "Robert Ashford",    "Angela Drummond",
    "Steven Caldwell",    "Laura Whitfield",   "Thomas Blackwood",
    "Emily Garrison",     "William Stanton",   "Katherine Mercer",
    "Daniel Fowler",      "Margaret Sinclair",  "Andrew Davenport",
    "Patricia Holloway",  "Charles Sutherland",
]

REGIONS = {
    "Americas":     ["United States", "Canada", "Brazil", "Mexico", "Chile"],
    "EMEA":         ["United Kingdom", "Germany", "France", "Netherlands", "Switzerland", "UAE", "South Africa"],
    "APAC":         ["Japan", "Australia", "Singapore", "Hong Kong", "South Korea", "India", "China"],
    "Global":       ["United States"],
}

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "SGD"]

FACILITY_STATUSES = ["Active", "Active", "Active", "Under Review", "Pending", "Closed"]

COMPANY_PREFIXES = [
    "Global", "National", "American", "Pacific", "Atlantic",
    "United", "Allied", "Continental", "International", "Premier",
    "Apex", "Summit", "Pinnacle", "Stellar", "Nexus",
    "Vector", "Titan", "Meridian", "Horizon", "Vantage",
]

COMPANY_CORES = [
    "Capital", "Industries", "Holdings", "Partners", "Solutions",
    "Enterprises", "Technologies", "Resources", "Systems", "Dynamics",
    "Ventures", "Financial", "Energy", "Healthcare", "Logistics",
    "Aerospace", "Pharmaceuticals", "Biotech", "Consulting", "Analytics",
    "Manufacturing", "Properties", "Infrastructure", "Services", "Innovations",
]

COMPANY_SUFFIXES = [
    "Inc.", "Corp.", "LLC", "Ltd.", "PLC",
    "Group", "S.A.", "GmbH", "AG", "N.V.",
]

OBLIGOR_TYPES = [
    "Corporate", "Corporate", "Corporate",
    "Financial Institution",
    "Special Purpose Vehicle",
    "Government Entity",
    "Non-Profit Organization",
]

INDUSTRIES = {
    "Banking & Finance":   ["Retail Banking", "Investment Banking", "Asset Management", "Insurance"],
    "Technology":          ["Software", "Hardware", "Semiconductors", "Cloud Services"],
    "Energy":              ["Oil & Gas", "Renewable Energy", "Utilities", "Mining"],
    "Healthcare":          ["Pharmaceuticals", "Medical Devices", "Hospitals", "Biotech"],
    "Real Estate":         ["Commercial REIT", "Residential REIT", "Development", "Property Management"],
    "Manufacturing":       ["Automotive", "Aerospace", "Consumer Goods", "Industrial Equipment"],
    "Retail & Consumer":   ["E-Commerce", "Grocery", "Luxury Goods", "Food & Beverage"],
    "Telecommunications":  ["Wireless", "Broadband", "Media", "Cable"],
    "Transportation":      ["Airlines", "Shipping", "Logistics", "Rail"],
    "Government":          ["Federal Agency", "State Authority", "Municipal"],
}

OBLIGOR_STATUSES    = ["Active", "Active", "Active", "Active", "Watchlist", "Defaulted", "Restructuring"]
RISK_GRADES         = ["Investment Grade", "Investment Grade", "Sub-Investment Grade", "High Yield", "Distressed"]

TRANSACTION_TYPES = [
    "Drawdown",      "Repayment",   "Interest Payment",
    "Fee Payment",   "Amendment",   "Waiver",
    "Syndication",   "Assignment",  "Participation",
    "Rollover",
]

TRANSACTION_STATUSES = ["Completed", "Completed", "Completed", "Pending", "Failed", "Cancelled"]

CREATED_BY_NAMES = [
    "J. Thompson", "A. Rodriguez", "S. Patel", "M. Chen", "L. Johnson",
    "R. Williams", "K. Brown", "D. Lee", "C. Davis", "P. Wilson",
]

COMMENT_TYPES  = ["Risk Note", "Compliance Flag", "Analyst Note", "Credit Review", "Legal Opinion",
                  "Operations Note", "Covenant Breach", "Waiver Request", "Escalation", "General"]
DEPARTMENTS    = ["Credit Risk", "Compliance", "Operations", "Legal", "Relationship Management",
                  "Portfolio Management", "Internal Audit", "Treasury", "Finance"]
COMMENT_STATUSES  = ["Open", "Resolved", "Acknowledged", "Escalated"]
COMMENT_PRIORITIES = ["Critical", "High", "Medium", "Low"]

COMMENT_TEMPLATES = [
    "Annual covenant review completed. Obligor remains in compliance with all financial covenants.",
    "Drawdown request reviewed and approved per credit authorization memo dated {date}.",
    "Leverage ratio covenant breach noted. Waiver request submitted to credit committee.",
    "KYC refresh completed. No adverse findings. Documentation filed in CRM.",
    "Interest rate reset processed. New rate effective immediately per SOFR + spread.",
    "Compliance screening completed. No hits on OFAC or PEP watchlists.",
    "Financial statements received and reviewed. Performance in line with projections.",
    "Site visit conducted. Operations appear satisfactory. Report forwarded to RM.",
    "Covenant test results: DSCR = {ratio}x (minimum {min}x). Pass.",
    "Borrowing base certificate reviewed. Advance rate adjusted accordingly.",
    "Repayment processed. Outstanding balance updated. Confirm with treasury.",
    "Legal counsel reviewed amendment terms. No material adverse change detected.",
    "Syndication agent notified of drawdown. Participant shares distributed accordingly.",
    "Credit committee approval received for facility increase. Effective {date}.",
    "Quarterly review call held with management. Guidance maintained. Notes attached.",
]


# ── Utility helpers ────────────────────────────────────────────────────────────

def rand_date(start: date, end: date) -> date:
    """Return a random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rand_money(lo: float, hi: float, decimals: int = 2) -> float:
    """Return a random float amount rounded to *decimals* places."""
    return round(random.uniform(lo, hi), decimals)


def rand_tin() -> str:
    """Return a plausible US EIN-style tax ID."""
    return f"{random.randint(10, 99)}-{random.randint(1000000, 9999999)}"


def rand_ref() -> str:
    """Return a reference number."""
    return f"REF-{random.randint(10_000_000, 99_999_999)}"


def make_company_name() -> str:
    """Assemble a plausible company name from pools."""
    prefix = random.choice(COMPANY_PREFIXES)
    core   = random.choice(COMPANY_CORES)
    suffix = random.choice(COMPANY_SUFFIXES)
    return f"{prefix} {core} {suffix}"


def make_facility_name(ftype: str) -> str:
    """Return a borrower company name (type stored separately in facility_type)."""
    return random.choice(FACILITY_BORROWERS)


# ── Generators ─────────────────────────────────────────────────────────────────

def generate_facilities(n: int) -> list[dict]:
    """Generate *n* facility records."""
    records = []
    for i in range(1, n + 1):
        ftype         = random.choice(FACILITY_TYPES)
        name          = make_facility_name(ftype)
        credit_limit  = rand_money(5_000_000, 5_000_000_000)
        outstanding   = rand_money(credit_limit * 0.1, credit_limit * 0.9)
        available     = round(credit_limit - outstanding, 2)
        region        = random.choice(list(REGIONS.keys()))
        country       = random.choice(REGIONS[region])
        created       = rand_date(date(2015, 1, 1), date(2022, 12, 31))
        maturity      = created + timedelta(days=random.randint(365 * 3, 365 * 10))
        risk_rating   = random.choice(RISK_RATINGS)
        risk_score    = round(random.uniform(1.0, 10.0), 2)

        records.append({
            "facility_id":          f"FAC-{i:04d}",
            "facility_name":        name,
            "facility_type":        ftype,
            "credit_limit":         credit_limit,
            "currency":             random.choice(CURRENCIES),
            "outstanding_balance":  outstanding,
            "available_credit":     available,
            "utilization_pct":      round(outstanding / credit_limit * 100, 2),
            "status":               random.choice(FACILITY_STATUSES),
            "risk_rating":          risk_rating,
            "risk_score":           risk_score,
            "relationship_manager": random.choice(RELATIONSHIP_MANAGERS),
            "region":               region,
            "country":              country,
            "created_date":         created.isoformat(),
            "maturity_date":        maturity.isoformat(),
            "interest_rate":        round(random.uniform(1.5, 9.5), 3),
        })
    return records


def generate_obligors(n: int, facilities: list[dict]) -> list[dict]:
    """
    Generate *n* obligor records, distributed across facilities.

    Each facility gets at least 1 obligor; remaining are distributed randomly.
    """
    fac_ids = [f["facility_id"] for f in facilities]

    # guarantee at least 1 obligor per facility
    assignments = fac_ids.copy()
    remaining   = n - len(fac_ids)
    assignments += random.choices(fac_ids, k=remaining)
    random.shuffle(assignments)

    records = []
    for i, fac_id in enumerate(assignments, start=1):
        industry       = random.choice(list(INDUSTRIES.keys()))
        sub_industry   = random.choice(INDUSTRIES[industry])
        region         = random.choice(list(REGIONS.keys()))
        country        = random.choice(REGIONS[region])
        fac            = next(f for f in facilities if f["facility_id"] == fac_id)
        exposure       = rand_money(fac["credit_limit"] * 0.01, fac["credit_limit"] * 0.4)
        outstanding    = rand_money(exposure * 0.0, exposure * 0.95)
        created        = rand_date(
            date.fromisoformat(fac["created_date"]),
            date(2023, 6, 30)
        )
        review         = created + timedelta(days=random.randint(180, 730))

        records.append({
            "obligor_id":       f"OBL-{i:05d}",
            "facility_id":      fac_id,
            "obligor_name":     make_company_name(),
            "obligor_type":     random.choice(OBLIGOR_TYPES),
            "tin":              rand_tin(),
            "industry":         industry,
            "sub_industry":     sub_industry,
            "country":          country,
            "credit_score":     random.randint(300, 850),
            "exposure_amount":  exposure,
            "outstanding_amount": outstanding,
            "status":           random.choice(OBLIGOR_STATUSES),
            "risk_grade":       random.choice(RISK_GRADES),
            "created_date":     created.isoformat(),
            "review_date":      review.isoformat(),
        })
    return records


def generate_transactions(n: int, obligors: list[dict]) -> list[dict]:
    """Generate *n* transaction records linked to obligors."""
    records = []
    for i in range(1, n + 1):
        obl          = random.choice(obligors)
        txn_date     = rand_date(date(2020, 1, 1), date(2024, 6, 30))
        value_date   = txn_date + timedelta(days=random.randint(0, 3))
        amount       = rand_money(10_000, obl["exposure_amount"] * 0.5)

        records.append({
            "transaction_id":   f"TXN-{i:06d}",
            "obligor_id":       obl["obligor_id"],
            "facility_id":      obl["facility_id"],
            "transaction_type": random.choice(TRANSACTION_TYPES),
            "amount":           amount,
            "currency":         "USD",
            "transaction_date": txn_date.isoformat(),
            "value_date":       value_date.isoformat(),
            "status":           random.choice(TRANSACTION_STATUSES),
            "reference_number": rand_ref(),
            "description":      f"{random.choice(TRANSACTION_TYPES)} processed under {obl['facility_id']}",
            "created_by":       random.choice(CREATED_BY_NAMES),
            "approved_by":      random.choice(CREATED_BY_NAMES),
        })
    return records


def generate_comments(n: int, transactions: list[dict]) -> list[dict]:
    """Generate *n* comment records, each linked to a random transaction."""
    records = []
    txn_sample = random.sample(transactions, min(n, len(transactions)))
    for i, txn in enumerate(txn_sample, start=1):
        txn_date = date.fromisoformat(txn["transaction_date"])
        cmt_date = txn_date + timedelta(days=random.randint(0, 30))
        template = random.choice(COMMENT_TEMPLATES).format(
            date=cmt_date.isoformat(),
            ratio=round(random.uniform(1.1, 3.5), 2),
            min=round(random.uniform(1.0, 1.5), 2),
        )

        records.append({
            "comment_id":       f"CMT-{i:06d}",
            "transaction_id":   txn["transaction_id"],
            "obligor_id":       txn["obligor_id"],
            "comment_text":     template,
            "comment_type":     random.choice(COMMENT_TYPES),
            "author":           random.choice(RELATIONSHIP_MANAGERS),
            "department":       random.choice(DEPARTMENTS),
            "created_date":     cmt_date.isoformat(),
            "status":           random.choice(COMMENT_STATUSES),
            "priority":         random.choice(COMMENT_PRIORITIES),
        })
    return records


# ── CSV writer ────────────────────────────────────────────────────────────────

def write_csv(filename: str, records: list[dict]) -> None:
    """Write *records* to DATA_DIR/<filename>."""
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, filename)
    if not records:
        print(f"  [WARN] No records to write for {filename}")
        return
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(records[0].keys()))
        writer.writeheader()
        writer.writerows(records)
    print(f"  [OK]  {filename:30s}  {len(records):>6,} rows  -> {path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    print("WF Enterprise Analytics — Synthetic Data Generator")
    print("=" * 60)

    print(f"\nGenerating {NUM_FACILITIES} facilities …")
    facilities = generate_facilities(NUM_FACILITIES)

    print(f"Generating {NUM_OBLIGORS} obligors …")
    obligors = generate_obligors(NUM_OBLIGORS, facilities)

    print(f"Generating {NUM_TRANSACTIONS} transactions …")
    transactions = generate_transactions(NUM_TRANSACTIONS, obligors)

    print(f"Generating {NUM_COMMENTS} comments …")
    comments = generate_comments(NUM_COMMENTS, transactions)

    print("\nWriting CSV files …")
    write_csv("facilities.csv",   facilities)
    write_csv("obligors.csv",     obligors)
    write_csv("transactions.csv", transactions)
    write_csv("comments.csv",     comments)

    print("\nDone.  All files written to:", DATA_DIR)


if __name__ == "__main__":
    main()
