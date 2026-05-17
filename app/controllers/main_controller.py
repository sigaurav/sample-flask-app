"""
Main (page) controller.

Serves the dashboard HTML page.  All data is loaded asynchronously
by the frontend via the API blueprint.
"""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET"])
def dashboard():
    """Render the enterprise analytics dashboard."""
    return render_template("dashboard.html", title="Credit Facility Analytics")


@main_bp.route("/obligors", methods=["GET"])
def obligors():
    """Render the all-obligors page."""
    return render_template("obligors.html", title="Obligors")


@main_bp.route("/transactions", methods=["GET"])
def transactions():
    """Render the all-transactions page."""
    return render_template("transactions.html", title="Transactions")


@main_bp.route("/health", methods=["GET"])
def health():
    """Simple liveness check endpoint."""
    from flask import jsonify
    return jsonify({"status": "ok", "service": "WF Enterprise Analytics"}), 200
