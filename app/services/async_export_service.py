"""
AsyncExportService — orchestrates async export job creation.

Responsibilities:
  1. Validate the incoming job specification.
  2. Create and persist the ExportJob record (status=QUEUED).
  3. Instantiate the appropriate DataSource for the requested source_type.
  4. Delegate background processing to the export worker.
  5. Return the job record immediately to the caller.

Controllers depend only on this service — data source selection and
worker dispatch are fully encapsulated here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.datasources.csv_datasource       import CSVDataSource
from app.datasources.excel_datasource     import ExcelDataSource
from app.datasources.dremio_datasource    import DremioDataSource
from app.datasources.sqlserver_datasource import SQLServerDataSource
from app.models.export_job                import ExportJob
from app.repositories.export_job_repository import ExportJobRepository
from app.workers.export_worker            import submit_export_job

log = logging.getLogger(__name__)

# ── Validation constants ──────────────────────────────────────────────────────

VALID_ENTITY_TYPES   = {"facilities", "obligors", "transactions", "comments"}
VALID_EXPORT_TYPES   = {"partial", "full"}
VALID_SCHEDULE_TYPES = {"H1", "H2", "all"}
VALID_FILE_FORMATS   = {"csv", "excel", "parquet"}
VALID_SOURCE_TYPES   = {"csv", "excel", "dremio", "sqlserver"}

_DATASOURCE_MAP = {
    "csv":       CSVDataSource,
    "excel":     ExcelDataSource,
    "dremio":    DremioDataSource,
    "sqlserver": SQLServerDataSource,
}


class AsyncExportService:
    """
    Thin coordination layer between the HTTP layer and the background worker.

    Instantiate per-request using ``current_app.config``:
        svc = AsyncExportService(
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
        self._data_dir   = data_dir
        self._export_dir = export_dir
        self._app_config = app_config or {}
        self._job_repo   = ExportJobRepository.get_instance()

    # ── Public interface ──────────────────────────────────────────────────────

    def create_export_job(
        self,
        user_id:       str,
        entity_type:   str,
        export_type:   str           = "full",
        schedule_type: str           = "H1",
        source_type:   str           = "csv",
        file_format:   str           = "csv",
        entity_id:     Optional[str] = None,
        filters:       Optional[Dict] = None,
        sorts:         Optional[List] = None,
    ) -> ExportJob:
        """
        Validate, persist, and enqueue a new export job.

        Returns the ``ExportJob`` record immediately (status=QUEUED).
        The caller should return ``job.job_id`` to the HTTP client for
        subsequent status polling.
        """
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

        self._job_repo.create(job)

        datasource = _DATASOURCE_MAP[source_type](self._build_ds_config(source_type))
        submit_export_job(job, datasource, self._export_dir)

        log.info(
            "Export job created job_id=%s user=%s entity=%s type=%s fmt=%s source=%s",
            job.job_id, user_id, entity_type, export_type, file_format, source_type,
        )
        return job

    def get_job(self, job_id: str) -> Optional[ExportJob]:
        return self._job_repo.get(job_id)

    # ── Validation ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate(entity_type, export_type, schedule_type, file_format, source_type) -> None:
        errors = []
        if entity_type   not in VALID_ENTITY_TYPES:   errors.append(f"entity_type={entity_type!r}")
        if export_type   not in VALID_EXPORT_TYPES:   errors.append(f"export_type={export_type!r}")
        if schedule_type not in VALID_SCHEDULE_TYPES: errors.append(f"schedule_type={schedule_type!r}")
        if file_format   not in VALID_FILE_FORMATS:   errors.append(f"file_format={file_format!r}")
        if source_type   not in VALID_SOURCE_TYPES:   errors.append(f"source_type={source_type!r}")
        if errors:
            raise ValueError(f"Invalid export parameters: {', '.join(errors)}")

    # ── DataSource config builder ─────────────────────────────────────────────

    def _build_ds_config(self, source_type: str) -> Dict[str, Any]:
        """Assemble the datasource config dict from the application config."""
        cfg = {"data_dir": self._data_dir}

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
