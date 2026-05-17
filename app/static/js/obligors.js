/**
 * obligors.js — Standalone Obligors page bootstrap.
 *
 * Initialises the obligors AG Grid, wires toolbar controls,
 * and provides drill-down into transactions via DrillDown.openTransactions().
 *
 * Depends on: api-utils.js, grid-config.js, modal-manager.js, drill-down.js
 */
const ObligorsApp = (function () {

  /** @type {GridManager|null} */
  let _grid = null;

  /** @type {Object[]|null} */
  let _allRecords = null;

  // ── Column definitions ──────────────────────────────────────────────────────

  function _buildColumns() {
    return [
      ColumnHelper.text('obligor_id', 'Obligor ID', {
        width: 110, pinned: 'left',
      }),
      ColumnHelper.text('obligor_name', 'Name', {
        flex: 2, minWidth: 160, tooltipField: 'obligor_name',
      }),
      ColumnHelper.text('obligor_type', 'Type', {
        flex: 1, minWidth: 120,
      }),
      ColumnHelper.text('facility_id', 'Facility ID', {
        width: 110,
      }),
      ColumnHelper.text('industry', 'Industry', {
        flex: 1, minWidth: 130,
      }),
      ColumnHelper.text('sub_industry', 'Sub-Industry', {
        flex: 1, minWidth: 130, hide: true,
      }),
      ColumnHelper.text('country', 'Country', {
        width: 100, hide: true,
      }),
      ColumnHelper.number('credit_score', 'Credit Score', {
        width: 110, hide: true,
      }),
      ColumnHelper.money('exposure_amount', 'Exposure', {
        flex: 1, minWidth: 120,
      }),
      ColumnHelper.money('outstanding_amount', 'Outstanding', {
        flex: 1, minWidth: 120,
      }),
      {
        headerName:   'Status',
        field:        'status',
        width:        118,
        filter:       'agTextColumnFilter',
        cellRenderer: CellRenderer.status,
      },
      ColumnHelper.text('risk_grade', 'Risk Grade', {
        width: 110, hide: true,
      }),
      ColumnHelper.date('review_date', 'Review Date', {
        width: 110, hide: true,
      }),
      // Drill-down to transactions
      {
        headerName:   'Transactions',
        field:        'transaction_count',
        width:        120,
        pinned:       'right',
        sortable:     true,
        filter:       'agNumberColumnFilter',
        cellClass:    'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          DrillDown.openTransactions(
            p.data.obligor_id,
            p.data.obligor_name,
            p.data.facility_id,
            p.data.facility_id,
          );
        }),
      },
    ];
  }

  // ── KPI strip ──────────────────────────────────────────────────────────────

  function _updateKpi(records) {
    const total  = records.length;
    const active = records.filter(r => r.status === 'Active').length;

    const elTotal  = document.getElementById('kpiTotal');
    const elActive = document.getElementById('kpiActive');

    if (elTotal)  elTotal.textContent  = total.toLocaleString();
    if (elActive) elActive.textContent = active.toLocaleString();
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadObligors(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/obligors', { per_page: 1000, search });
      const resp = await ApiUtils.get(url);

      _allRecords = resp.data || [];
      _grid.setData(_allRecords);
      _updateKpi(_allRecords);

      setTimeout(() => _grid.getApi().sizeColumnsToFit(), 50);

    } catch (err) {
      Toast.error('Failed to load obligors', err.message || 'Please ensure the server is running.');
      console.error('Obligors load error:', err);
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {
    const gridSearch = document.getElementById('gridSearch');
    if (gridSearch) {
      let _debounce;
      gridSearch.addEventListener('input', () => {
        clearTimeout(_debounce);
        _debounce = setTimeout(() => {
          _grid.setQuickFilter(gridSearch.value);
        }, 200);
      });
    }

    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
      globalSearch.addEventListener('input', () => {
        if (gridSearch) gridSearch.value = globalSearch.value;
        _loadObligors(globalSearch.value.trim());
      });
    }

    const btnShowHide = document.getElementById('btnShowHideColumns');
    if (btnShowHide) {
      btnShowHide.addEventListener('click', () => _grid.toggleColumnsPanel(btnShowHide));
    }

    const btnClearFilters = document.getElementById('btnClearFilters');
    if (btnClearFilters) {
      btnClearFilters.addEventListener('click', () => {
        _grid.clearFilters();
        if (gridSearch) gridSearch.value = '';
        _grid.setQuickFilter('');
        Toast.info('Filters cleared', 'All column filters have been removed.');
      });
    }

    document.querySelectorAll('.btn-export[data-format]').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        if (fmt === 'csv') {
          _grid.exportCsv('obligors.csv');
          Toast.success('CSV exported', 'Downloading current view as CSV.');
        } else {
          ApiUtils.downloadFile(`/api/export/obligors?format=${fmt}`);
          Toast.success('Export started', `Downloading full obligors dataset as ${fmt.toUpperCase()}.`);
        }
      });
    });

    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar        = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebar.classList.toggle('collapsed');
        const main = document.getElementById('mainContent');
        if (main) main.classList.toggle('sidebar-collapsed');
        setTimeout(() => _grid && _grid.getApi().sizeColumnsToFit(), 200);
      });
    }
  }

  // ── Public init ────────────────────────────────────────────────────────────

  async function init() {
    _grid = new GridManager(
      'obligorsGrid',
      _buildColumns(),
      {
        paginationPageSize:         25,
        paginationPageSizeSelector: [10, 25, 50, 100],
      }
    ).init();

    _wireToolbar();
    await _loadObligors();

    Toast.success('Obligors ready', `${(_allRecords || []).length} obligors loaded.`, undefined, 3000);
  }

  return { init };

}());
