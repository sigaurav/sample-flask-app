# WF Enterprise Analytics — Architecture Guide

## What the application does

FR Y-14Q Schedule H1 analytics platform.  Reads wholesale credit data
(Facilities → Obligations → Property) from configurable data sources
(CSV, Dremio, SQL Server, Teradata), renders schema-driven grids with
multi-level drill-down, and exports results asynchronously.

---

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | Flask (Python) |
| Data wrangling | pandas |
| Data sources | CSV (default), Dremio, SQL Server, Teradata |
| Frontend grids | Custom `GridManager` (wraps ag-Grid Community) |
| Async exports | `ThreadPoolExecutor` (in-process, Phase 1) |
| Templating | Jinja2 |

---

## Directory layout

```
app/
  __init__.py               Application factory (create_app)
  config.py                 All configuration — ENTITIES is the key dict
  adapters/                 One class per data source
    base_adapter.py         Abstract base with shared pandas filters
    csv_adapter.py
    dremio_adapter.py
    sqlserver_adapter.py
    teradata_adapter.py
  blueprints/
    main/routes.py          Page routes  (/, /<entity_type>)
    api/routes.py           Data API     (/api/<entity>, /api/<parent>/<child>)
    export/routes.py        Export API   (/api/exports/*)
  models/
    export_job.py           Export job dataclass
  repositories/
    base_repository.py      Static paginate() helper
    export_job_repository.py In-memory export job store
  schemas/
    __init__.py             Schema registry (loads JSON, caches, exposes helpers)
    facilities.json         Column descriptors for Facilities
    obligations.json        Column descriptors for Obligations
    property.json           Column descriptors for Property
  services/
    data_service.py         Adapter registry
    reporting_service.py    Generic get_entity() — the only data-access facade
    export_service.py       Job creation, validation, dispatch
  static/js/
    entity-page.js          Generic standalone page (init for any entity type)
    drill-down.js           Generic multi-level drill-down modal
    grid-config.js          GridManager class + buildColumnsFromSchema()
    api-utils.js            Fetch wrapper, context injection, KPI helpers
    context-bar.js          SOR + date picker, localStorage persistence
    export-tracker.js       Polling export status badge
  templates/
    base.html               Shell: nav, context bar, script includes, APP_CONFIG
    entity.html             Generic entity page (title, grid, toolbar — all templated)
    components/             Shared partials (header, sidebar, breadcrumb)
workers/
  export_worker.py          Background thread worker
scripts/
  refresh_schema.py         Schema drift CLI
```

---

## Configuration: ENTITIES is the single source of truth

`app/config.py` contains one dict that drives the entire application:

```python
ENTITIES = {
    "facilities": {
        "source":        "csv",          # which adapter to use
        "label":         "Credit Facilities",  # display name
        "pk":            ["FACLTY_ID", "FACLTY_OBLGR_ID"],
        "label_field":   "OBLIGOR_NAME", # column used in breadcrumbs
        "active_filter": {"field": "ACTIVE_FLAG", "value": "Y"},  # KPI strip
        "columns":       ["*"],          # column selection sent to adapter
        "children": {
            "obligations": {
                "fk":        ["LOANNUMBER"],        # FK on the child table
                "count_col": "OBLIGATION_COUNT",    # computed column added to parent rows
            },
            "property": {
                "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                "count_col": "PROPERTY_COUNT",
            },
        },
    },
    "obligations": { ... },
    "property":    { ... },
}
```

Everything else reads from this dict at runtime:

| Component | What it reads |
|---|---|
| `DataService` | `source` values → which adapters to initialise |
| `ReportingService` | `children[*].fk` and `children[*].count_col` → enrichment |
| `api/routes.py` | `children` dict → validates parent/child pairs |
| `main/routes.py` | `label` → page title, breadcrumb, KPI heading |
| `entity.html` | `entity_type` variable → grid div ID, `EntityPage.init()` call |
| `drill-down.js` | `APP_CONFIG.entities` → FK columns, grandchild drill handlers |
| `entity-page.js` | `APP_CONFIG.entities` → drill handlers, active KPI predicate |
| `base.html` | Serialises entire `ENTITIES` dict into `window.APP_CONFIG.entities` |

`ENABLED_DATA_SOURCES` acts as a gateway: only sources that appear in
**both** `ENTITIES[*].source` and `ENABLED_DATA_SOURCES` get an adapter
instance.  Removing a source from the allowlist prevents connections
without touching entity config.

---

## Request lifecycle — page load

```
Browser GET /obligations
  └─ main/routes.py: entity_page("obligations")
       └─ _render_entity("obligations")
            reads ENTITIES["obligations"]["label"] → "Obligations"
            └─ render_template("entity.html",
                   entity_type="obligations",
                   entity_label="Obligations")
                   serialises ENTITIES → window.APP_CONFIG.entities
```

`entity.html` is the only page template.  Jinja fills in:

| Expression | Result |
|---|---|
| `{{ entity_label }}` | `Obligations` |
| `id="{{ entity_type }}Grid"` | `id="obligationsGrid"` |
| `EntityPage.init('{{ entity_type }}')` | `EntityPage.init('obligations')` |

---

## Request lifecycle — data API

```
Browser GET /api/obligations?sor=1SOR&fic_mis_date=2024-01-31&per_page=500
  └─ api/routes.py: get_entity("obligations")
       validates entity_type in ENTITIES
       └─ ReportingService.get_entity("obligations", ...)
            └─ DataService.get_adapter_for_entity("obligations")
                 reads ENTITIES["obligations"]["source"] → "csv"
                 returns CSVAdapter
            CSVAdapter.fetch("obligations", filters={"_sor": "1SOR", ...})
              applies context filter (FACLTY_SOR_ID + PERIOD_DT)
              applies quick_filter, col_filters, sorts
              applies column selection
            _enrich_with_child_counts(df, "obligations", ctx)
              reads ENTITIES["obligations"]["children"]
              fetches property rows, groupby FACLTY_ID+FACLTY_OBLGR_ID → counts
              adds PROPERTY_COUNT column to df
            BaseRepository.paginate(df, page, per_page)
            _schema_coerce_records(df_page, "obligations")
              filters to columns declared in obligations.json schema
              coerces numeric fields to float
            returns {"records": [...], "total": N, "page": 1, "per_page": 500}
  └─ paginated_response(...)  →  {"data": [...], "meta": {...}}
```

---

## Request lifecycle — drill-down (child entity)

```
Browser GET /api/facilities/obligations?LOANNUMBER=LN-001&sor=1SOR&...
  └─ api/routes.py: get_child_entity("facilities", "obligations")
       reads ENTITIES["facilities"]["children"]["obligations"]
       fk_cols = ["LOANNUMBER"]
       fk_vals = {"LOANNUMBER": "LN-001"}
       └─ ReportingService.get_entity("obligations",
              entity_key={"LOANNUMBER": "LN-001"}, ...)
            CSVAdapter.fetch("obligations",
                entity_key={"LOANNUMBER": "LN-001"}, ...)
              filters df where LOANNUMBER == "LN-001"
            _enrich_with_child_counts(...)  # adds PROPERTY_COUNT
            _schema_coerce_records(...)
```

The route validates the parent/child relationship against `ENTITIES` before
calling the service — an invalid pair (e.g. `/api/property/obligations`)
returns 404.

---

## Schema system

Each entity has a JSON schema file in `app/schemas/`.  Every entry is a
column descriptor:

```json
{
  "field": "COMMITMENT_AMT",
  "label": "Commitment Amount",
  "type":  "money",
  "flex":  1,
  "minWidth": 120
}
```

Key descriptor keys:

| Key | Purpose |
|---|---|
| `field` | Column name in source data and API JSON key |
| `label` | Grid header and export header |
| `type` | `text` / `number` / `money` / `date` / `drill` — drives coercion and renderer |
| `computed` | `true` → count column added by service, not in source file |
| `drill_target` | Entity name the drill column opens (e.g. `"obligations"`) |
| `searchable` | `true` → included in quick-filter search |
| `deprecated` | `true` → hidden from grid, search, export (set by refresh script) |
| `hide` | `true` → column hidden by default but user can show it |
| `pinned` | `"left"` or `"right"` |

`app/schemas/__init__.py` loads files on first access and caches them.
`get_schema()`, `get_api_fields()`, and `get_numeric_fields()` are the
public helpers used by `ReportingService`.

### Keeping schemas in sync

```bash
# Check drift between CSV headers and schema file
python scripts/refresh_schema.py --entity facilities

# Apply changes (new columns added, removed columns marked deprecated)
python scripts/refresh_schema.py --entity facilities --apply

# Check all entities at once
python scripts/refresh_schema.py --all --apply
```

The script reads entity names from `ENTITIES` config, uses each entity's
configured adapter for column introspection, and never deletes schema
entries — removed columns are marked `"deprecated": true` to preserve
export history.

---

## Frontend architecture

### `window.APP_CONFIG`

Injected by `base.html` before any other script runs:

```javascript
window.APP_CONFIG = {
  enabledSors: ["1SOR", "2SOR", "3SOR"],
  entities: {
    "facilities": {
      "source": "csv", "label": "Credit Facilities",
      "pk": ["FACLTY_ID", "FACLTY_OBLGR_ID"],
      "label_field": "OBLIGOR_NAME",
      "active_filter": {"field": "ACTIVE_FLAG", "value": "Y"},
      "children": {
        "obligations": {"fk": ["LOANNUMBER"], "count_col": "OBLIGATION_COUNT"},
        "property": {"fk": ["FACLTY_ID", "FACLTY_OBLGR_ID"], "count_col": "PROPERTY_COUNT"}
      }
    },
    ...
  }
};
```

Every JS module reads from this instead of hardcoding FK columns or entity
names.

### Query context

`ContextBar` (context-bar.js) stores `{sor, fic_mis_date}` in
`localStorage["wf_query_context"]`.  `ApiUtils` reads this on every
outgoing request and appends `?sor=...&fic_mis_date=...` automatically —
individual JS modules never handle context params manually.

### Entity page flow

```
DOMContentLoaded
  └─ EntityPage.init("facilities")              [entity-page.js]
       GET /api/schema/facilities
         → schema JSON array
       buildColumnsFromSchema(schema, drillHandlers)   [grid-config.js]
         maps each descriptor to a GridManager column def
         wires drill columns to DrillDown.open() closures
       new GridManager("facilitiesGrid", columnDefs).init()
       ApiUtils.wireGridToolbar(grid, loadFn)
       ApiUtils.wireExportDropdown(grid, "facilities", "Credit Facilities")
       _loadData("facilities", grid)
         GET /api/facilities?per_page=500&sor=...&fic_mis_date=...
         grid.setData(records)
         ApiUtils.updateKpi(records, activeFilter predicate)
```

### Drill-down flow

```
User clicks drill cell in facilities grid
  └─ DrillDown.open("facilities", "obligations", rowData, "Acme Corp")
       reads APP_CONFIG.entities["facilities"].children["obligations"].fk
         → ["LOANNUMBER"]
       fkValues = { LOANNUMBER: rowData["LOANNUMBER"] }
       ModalManager.open({ title: "Obligations", breadcrumb: [...] })
         └─ _mountModal(panel, "facilities", "obligations", fkValues, "Acme Corp")
              GET /api/schema/obligations
              reads APP_CONFIG.entities["obligations"].children
                → { "property": {...} }          ← auto-wires next level
              drillHandlers["property"] = (p) => DrillDown.open(
                "obligations", "property", p.data, labelForRow, "Acme Corp"
              )
              buildColumnsFromSchema(schema, drillHandlers)
              new GridManager("drill-grid-obligations-LN-001", columnDefs).init()
              GET /api/facilities/obligations?LOANNUMBER=LN-001&sor=...
              grid.setData(records)
```

`DrillDown.open()` is fully recursive — it reads the opened entity's
children from config and auto-wires handlers for the next level.  Adding a
fourth level to the hierarchy requires only a config change; no JS changes.

### `buildColumnsFromSchema(schema, drillHandlers)`

Converts the JSON schema array into GridManager column defs.  The
`drill_target` key is the bridge between schema and JS: the schema says
`"drill_target": "obligations"` and the caller provides a closure at
`drillHandlers["obligations"]`.  This keeps the schema JSON-serialisable
while allowing context-specific closures at call time.

---

## Export system

```
User clicks "Full Export" in a grid toolbar
  └─ ApiUtils.triggerExportJob({entity_type, export_type, file_format, ...})
       POST /api/exports/
         └─ ExportService.create_job(...)
              creates ExportJob(status=QUEUED)
              persists in ExportJobRepository (in-memory)
              DataService.get_adapter_for_entity(entity_type) → adapter
              submit_export_job(job, adapter, export_dir)
                └─ ThreadPoolExecutor.submit(_run_export, job_id, adapter, export_dir)
                   returns immediately
       returns { job_id: "abc123" }
  export-tracker.js polls GET /api/exports/{job_id} every few seconds
    shows status badge: QUEUED → RUNNING → COMPLETED
    on COMPLETED: shows download link
```

The `entity_id` field on an export job is a JSON-encoded FK dict for
drill-down exports (e.g. `'{"LOANNUMBER": "LN-001"}'`), decoded by the
worker to scope the fetch.

---

## Adding a new entity

**Example: add a "collateral" entity.**

### 1. Add to `ENTITIES` in `app/config.py`

```python
"collateral": {
    "source":      "csv",           # or "dremio", "sqlserver"
    "label":       "Collateral",
    "pk":          ["COLLAT_ID"],
    "label_field": "COLLAT_DESC",
    "columns":     ["*"],
    "children":    {},              # add children here if needed
},
```

If collateral is a child of obligations, add to the obligations block:

```python
"obligations": {
    ...
    "children": {
        "property":    { ... },
        "collateral":  {"fk": ["OBLGN_ID"], "count_col": "COLLATERAL_COUNT"},
    },
},
```

### 2. Create the data file

Drop `data/collateral.csv` with appropriate columns.

### 3. Generate the schema JSON

```bash
python scripts/refresh_schema.py --entity collateral --apply
```

Review `app/schemas/collateral.json`.  Set `"drill_target"` on any drill
column, adjust `"type"`, `"hide"`, `"pinned"` as needed.  Update
`app/schemas/__init__.py` to include `"collateral": "collateral.json"` in
`_REGISTRY_FILES`.

### 4. Add a sidebar link

In `app/templates/components/sidebar.html`, add one `<a>` tag pointing to
`/collateral`.  The route, the page template, the API endpoints, and the
drill-down handlers are all generated automatically from the config.

### 5. Done

- `GET /collateral` → `entity.html` with `entity_type="collateral"`, `entity_label="Collateral"`
- `GET /api/collateral` → generic route, returns paginated collateral records
- `GET /api/obligations/collateral?OBLGN_ID=...` → drill-down route (if child relationship declared)
- `DrillDown.open("obligations", "collateral", ...)` → works with zero JS changes

---

## Switching a data source

To move obligations from CSV to Dremio:

1. Ensure `"dremio"` is in `ENABLED_DATA_SOURCES`.
2. Change `ENTITIES["obligations"]["source"]` from `"csv"` to `"dremio"`.
3. Set Dremio connection config (`DREMIO_HOST`, `DREMIO_PORT`, `DREMIO_SOURCE`).

No other code changes needed.  `DataService` initialises the Dremio adapter
at startup, and `get_adapter_for_entity("obligations")` returns it.

---

## Environment configuration

```bash
# Development (default): CSV data, debug logging
python run.py

# Production
FLASK_ENV=production python run.py

# Point refresh_schema.py at production source
FLASK_ENV=production python scripts/refresh_schema.py --all
```

Config classes in `app/config.py`:

| Class | Log level | Debug | Log file |
|---|---|---|---|
| `DevelopmentConfig` | DEBUG | on | `logs/wf_analytics.log` |
| `ProductionConfig` | WARNING | off | `logs/wf_analytics.log` |
| `TestingConfig` | DEBUG | on | none |
