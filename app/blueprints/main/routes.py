from flask import jsonify, render_template

from app.blueprints.main import main_bp


@main_bp.route("/", methods=["GET"])
def dashboard():
    return render_template("dashboard.html", title="Credit Facility Analytics")


@main_bp.route("/obligors", methods=["GET"])
def obligors():
    return render_template("obligors.html", title="Obligors")


@main_bp.route("/transactions", methods=["GET"])
def transactions():
    return render_template("transactions.html", title="Transactions")


@main_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "WF Enterprise Analytics"}), 200
