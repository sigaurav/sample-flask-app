from __future__ import  annotations

from flask import current_app, request, jsonify
from app.utils.response_utils import error_response
from app.blueprints.jira import jira_bp


def _require_jira_service():
    """Return an error response tuple if Jira isn't configured, else None."""
    if current_app.jira_service is None:
        return error_response("Jira integration is not configured", 503)
    return None


@jira_bp.route('/search', methods=['GET'])
def jira_search():
    guard = _require_jira_service()
    if guard:
        return guard

    myjql = request.args.get("jql")

    if not myjql:
        return jsonify({"error": "jql is required"}), 400

    output_fields = ["key", "summary", "status", "links"]
    result = current_app.jira_service.search_jira_issues(jql=myjql, output_fields=output_fields)
    return jsonify(result)


@jira_bp.route("/search2", methods=["GET"])
def jira_search2():
    guard = _require_jira_service()
    if guard:
        return guard

    jql = request.args.get("jql")
    if not jql:
        return jsonify({"error": "jql is required"}), 400

    result = current_app.jira_service.search_jira_issues(jql)
    return jsonify(result)


@jira_bp.route("/assignees", methods=["GET"])
def jira_assignees():
    period_dt = request.args.get("period_dt", "")
    result = current_app.reporting_service.get_entity(
        "investigation_assignees", period_dt=period_dt,
    )
    return jsonify(result)


@jira_bp.route("/issues", methods=["GET"])
def jira_issues():
    guard = _require_jira_service()
    if guard:
        return guard

    keys = [k.strip() for k in request.args.get("keys", "").split(",") if k.strip()]
    if not keys:
        return jsonify({"success": True, "status_code": 200, "data": [], "error": None})

    jql = "key in (" + ",".join(keys) + ")"
    result = current_app.jira_service.search_jira_issues(
        jql=jql,
        output_fields=["key", "summary", "status", "priority", "assignee", "description", "created", "updated"],
    )
    return jsonify(result)


@jira_bp.route("/investigation/create", methods=["POST"])
def jira_investigation_create():
    guard = _require_jira_service()
    if guard:
        return guard

    from app.schemas import get_pk
    from pathlib import Path

    def delete_temp_files(file_paths: list[str]) -> None:
        for file_path in file_paths:
            path = Path(file_path)
            try:
                if path.exists() and path.is_file():
                    path.unlink()
            except Exception as e:
                current_app.logger.warning("Failed to delete temp file: %s (%s)", path, e)

    body = request.get_json(silent=True) or {}

    required = [
        "priority",
        "summary",
        "assignee",
        "description_data",
        "acceptancecriteria_data",
        "records",
    ]

    missing = [k for k in required if not body.get(k)]
    if missing:
        return error_response(f"Missing required field(s): {missing}", 400)

    # Required Fields
    assignee_data = body.get("assignee")
    assignee = assignee_data.get("assignee_emailaddress")
    project_key = assignee_data.get("assignee_jiraproject")
    issue_type = "Story"
    summary = body.get("summary")
    priority = body.get("priority")
    acceptancecriteria_data = body.get("acceptancecriteria_data")
    records = body.get("records")
    description_data = body.get("description_data")
    
    # Build Jira additional fields
    additional_fields = {}

    # Convert xxxxx_data to clean Jira markup
    description = current_app.jira_service.build_jira_description(description_data)
    acceptancecriteria = current_app.jira_service.build_jira_acceptancecriteria(acceptancecriteria_data)

    additional_fields["priority"] = {"name": priority}
    additional_fields["description"] = description
    additional_fields["customfield_10601"] = acceptancecriteria

    if (
        not project_key or
        not issue_type or
        not summary or
        not assignee
    ):
        return jsonify({
            "success": False,
            "status_code": 400,
            "data": None,
            "error":
                "Missing required fields: project_key, issue_type, summary, assignee"
        })

    result = current_app.jira_service.create_jira_issue(
        project_key=project_key,
        issue_type=issue_type,
        summary=summary,
        assignee=assignee,
        additional_fields=additional_fields
)

    if result["success"] == True:

        jira_key = result.get("data", {}).get("key")

        # Need to create the database record
        records_to_insert = []

        # RD primary key fields
        primary_key_fields = get_pk("facilities")

        for row in records:

            record = {}

            record["entity_type"] = "facilities"
            record["entity_key"] = row.get("composite_key")

            record["jira_key"] = jira_key

            records_to_insert.append(record)

        expected_count = 0
        inserted_count = 0

        if jira_key and records_to_insert:

            # Insert record into the tracker
            expected_count = len(records_to_insert)

            result2 = current_app.reporting_service.put_entity(
                entity_type="investigation_tracker",
                data=records_to_insert
            )

            inserted_count = result2.get("total", -1)

        if inserted_count == expected_count and inserted_count > 0:

            facilities_pk = get_pk("facilities")
            facilities_pk_count = len(facilities_pk)

            obligations_pk = get_pk("obligations")
            property_pk = get_pk("property")

            # Export CSVs
            csv_path = []

            # --------------------------------------------------
            # Export CSV - Facilities
            # --------------------------------------------------
            csv_path.append(
                current_app.reporting_service.get_reference_records_csv_outputfile_path(
                    entity_type="facilities",
                    records=records,
                    origin_pk_columns=facilities_pk,
                    reference_pk_columns=facilities_pk,
                    output_file="facility_investigation.csv"
                )
            )

            # --------------------------------------------------
            # Export CSV - Obligations
            # --------------------------------------------------
            csv_path.append(
                current_app.reporting_service.get_reference_records_csv_outputfile_path(
                    entity_type="obligations",
                    records=records,
                    origin_pk_columns=facilities_pk,
                    reference_pk_columns=obligations_pk[:facilities_pk_count],
                    output_file="obligations_investigation.csv"
                )
            )

            # --------------------------------------------------
            # Export CSV - Property
            # --------------------------------------------------
            csv_path.append(
                current_app.reporting_service.get_reference_records_csv_outputfile_path(
                    entity_type="property",
                    records=records,
                    origin_pk_columns=facilities_pk,
                    reference_pk_columns=property_pk[:facilities_pk_count],
                    output_file="property_investigation.csv"
                )
            )

            # --------------------------------------------------
            # Upload files into the Jira ticket
            # --------------------------------------------------
            result3 = current_app.jira_service.add_jira_attachments(
                jira_key,
                csv_path
            )

            # Once the files are uploaded, remove them from temp space
            if result3["success"]:
                delete_temp_files(csv_path)

            else:
                # Need to update/cancel the recently created Jira ticket
                cancel_result = current_app.jira_service.transition_jira_issue_by_name(
                    issue_key=jira_key,
                    transition_names=[
                        "Cancel",
                        "Cancelled",
                        "Canceled"
                    ],
                    comment=(
                        "Investigation ticket was automatically cancelled because "
                        "the application could not create the required tracking records."
                    )
                )

                return jsonify({
                    "success": False,
                    "message": "Ticket created but attachment upload failed.",
                    "jira_key": jira_key,
                    "expected_tracking_records": expected_count,
                    "inserted_tracking_records": inserted_count,
                    "cancel_result": cancel_result
                }), 500

            return jsonify({
                "success": True,
                "message": "Investigation created successfully"
            }), 200

        else:
            # Need to update/cancel the recently created Jira ticket since the
            # tracking records could not be created.
            cancel_result = current_app.jira_service.transition_jira_issue_by_name(
                issue_key=jira_key,
                transition_names=[
                    "Cancel",
                    "Cancelled",
                    "Canceled"
                ],
                comment=(
                    "Investigation ticket was automatically cancelled because "
                    "the application could not create the required tracking records."
                )
            )

            return jsonify({
                "success": False,
                "message": "Ticket created but tracking records failed to be created.",
                "jira_key": jira_key,
                "expected_tracking_records": expected_count,
                "inserted_tracking_records": inserted_count,
                "cancel_result": cancel_result
            }), 500

    else:

        return jsonify({
            "success": False,
            "message": "Failed to create investigation",
            "status_code": result.get("status_code"),
            "error": result.get("error"),
            "data": result.get("data")
        }), result.get("status_code", 500)


    
    