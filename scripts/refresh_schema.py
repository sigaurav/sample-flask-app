"""
refresh_schema.py — CLI to detect drift between the active data source and JSON schema files.

Usage:
    python scripts/refresh_schema.py --entity facilities
    python scripts/refresh_schema.py --entity facilities --apply
    python scripts/refresh_schema.py --all

The script uses whichever adapter is currently configured in ENABLED_DATA_SOURCES
(csv / dremio / sqlserver) — set FLASK_ENV to target a specific environment.

    FLASK_ENV=production python scripts/refresh_schema.py --all

Each run compares the live source columns against the corresponding JSON schema file:
  - NEW columns (in source, not in schema) → appended as hidden text fields
  - REMOVED columns (in schema, not in source) → marked {"deprecated": true}
  - Key columns ("key": "primary" or "foreign") → never deprecated
  - Computed columns ("computed": true) → skipped in both directions
  - Context columns (SOR, FIC_MIS_DATE) → always ignored

Git provides the audit trail: commit the updated JSON files after applying.
"""

import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR   = os.path.join(_PROJECT_ROOT, "app", "schemas")

sys.path.insert(0, _PROJECT_ROOT)

_ENTITIES = ["facilities", "obligors", "transactions", "comments"]

_CONTEXT_COLUMNS = {"SOR", "FIC_MIS_DATE"}


# ── Schema file helpers ───────────────────────────────────────────────────────

def _load_schema(entity_type: str) -> list[dict]:
    path = os.path.join(_SCHEMA_DIR, entity_type + ".json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_schema(entity_type: str, schema: list[dict]) -> None:
    path = os.path.join(_SCHEMA_DIR, entity_type + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ── Drift detection ───────────────────────────────────────────────────────────

def _diff(entity_type: str, source_cols: list[str]) -> dict:
    source_cols = [c for c in source_cols if c not in _CONTEXT_COLUMNS]
    schema      = _load_schema(entity_type)
    schema_live = [c for c in schema if not c.get("computed") and not c.get("deprecated")]
    schema_keys = {c["field"] for c in schema_live}
    source_set  = set(source_cols)

    added   = [c for c in source_cols if c not in schema_keys]
    removed = [
        c["field"] for c in schema_live
        if c["field"] not in source_set and c.get("key") not in ("primary", "foreign")
    ]
    return {"added": added, "removed": removed, "schema": schema}


def _print_diff(entity_type: str, diff: dict) -> None:
    if not diff["added"] and not diff["removed"]:
        print(f"  {entity_type}: no drift detected")
        return
    if diff["added"]:
        print(f"  {entity_type}: NEW   → {diff['added']}")
    if diff["removed"]:
        print(f"  {entity_type}: GONE  → {diff['removed']}")


def _apply_diff(entity_type: str, diff: dict) -> None:
    if not diff["added"] and not diff["removed"]:
        return

    schema = diff["schema"]

    for field in diff["removed"]:
        for col in schema:
            if col["field"] == field:
                col["deprecated"] = True
                break

    first_computed = next(
        (i for i, c in enumerate(schema) if c.get("computed")), len(schema)
    )
    for field in diff["added"]:
        schema.insert(first_computed, {
            "field": field,
            "label": field.replace("_", " ").title(),
            "type": "text",
            "hide": True,
            "searchable": False,
        })
        first_computed += 1

    _save_schema(entity_type, schema)
    print(f"  {entity_type}: schema file updated")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect and apply schema drift between the active data source and JSON schema files."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--entity", choices=_ENTITIES, help="Single entity to check")
    group.add_argument("--all",    action="store_true", help="Check all entities")
    parser.add_argument("--apply", action="store_true", help="Write changes to JSON schema files")
    args = parser.parse_args()

    entities = _ENTITIES if args.all else [args.entity]

    # ── Resolve the active adapter via the Flask app ──────────────────────────
    from app import create_app
    flask_app = create_app(os.getenv("FLASK_ENV", "development"))
    adapter   = flask_app.data_service.get_adapter()
    print(f"Source: {adapter.source_type}  (set FLASK_ENV to switch environment)\n")

    # ── Introspect columns and diff ───────────────────────────────────────────
    print("Checking schema drift…")
    diffs: dict = {}
    for ent in entities:
        source_cols  = adapter.introspect_columns(ent)
        diffs[ent]   = _diff(ent, source_cols)
        _print_diff(ent, diffs[ent])

    has_drift = any(d["added"] or d["removed"] for d in diffs.values())
    if not has_drift:
        print("\nAll schemas are up to date.")
        return

    if not args.apply:
        print("\nRe-run with --apply to write changes.")
        return

    print("\nApplying changes…")
    for ent in entities:
        _apply_diff(ent, diffs[ent])
    print("\nDone. Commit the updated JSON files to preserve the audit trail.")


if __name__ == "__main__":
    main()
