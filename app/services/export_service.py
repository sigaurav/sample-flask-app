"""
ExportService — single service for all async export operations.

Handles job creation, validation, worker dispatch, status queries,
and download access checks.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.models.export_job                   import ExportJob
from app.repositories.export_job_repository  import ExportJobRepository
from app.services.data_service               import DataService
from app.workers.export_worker               import submit_export_job

VALID_EXPORT_TYPES   = {"partial", "full"}
VALID_SCHEDULE_TYPES = {"H1", "H2", "all"}
VALID_FILE_FORMATS   = {"csv", "excel", "parquet"}


class ExportService:
    """
    All export operations in one place: create, validate, dispatch,
    query status, and authorise downloads.

    Instantiate per request:
        svc = ExportService(
            data_service = current_app.data_service,
            export_dir   = current_app.config['EXPORT_DIR'],
        )
    """

    def __init__(self, data_service: DataService, export_dir: str) -> None:
        self._data_service = data_service
        self._export_dir   = export_dir
        self.log           = logging.getLogger(__name__)
        self._repo         = ExportJobRepository.get_instance()

    # ── Job creation ──────────────────────────────────────────────────────────

    def create_job(
        self,
        user_id:       str,
        entity_type:   str,
        export_type:   str            = "full",
        schedule_type: str            = "H1",
        file_format:   str            = "csv",
        entity_id:     Optional[str]  = None,
        filters:       Optional[Dict] = None,
        sorts:         Optional[List] = None,
    ) -> ExportJob:
        """Validate, persist, and enqueue a new export job. Returns the job immediately."""
        valid_entities = set(self._data_service._config.get("ENTITIES", {}).keys())
        self._validate(entity_type, export_type, schedule_type, file_format, valid_entities)

        job = ExportJob(
            job_id        = uuid.uuid4().hex,
            user_id       = user_id,
            export_type   = export_type,
            schedule_type = schedule_type,
            entity_type   = entity_type,
            file_format   = file_format,
            entity_id     = entity_id,
            filters       = filters or {},
            sorts         = sorts   or [],
            status        = "QUEUED",
            created_at    = datetime.now(timezone.utc),
        )

        self._repo.create(job)

        adapter = self._data_service.get_adapter_for_entity(entity_type)
        submit_export_job(job, adapter, self._export_dir)

        self.log.info(
            "Export job created job_id=%s user=%s entity=%s type=%s fmt=%s",
            job.job_id, user_id, entity_type, export_type, file_format,
        )
        return job

    # ── Status queries ────────────────────────────────────────────────────────

    def get_status(self, job_id: str) -> Optional[Dict]:
        """Return full job metadata as a JSON-serialisable dict, or None if not found."""
        job = self._repo.get(job_id)
        return job.to_dict() if job else None

    def get_file_path(self, job_id: str) -> Optional[str]:
        """Return the absolute path to a completed export file, or None."""
        job = self._repo.get(job_id)
        if job and job.status == "COMPLETED" and job.file_path:
            return job.file_path
        return None

    def is_downloadable(self, job_id: str) -> bool:
        """True only when the job completed successfully and the file exists on disk."""
        path = self.get_file_path(job_id)
        return path is not None and os.path.exists(path)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _validate(
        entity_type: str, export_type: str, schedule_type: str, file_format: str,
        valid_entities: set,
    ) -> None:
        errors = []
        if entity_type   not in valid_entities:       errors.append(f"entity_type={entity_type!r}")
        if export_type   not in VALID_EXPORT_TYPES:   errors.append(f"export_type={export_type!r}")
        if schedule_type not in VALID_SCHEDULE_TYPES: errors.append(f"schedule_type={schedule_type!r}")
        if file_format   not in VALID_FILE_FORMATS:   errors.append(f"file_format={file_format!r}")
        if errors:
            raise ValueError(f"Invalid export parameters: {', '.join(errors)}")

