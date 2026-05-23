/**
 * obligors.js — FR Y-14Q Schedule H1 Counterparty Register page bootstrap.
 *
 * Initialises the counterparty grid, wires toolbar controls including
 * the async export dropdown, and provides drill-down into exposure events.
 *
 * Depends on: api-utils.js, grid-config.js, modal-manager.js, drill-down.js
 */
const ObligorsApp = (function () {

  let _grid       = null;
  let _allRecords = null;

  // ── Column definitions ─────────────────────────────────────────────────────

  function _buildColumns() {
    return [
      ColumnHelper.text('obligor_id', 'Obligor ID', {
        width: 125, pinned: 'left',
      }),
      ColumnHelper.text('obligor_name', 'Obligor Name', {
        flex: 2, minWidth: 180, tooltipField: 'obligor_name',
      }),
      ColumnHelper.text('obligor_type', 'Obligor Type', {
        flex: 1, minWidth: 130,
      }),
      ColumnHelper.text('facility_id', 'Facility ID', { width: 110 }),
      ColumnHelper.text('industry',    'Industry',    { flex: 1, minWidth: 140 }),
      ColumnHelper.text('sub_industry','Sub-Industry',{ flex: 1, minWidth: 140, hide: true }),
      ColumnHelper.text('country',     'Country',     { width: 100, hide: true }),
      ColumnHelper.number('credit_score', 'Credit Score', { width: 110, hide: true }),
      ColumnHelper.money('exposure_amount',    'Exposure Amount',   { flex: 1, minWidth: 130 }),
      ColumnHelper.money('outstanding_amount', 'Outstanding Amount',{ flex: 1, minWidth: 130 }),
      /* Status column — hidden per product decision; restore by removing this comment block
      {
        headerName:   'Status',
        field:        'status',
        width:        118,
        filter:       'agTextColumnFilter',
        cellRenderer: CellRenderer.status,
        values:       ['Active', 'Inactive', 'Under Review', 'Closed', 'Watch List'],
      },
      */
      ColumnHelper.text('risk_grade',  'Risk Grade',  { width: 110, hide: true }),
      ColumnHelper.date('review_date', 'Review Date', { width: 115, hide: true }),

      // Drill-down to exposure events
      {
        headerName:   'Transactions',
        field:        'transaction_count',
        width:        110,
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
    const el = (id) => document.getElementById(id);
    if (el('kpiTotal'))  el('kpiTotal').textContent  = records.length.toLocaleString();
    if (el('kpiActive')) el('kpiActive').textContent =
      records.filter(r => r.status === 'Active').length.toLocaleString();
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
      Toast.error('Failed to load counterparties', err.message || 'Ensure the server is running.');
      console.error('Obligors load error:', err);
    }
  }

  // ── Async export ───────────────────────────────────────────────────────────

  async function _triggerAsyncExport(exportType, fileFormat) {
    const state = _grid.getFilterSortState();
    const spec  = {
      entity_type:   'obligors',
      export_type:   exportType,
      schedule_type: 'H1',
      source_type:   'csv',
      file_format:   fileFormat,
      filters:       exportType === 'partial'
        ? { col_filters: state.col_filters, quick_filter: state.quick_filter }
        : {},
      sorts: exportType === 'partial' ? state.sort_state : [],
    };
    try {
      const job = await ApiUtils.createExportJob(spec);
      const label = exportType === 'partial' ? 'Partial' : 'Full';
      Toast.info(`${label} export queued`, `Preparing ${fileFormat.toUpperCase()} file…`);
      await ApiUtils.pollUntilComplete(job.job_id, (status, data) => {
        if (status === 'COMPLETED') {
          ApiUtils.downloadExport(job.job_id);
          Toast.success('Export ready', `${label} counterparty export downloaded.`);
        } else if (status === 'FAILED') {
          Toast.error('Export failed', 'Check the server log for details.');
        } else if (status === 'TIMEOUT') {
          Toast.warning('Export delayed', 'Job still processing — retry later.');
        }
      });
    } catch (err) {
      Toast.error('Export error', err.message || 'Failed to start export.');
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {
    const gridSearch = document.getElementById('gridSearch');
    if (gridSearch) {
      let _t;
      gridSearch.addEventListener('input', () => {
        clearTimeout(_t);
        _t = setTimeout(() => _grid.setQuickFilter(gridSearch.value), 200);
      });
    }

    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
      globalSearch.addEventListener('input', () => {
        if (gridSearch) gridSearch.value = globalSearch.value;
        _loadObligors(globalSearch.value.trim());
      });
    }

    document.getElementById('btnShowHideColumns')?.addEventListener('click', (e) => {
      _grid.toggleColumnsPanel(e.currentTarget);
    });

    document.getElementById('btnClearFilters')?.addEventListener('click', () => {
      _grid.clearFilters();
      if (gridSearch) gridSearch.value = '';
      Toast.info('Filters cleared', 'All filters and sort order reset.');
    });

    // Export dropdown
    const btnExport  = document.getElementById('btnExport');
    const exportMenu = document.getElementById('exportMenu');
    if (btnExport && exportMenu) {
      btnExport.addEventListener('click', (e) => {
        e.stopPropagation();
        const open = exportMenu.getAttribute('aria-hidden') !== 'true';
        exportMenu.setAttribute('aria-hidden', open ? 'true' : 'false');
      });
      document.addEventListener('click', (e) => {
        if (!exportMenu.contains(e.target) && e.target !== btnExport)
          exportMenu.setAttribute('aria-hidden', 'true');
      });
      const _fmt = () => (document.querySelector('input[name="exportFmt"]:checked') || {}).value || 'csv';
      document.getElementById('btnPartialExport')?.addEventListener('click', () => {
        exportMenu.setAttribute('aria-hidden', 'true');
        _triggerAsyncExport('partial', _fmt());
      });
      document.getElementById('btnFullExport')?.addEventListener('click', () => {
        exportMenu.setAttribute('aria-hidden', 'true');
        _triggerAsyncExport('full', _fmt());
      });
    }

    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', () => {
        document.getElementById('sidebar')?.classList.toggle('collapsed');
        document.getElementById('mainContent')?.classList.toggle('sidebar-collapsed');
        setTimeout(() => _grid?.getApi().sizeColumnsToFit(), 200);
      });
    }
  }

  // ── Public init ────────────────────────────────────────────────────────────

  async function init() {
    _grid = new GridManager(
      'obligorsGrid',
      _buildColumns(),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    await _loadObligors();

    Toast.success(
      'H1 Counterparties loaded',
      `${(_allRecords || []).length} counterparties ready.`,
      undefined, 3000
    );
  }

  return { init };

}());
