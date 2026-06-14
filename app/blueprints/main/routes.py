from flask import abort, current_app, jsonify, render_template

from app.blueprints.main import main_bp


def _render_entity(entity_type: str):
    entities = current_app.config.get("ENTITIES", {})
    cfg      = entities.get(entity_type, {})
    label    = cfg.get("label", entity_type.capitalize())
    return render_template("entity.html", entity_type=entity_type, entity_label=label)


@main_bp.route("/")
def index():
    return _render_entity("facilities")


@main_bp.route("/health")
def health():
    return jsonify({"status": "ok", "service": "WF Enterprise Analytics"}), 200


@main_bp.route("/<entity_type>")
def entity_page(entity_type: str):
    entities = current_app.config.get("ENTITIES", {})
    if entity_type not in entities:
        abort(404)
    return _render_entity(entity_type)
