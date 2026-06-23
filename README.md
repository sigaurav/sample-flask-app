# WF Enterprise Analytics Platform

A professional enterprise-grade web application for credit facility portfolio management with multi-level drill-down capabilities. Built with Python / Flask / WF Grid Community.

---

## Screenshots & Features

| Feature | Detail |
|---------|--------|
| **Dashboard** | WF-inspired banking UI — deep red, gold accents |
| **Main Grid** | 100 facilities with sorting, filtering, pagination, column management |
| **Drill-Down L2** | Click Obligors count → modal with 500 obligors |
| **Drill-Down L3** | Click Transactions count → nested modal with 5 000 transactions |
| **Drill-Down L4** | Click Comments count → deepest modal with 2 000 analyst comments |
| **Export** | CSV, Excel (.xlsx), Parquet — at every drill-down level |

---

## Folder Structure

```
SampleApp4/
├── app/
│   ├── __init__.py              # Flask application factory
│   ├── config.py                # Hierarchical config classes
│   ├── controllers/             # Flask Blueprints (routes)
│   │   ├── main_controller.py   # Page routes
│   │   ├── api_controller.py    # JSON data API
│   │   └── export_controller.py # File download API
│   ├── services/                # Business logic layer
│   │   ├── base_service.py      # ABC for all services
│   │   ├── facility_service.py
│   │   ├── obligor_service.py
│   │   ├── transaction_service.py
│   │   └── export_service.py
│   ├── repositories/            # CSV data access layer
│   │   ├── base_repository.py   # ABC with cache + helpers
│   │   ├── facility_repository.py
│   │   ├── obligor_repository.py
│   │   ├── transaction_repository.py
│   │   └── comment_repository.py
│   ├── models/                  # Dataclass domain models
│   │   ├── facility.py
│   │   ├── obligor.py
│   │   ├── transaction.py
│   │   └── comment.py
│   ├── utils/
│   │   ├── logger.py            # Centralised logging setup
│   │   └── response_utils.py    # JSON response envelope helpers
│   ├── templates/
│   │   ├── base.html            # Master layout (header, sidebar, scripts)
│   │   ├── dashboard.html       # Main facility grid page
│   │   └── components/
│   │       ├── header.html
│   │       ├── sidebar.html
│   │       └── breadcrumb.html
│   └── static/
│       ├── css/
│       │   ├── main.css         # WF-themed layout & components
│       │   ├── grid.css         # WF Grid custom theme overrides
│       │   └── modal.css        # Stacked modal system styles
│       └── js/
│           ├── api-utils.js     # Fetch wrapper, loading overlay
│           ├── grid-config.js   # GridManager, ColumnHelper, CellRenderer
│           ├── modal-manager.js # Stack-based modal + Toast system
│           ├── drill-down.js    # 4-level drill-down orchestrator
│           └── app.js           # Dashboard bootstrap, main grid
├── data/                        # Generated CSV files (git-ignored)
├── exports/                     # Temporary export files
├── generate_data.py             # Synthetic data generator
├── run.py                       # Application entry point
└── requirements.txt
```

---

## Setup Instructions

### 1. Prerequisites

- Python 3.12 (3.11+ should work too)
- pip

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Generate sample data (run once)

```bash
python generate_data.py
```

This creates four CSV files in the `data/` directory:

| File | Rows | Description |
|------|------|-------------|
| `facilities.csv` | 100 | Credit facility register |
| `obligors.csv` | 500 | Borrowers mapped to facilities |
| `transactions.csv` | 5 000 | Financial transactions per obligor |
| `comments.csv` | 2 000 | Analyst notes per transaction |

### 5. Start the application

```bash
python run.py
```

Open your browser at **http://localhost:5000**

---

## Demo Workflow

1. **Load dashboard** — 100 facilities displayed in the main WF Grid
2. **Sort / filter** — click column headers, use the filter icon
3. **Search** — type in the search box (top-left of toolbar)
4. **Show / Hide columns** — click the Columns button
5. **Click an Obligors count** (red link) → obligors modal opens
6. **Click a Transactions count** → nested transaction modal opens
7. **Click a Comments count** → deepest comments modal opens
8. **Export** — use CSV / Excel / Parquet buttons at any level

---

## API Endpoints

### Data endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/facilities` | Paginated facilities with obligor counts |
| GET | `/api/facilities/<id>` | Single facility |
| GET | `/api/facilities/<id>/obligors` | Paginated obligors for a facility |
| GET | `/api/obligors/<id>/transactions` | Paginated transactions for an obligor |
| GET | `/api/transactions/<id>/comments` | Paginated comments for a transaction |

**Common query parameters:**
- `page` (int, default 1)
- `per_page` (int, default 50, max 500)
- `search` (str, searches multiple fields)

### Export endpoints

| Method | Path | Formats |
|--------|------|---------|
| GET | `/api/export/facilities` | csv, excel, parquet |
| GET | `/api/export/facilities/<id>/obligors` | csv, excel, parquet |
| GET | `/api/export/obligors/<id>/transactions` | csv, excel, parquet |
| GET | `/api/export/transactions/<id>/comments` | csv, excel, parquet |

**Query parameter:** `?format=csv` (or `excel`, `parquet`)

---

## Architecture

### Backend (Python / Flask)

```
Request → Blueprint Controller → Service → Repository → CSV
                                     ↓
                               Domain Model
                                     ↓
                         JSON Response (success envelope)
```

- **Controllers**: Thin HTTP layer — parse params, call service, return JSON
- **Services**: Business logic — enrichment (obligor counts, transaction counts), pagination
- **Repositories**: Data access — CSV loading, caching, filtering, searching
- **Models**: Typed dataclasses with `to_dict()` / `from_dict()` methods

### Frontend (Vanilla JS)

```
WFApp.init()
  └─ GridManager (facility grid)
       └─ CellRenderer.drillDownLink (Obligors column)
            └─ DrillDown.openObligors()
                 └─ ModalManager.open()
                      └─ GridManager (obligors grid)
                           └─ DrillDown.openTransactions()
                                └─ ModalManager.open()  [stacked]
                                     └─ GridManager (transactions grid)
                                          └─ DrillDown.openComments()
```

- **GridManager**: Wraps `agGrid.createGrid()`, manages lifecycle
- **ColumnHelper / CellRenderer**: Typed column factories
- **ModalManager**: Stack-based modals with CSS transitions
- **Toast**: Auto-dismissing notification system
- **ApiUtils**: Fetch wrapper with loading overlay management
- **DrillDown**: Orchestrates all four drill-down levels

### Drill-Down Architecture (extensible)

Adding a new drill-down level requires:
1. A new repository method (`filter_by`)
2. A new service method (enrichment + pagination)
3. A new API endpoint in `api_controller.py`
4. A new export endpoint in `export_controller.py`
5. A new `DrillDown.openXxx()` function in `drill-down.js`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | `development` | `development` / `production` / `testing` |
| `SECRET_KEY` | dev key | Flask session secret |
| `HOST` | `0.0.0.0` | Bind address |
| `PORT` | `5000` | Bind port |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, Flask 3.0 |
| Templates | Jinja2 |
| Data | pandas, CSV files |
| Export | pandas + openpyxl (Excel), pyarrow (Parquet) |
| Frontend | Vanilla JavaScript (ES2020), HTML5, CSS3 |
| Grid | WF Grid Community 31.3.2 (CDN) |
| Styling | Custom CSS — WF design system |
