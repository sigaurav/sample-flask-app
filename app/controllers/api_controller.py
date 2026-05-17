"""
API controller — JSON data endpoints for AG Grid consumption.

All endpoints follow the pattern:
    GET /api/<resource>?page=1&per_page=50&search=<query>

Drill-down endpoints:
    GET /api/facilities/<id>/obligors
    GET /api/obligors/<id>/transactions
    GET /api/transactions/<id>/comments
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, request

from app.services.facility_service    import FacilityService
from app.services.obligor_service     import ObligorService
from app.services.transaction_service import TransactionService
from app.utils.response_utils         import error_response, paginated_response

api_bp = Blueprint("api", __name__)
log    = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_pagination() -> tuple[int, int]:
    """Extract and clamp page/per_page from query-string."""
    page     = max(1, request.args.get("page",     1,  type=int))
    per_page = max(1, min(
        request.args.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"], type=int),
        current_app.config["MAX_PAGE_SIZE"],
    ))
    return page, per_page


def _data_dir() -> str:
    return current_app.config["DATA_DIR"]


# ── Facility endpoints ────────────────────────────────────────────────────────

@api_bp.route("/facilities", methods=["GET"])
def get_facilities():
    """
    Return paginated facility records enriched with obligor counts.

    Query params:
        page     (int)  – 1-based page number
        per_page (int)  – rows per page
        search   (str)  – optional text filter
    """
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()

        svc    = FacilityService(_data_dir())
        result = svc.get_facilities(search=search, page=page, per_page=per_page)

        return paginated_response(
            data=result["records"],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        log.error("Data file missing: %s", exc)
        return error_response(str(exc), 503)
    except Exception as exc:
        log.exception("Unexpected error in get_facilities")
        return error_response("Internal server error", 500)


@api_bp.route("/facilities/<facility_id>", methods=["GET"])
def get_facility(facility_id: str):
    """Return a single facility record."""
    try:
        svc      = FacilityService(_data_dir())
        facility = svc.get_facility_by_id(facility_id)
        if facility is None:
            return error_response(f"Facility '{facility_id}' not found", 404)
        from app.utils.response_utils import success_response
        return success_response(facility.to_dict())
    except Exception as exc:
        log.exception("Error fetching facility %s", facility_id)
        return error_response("Internal server error", 500)


# ── All-obligors endpoint ─────────────────────────────────────────────────────

@api_bp.route("/obligors", methods=["GET"])
def get_all_obligors():
    """Return paginated obligors across all facilities, enriched with transaction counts."""
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        svc    = ObligorService(_data_dir())
        result = svc.get_all_obligors(search=search, page=page, per_page=per_page)
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"], per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching all obligors")
        return error_response("Internal server error", 500)


# ── All-transactions endpoint ─────────────────────────────────────────────────

@api_bp.route("/transactions", methods=["GET"])
def get_all_transactions():
    """Return paginated transactions across all obligors, enriched with comment counts."""
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        svc    = TransactionService(_data_dir())
        result = svc.get_all_transactions(search=search, page=page, per_page=per_page)
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"], per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching all transactions")
        return error_response("Internal server error", 500)


# ── Obligor drill-down endpoints ───────────────────────────────────────────────

@api_bp.route("/facilities/<facility_id>/obligors", methods=["GET"])
def get_obligors_for_facility(facility_id: str):
    """
    Return paginated obligors belonging to *facility_id*.

    Obligor records are enriched with transaction counts.
    """
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()

        svc    = ObligorService(_data_dir())
        result = svc.get_obligors_for_facility(
            facility_id, search=search, page=page, per_page=per_page
        )

        return paginated_response(
            data=result["records"],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching obligors for facility %s", facility_id)
        return error_response("Internal server error", 500)


# ── Transaction drill-down endpoints ───────────────────────────────────────────

@api_bp.route("/obligors/<obligor_id>/transactions", methods=["GET"])
def get_transactions_for_obligor(obligor_id: str):
    """
    Return paginated transactions belonging to *obligor_id*.

    Transaction records are enriched with comment counts.
    """
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()

        svc    = TransactionService(_data_dir())
        result = svc.get_transactions_for_obligor(
            obligor_id, search=search, page=page, per_page=per_page
        )

        return paginated_response(
            data=result["records"],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching transactions for obligor %s", obligor_id)
        return error_response("Internal server error", 500)


# ── Comment drill-down endpoints ───────────────────────────────────────────────

@api_bp.route("/transactions/<transaction_id>/comments", methods=["GET"])
def get_comments_for_transaction(transaction_id: str):
    """Return paginated comments belonging to *transaction_id*."""
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()

        svc    = TransactionService(_data_dir())
        result = svc.get_comments_for_transaction(
            transaction_id, search=search, page=page, per_page=per_page
        )

        return paginated_response(
            data=result["records"],
            total=result["total"],
            page=result["page"],
            per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching comments for transaction %s", transaction_id)
        return error_response("Internal server error", 500)
