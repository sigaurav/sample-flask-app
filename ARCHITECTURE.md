# WF Enterprise Analytics — Architecture Guide

## What the application does

FR Y-14Q Schedule H1 analytics platform.  Reads wholesale credit data
(Facilities → Obligations → Property) from configurable data sources
(CSV, Dremio, SQL Server, Teradata), renders schema-driven grids with
multi-level drill-down, server-side pagination, and exports results
asynchronously.

---

## Technology stack

| Layer | Technology |
|---|---|
| Web framework | Flask (Python) |
| Data wrangling | pandas |
| Data sources | CSV (default), Dremio, SQL Server, Teradata |
| Frontend grids | Custom `GridManager` (no external dependencies) |
| Async exports | `ThreadPoolExecutor` (in-process) |
| Templating | Jinja2 |

---

## Directory layout

```
app/
  __init__.py               Application factory (create_app)
  config.py                 All configuration — ENTITIES is the key dict
  adapters/                 One class per data source
    base_adapter.py         Abstract base with shared pandas filters + SQL helpers
    csv_adapter.py
    dremio_adapter.py       CTE-wrapped SQL with filter/sort/paginate
    sqlserver_adapter.py    CTE-wrapped SQL with filter/sort/paginate
    teradata_adapter.py     CTE-wrapped SQL with filter/sort/paginate
  blueprints/
    main/routes.py          Page routes  (/, /<entity_type>)
    api/routes.py           Data API     (GET + POST /query endpoints)
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
  security/
    credential_provider.py  Abstract credential interface
    windows_credential_provider.py  Windows Credential Manager via keyring
  static/js/
    entity-page.js          Generic standalone page (server-side pagination)
    drill-down.js           Generic multi-level drill-down modal
    grid-config.js          GridManager class + buildColumnsFromSchema()
    api-utils.js            GET/POST wrappers, toolbar wiring, KPI helpers
    context-bar.js          Date picker, localStorage persistence
    modal-manager.js        Stack-based modal system + Toast notifications
    export-tracker.js       Polling export status badge
  templates/
    base.html               Shell: nav, context bar, script includes, APP_CONFIG
    entity.html             Generic entity page (title, grid, toolbar)
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
        "source":        "csv",
        "label":         "Credit Facilities",
        "pk":            ["FACLTY_ID", "FACLTY_OBLGR_ID"],
        "label_field":   "OBLIGOR_NAME",
        "active_filter": {"field": "ACTIVE_FLAG", "value": "Y"},
        "columns":       ["*"],
        "children": {
            "obligations": {
                "fk":        ["LOANNUMBER"],
                "child_fk":  ["LOAN_NUMBER"],
                "count_col": "OBLIGATION_COUNT",
            },
            "property": {
                "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                "child_fk":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
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
| `ReportingService` | `children[*].fk`, `child_fk`, `count_col` → enrichment |
| `api/routes.py` | `children` dict → validates parent/child pairs |
| `main/routes.py` | `label` → page title, breadcrumb, KPI heading |
| `entity.html` | `entity_type` variable → grid div ID, `EntityPage.init()` call |
| `drill-down.js` | `APP_CONFIG.entities` → FK columns, grandchild drill handlers |
| `entity-page.js` | `APP_CONFIG.entities` → drill handlers, active KPI predicate |
| `base.html` | Serialises entire `ENTITIES` dict into `window.APP_CONFIG.entities` |

---

## Server-side pagination

All data queries use server-side pagination.  The frontend sends sort/filter
state to the server, which applies it and returns one page of data.

### API endpoints

| Verb | Route | Purpose |
|---|---|---|
| `POST` | `/api/<entity>/query` | Paginated query with sort/filter (primary) |
| `POST` | `/api/<parent>/<child>/query` | Paginated child entity query |
| `GET`  | `/api/<entity>` | Backward-compatible (used by exports) |
| `GET`  | `/api/<parent>/<child>` | Backward-compatible |
| `GET`  | `/api/schema/<entity>` | Column descriptors for grid setup |

### POST body (query endpoints)

```json
{
  "fic_mis_date": "2024-01-31",
  "page": 1,
  "per_page": 75,
  "sorts": [{"field": "OBLIGOR_NAME", "dir": "asc"}],
  "col_filters": {"ACTIVE_FLAG": {"op": "equals", "val": "Y"}},
  "quick_filter": "",
  "entity_key": {"LOANNUMBER": "LN-001"}
}
```

### Response shape

```json
{
  "success": true,
  "data": [ ... 75 records ... ],
  "meta": {
    "total": 19766,
    "active": 19766,
    "page": 1,
    "per_page": 75,
    "total_pages": 264,
    "has_next": true,
    "has_prev": false
  }
}
```

### Frontend batch fetching

GridManager in server-side mode fetches 3 pages at a time.  Page
navigation within the batch is instant (from buffer).  Navigating
outside the buffer triggers a new server request.

Sort and filter changes are **not** sent immediately — they set a
"pending changes" state.  The user clicks **Apply Filters** to send
one consolidated request.  Page navigation auto-fires with current
sort/filter state.

### DB adapter CTE pattern

DB adapters (SQL Server, Dremio, Teradata) push filter/sort/paginate
into SQL so the database engine handles it.  The base query from
`_QUERY_MAP` is wrapped in a CTE:

```sql
WITH _base AS (
    -- developer-written query from _QUERY_MAP (untouched)
    SELECT f.*, o.OBLIGOR_NAME
    FROM [dbo].[H1_FACILITIES] f
    JOIN [dbo].[OBLIGORS] o ON f.OBLGR_ID = o.OBLGR_ID
    WHERE f.[PERIOD_DT] = :fic_mis_date
)
-- dynamic wrapper built from user's sort/filter spec
SELECT * FROM _base
WHERE [ACTIVE_FLAG] = :_f0
ORDER BY [OBLIGOR_NAME] ASC
OFFSET :_offset ROWS FETCH NEXT :_limit ROWS ONLY
```

Any `ORDER BY` in the base query is stripped automatically — the outer
query provides its own.  The base query can contain joins, subqueries,
CTEs, or any SQL complexity.

CSV adapter uses in-memory pandas filtering (DuckDB cache planned for
Phase 2).

---

## Request lifecycle — data query

```
Browser POST /api/facilities/query
  { fic_mis_date, page, per_page, sorts, col_filters }
  └─ api/routes.py: query_entity("facilities")
       validates entity_type in ENTITIES
       └─ ReportingService.get_entity("facilities", sorts=..., col_filters=...)
            └─ DataService.get_adapter_for_entity("facilities")
                 reads ENTITIES["facilities"]["source"] → "csv"
                 returns CSVAdapter
            CSVAdapter.fetch("facilities", filters={...}, sorts=[...])
              applies context filter (PERIOD_DT)
              applies col_filters, quick_filter, sorts
            _enrich_with_child_counts(df, "facilities", ctx)
              fetches obligations → groupby → OBLIGATION_COUNT
              fetches property → groupby → PROPERTY_COUNT
            _count_active(df, "facilities") → active count from full dataset
            BaseRepository.paginate(df, page, per_page) → one page
            _schema_coerce_records(df_page, "facilities") → API records
       returns paginated_response with meta.total, meta.active
```

---

## Query context (date only)

`ContextBar` (context-bar.js) stores `{fic_mis_date}` in
`localStorage["wf_query_context"]`.  For GET requests, `ApiUtils`
appends `?fic_mis_date=...` automatically.  For POST query requests,
the `queryFn` includes it in the JSON body.

---

## Frontend architecture

### `window.APP_CONFIG`

Injected by `base.html` before any other script runs:

```javascript
window.APP_CONFIG = {
  entities: { ... },    // full ENTITIES dict from config.py
  maxPageSize: 100000
};
```

### Entity page flow

```
DOMContentLoaded
  └─ EntityPage.init("facilities")              [entity-page.js]
       GET /api/schema/facilities → schema JSON
       buildColumnsFromSchema(schema, drillHandlers)
       new GridManager("facilitiesGrid", columnDefs, { queryFn }).init()
       wire Apply Filters button → grid.applyFilters()
       grid.applyFilters()  →  initial server fetch
         └─ POST /api/facilities/query { page:1, per_page:75, sorts:[pk], ... }
         └─ updateKpi(resp.meta)  → total + active from server
```

### Drill-down flow

```
User clicks drill cell in facilities grid
  └─ DrillDown.open("facilities", "obligations", rowData, "Acme Corp")
       ModalManager.open(...)
         └─ _mountModal(...)
              GET /api/schema/obligations
              new GridManager(..., { queryFn }).init()
              grid.applyFilters()  →  POST /api/facilities/obligations/query
                { entity_key: {LOANNUMBER: "LN-001"}, page:1, per_page:30, ... }
```

### `buildColumnsFromSchema(schema, drillHandlers)`

Converts the JSON schema array into GridManager column defs.  The
`drill_target` key is the bridge between schema and JS: the schema says
`"drill_target": "obligations"` and the caller provides a closure at
`drillHandlers["obligations"]`.

---

## Export system

```
User clicks "Full Export" in a grid toolbar
  └─ ApiUtils.triggerExportJob({entity_type, export_type, file_format, ...})
       POST /api/exports/
         └─ ExportService.create_job(...)
              creates ExportJob(status=QUEUED)
              submits to ThreadPoolExecutor
       returns { job_id: "abc123" }
  export-tracker.js polls GET /api/internal/exports/{job_id}/status
    on COMPLETED: triggers download
```

---

## Adding a new entity — checklist

1. **`app/config.py`** — add block to `ENTITIES` with `source`, `pk`,
   `label_field`, `children` (each child needs `fk` + `child_fk` + `count_col`)
2. **Data file** — `data/<entity>.csv` (CSV) or `_QUERY_MAP` entry in DB adapter
3. **Schema file** — `app/schemas/<entity>.json` + register in `__init__.py`
4. **Sidebar link** — add nav entry in `components/sidebar.html`
5. Run `python scripts/refresh_schema.py --entity <entity>` to validate

No other code changes needed — routes, pages, drill-down, and export are
fully generic.

---

## Switching a data source

To move obligations from CSV to Dremio:

1. Ensure `"dremio"` is in `ENABLED_DATA_SOURCES`.
2. Change `ENTITIES["obligations"]["source"]` from `"csv"` to `"dremio"`.
3. Add an entry to `DremioAdapter._QUERY_MAP["obligations"]`.
4. Set Dremio connection config (`DREMIO_HOST`, `DREMIO_PORT`, `DREMIO_SOURCE`).

`DataService` initialises the Dremio adapter at startup, and
`get_adapter_for_entity("obligations")` returns it.  The DB adapter
pushes filter/sort/paginate into SQL via the CTE pattern.

---

## Environment configuration

```bash
# Development (default): CSV data, debug logging
python run.py

# Production
FLASK_ENV=production python run.py
```

| Class | Log level | Debug | Log file |
|---|---|---|---|
| `DevelopmentConfig` | DEBUG | on | `logs/wf_analytics.log` |
| `ProductionConfig` | WARNING | off | `logs/wf_analytics.log` |
| `TestingConfig` | DEBUG | on | none |
