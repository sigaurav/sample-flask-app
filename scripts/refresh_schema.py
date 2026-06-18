"""
refresh_schema.py — CLI to detect drift between the active data source and JSON schema files.

Usage:
    python scripts/refresh_schema.py --entity facilities
    python scripts/refresh_schema.py --entity facilities --apply
    python scripts/refresh_schema.py --all

The script reads ENTITIES config directly (no Flask app needed) and creates only
the adapter required by each entity being checked. Set FLASK_ENV to target a
specific environment.

    FLASK_ENV=production python scripts/refresh_schema.py --all

Each run compares the live source columns against the corresponding JSON schema file:
  - NEW columns (in source, not in schema) -> appended as hidden text fields
  - REMOVED columns (in schema, not in source) -> marked {"deprecated": true}
  - Key columns ("key": "primary" or "foreign") -> never deprecated
  - Computed columns ("computed": true) -> skipped in both directions
  - Context columns (SOR, FIC_MIS_DATE) -> always ignored

Git provides the audit trail: commit the updated JSON files after applying.
"""

import argparse
import json
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCHEMA_DIR   = os.path.join(_PROJECT_ROOT, "app", "schemas")

sys.path.insert(0, _PROJECT_ROOT)

_CONTEXT_COLUMNS = {"SOR", "FIC_MIS_DATE"}


def _load_config() -> dict:
    """Load Flask config without starting the app or initialising any adapters."""
    from app.config import config_map
    name = os.getenv("FLASK_ENV", "development")
    cls  = config_map.get(name, config_map.get("default"))
    if cls is None:
        raise RuntimeError(f"No config found for FLASK_ENV={name!r}")
    cfg = {}
    for key in dir(cls):
        if not key.startswith("_"):
            cfg[key] = getattr(cls, key)
    if "DATA_DIR" not in cfg or not cfg["DATA_DIR"]:
        cfg["DATA_DIR"] = os.path.join(_PROJECT_ROOT, "data")
    return cfg


def _get_adapter(config: dict, entity_type: str):
    """Instantiate only the adapter needed for this entity — no other adapters are touched."""
    entities = config.get("ENTITIES", {})
    source   = entities.get(entity_type, {}).get("source", "csv")

    if source == "csv":
        from app.adapters.csv_adapter import CSVAdapter
        return CSVAdapter(config)

    if source == "dremio":
        from app.adapters.dremio_adapter import DremioAdapter
        try:
            from app.security.windows_credential_provider import WindowsCredentialProvider
            cp = WindowsCredentialProvider()
        except Exception:
            cp = None
        return DremioAdapter(config, cp)

    if source == "sqlserver":
        from app.adapters.sqlserver_adapter import SQLServerAdapter
        return SQLServerAdapter(config)

    if source == "teradata":
        from app.adapters.teradata_adapter import TeradataAdapter
        return TeradataAdapter(config)

    from app.adapters.csv_adapter import CSVAdapter
    return CSVAdapter(config)


def _infer_type(field: str) -> str:
    """Guess a schema type from the column name as a best-effort default."""
    name = field.lower()
    if name.endswith(("_amt", "_amount")):
        return "money"
    if name.endswith(("_date", "_dt", "_ts", "_timestamp")):
        return "date"
    if name.endswith(("_pct", "_rate", "_score", "_count", "_qty", "_num")):
        return "number"
    return "text"


# -- Schema file helpers -------------------------------------------------------

def _load_schema(entity_type: str) -> list:
    path = os.path.join(_SCHEMA_DIR, entity_type + ".json")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_schema(entity_type: str, schema: list) -> None:
    path = os.path.join(_SCHEMA_DIR, entity_type + ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, ensure_ascii=False)
        f.write("\n")


# -- Drift detection ----------------------------------------------------------

def _diff(entity_type: str, source_cols: list) -> dict:
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
        print(f"  {entity_type}: NEW   -> {diff['added']}")
    if diff["removed"]:
        print(f"  {entity_type}: GONE  -> {diff['removed']}")


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
        inferred = _infer_type(field)
        schema.insert(first_computed, {
            "field":      field,
            "label":      field.replace("_", " ").title(),
            "type":       inferred,
            "hide":       True,
            "searchable": inferred == "text",
        })
        first_computed += 1

    _save_schema(entity_type, schema)
    print(f"  {entity_type}: schema file updated")


# -- Entry point --------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect and apply schema drift between the active data source and JSON schema files."
    )
    parser.add_argument("--apply", action="store_true", help="Write changes to JSON schema files")
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--entity", metavar="ENTITY", help="Single entity to check")
    target_group.add_argument("--all",    action="store_true", help="Check all entities")
    args = parser.parse_args()

    config       = _load_config()
    all_entities = list(config.get("ENTITIES", {}).keys())

    if not all_entities:
        print("ERROR: No entities found in config. Check FLASK_ENV and app/config.py.")
        sys.exit(1)

    if args.entity:
        if args.entity not in all_entities:
            parser.error(f"Unknown entity '{args.entity}'. Known: {all_entities}")
        entities = [args.entity]
    else:
        entities = all_entities

    env = os.getenv("FLASK_ENV", "development")
    print(f"Entities: {entities}  (FLASK_ENV={env})\n")

    print("Checking schema drift...")
    diffs = {}
    for ent in entities:
        adapter     = _get_adapter(config, ent)
        source_cols = adapter.introspect_columns(ent)
        diffs[ent]  = _diff(ent, source_cols)
        _print_diff(ent, diffs[ent])

    has_drift = any(d["added"] or d["removed"] for d in diffs.values())
    if not has_drift:
        print("\nAll schemas are up to date.")
        return

    if not args.apply:
        print("\nRe-run with --apply to write changes.")
        return

    print("\nApplying changes...")
    for ent in entities:
        _apply_diff(ent, diffs[ent])
    print("\nDone. Commit the updated JSON files to preserve the audit trail.")


if __name__ == "__main__":
    main()
