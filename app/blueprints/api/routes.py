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


# ── Schema endpoint (registered first so literal "schema" beats /<entity_type>) ──

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


# ── Generic entity routes ─────────────────────────────────────────────────────

@api_bp.route("/<entity_type>", methods=["GET"])
def get_entity(entity_type: str):
    entities = current_app.config.get("ENTITIES", {})
    if entity_type not in entities:
        return error_response(f"Unknown entity: '{entity_type}'", 404)
    try:
        page, per_page    = _parse_pagination()
        search            = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        result = current_app.reporting_service.get_entity(
            entity_type, search=search, page=page, per_page=per_page,
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
        log.exception("Unexpected error fetching %s", entity_type)
        return error_response("Internal server error", 500)


@api_bp.route("/<parent_entity>/<child_entity>", methods=["GET"])
def get_child_entity(parent_entity: str, child_entity: str):
    entities = current_app.config.get("ENTITIES", {})
    if parent_entity not in entities:
        return error_response(f"Unknown entity: '{parent_entity}'", 404)
    children = entities[parent_entity].get("children", {})
    if child_entity not in children:
        return error_response(
            f"'{child_entity}' is not a declared child of '{parent_entity}'", 404
        )
    try:
        page, per_page    = _parse_pagination()
        search            = request.args.get("search", "").strip()
        sor, fic_mis_date = _parse_context()
        fk_cols    = children[child_entity]["fk"]
        fk_vals    = {col: request.args.get(col, "").strip() for col in fk_cols}
        entity_key = fk_vals if all(fk_vals.values()) else None
        result = current_app.reporting_service.get_entity(
            child_entity, entity_key=entity_key, search=search,
            page=page, per_page=per_page, sor=sor, fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception(
            "Unexpected error fetching %s → %s", parent_entity, child_entity
        )
        return error_response("Internal server error", 500)
