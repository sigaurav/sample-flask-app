from __future__ import annotations

import logging
import os

from flask import current_app, g, request, send_file

from app.blueprints.export        import export_bp, internal_export_bp
from app.services.export_service  import ExportService
from app.utils.response_utils     import error_response, success_response

log = logging.getLogger(__name__)

_MIME_MAP = {
    ".csv":     "text/csv",
    ".xlsx":    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".parquet": "application/octet-stream",
}


def _svc() -> ExportService:
    return ExportService(
        data_service = current_app.data_service,
        export_dir   = current_app.config["EXPORT_DIR"],
    )


def _user_id() -> str:
    return getattr(g, "user_id", "anonymous")


#  POST /api/exports ─

@export_bp.route("", methods=["POST"])
def create_export():
    payload = request.get_json(silent=True) or {}
    entity_type = payload.get("entity_type", "").strip()
    if not entity_type:
        return error_response("entity_type is required", 400)
    try:
        job = _svc().create_job(
            user_id       = _user_id(),
            entity_type   = entity_type,
            export_type   = payload.get("export_type",   "full"),
            schedule_type = payload.get("schedule_type", "H1"),
            file_format   = payload.get("file_format",   "csv"),
            entity_id     = payload.get("entity_id") or None,
            filters       = payload.get("filters", {}),
            sorts         = payload.get("sorts",   []),
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Failed to create export job")
        return error_response("Failed to create export job", 500)
    return success_response({"job_id": job.job_id, "status": job.status}, status_code=202)


@internal_export_bp.route("/<job_id>/status", methods=["GET"])
def export_status(job_id: str):
    status = _svc().get_status(job_id)
    if status is None:
        return error_response(f"Export job not found: {job_id}", 404)
    return success_response(status)


@internal_export_bp.route("/<job_id>/download", methods=["GET"])
def export_download(job_id: str):
    svc    = _svc()
    status = svc.get_status(job_id)
    if status is None:
        return error_response(f"Export job not found: {job_id}", 404)
    if status["status"] == "FAILED":
        return error_response("Export job failed — no file available.", 409)
    if status["status"] in ("QUEUED", "RUNNING"):
        return error_response("Export not yet complete.", 409)
    if not svc.is_downloadable(job_id):
        return error_response("Export file not available on disk.", 410)
    file_path = svc.get_file_path(job_id)
    ext       = os.path.splitext(file_path)[1].lower()
    mime      = _MIME_MAP.get(ext, "application/octet-stream")
    entity    = status.get("entity_type", "export")
    dl_name   = f"FR_Y14Q_{entity}_{status['export_type']}{ext}"
    log.info("Export download served job_id=%s user=%s", job_id, _user_id())
    return send_file(file_path, mimetype=mime, as_attachment=True, download_name=dl_name)
