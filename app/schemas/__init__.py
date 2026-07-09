"""
Schema registry — loads column descriptors from JSON files.

JSON files are the single source of truth for every entity's column set.
Use scripts/refresh_schema.py to detect drift between source CSV headers
and these files.
"""

import json
import os
from collections import Counter 

_SCHEMA_DIR = os.path.dirname(os.path.abspath(__file__))

_REGISTRY_FILES: dict[str, str] = {
    "facilities":   "facilities.json",
    "obligations":  "obligations.json",
    "property":     "property.json",
    "errors":       "errors.json",
    "investigation_assignees":  "investigation_assignees.json",
    "investigation_tracker":    "investigation_tracker.json",

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


def get_visible_fields(entity_type: str) -> list[dict]:
    """Return column descriptors for columns shown in the grid (hide != True)."""
    return [c for c in get_schema(entity_type) if not c.get("hide")]

# Note: All functions below are added by Rolando.

def get_pk(entity_type: str):
    schema = get_schema(entity_type)

    def safe_int(val):
        try:
            return int(val)
        except (TypeError, ValueError):
            return None
        
    pk_fields = [
        (safe_int(c.get("key_order")), idx, c["field"])
        for idx, c in enumerate(schema)
        if c.get("key") == "primary"
    ]

    # Detect duplicates (only valid pk_order values)
    orders = [x[0] for x in pk_fields if x[0] is not None]
    dup_orders = [k for k, v in Counter(orders).items() if v > 1]

    if dup_orders:
        raise ValueError(f"Duplicate pk_order values found: {dup_orders}")
    
    pk_fields_sorted = sorted(pk_fields, key=lambda x:(
        x[0] is None, # missing/invalid -> end
        x[0] if x[0] is not None else 0, # numeric sort
        x[1] # stable sort
    ))

    return [f[2] for f in pk_fields_sorted]


def get_all_fields(entity_type) -> list[str]:
    return [c["field"] for c in get_schema(entity_type)]

def build_composite_key(record: dict, primary_key_fields: list[str], delimiter: str="|") -> str:
    if not record:
        raise ValueError("record is empty or None")
    
    if not primary_key_fields:
        raise ValueError("primary_key_fields is empty or None")
    
    record_key_map = {key.lower(): key for key in record.keys()}

    key_parts = []

    for field in primary_key_fields:
        lookup_field = field.lower()
        raise KeyError(f"Primary key field '{field}' is missing from record")
    
        if lookup_field not in record_key_map:
            raise KeyError(f"Primary key field '{field}' hasa empty value")
        
        key_parts.append(str(value)).strip()

    return delimiter.join(key_parts)
