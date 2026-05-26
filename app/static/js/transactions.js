/**
 * transactions.js — FR Y-14Q Schedule H1 Exposure Event Ledger page bootstrap.
 *
 * Initialises the exposure events grid, wires toolbar controls including
 * the async export dropdown, and provides drill-down into analyst comments.
 *
 * Depends on: api-utils.js, grid-config.js, modal-manager.js, drill-down.js
 */
const TransactionsApp = (function () {

  let _grid       = null;
  let _allRecords = null;

  // ── Column definitions ─────────────────────────────────────────────────────

  function _buildColumns() {
    return [
      ColumnHelper.text('transaction_id', 'Transaction ID', {
        width: 130, pinned: 'left',
      }),
      ColumnHelper.text('obligor_id',      'Obligor ID',       { width: 120 }),
      ColumnHelper.text('reference_number','Reference',        { width: 130, hide: true }),
      ColumnHelper.text('transaction_type','Transaction Type', { flex: 1, minWidth: 140 }),
      ColumnHelper.money('amount',         'Amount',           { flex: 1, minWidth: 130 }),
      ColumnHelper.text('currency',        'Currency',         { width: 70 }),
      ColumnHelper.date('transaction_date','Transaction Date', { width: 115 }),
      ColumnHelper.date('value_date',      'Value Date',      { width: 115, hide: true }),
      /* Status column — hidden per product decision; restore by removing this comment block
      {
        headerName:   'Status',
        field:        'status',
        width:        118,
        filter:       'wfTextFilter',
        cellRenderer: CellRenderer.status,
        values:       ['Pending', 'Active', 'Completed', 'Cancelled', 'Failed'],
      },
      */
      ColumnHelper.text('created_by',  'Created By',  { width: 130, hide: true }),
      ColumnHelper.text('approved_by', 'Approved By', { width: 130, hide: true }),
      ColumnHelper.text('description', 'Description', {
        flex: 2, minWidth: 180, tooltipField: 'description',
      }),

      // Drill-down to analyst comments
      {
        headerName:   'Comments',
        field:        'comment_count',
        width:        100,
        pinned:       'right',
        sortable:     true,
        filter:       'wfNumberFilter',
        cellClass:    'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          DrillDown.openComments(
            p.data.transaction_id,
            p.data.transaction_type,
            p.data.reference_number,
            p.data.obligor_id,
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
      records.filter(r => r.status === 'Completed').length.toLocaleString();
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadTransactions(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/transactions', { per_page: 1000, search });
      const resp = await ApiUtils.get(url);
      _allRecords = resp.data || [];
      _grid.setData(_allRecords);
      _updateKpi(_allRecords);
      setTimeout(() => _grid.getApi().sizeColumnsToFit(), 50);
    } catch (err) {
      Toast.error('Failed to load exposure events', err.message || 'Ensure the server is running.');
      console.error('Transactions load error:', err);
    }
  }

  // ── Async export ───────────────────────────────────────────────────────────

  async function _triggerAsyncExport(exportType, fileFormat) {
    const state = _grid.getFilterSortState();
    const spec  = {
      entity_type:   'transactions',
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
      const job   = await ApiUtils.createExportJob(spec);
      const label = exportType === 'partial' ? 'Partial' : 'Full';
      Toast.info(`${label} export queued`, `Preparing ${fileFormat.toUpperCase()} file…`);
      await ApiUtils.pollUntilComplete(job.job_id, (status, data) => {
        if (status === 'COMPLETED') {
          ApiUtils.downloadExport(job.job_id);
          Toast.success('Export ready', `${label} exposure event export downloaded.`);
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
        _loadTransactions(globalSearch.value.trim());
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
      'transactionsGrid',
      _buildColumns(),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    await _loadTransactions();

    Toast.success(
      'H1 Exposure Events loaded',
      `${(_allRecords || []).length} exposure events ready.`,
      undefined, 3000
    );
  }

  return { init };

}());
