"""
Reusable Flask JSON response helpers.

All API endpoints use these factory functions to guarantee a consistent
response envelope:

    Success:
        {"success": true, "data": <payload>, "meta": {...}}

    Error:
        {"success": false, "error": "<message>", "code": <http-status>}
"""

from __future__ import annotations

from typing import Any

from flask import jsonify


def success_response(
    data: Any,
    status_code: int = 200,
    meta: dict | None = None,
) -> tuple:
    """
    Wrap *data* in a successful JSON envelope.

    Args:
        data:        The payload to return.
        status_code: HTTP status code (default 200).
        meta:        Optional metadata dict (e.g. pagination info).

    Returns:
        Flask (response, status_code) tuple.
    """
    body: dict = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return jsonify(body), status_code


def error_response(message: str, status_code: int = 500) -> tuple:
    """
    Wrap an error message in a JSON error envelope.

    Args:
        message:     Human-readable error description.
        status_code: HTTP status code.

    Returns:
        Flask (response, status_code) tuple.
    """
    body: dict = {"success": False, "error": message, "code": status_code}
    return jsonify(body), status_code


def paginated_response(
    data: list,
    total: int,
    page: int,
    per_page: int,
    status_code: int = 200,
) -> tuple:
    """
    Return a paginated JSON response with navigation metadata.

    Args:
        data:      Page of records.
        total:     Total record count (all pages).
        page:      Current 1-based page number.
        per_page:  Records per page.
        status_code: HTTP status code.

    Returns:
        Flask (response, status_code) tuple.
    """
    meta = {
        "total":       total,
        "page":        page,
        "per_page":    per_page,
        "total_pages": max(1, -(-total // per_page)),  # ceiling division
        "has_next":    page * per_page < total,
        "has_prev":    page > 1,
    }
    return success_response(data, status_code=status_code, meta=meta)
