"""
Export controller — streaming file download endpoints.

Endpoints:
    GET /api/export/facilities?format=csv|excel|parquet
    GET /api/export/facilities/<id>/obligors?format=…
    GET /api/export/obligors/<id>/transactions?format=…
    GET /api/export/transactions/<id>/comments?format=…
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, request, send_file

from app.services.export_service  import ExportService
from app.utils.response_utils     import error_response

export_bp = Blueprint("export", __name__)
log       = logging.getLogger(__name__)

VALID_FORMATS = {"csv", "excel", "parquet"}


def _fmt() -> str:
    """Extract and validate the 'format' query parameter."""
    fmt = request.args.get("format", "csv").lower()
    if fmt not in VALID_FORMATS:
        raise ValueError(f"Invalid format '{fmt}'. Allowed: {', '.join(VALID_FORMATS)}")
    return fmt


def _data_dir() -> str:
    return current_app.config["DATA_DIR"]


# ── Facilities export ─────────────────────────────────────────────────────────

@export_bp.route("/facilities", methods=["GET"])
def export_facilities():
    """Download full facilities dataset in the requested format."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_facilities(_fmt())
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting facilities")
        return error_response("Export failed", 500)


# ── All obligors / all transactions exports ───────────────────────────────────

@export_bp.route("/obligors", methods=["GET"])
def export_all_obligors():
    """Download full obligors dataset."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_all_obligors(_fmt())
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting all obligors")
        return error_response("Export failed", 500)


@export_bp.route("/transactions", methods=["GET"])
def export_all_transactions():
    """Download full transactions dataset."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_all_transactions(_fmt())
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting all transactions")
        return error_response("Export failed", 500)


# ── Obligors export ───────────────────────────────────────────────────────────

@export_bp.route("/facilities/<facility_id>/obligors", methods=["GET"])
def export_obligors(facility_id: str):
    """Download obligors for *facility_id* in the requested format."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_obligors_for_facility(
            facility_id, _fmt()
        )
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting obligors for facility %s", facility_id)
        return error_response("Export failed", 500)


# ── Transactions export ───────────────────────────────────────────────────────

@export_bp.route("/obligors/<obligor_id>/transactions", methods=["GET"])
def export_transactions(obligor_id: str):
    """Download transactions for *obligor_id* in the requested format."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_transactions_for_obligor(
            obligor_id, _fmt()
        )
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting transactions for obligor %s", obligor_id)
        return error_response("Export failed", 500)


# ── Comments export ───────────────────────────────────────────────────────────

@export_bp.route("/transactions/<transaction_id>/comments", methods=["GET"])
def export_comments(transaction_id: str):
    """Download comments for *transaction_id* in the requested format."""
    try:
        buf, mime, fname = ExportService(_data_dir()).export_comments_for_transaction(
            transaction_id, _fmt()
        )
        return send_file(buf, mimetype=mime, as_attachment=True, download_name=fname)
    except ValueError as exc:
        return error_response(str(exc), 400)
    except Exception:
        log.exception("Error exporting comments for transaction %s", transaction_id)
        return error_response("Export failed", 500)
