"""
ExportManifestService — queryable manifest of all async export jobs.

Provides read-only views over the ExportJobRepository so that audit
dashboards and the export status API can retrieve job metadata without
coupling to the repository directly.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.models.export_job import ExportJob
from app.repositories.export_job_repository import ExportJobRepository

log = logging.getLogger(__name__)


class ExportManifestService:
    """
    Read-only facade for querying export job records.

    Controllers use this class for status polling and download authorisation.
    The service never mutates job state — that is the worker's responsibility.
    """

    def __init__(self) -> None:
        self._repo = ExportJobRepository.get_instance()

    # ── Status queries ────────────────────────────────────────────────────────

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Return full job metadata as a JSON-serialisable dict, or ``None``
        if the job does not exist.
        """
        job = self._repo.get(job_id)
        if not job:
            return None
        return job.to_dict()

    def get_file_path(self, job_id: str) -> Optional[str]:
        """
        Return the absolute path to the completed export file.

        Returns ``None`` if the job does not exist, is not yet complete,
        or the file_path field was not set by the worker.
        """
        job = self._repo.get(job_id)
        if job and job.status == "COMPLETED" and job.file_path:
            return job.file_path
        return None

    def job_is_downloadable(self, job_id: str) -> bool:
        """True only when the job completed successfully and file exists."""
        path = self.get_file_path(job_id)
        import os
        return path is not None and os.path.exists(path)

    # ── List / audit views ────────────────────────────────────────────────────

    def list_recent_jobs(self, limit: int = 100) -> List[Dict]:
        """Return summary dicts for the *limit* most-recent jobs."""
        return [self._to_summary(j) for j in self._repo.list_recent(limit)]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _to_summary(job: ExportJob) -> Dict:
        return {
            "job_id":           job.job_id,
            "user_id":          job.user_id,
            "export_type":      job.export_type,
            "schedule_type":    job.schedule_type,
            "entity_type":      job.entity_type,
            "file_format":      job.file_format,
            "source_type":      job.source_type,
            "status":           job.status,
            "created_at":       job.created_at.isoformat() + "Z",
            "row_count":        job.row_count,
            "duration_seconds": job.duration_seconds,
        }
