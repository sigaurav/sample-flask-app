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
    sqlserver_adapter.py    Table-driven _build_query() with filter/sort/paginate (no CTE — see below)
    teradata_adapter.py     CTE-wrapped SQL with filter/sort/paginate
  blueprints/
    main/routes.py          Page routes  (/, /<entity_type>)
    api/routes.py           Data API     (GET + POST /<entity> endpoints)
    export/routes.py        Export API   (/api/exports/*)
    jira/routes.py          Jira API     (/jira/*)
  jira/
    client.py                Reserved for a future dedicated Jira HTTP client — currently an
                              empty stub; all Jira REST calls live in services/jira_service.py
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
    investigation_assignees.json  Column descriptors for the Jira-assignee reference list
    investigation_tracker.json    Column descriptors for created Jira tickets per record
  services/
    data_service.py         Adapter registry
    reporting_service.py    Generic get_entity()/put_entity() — the primary data-access facade
    export_service.py       Job creation, validation, dispatch
    jira_service.py         JiraService — all Jira REST calls (search/create/attach/transition)
    jira_mappings.py        Jira issue field-mapping tables consumed by JiraService
  security/
    credential_provider.py  Abstract credential interface
    windows_credential_provider.py  Windows Credential Manager via keyring
  static/js/
    entity-page.js          Generic standalone page (server-side pagination); "Open Investigation" row action
    drill-down.js           Generic multi-level drill-down modal
    jira-investigations.js  "Investigations" drill-down — two-pane modal (ticket list + detail)
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
                "fk_child":  ["LOAN_NUMBER"],
                "count_col": "OBLIGATION_COUNT",
            },
            "property": {
                "fk":        ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                "fk_child":  ["FACLTY_ID", "FACLTY_OBLGR_ID"],
                "count_col": "PROPERTY_COUNT",
            },
            "investigation_tracker": {
                "fk": [
                    "PERIOD_DT", "FACLTY_SOR_ID", "FACLTY_BNK_NBR_ID",
                    "FACLTY_ID", "FACLTY_OBLGR_ID", "FACLTY_AU_CD",
                ],
                "fk_child":            ["entity_key"],
                "concat_separator":    "|",
                "child_static_filter": {"field": "entity_type", "value": "facilities"},
                "count_col":           "INVESTIGATION_COUNT",
            },
        },
    },
    "obligations": { ... },
    "property":    { ... },
}
```

### `child_static_filter` (optional) — polymorphic child tables

Some child tables are **polymorphic**: `investigation_tracker` stores rows for
multiple different parent entities (facilities, obligations, property) in one
table, discriminated by an `entity_type` column. The `fk`/`fk_child` join alone
can't express "and also only rows where `entity_type == 'facilities'`" — that's
what `child_static_filter` adds:

```python
"child_static_filter": {"field": "entity_type", "value": "facilities"},
```

- **`ReportingService._enrich_with_child_counts`** filters the child dataframe
  down to matching rows before computing the count.
- **`api/routes.py` `get_child_entity`** merges `{field: value}` directly into the
  `entity_key` dict passed to `ReportingService.get_entity()` — no adapter changes
  needed, since `entity_key`-based exact-match filtering already applies every key
  in the dict generically (`CSVAdapter.fetch`, `SQLServerAdapter._build_query`).
- Omit it entirely for non-polymorphic child tables (the existing default).

Everything else reads from this dict at runtime:

| Component | What it reads |
|---|---|
| `DataService` | `source` values → which adapters to initialise |
| `ReportingService` | `children[*].fk`, `fk_child`, `count_col` → enrichment |
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
| `POST` | `/api/<entity>` | Paginated query with sort/filter (primary) |
| `POST` | `/api/<parent>/<child>` | Paginated child entity query |
| `GET`  | `/api/schema/<entity>` | Column descriptors for grid setup |
| `GET`  | `/jira/assignees` | Investigation-assignee reference list |
| `GET`  | `/jira/issues?keys=K1,K2` | Live Jira issue detail for the given keys |
| `POST` | `/jira/investigation/create` | Create a Jira issue, track it, attach reference CSVs |

### POST body (query endpoints)

```json
{
  "period_dt": "2024-01-31",
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

### DB adapter query patterns

**Dremio and Teradata** push filter/sort/paginate into SQL via a CTE wrapped
around a developer-written base query from `_QUERY_MAP`:

```sql
WITH _base AS (
    -- developer-written query from _QUERY_MAP (untouched)
    SELECT f.*, o.OBLIGOR_NAME
    FROM [dbo].[H1_FACILITIES] f
    JOIN [dbo].[OBLIGORS] o ON f.OBLGR_ID = o.OBLGR_ID
    WHERE f.[PERIOD_DT] = :period_dt
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

**SQL Server departs from this pattern.** Instead of a `_QUERY_MAP` string per
entity, `SQLServerAdapter._build_query()` builds `SELECT ... FROM [schema].[table]
WHERE ...` directly from `ENTITIES[entity_type]["table"]`, appending `ORDER BY` and
`OFFSET/FETCH` onto the same statement (no CTE needed since it already selects
straight from the table). `_build_query()` is the single query path for both
`fetch()` and `fetch_count()` (the latter with `count_only=True`, selecting
`COUNT(*)` and skipping sort/pagination). This is an intentional, adapter-specific
exception — Dremio/Teradata are unchanged and still expect a `_QUERY_MAP` entry.

CSV adapter uses in-memory pandas filtering (DuckDB cache planned for
Phase 2).

---

## Request lifecycle — data query

```
Browser POST /api/facilities
  { period_dt, page, per_page, sorts, col_filters }
  └─ api/routes.py: get_entity("facilities")
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

`ContextBar` (context-bar.js) stores `{period_dt}` in
`localStorage["wf_query_context"]`.  For GET requests, `ApiUtils`
appends `?period_dt=...` automatically.  For POST query requests,
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
         └─ POST /api/facilities { page:1, per_page:75, sorts:[pk], ... }
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
              grid.applyFilters()  →  POST /api/facilities/obligations
                { entity_key: {LOANNUMBER: "LN-001"}, page:1, per_page:30, ... }
```

### Jira "Investigations" drill-down flow

A second kind of drill-down — a bespoke two-pane modal instead of a `GridManager`
child grid — surfaces Jira tickets filed against a facility:

```
User clicks the "Investigations" drill cell in facilities grid
  └─ JiraInvestigations.open("facilities", rowData)       [jira-investigations.js]
       ModalManager.open({ onMount })
         └─ POST /api/facilities/investigation_tracker    (existing generic child-entity route;
              { entity_key: {<6-column fk>}, ... }          entity_key includes the
                                                              child_static_filter's entity_type too)
              → investigation_tracker rows for this facility (jira_key, createdDate)
         └─ GET /jira/issues?keys=<jira_key,...>           (only if the above returned rows)
              → JiraService.search_jira_issues(jql="key in (...)")
              → live summary/status/priority/assignee/description/created/updated
         └─ top pane: one row per ticket (key + live summary/status)
            bottom pane: full detail of the selected ticket (from the same fetch — no extra request)
```

### "Open Investigation" row-action flow

```
User selects row(s) → clicks "..." action button → "Open Investigation"
  └─ entity-page.js: openInvestigationModal(entityType, records, grid)
       ModalManager.open({ onMount })         # onMount injects the form HTML into .modal-body itself —
                                               # ModalManager never accepts a `body` option
         EasyMDE editors for description / acceptance criteria (Markdown → Jira wiki markup client-side)
         GET /jira/assignees → populate assignee <select>
       On submit → POST /jira/investigation/create
         { priority, summary, assignee: {assignee_emailaddress, assignee_jiraproject},
           description_data, acceptancecriteria_data, records }
         └─ JiraService.create_jira_issue(...)
         └─ ReportingService.put_entity("investigation_tracker", records_to_insert)
         └─ ReportingService.get_reference_records_csv_outputfile_path(...) × 3
              (facilities / obligations / property reference CSVs)
         └─ JiraService.add_jira_attachments(jira_key, csv_paths)
              on failure → JiraService.transition_jira_issue_by_name(..., "Cancel")
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
   `label_field`, `children` (each child needs `fk` + `fk_child` + `count_col`;
   add `concat_separator` if the child stores a concatenated key, and
   `child_static_filter` if the child table is polymorphic across parents)
2. **Data file** — `data/<entity>.csv` (CSV) or `_QUERY_MAP`/`table` entry in DB adapter
3. **Schema file** — `app/schemas/<entity>.json` + register in `__init__.py`
4. **Sidebar link** — add nav entry in `components/sidebar.html`
5. Run `python scripts/refresh_schema.py --entity <entity>` to validate

No other code changes needed — routes, pages, drill-down, and export are
fully generic.

---

## Jira integration

Lives mostly outside the generic entity-graph machinery: `app/services/jira_service.py`
(`JiraService`) wraps every Jira REST call (search, create issue, attachments,
transitions) behind a `{success, status_code, data, error}` envelope, using
`app/services/jira_mappings.py`'s field-mapping tables to normalize raw Jira JSON.
`app/blueprints/jira/routes.py` is the thin HTTP layer on top of it.

- **Optional at boot.** `app/__init__.py` only constructs `JiraService` (and sets
  `app.jira_service`) when `JIRA_BASE_URL`/`JIRA_TOKEN` are both configured;
  otherwise `app.jira_service = None` and every `/jira/*` route returns a `503`
  via a shared `_require_jira_service()` guard. This keeps the rest of the app
  fully usable with no Jira access at all.
- **Two entities back it**: `investigation_assignees` (a small reference list —
  who can be assigned a ticket, and which Jira project) and `investigation_tracker`
  (one row per created ticket: `entity_type`, `entity_key`, `jira_key`, `createdDate`).
  Both are ordinary CSV-backed `ENTITIES` entries — no special-casing beyond the
  `child_static_filter` extension described above.
- **Two frontend surfaces** consume it, both described under Request Lifecycle
  above: the **"Open Investigation" row action** (creates a ticket) and the
  **"Investigations" drill-down** (reads tickets back, live from Jira).
- **Auth**: Bearer-token (`Authorization: Bearer <JIRA_TOKEN>`), matching on-prem
  Jira Server/Data Center PATs. Jira **Cloud** normally requires Basic Auth
  instead — this is a known gap if the target is Cloud, not yet implemented.
- To enable it on a machine with Jira access, see **README.md → Jira setup**.

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

# With Jira enabled (either environment) — see README.md → Jira setup
JIRA_BASE_URL=https://your-jira-host JIRA_TOKEN=<token> python run.py
```

| Class | Log level | Debug | Log file |
|---|---|---|---|
| `DevelopmentConfig` | DEBUG | on | `logs/wf_analytics.log` |
| `ProductionConfig` | WARNING | off | `logs/wf_analytics.log` |
| `TestingConfig` | DEBUG | on | none |

| Variable | Default | Description |
|---|---|---|
| `JIRA_BASE_URL` | *(empty)* | Jira instance base URL. Unset → `app.jira_service` is `None`, `/jira/*` returns 503 |
| `JIRA_TOKEN` | *(empty)* | Jira API token / PAT, sent as `Authorization: Bearer <token>` |
| `PAGE_SIZE` | `100` | Page size `JiraService.search_jira_issues` uses when paginating a JQL search |
