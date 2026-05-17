/**
 * app.js — Application bootstrap and main facility grid.
 *
 * Initialises the facility AG Grid on the dashboard page,
 * wires toolbar controls (search, filters, export, show/hide columns),
 * and populates the KPI strip.
 *
 * Depends on: api-utils.js, grid-config.js, modal-manager.js, drill-down.js
 */
const WFApp = (function () {

  /** @type {GridManager|null} The main facility grid manager. */
  let _facilityGrid = null;

  /** @type {Object[]|null} Raw facility data from API (all pages). */
  let _allFacilities = null;

  // ── Facility column definitions ────────────────────────────────────────────
  //
  // Strategy: pinned / chip / date columns keep a fixed `width`.
  //           Name / text / money columns use `flex` so AG Grid distributes
  //           the remaining space proportionally — no horizontal scroll.

  function _buildFacilityColumns() {
    return [
      // ── Pinned left (fixed widths) ───────────────────────────────────────
      ColumnHelper.text('facility_id', 'Facility ID', {
        width: 115, pinned: 'left',
      }),

      // ── Flex columns — share available space ─────────────────────────────
      ColumnHelper.text('facility_name', 'Facility Name', {
        flex: 2, minWidth: 160, tooltipField: 'facility_name',
      }),
      ColumnHelper.text('facility_type', 'Type', {
        flex: 1.5, minWidth: 130,
      }),
      ColumnHelper.money('credit_limit', 'Credit Limit', {
        flex: 1, minWidth: 115,
      }),
      ColumnHelper.money('outstanding_balance', 'Outstanding', {
        flex: 1, minWidth: 115,
      }),

      // ── Fixed-size columns ────────────────────────────────────────────────
      {
        headerName:   'Utilisation',
        field:        'utilization_pct',
        width:        150,
        filter:       'agNumberColumnFilter',
        sortable:     true,
        cellRenderer: CellRenderer.utilisation,
      },
      {
        headerName:   'Status',
        field:        'status',
        width:        118,
        filter:       'agTextColumnFilter',
        cellRenderer: CellRenderer.status,
      },
      {
        headerName:   'Risk',
        field:        'risk_rating',
        width:        95,
        filter:       'agTextColumnFilter',
        cellRenderer: CellRenderer.riskRating,
      },
      ColumnHelper.text('relationship_manager', 'Rel. Manager', {
        flex: 1, minWidth: 130,
      }),
      ColumnHelper.text('region', 'Region', { width: 95 }),

      // ── Hidden columns (toggle via Columns panel) ─────────────────────────
      ColumnHelper.money('available_credit', 'Available',     { flex: 1, minWidth: 110, hide: true }),
      ColumnHelper.text('currency',           'Currency',     { width: 85,  hide: true }),
      ColumnHelper.number('risk_score',       'Risk Score',   { width: 95,  hide: true }),
      ColumnHelper.text('country',            'Country',      { width: 110, hide: true }),
      ColumnHelper.date('created_date',       'Created',      { width: 105, hide: true }),
      ColumnHelper.date('maturity_date',      'Maturity',     { width: 105, hide: true }),
      ColumnHelper.number('interest_rate',    'Rate (%)',     { width: 85,  hide: true }),

      // ── Pinned right — drill-down trigger ────────────────────────────────
      {
        headerName: 'Obligors',
        field:      'obligor_count',
        width:      98,
        pinned:     'right',
        sortable:   true,
        filter:     'agNumberColumnFilter',
        cellClass:  'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          DrillDown.openObligors(p.data.facility_id, p.data.facility_name);
        }),
      },
    ];
  }

  // ── KPI strip ──────────────────────────────────────────────────────────────

  function _updateKpi(facilities) {
    const total  = facilities.length;
    const active = facilities.filter(f => f.status === 'Active').length;

    const elTotal  = document.getElementById('kpiTotal');
    const elActive = document.getElementById('kpiActive');

    if (elTotal)  elTotal.textContent  = total.toLocaleString();
    if (elActive) elActive.textContent = active.toLocaleString();
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadFacilities(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/facilities', { per_page: 500, search });
      const resp = await ApiUtils.get(url);

      _allFacilities = resp.data || [];
      _facilityGrid.setData(_allFacilities);
      _updateKpi(_allFacilities);

      // Resize flex columns after data arrives so the grid has a known width
      setTimeout(() => _facilityGrid.getApi().sizeColumnsToFit(), 50);

    } catch (err) {
      Toast.error('Failed to load facilities', err.message || 'Please ensure the server is running and data has been generated.');
      console.error('Facility load error:', err);
    }
  }

  // ── Toolbar wiring ────────────────────────────────────────────────────────

  function _wireToolbar() {

    // Grid search box
    const gridSearch = document.getElementById('gridSearch');
    if (gridSearch) {
      let _debounce;
      gridSearch.addEventListener('input', () => {
        clearTimeout(_debounce);
        _debounce = setTimeout(() => {
          _facilityGrid.setQuickFilter(gridSearch.value);
        }, 200);
      });
    }

    // Global header search (mirrors grid search)
    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
      globalSearch.addEventListener('input', () => {
        if (gridSearch) gridSearch.value = globalSearch.value;
        _loadFacilities(globalSearch.value.trim());
      });
    }

    // Show/hide columns panel
    const btnShowHide = document.getElementById('btnShowHideColumns');
    if (btnShowHide) {
      btnShowHide.addEventListener('click', () => {
        _facilityGrid.toggleColumnsPanel();
      });
    }

    // Clear filters
    const btnClearFilters = document.getElementById('btnClearFilters');
    if (btnClearFilters) {
      btnClearFilters.addEventListener('click', () => {
        _facilityGrid.clearFilters();
        if (gridSearch) gridSearch.value = '';
        _facilityGrid.setQuickFilter('');
        Toast.info('Filters cleared', 'All column filters have been removed.');
      });
    }

    // Export buttons
    document.querySelectorAll('.btn-export[data-format]').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        if (fmt === 'csv') {
          _facilityGrid.exportCsv('facilities.csv');
          Toast.success('CSV exported', 'Downloading current view as CSV.');
        } else {
          ApiUtils.downloadFile(`/api/export/facilities?format=${fmt}`);
          Toast.success('Export started', `Downloading full facilities dataset as ${fmt.toUpperCase()}.`);
        }
      });
    });

    // Sidebar toggle — collapse/expand sidebar and re-fit grid columns
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar        = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebar.classList.toggle('collapsed');
        const main = document.getElementById('mainContent');
        if (main) main.classList.toggle('sidebar-collapsed');

        // Re-fit flex columns once CSS transition (150 ms) completes
        setTimeout(() => _facilityGrid && _facilityGrid.getApi().sizeColumnsToFit(), 200);
      });
    }
  }

  // ── Public init ────────────────────────────────────────────────────────────

  async function init() {
    _facilityGrid = new GridManager(
      'facilityGrid',
      _buildFacilityColumns(),
      {
        sideBar: {
          toolPanels: [
            {
              id:           'columns',
              labelDefault: 'Columns',
              labelKey:     'columns',
              iconKey:      'columns',
              toolPanel:    'agColumnsToolPanel',
              toolPanelParams: {
                suppressRowGroups: true, suppressValues: true,
                suppressPivots: true,   suppressPivotMode: true,
              },
            },
            {
              id:           'filters',
              labelDefault: 'Filters',
              labelKey:     'filters',
              iconKey:      'filter',
              toolPanel:    'agFiltersToolPanel',
            },
          ],
          defaultToolPanel: '',
        },
        paginationPageSize:         25,
        paginationPageSizeSelector: [10, 25, 50, 100],
      }
    ).init();

    _wireToolbar();
    await _loadFacilities();

    Toast.success('Dashboard ready', `${(_allFacilities || []).length} facilities loaded.`, undefined, 3000);
  }

  return { init };

}());
