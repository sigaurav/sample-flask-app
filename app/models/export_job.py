"""
ExportJob — domain model for async export audit tracking.

Each export request creates one ExportJob record.  The record persists
for the lifetime of the process (Phase 1: in-memory).  Phase 2 will
persist to a database table for cross-process and cross-restart durability.

Auditable fields captured per the regulatory observability requirements:
    job_id, user_id, export_type, schedule_type, source_type,
    entity_type, entity_id, file_format, filters, sorts,
    status, created_at, started_at, completed_at,
    row_count, file_path, error_message
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExportJob:
    """
    Tracks the lifecycle of a single asynchronous export request.

    Statuses:
        QUEUED    → submitted, not yet picked up by worker
        RUNNING   → worker has started processing
        COMPLETED → file written, download available
        FAILED    → worker encountered an unrecoverable error
    """

    # ── Identity ───────────────────────────────────────────────────────────────
    job_id:        str
    user_id:       str

    # ── Request spec (what was asked for) ─────────────────────────────────────
    export_type:   str           # "partial" | "full"
    schedule_type: str           # "H1" | "H2" | "all"
    source_type:   str           # "csv" | "excel" | "dremio" | "sqlserver"
    entity_type:   str           # "facilities" | "obligors" | "transactions" | "comments"
    file_format:   str           # "csv" | "excel" | "parquet"

    # ── Lifecycle ──────────────────────────────────────────────────────────────
    status:        str
    created_at:    datetime

    # ── Optional scope / filter state ─────────────────────────────────────────
    entity_id:     Optional[str]  = None
    filters:       Dict[str, Any] = field(default_factory=dict)
    sorts:         List[Dict]     = field(default_factory=list)

    # ── Worker result ──────────────────────────────────────────────────────────
    started_at:    Optional[datetime] = None
    completed_at:  Optional[datetime] = None
    row_count:     Optional[int]      = None
    file_path:     Optional[str]      = None
    error_message: Optional[str]      = None

    # ── Computed ───────────────────────────────────────────────────────────────

    @property
    def duration_seconds(self) -> Optional[float]:
        """Wall-clock seconds from worker start to completion."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable representation for API responses."""
        d = asdict(self)
        for key in ("created_at", "started_at", "completed_at"):
            v = d[key]
            if v is not None:
                d[key] = v.isoformat() + "Z"
        d["duration_seconds"] = self.duration_seconds
        return d
