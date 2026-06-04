"""
ExportService — single service for all async export operations.

Handles job creation, validation, worker dispatch, status queries,
and download access checks. Consolidates the former AsyncExportService,
ExportManifestService, and synchronous ExportService into one class.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.adapters.csv_adapter        import CSVAdapter
from app.adapters.excel_adapter      import ExcelAdapter
from app.adapters.dremio_adapter     import DremioAdapter
from app.adapters.sqlserver_adapter  import SQLServerAdapter
from app.models.export_job                import ExportJob
from app.repositories.export_job_repository import ExportJobRepository
from app.services.base_service            import BaseService
from app.workers.export_worker            import submit_export_job

VALID_ENTITY_TYPES   = {"facilities", "obligors", "transactions", "comments"}
VALID_EXPORT_TYPES   = {"partial", "full"}
VALID_SCHEDULE_TYPES = {"H1", "H2", "all"}
VALID_FILE_FORMATS   = {"csv", "excel", "parquet"}
VALID_SOURCE_TYPES   = {"csv", "excel", "dremio", "sqlserver"}

_ADAPTER_MAP = {
    "csv":       CSVAdapter,
    "excel":     ExcelAdapter,
    "dremio":    DremioAdapter,
    "sqlserver": SQLServerAdapter,
}


class ExportService(BaseService):
    """
    All export operations in one place: create, validate, dispatch,
    query status, and authorise downloads.

    Instantiate per request:
        svc = ExportService(
            data_dir   = current_app.config['DATA_DIR'],
            export_dir = current_app.config['EXPORT_DIR'],
            app_config = current_app.config,
        )
    """

    def __init__(
        self,
        data_dir:   str,
        export_dir: str,
        app_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(data_dir)
        self._export_dir = export_dir
        self._app_config = app_config or {}
        self._repo       = ExportJobRepository.get_instance()

    # ── Job creation ──────────────────────────────────────────────────────────

    def create_job(
        self,
        user_id:       str,
        entity_type:   str,
        export_type:   str            = "full",
        schedule_type: str            = "H1",
        source_type:   str            = "csv",
        file_format:   str            = "csv",
        entity_id:     Optional[str]  = None,
        filters:       Optional[Dict] = None,
        sorts:         Optional[List] = None,
    ) -> ExportJob:
        """Validate, persist, and enqueue a new export job. Returns the job immediately."""
        self._validate(entity_type, export_type, schedule_type, file_format, source_type)

        job = ExportJob(
            job_id        = uuid.uuid4().hex,
            user_id       = user_id,
            export_type   = export_type,
            schedule_type = schedule_type,
            source_type   = source_type,
            entity_type   = entity_type,
            file_format   = file_format,
            entity_id     = entity_id,
            filters       = filters or {},
            sorts         = sorts   or [],
            status        = "QUEUED",
            created_at    = datetime.now(timezone.utc),
        )

        self._repo.create(job)

        datasource = _ADAPTER_MAP[source_type](self._build_ds_config(source_type))
        submit_export_job(job, datasource, self._export_dir)

        self.log.info(
            "Export job created job_id=%s user=%s entity=%s type=%s fmt=%s source=%s",
            job.job_id, user_id, entity_type, export_type, file_format, source_type,
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

    def list_recent(self, limit: int = 100) -> List[Dict]:
        """Return summary dicts for the most-recent *limit* jobs."""
        return [self._job_summary(j) for j in self._repo.list_recent(limit)]

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _validate(
        entity_type: str, export_type: str, schedule_type: str,
        file_format: str, source_type: str,
    ) -> None:
        errors = []
        if entity_type   not in VALID_ENTITY_TYPES:   errors.append(f"entity_type={entity_type!r}")
        if export_type   not in VALID_EXPORT_TYPES:   errors.append(f"export_type={export_type!r}")
        if schedule_type not in VALID_SCHEDULE_TYPES: errors.append(f"schedule_type={schedule_type!r}")
        if file_format   not in VALID_FILE_FORMATS:   errors.append(f"file_format={file_format!r}")
        if source_type   not in VALID_SOURCE_TYPES:   errors.append(f"source_type={source_type!r}")
        if errors:
            raise ValueError(f"Invalid export parameters: {', '.join(errors)}")

    def _build_ds_config(self, source_type: str) -> Dict[str, Any]:
        cfg: Dict[str, Any] = {"data_dir": self._data_dir}
        if source_type == "dremio":
            cfg.update({
                "dremio_host":     self._app_config.get("DREMIO_HOST", ""),
                "dremio_port":     self._app_config.get("DREMIO_PORT", 32010),
                "dremio_user":     self._app_config.get("DREMIO_USER", ""),
                "dremio_password": self._app_config.get("DREMIO_PASSWORD", ""),
                "dremio_source":   self._app_config.get("DREMIO_SOURCE", "FR_Y14Q"),
            })
        elif source_type == "sqlserver":
            cfg.update({
                "sqlserver_host":     self._app_config.get("SQLSERVER_HOST", ""),
                "sqlserver_port":     self._app_config.get("SQLSERVER_PORT", 1433),
                "sqlserver_db":       self._app_config.get("SQLSERVER_DB", ""),
                "sqlserver_user":     self._app_config.get("SQLSERVER_USER", ""),
                "sqlserver_password": self._app_config.get("SQLSERVER_PASSWORD", ""),
                "sqlserver_schema":   self._app_config.get("SQLSERVER_SCHEMA", "dbo"),
            })
        elif source_type == "excel":
            cfg["excel_path"] = self._app_config.get("EXCEL_DATA_PATH", "")
        return cfg

    @staticmethod
    def _job_summary(job: ExportJob) -> Dict:
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
