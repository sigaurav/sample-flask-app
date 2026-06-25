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


def _parse_context() -> str:
    return request.args.get("fic_mis_date", "").strip()


def _to_str(val):
    """Convert a value to string, reversing float coercion for integer-valued floats."""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val) if val is not None else ""


def _build_entity_key(fk_cols, child_fk_cols, fk_vals, concat_sep=None):
    if not fk_vals or not all(fk_vals.get(c) for c in fk_cols):
        return None
    if concat_sep:
        concat_val = concat_sep.join(_to_str(fk_vals.get(c, "")) for c in fk_cols)
        return {child_fk_cols[0]: concat_val}
    return {child_col: fk_vals.get(parent_col, "")
            for parent_col, child_col in zip(fk_cols, child_fk_cols)}


#  Schema endpoint (registered first so literal "schema" beats /<entity_type>) 

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


#  Generic entity routes ─

@api_bp.route("/<entity_type>/query", methods=["POST"])
def query_entity(entity_type: str):
    entities = current_app.config.get("ENTITIES", {})
    if entity_type not in entities:
        return error_response(f"Unknown entity: '{entity_type}'", 404)
    try:
        payload  = request.get_json(silent=True) or {}
        page     = max(1, payload.get("page", 1))
        per_page = max(1, min(
            payload.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"]),
            current_app.config["MAX_PAGE_SIZE"],
        ))
        result = current_app.reporting_service.get_entity(
            entity_type,
            search=payload.get("quick_filter", ""),
            page=page, per_page=per_page,
            fic_mis_date=payload.get("fic_mis_date", ""),
            sorts=payload.get("sorts", []),
            col_filters=payload.get("col_filters", {}),
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
            active=result.get("active"),
        )
    except FileNotFoundError as exc:
        log.error("Data file missing: %s", exc)
        return error_response(str(exc), 503)
    except Exception:
        log.exception("Unexpected error querying %s", entity_type)
        return error_response("Internal server error", 500)


@api_bp.route("/<parent_entity>/<child_entity>/query", methods=["POST"])
def query_child_entity(parent_entity: str, child_entity: str):
    entities = current_app.config.get("ENTITIES", {})
    if parent_entity not in entities:
        return error_response(f"Unknown entity: '{parent_entity}'", 404)
    children = entities[parent_entity].get("children", {})
    if child_entity not in children:
        return error_response(
            f"'{child_entity}' is not a declared child of '{parent_entity}'", 404
        )
    try:
        payload  = request.get_json(silent=True) or {}
        page     = max(1, payload.get("page", 1))
        per_page = max(1, min(
            payload.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"]),
            current_app.config["MAX_PAGE_SIZE"],
        ))
        child_rel     = children[child_entity]
        fk_cols       = child_rel["fk"]
        child_fk_cols = child_rel["child_fk"]
        concat_sep    = child_rel.get("concat_separator")

        fk_vals    = payload.get("entity_key", {})
        entity_key = _build_entity_key(fk_cols, child_fk_cols, fk_vals, concat_sep)
        result = current_app.reporting_service.get_entity(
            child_entity, entity_key=entity_key,
            search=payload.get("quick_filter", ""),
            page=page, per_page=per_page,
            fic_mis_date=payload.get("fic_mis_date", ""),
            sorts=payload.get("sorts", []),
            col_filters=payload.get("col_filters", {}),
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
            active=result.get("active"),
        )
    except FileNotFoundError as exc:
        return error_response(str(exc), 503)
    except Exception:
        log.exception(
            "Unexpected error querying %s → %s", parent_entity, child_entity
        )
        return error_response("Internal server error", 500)


@api_bp.route("/<entity_type>", methods=["GET"])
def get_entity(entity_type: str):
    entities = current_app.config.get("ENTITIES", {})
    if entity_type not in entities:
        return error_response(f"Unknown entity: '{entity_type}'", 404)
    try:
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        fic_mis_date   = _parse_context()
        result = current_app.reporting_service.get_entity(
            entity_type, search=search, page=page, per_page=per_page,
            fic_mis_date=fic_mis_date,
        )
        return paginated_response(
            data=result["records"], total=result["total"],
            page=result["page"],   per_page=result["per_page"],
            active=result.get("active"),
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
        page, per_page = _parse_pagination()
        search         = request.args.get("search", "").strip()
        fic_mis_date   = _parse_context()
        child_rel     = children[child_entity]
        fk_cols       = child_rel["fk"]
        child_fk_cols = child_rel["child_fk"]
        concat_sep    = child_rel.get("concat_separator")

        fk_vals    = {col: request.args.get(col, "").strip() for col in fk_cols}
        entity_key = _build_entity_key(fk_cols, child_fk_cols, fk_vals, concat_sep)
        result = current_app.reporting_service.get_entity(
            child_entity, entity_key=entity_key, search=search,
            page=page, per_page=per_page, fic_mis_date=fic_mis_date,
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
