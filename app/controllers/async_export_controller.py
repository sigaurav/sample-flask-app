"""
Async export controller — enterprise FR Y-14Q export API.

Endpoints:
    POST /api/exports
        Create an async export job.  Returns immediately with job_id and
        QUEUED status.  Background worker processes the file.

    GET  /api/exports/<job_id>/status
        Poll job status.  Returns full job metadata including status,
        row_count, duration_seconds.

    GET  /api/exports/<job_id>/download
        Download the completed export file.  Returns 404 if job not
        found, 409 if not yet complete, 200 with file otherwise.

    GET  /api/exports  (optional: manifest list)
        List recent export jobs for audit / observability.

Request body (POST /api/exports):
    {
        "entity_type":   "facilities",        // required
        "export_type":   "full",              // "partial" | "full"
        "schedule_type": "H1",               // "H1" | "H2" | "all"
        "source_type":   "csv",              // "csv" | "excel" | "dremio" | "sqlserver"
        "file_format":   "csv",              // "csv" | "excel" | "parquet"
        "entity_id":     null,               // optional: scoped to parent entity
        "filters":       { "col_filters": {}, "quick_filter": "" },
        "sorts":         [{"field":"...", "dir":"asc"}]
    }
"""

from __future__ import annotations

import logging
import os

from flask import Blueprint, current_app, g, jsonify, request, send_file

from app.services.async_export_service   import AsyncExportService
from app.services.export_manifest_service import ExportManifestService
from app.utils.response_utils            import error_response, success_response

async_export_bp = Blueprint("async_export", __name__)
log             = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _svc() -> AsyncExportService:
    return AsyncExportService(
        data_dir   = current_app.config["DATA_DIR"],
        export_dir = current_app.config["EXPORT_DIR"],
        app_config = current_app.config,
    )

def _manifest_svc() -> ExportManifestService:
    return ExportManifestService()

def _user_id() -> str:
    return getattr(g, "user_id", "anonymous")


# ── POST /api/exports — create export job ─────────────────────────────────────

@async_export_bp.route("", methods=["POST"])
def create_export():
    """Create an asynchronous export job and return the job_id immediately."""
    payload = request.get_json(silent=True) or {}

    entity_type   = payload.get("entity_type", "").strip()
    export_type   = payload.get("export_type",   "full")
    schedule_type = payload.get("schedule_type", "H1")
    source_type   = payload.get("source_type",   "csv")
    file_format   = payload.get("file_format",   "csv")
    entity_id     = payload.get("entity_id")
    filters       = payload.get("filters",  {})
    sorts         = payload.get("sorts",    [])

    if not entity_type:
        return error_response("entity_type is required", 400)

    try:
        job = _svc().create_export_job(
            user_id       = _user_id(),
            entity_type   = entity_type,
            export_type   = export_type,
            schedule_type = schedule_type,
            source_type   = source_type,
            file_format   = file_format,
            entity_id     = entity_id or None,
            filters       = filters,
            sorts         = sorts,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Failed to create export job")
        return error_response("Failed to create export job", 500)

    return success_response(
        {"job_id": job.job_id, "status": job.status},
        status_code=202,
        meta={"message": "Export job queued. Poll /api/exports/{job_id}/status."},
    )


# ── GET /api/exports/<job_id>/status ─────────────────────────────────────────

@async_export_bp.route("/<job_id>/status", methods=["GET"])
def export_status(job_id: str):
    """Return full job metadata for status polling."""
    status = _manifest_svc().get_job_status(job_id)
    if status is None:
        return error_response(f"Export job not found: {job_id}", 404)
    return success_response(status)


# ── GET /api/exports/<job_id>/download ───────────────────────────────────────

@async_export_bp.route("/<job_id>/download", methods=["GET"])
def export_download(job_id: str):
    """Stream the completed export file to the client."""
    manifest = _manifest_svc()

    status = manifest.get_job_status(job_id)
    if status is None:
        return error_response(f"Export job not found: {job_id}", 404)

    if status["status"] == "FAILED":
        return error_response("Export job failed — no file available.", 409)

    if status["status"] in ("QUEUED", "RUNNING"):
        return error_response("Export not yet complete. Retry after polling status.", 409)

    if not manifest.job_is_downloadable(job_id):
        return error_response("Export file not available on disk.", 410)

    file_path = manifest.get_file_path(job_id)
    ext       = os.path.splitext(file_path)[1].lower()

    mime_map = {
        ".csv":     "text/csv",
        ".xlsx":    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".parquet": "application/octet-stream",
    }
    mime = mime_map.get(ext, "application/octet-stream")

    entity   = status.get("entity_type", "export")
    fmt_name = ext.lstrip(".")
    download_name = f"FR_Y14Q_{entity}_{status['export_type']}.{fmt_name}"

    log.info(
        "Export download served job_id=%s user=%s file=%s",
        job_id, _user_id(), os.path.basename(file_path),
        extra={"job_id": job_id},
    )

    return send_file(
        file_path,
        mimetype=mime,
        as_attachment=True,
        download_name=download_name,
    )


# ── GET /api/exports — manifest list ─────────────────────────────────────────

@async_export_bp.route("", methods=["GET"])
def list_exports():
    """Return recent export jobs for audit observability."""
    limit = min(int(request.args.get("limit", 50)), 200)
    jobs  = _manifest_svc().list_recent_jobs(limit)
    return success_response(jobs, meta={"count": len(jobs)})
