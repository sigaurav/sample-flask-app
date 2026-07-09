from __future__ import annotations

import logging

from flask import current_app, request

from app.blueprints.api        import api_bp
from app.utils.response_utils  import error_response, paginated_response, success_response

log = logging.getLogger(__name__)



# Rolando's code does not have _to_str and _build_entity_key, but they are needed to support child entity queries.
def _to_str(val):
    """Convert a value to string, reversing float coercion for integer-valued floats."""
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val) if val is not None else ""


def _build_entity_key(fk_cols, child_fk_cols, fk_vals, concat_sep=None, static_filter=None):
    if not fk_vals or not all(fk_vals.get(c) for c in fk_cols):
        return None
    if concat_sep:
        concat_val = concat_sep.join(_to_str(fk_vals.get(c, "")) for c in fk_cols)
        entity_key = {child_fk_cols[0]: concat_val}
    else:
        entity_key = {child_col: fk_vals.get(parent_col, "")
                      for parent_col, child_col in zip(fk_cols, child_fk_cols)}
    if static_filter:
        entity_key[static_filter["field"]] = static_filter["value"]
    return entity_key


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

# Rolando updated below route and function name:
@api_bp.route("/<entity_type>", methods=["POST"])
def get_entity(entity_type: str):
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
            period_dt=payload.get("period_dt", ""),
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
    

# Rolando updated below route and function name:
@api_bp.route("/<parent_entity>/<child_entity>", methods=["POST"])
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
        payload  = request.get_json(silent=True) or {}
        page     = max(1, payload.get("page", 1))
        per_page = max(1, min(
            payload.get("per_page", current_app.config["DEFAULT_PAGE_SIZE"]),
            current_app.config["MAX_PAGE_SIZE"],
        ))
        child_rel      = children[child_entity]
        fk_cols        = child_rel["fk"]
        child_fk_cols  = child_rel["fk_child"]
        concat_sep     = child_rel.get("concat_separator")
        static_filter  = child_rel.get("child_static_filter")

        fk_vals    = payload.get("entity_key", {})
        entity_key = _build_entity_key(fk_cols, child_fk_cols, fk_vals, concat_sep, static_filter)
        result = current_app.reporting_service.get_entity(
            child_entity, entity_key=entity_key,
            search=payload.get("quick_filter", ""),
            page=page, per_page=per_page,
            period_dt=payload.get("period_dt", ""),
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


