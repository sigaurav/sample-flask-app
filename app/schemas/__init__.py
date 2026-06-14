"""
Schema registry — loads column descriptors from JSON files.

JSON files are the single source of truth for every entity's column set.
Use scripts/refresh_schema.py to detect drift between source CSV headers
and these files.
"""

import json
import os

_SCHEMA_DIR = os.path.dirname(os.path.abspath(__file__))

_REGISTRY_FILES: dict[str, str] = {
    "facilities":   "facilities.json",
    "obligations":  "obligations.json",
    "property":     "property.json",
}

_CACHE: dict[str, list] = {}


def _load(entity_type: str) -> list:
    path = os.path.join(_SCHEMA_DIR, _REGISTRY_FILES[entity_type])
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_schema(entity_type: str, include_deprecated: bool = False) -> list:
    if entity_type not in _CACHE:
        _CACHE[entity_type] = _load(entity_type)
    schema = _CACHE[entity_type]
    if include_deprecated:
        return schema
    return [c for c in schema if not c.get("deprecated")]


def get_api_fields(entity_type: str) -> list[str]:
    return [c["field"] for c in get_schema(entity_type)]


def get_numeric_fields(entity_type: str) -> list[str]:
    return [c["field"] for c in get_schema(entity_type) if c["type"] in ("number", "money")]
