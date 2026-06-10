from __future__ import annotations

import logging

from flask import current_app, request

from app.blueprints.api        import api_bp
from app.utils.response_utils  import error_response, paginated_response, success_response

log = logging.getLogger(__name__)


def _parse_pagination() -> tuple[int, int]:
    page     = max(1, request.args.get("page",     1,  type=int))
    per_page = max(1, min(
        request.args.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"], type=int),
        current_app.config["MAX_PAGE_SIZE"],
    ))
    return page, per_page


def _parse_context() -> tuple[str, str]:
    return (
        request.args.get("sor",          "").strip(),
        request.args.get("fic_mis_date", "").strip(),
    )


# ── Facilities ────────────────────────────────────────────────────────────────

@api_bp.route("/facilities", methods=["GET"])
def get_facilities():
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_facilities(
            search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        log.error("Data file missing: %s", exc)
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Unexpected error in get_facilities")
        return error_response("Internal server error", 500)


@api_bp.route("/facilities/<facility_id>", methods=["GET"])
def get_facility(facility_id: str):
    try:
        sor, fic_mis_date = _parse_context()
        facility = current_app.reporting_service.get_facility_by_id(
            facility_id, sor=sor, fic_mis_date=fic_mis_date
        )
        if facility is None:
            return error_response(f"Facility '{facility_id}' not found", 404)
        return success_response(facility)
    except Exception:
        log.exception("Error fetching facility %s", facility_id)
        return error_response("Internal server error", 500)


# ── Obligors ──────────────────────────────────────────────────────────────────

@api_bp.route("/obligors", methods=["GET"])
def get_all_obligors():
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_all_obligors(
            search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching all obligors")
        return error_response("Internal server error", 500)


# ── Transactions ──────────────────────────────────────────────────────────────

@api_bp.route("/transactions", methods=["GET"])
def get_all_transactions():
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_all_transactions(
            search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching all transactions")
        return error_response("Internal server error", 500)


# ── Drill-down endpoints ──────────────────────────────────────────────────────

@api_bp.route("/facilities/<facility_id>/obligors", methods=["GET"])
def get_obligors_for_facility(facility_id: str):
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_obligors_for_facility(
            facility_id, search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching obligors for facility %s", facility_id)
        return error_response("Internal server error", 500)


@api_bp.route("/obligors/<obligor_id>/transactions", methods=["GET"])
def get_transactions_for_obligor(obligor_id: str):
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_transactions_for_obligor(
            obligor_id, search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching transactions for obligor %s", obligor_id)
        return error_response("Internal server error", 500)


@api_bp.route("/transactions/<transaction_id>/comments", methods=["GET"])
def get_comments_for_transaction(transaction_id: str):
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_comments_for_transaction(
            transaction_id, search=search, page=page, per_page=per_page,
            sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Error fetching comments for transaction %s", transaction_id)
        return error_response("Internal server error", 500)


# ── Schema endpoints ──────────────────────────────────────────────────────────

@api_bp.route("/schema/<entity_type>", methods=["GET"])
def get_entity_schema(entity_type: str):
    try:
        from app.schemas import get_schema
        return success_response(get_schema(entity_type))
    except KeyError:
        return error_response(f"Unknown entity type: '{entity_type}'", 404)
    except Exception:
        log.exception("Error fetching schema for %s", entity_type)
        return error_response("Internal server error", 500)
