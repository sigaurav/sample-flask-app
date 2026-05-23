"""
Export worker — processes async export jobs in a background thread pool.

Architecture (Phase 1):
    ThreadPoolExecutor(max_workers=4) — one executor per process.
    Each job is a plain function call submitted with executor.submit().

Architecture (Phase 2 migration path):
    Replace ``_executor.submit(_run_export, ...)`` with a Celery task
    dispatch.  The ``_run_export`` function signature is Celery-compatible
    (accepts only serialisable arguments).

Observability:
    Every state transition is logged with structured extra fields:
        job_id, entity_type, export_type, source_type, row_count,
        duration_s, file_path
"""

from __future__ import annotations

import logging
import os
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.repositories.export_job_repository import ExportJobRepository

if TYPE_CHECKING:
    from app.datasources.base_datasource import BaseDataSource
    from app.models.export_job import ExportJob

log = logging.getLogger(__name__)

# Phase 1: shared process-level executor.
# max_workers is overridden by EXPORT_WORKER_THREADS in config if set.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="wf-export")


# ── Public interface ──────────────────────────────────────────────────────────

def submit_export_job(job: "ExportJob", datasource: "BaseDataSource", export_dir: str) -> None:
    """
    Enqueue *job* for background processing.

    Returns immediately after submitting to the thread pool.
    The caller should have already persisted the job record with
    status=QUEUED before calling this function.
    """
    _executor.submit(_run_export, job.job_id, datasource, export_dir)
    log.info(
        "Export job queued job_id=%s entity=%s type=%s fmt=%s source=%s",
        job.job_id, job.entity_type, job.export_type, job.file_format, job.source_type,
        extra={"job_id": job.job_id},
    )


# ── Worker ────────────────────────────────────────────────────────────────────

def _run_export(job_id: str, datasource: "BaseDataSource", export_dir: str) -> None:
    """
    Background worker function — runs in thread pool.

    1. Marks job RUNNING.
    2. Calls datasource.fetch() with the job's filter/sort spec.
    3. Serialises the resulting DataFrame to a file.
    4. Marks job COMPLETED with row_count and file_path.
    5. On any exception: marks job FAILED with error_message.
    """
    repo = ExportJobRepository.get_instance()
    job  = repo.get(job_id)
    if not job:
        log.error("Export worker: job record not found job_id=%s", job_id)
        return

    started = datetime.now(timezone.utc)
    repo.update(job_id, status="RUNNING", started_at=started)

    log.info(
        "Export job started job_id=%s entity=%s type=%s source=%s",
        job_id, job.entity_type, job.export_type, job.source_type,
        extra={"job_id": job_id},
    )

    try:
        # For full exports ignore client-side filter/sort state.
        filters = job.filters if job.export_type == "partial" else None
        sorts   = job.sorts   if job.export_type == "partial" else None

        df = datasource.fetch(
            entity_type=job.entity_type,
            entity_id=job.entity_id,
            filters=filters,
            sorts=sorts,
        )

        row_count = len(df)
        file_path = _serialize(df, job, export_dir)
        completed = datetime.now(timezone.utc)
        duration  = (completed - started).total_seconds()

        repo.update(
            job_id,
            status="COMPLETED",
            completed_at=completed,
            row_count=row_count,
            file_path=file_path,
        )

        log.info(
            "Export job completed job_id=%s rows=%d duration_s=%.2f file=%s",
            job_id, row_count, duration, os.path.basename(file_path),
            extra={"job_id": job_id, "row_count": row_count, "duration_s": duration},
        )

    except Exception:
        completed = datetime.now(timezone.utc)
        err_msg   = _last_tb_lines(500)
        repo.update(
            job_id,
            status="FAILED",
            completed_at=completed,
            error_message=err_msg,
        )
        log.exception(
            "Export job failed job_id=%s",
            job_id,
            extra={"job_id": job_id},
        )


# ── Serialisation ─────────────────────────────────────────────────────────────

def _serialize(df, job: "ExportJob", export_dir: str) -> str:
    """Write *df* to *export_dir* and return the absolute file path."""
    import pandas as pd  # local import — worker threads don't always share the GIL

    os.makedirs(export_dir, exist_ok=True)
    stem = f"{job.job_id}_{job.entity_type}_{job.export_type}"

    if job.file_format == "csv":
        path = os.path.join(export_dir, f"{stem}.csv")
        df.to_csv(path, index=False, encoding="utf-8-sig")

    elif job.file_format == "excel":
        path = os.path.join(export_dir, f"{stem}.xlsx")
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")

    elif job.file_format == "parquet":
        path = os.path.join(export_dir, f"{stem}.parquet")
        df.to_parquet(path, index=False, engine="pyarrow")

    else:
        raise ValueError(f"Unsupported file_format: {job.file_format!r}")

    return path


def _last_tb_lines(max_chars: int = 500) -> str:
    return traceback.format_exc()[-max_chars:]
