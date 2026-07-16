# WF Enterprise Analytics Platform

Flask application for FR Y-14Q Schedule H1 regulatory reporting.  Multi-entity
data grid with server-side pagination, multi-level drill-down, async export,
and schema-driven column definitions.  Adapters abstract CSV (dev), Dremio,
SQL Server, and Teradata behind a single interface.

---

## Features

| Feature | Detail |
|---------|--------|
| **Schema-driven grids** | Column definitions loaded from JSON — no JS changes when columns change |
| **Server-side pagination** | Sort/filter/paginate on the server; frontend receives one page at a time |
| **Apply Filters** | Sort and filter changes are batched; user clicks Apply to send one request |
| **Multi-level drill-down** | Facilities → Obligations → Property (auto-wired from config) |
| **Jira investigations** | row-actions "Open Investigation" creates a Jira ticket; an "Investigations" drill-down column shows ticket status/detail per facility |
| **Async export** | CSV, Excel, Parquet — background worker with polling status |
| **Multi-source adapters** | CSV, Dremio, SQL Server, Teradata — same interface |

---

## Folder Structure

```
app/
  __init__.py              Flask application factory
  config.py                ENTITIES config — single source of truth
  adapters/                BaseAdapter + CSV, Dremio, SQLServer, Teradata
  blueprints/
    main/routes.py         Page routes (/, /<entity_type>)
    api/routes.py          Data API (GET + POST /<entity> endpoints)
    export/routes.py       Export API (/api/exports/*)
    jira/routes.py         Jira API (/jira/*) — search, assignees, issue detail, create investigation
  jira/
    client.py              Reserved for a future dedicated Jira HTTP client; currently an empty
                            stub (all Jira REST calls live in services/jira_service.py)
  models/
    export_job.py          Export job dataclass
  repositories/
    base_repository.py     Static paginate() helper
    export_job_repository.py In-memory export job store
  schemas/                 JSON column descriptors + registry
  services/
    data_service.py        Adapter registry
    reporting_service.py   Generic get_entity() / put_entity() facade
    export_service.py      Job creation, validation, dispatch
    jira_service.py        JiraService — all Jira REST calls (search, create issue, attachments, transitions)
    jira_mappings.py       Jira issue field-mapping tables consumed by JiraService
  security/                Credential providers (Windows Credential Manager)
  workers/
    export_worker.py       Background thread pool worker
  templates/
    base.html              Master layout, APP_CONFIG injection
    entity.html            Generic entity page (all entities use this)
    components/            Header, sidebar, breadcrumb partials
  static/
    css/                   main.css, grid.css, modal.css, context-bar.css, export-tracker.css
    js/
      entity-page.js       Generic page (server-side pagination via queryFn); "Open Investigation" row action
      drill-down.js        Multi-level drill-down modal
      jira-investigations.js  "Investigations" drill-down — two-pane modal (ticket list + detail)
      grid-config.js       GridManager class + buildColumnsFromSchema()
      api-utils.js         GET/POST wrappers, toolbar wiring, KPI helpers
      context-bar.js       Date picker, localStorage persistence
      modal-manager.js     Stack-based modals + Toast notifications
      export-tracker.js    Polling export status badge
data/                      CSV files (one per entity, incl. investigation_assignees.csv, investigation_tracker.csv)
scripts/
  refresh_schema.py        Schema drift detection CLI
run.py                     Application entry point
```

---

## Setup

### Prerequisites

- Python 3.11+
- pip

### Install and run

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1     # Windows
# source .venv/bin/activate    # macOS / Linux

pip install -r requirements.txt
python run.py
```

Open **http://localhost:5000**

### Data files

CSV data files are in `data/`:

| File | Entity |
|------|--------|
| `facilities.csv` | Credit facilities (Schedule H1) |
| `obligations.csv` | Obligations linked to facilities |
| `property.csv` | Property collateral linked to obligations |

---

## API Endpoints

### Query endpoints (primary — server-side pagination)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/<entity>` | Paginated query with sort/filter |
| POST | `/api/<parent>/<child>` | Paginated child entity query |
| GET | `/api/schema/<entity>` | Column descriptors for grid setup |

POST body: `{ period_dt, page, per_page, sorts, col_filters, quick_filter, entity_key }`

### Export endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/exports` | Create async export job |
| GET | `/api/internal/exports/<id>/status` | Poll job status |
| GET | `/api/internal/exports/<id>/download` | Download completed file |

### Jira endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/jira/assignees` | List of investigation assignees (from `investigation_assignees` entity) |
| GET | `/jira/issues?keys=KEY1,KEY2` | Live Jira issue detail for the given keys (search + detail pane) |
| GET | `/jira/search` / `/jira/search2` | Raw JQL search passthrough |
| POST | `/jira/investigation/create` | Create a Jira issue for selected records, track it in `investigation_tracker`, attach reference CSVs |

All `/jira/*` routes return `503 {"error": "Jira integration is not configured"}` when
`JIRA_BASE_URL`/`JIRA_TOKEN` aren't set — see [Jira setup](#jira-setup) below.

---

## Architecture

```
POST /api/facilities { sorts, col_filters, page, per_page, period_dt }
  └─ routes.py → ReportingService.get_entity()
       └─ adapter.fetch(filters, sorts, page, per_page)
            CSV:        pandas filter/sort → slice page
            SQL Server: _build_query() → SQL WHERE/ORDER BY/OFFSET-FETCH (table-driven, no CTE)
            Dremio/Teradata: CTE wrapper → SQL WHERE/ORDER BY/OFFSET-FETCH
       └─ _enrich_with_child_counts()
       └─ _count_active() → KPI from full dataset
       └─ paginated_response(data, total, active)
```

- **Adapters** abstract the data source. Dremio/Teradata push filter/sort/paginate
  into SQL via a CTE wrapper around the base `_QUERY_MAP` query; SQL Server instead
  builds `SELECT ... FROM [schema].[table] WHERE ...` directly from `ENTITIES[*]["table"]`
  (see `ARCHITECTURE.md` for why SQL Server departs from the `_QUERY_MAP` pattern).
- **ReportingService** is the primary data-access facade — routes call `get_entity()`
  to read and `put_entity()` to write (used by the Jira investigation-tracking flow).
- **GridManager** in server-side mode sends `queryFn` POST requests.  Sort/filter
  changes are batched behind an Apply Filters button.  Page navigation auto-fires.

### Adding a new entity

1. Add to `ENTITIES` in `config.py` (source, pk, label_field, children)
2. Create data file (`data/<entity>.csv` or `_QUERY_MAP`/`table` entry)
3. Create schema (`app/schemas/<entity>.json` + register in `__init__.py`)
4. Add sidebar link in `components/sidebar.html`

No other code changes needed — routes, pages, drill-down, and export are generic.

---

## Jira setup

The Jira integration (`app/services/jira_service.py`, `app/blueprints/jira/`) is
**optional** — the app boots and runs fine without it; every `/jira/*` route just
returns a `503` until it's configured. To enable it on a machine with Jira access:

1. **Set the environment variables** before starting the server (no `.env` file
   support today — these must be real shell/OS environment variables):

   ```powershell
   $env:JIRA_BASE_URL = "https://your-jira-host"          # e.g. https://yoursite.atlassian.net
   $env:JIRA_TOKEN    = "<your Jira API token / PAT>"
   python run.py
   ```

2. **Restart the server after setting them** — `app.jira_service` is constructed
   once at startup (`app/__init__.py`); it won't pick up env var changes on a
   running process.

3. **Confirm it's live**: `GET /jira/assignees` should return your
   `investigation_assignees` reference data (no Jira call), and `GET /jira/issues?keys=<a-real-key>`
   should return live issue data from your Jira instance.

4. **Auth scheme note**: `jira_service.py` authenticates with
   `Authorization: Bearer <JIRA_TOKEN>` — the scheme used by on-prem **Jira
   Server/Data Center** Personal Access Tokens. **Jira Cloud** normally expects
   Basic Auth (`email:api_token`, base64-encoded) instead, so a Cloud instance
   will likely 401 with Bearer auth as-is. If your target is Jira Cloud, this
   auth code needs a Basic-auth path added before it will authenticate.

5. Optional: `PAGE_SIZE` (default `100`) controls how many issues `search_jira_issues`
   fetches per page when paginating a JQL search.

---

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` / `production` / `testing` |
| `SECRET_KEY` | dev key | Flask session secret |
| `JIRA_BASE_URL` | *(empty — disabled)* | Jira instance base URL; see [Jira setup](#jira-setup) |
| `JIRA_TOKEN` | *(empty — disabled)* | Jira API token / PAT (sent as a Bearer token) |
| `PAGE_SIZE` | `100` | Jira search pagination page size |

| Config class | Log level | Debug |
|---|---|---|
| `DevelopmentConfig` | DEBUG | on |
| `ProductionConfig` | WARNING | off |
| `TestingConfig` | DEBUG | on |
