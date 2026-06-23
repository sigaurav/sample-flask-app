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
    api/routes.py          Data API (GET + POST /query endpoints)
    export/routes.py       Export API (/api/exports/*)
  models/
    export_job.py          Export job dataclass
  repositories/
    base_repository.py     Static paginate() helper
    export_job_repository.py In-memory export job store
  schemas/                 JSON column descriptors + registry
  services/
    data_service.py        Adapter registry
    reporting_service.py   Generic get_entity() facade
    export_service.py      Job creation, validation, dispatch
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
      entity-page.js       Generic page (server-side pagination via queryFn)
      drill-down.js        Multi-level drill-down modal
      grid-config.js       GridManager class + buildColumnsFromSchema()
      api-utils.js         GET/POST wrappers, toolbar wiring, KPI helpers
      context-bar.js       Date picker, localStorage persistence
      modal-manager.js     Stack-based modals + Toast notifications
      export-tracker.js    Polling export status badge
data/                      CSV files (one per entity)
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
| POST | `/api/<entity>/query` | Paginated query with sort/filter |
| POST | `/api/<parent>/<child>/query` | Paginated child entity query |

POST body: `{ fic_mis_date, page, per_page, sorts, col_filters, quick_filter, entity_key }`

### Backward-compatible GET endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/<entity>` | Query params: page, per_page, search, fic_mis_date |
| GET | `/api/<parent>/<child>` | Same + FK params |
| GET | `/api/schema/<entity>` | Column descriptors for grid setup |

### Export endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/exports` | Create async export job |
| GET | `/api/internal/exports/<id>/status` | Poll job status |
| GET | `/api/internal/exports/<id>/download` | Download completed file |

---

## Architecture

```
POST /api/facilities/query { sorts, col_filters, page, per_page, fic_mis_date }
  └─ routes.py → ReportingService.get_entity()
       └─ adapter.fetch(filters, sorts, page, per_page)
            CSV:  pandas filter/sort → slice page
            DB:   CTE wrapper → SQL WHERE/ORDER BY/OFFSET-FETCH
       └─ _enrich_with_child_counts()
       └─ _count_active() → KPI from full dataset
       └─ paginated_response(data, total, active)
```

- **Adapters** abstract the data source.  DB adapters push filter/sort/paginate
  into SQL via a CTE wrapper around the base `_QUERY_MAP` query.
- **ReportingService** is the only data-access facade — all routes call `get_entity()`.
- **GridManager** in server-side mode sends `queryFn` POST requests.  Sort/filter
  changes are batched behind an Apply Filters button.  Page navigation auto-fires.

### Adding a new entity

1. Add to `ENTITIES` in `config.py` (source, pk, label_field, children)
2. Create data file (`data/<entity>.csv` or `_QUERY_MAP` entry)
3. Create schema (`app/schemas/<entity>.json` + register in `__init__.py`)
4. Add sidebar link in `components/sidebar.html`

No other code changes needed — routes, pages, drill-down, and export are generic.

---

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` / `production` / `testing` |
| `SECRET_KEY` | dev key | Flask session secret |

| Config class | Log level | Debug |
|---|---|---|
| `DevelopmentConfig` | DEBUG | on |
| `ProductionConfig` | WARNING | off |
| `TestingConfig` | DEBUG | on |
