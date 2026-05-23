/**
 * app.js — FR Y-14Q Schedule H1 dashboard bootstrap.
 *
 * Initialises the credit exposure grid, wires toolbar controls
 * (search, column visibility, multi-sort clear, async export dropdown),
 * and populates the KPI strip.
 *
 * Depends on: api-utils.js, grid-config.js, modal-manager.js, drill-down.js
 */
const WFApp = (function () {

  let _facilityGrid  = null;
  let _allFacilities = null;

  // ── Column definitions ─────────────────────────────────────────────────────

  function _buildFacilityColumns() {
    return [
      ColumnHelper.text('facility_id', 'Facility ID', {
        width: 115, pinned: 'left',
      }),

      ColumnHelper.text('facility_name', 'Facility Name', {
        flex: 2, minWidth: 160, tooltipField: 'facility_name',
      }),
      ColumnHelper.text('facility_type', 'Facility Type', {
        flex: 1.5, minWidth: 130,
      }),
      ColumnHelper.money('credit_limit', 'Credit Limit', {
        flex: 1, minWidth: 120,
      }),
      ColumnHelper.money('outstanding_balance', 'Outstanding Balance', {
        flex: 1, minWidth: 115,
      }),

      {
        headerName:   'Utilisation',
        field:        'utilization_pct',
        width:        150,
        filter:       'agNumberColumnFilter',
        sortable:     true,
        cellRenderer: CellRenderer.utilisation,
      },
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
      {
        headerName:   'Risk Rating',
        field:        'risk_rating',
        width:        105,
        filter:       'agTextColumnFilter',
        cellRenderer: CellRenderer.riskRating,
        values:       ['AAA','AA','A','BBB','BB','B','CCC','CC','C','D'],
      },
      ColumnHelper.text('relationship_manager', 'Rel. Manager', {
        flex: 1, minWidth: 130,
      }),
      ColumnHelper.text('region', 'Region', { width: 95 }),

      // Hidden columns — toggleable via Columns panel
      ColumnHelper.money('available_credit', 'Available',   { flex: 1, minWidth: 110, hide: true }),
      ColumnHelper.text('currency',          'Currency',    { width: 85,  hide: true }),
      ColumnHelper.number('risk_score',      'Risk Score',  { width: 95,  hide: true }),
      ColumnHelper.text('country',           'Country',     { width: 110, hide: true }),
      ColumnHelper.date('created_date',      'Created',     { width: 105, hide: true }),
      ColumnHelper.date('maturity_date',     'Maturity',    { width: 105, hide: true }),
      ColumnHelper.number('interest_rate',   'Rate (%)',    { width: 85,  hide: true }),

      // Pinned right — drill-down to counterparties
      {
        headerName: 'Counterparties',
        field:      'obligor_count',
        width:      118,
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
    const el = (id) => document.getElementById(id);
    if (el('kpiTotal'))  el('kpiTotal').textContent  = total.toLocaleString();
    if (el('kpiActive')) el('kpiActive').textContent = active.toLocaleString();
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadFacilities(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/facilities', { per_page: 500, search });
      const resp = await ApiUtils.get(url);

      _allFacilities = resp.data || [];
      _facilityGrid.setData(_allFacilities);
      _updateKpi(_allFacilities);

      setTimeout(() => _facilityGrid.getApi().sizeColumnsToFit(), 50);

    } catch (err) {
      Toast.error('Failed to load exposures', err.message ||
        'Ensure the server is running and data has been generated.');
      console.error('Facility load error:', err);
    }
  }

  // ── Async export ───────────────────────────────────────────────────────────

  async function _triggerAsyncExport(exportType, fileFormat) {
    const state = _facilityGrid.getFilterSortState();

    const spec = {
      entity_type:   'facilities',
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
      const typeLabel = exportType === 'partial' ? 'Partial' : 'Full';
      Toast.info(
        `${typeLabel} export queued`,
        `Job ${job.job_id.slice(0, 8)}… — preparing ${fileFormat.toUpperCase()} file.`
      );

      await ApiUtils.pollUntilComplete(job.job_id, (status, data) => {
        if (status === 'COMPLETED') {
          ApiUtils.downloadExport(job.job_id);
          const rows = data?.row_count ? ` (${data.row_count.toLocaleString()} rows)` : '';
          Toast.success('Export ready', `${typeLabel} export downloaded${rows}.`);
        } else if (status === 'FAILED') {
          Toast.error('Export failed', 'The export job encountered an error. Check the server log.');
        } else if (status === 'TIMEOUT') {
          Toast.warning('Export delayed', 'Job still processing — check back via /api/exports.');
        }
      });

    } catch (err) {
      Toast.error('Export error', err.message || 'Failed to start export.');
      console.error('Export error:', err);
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {

    // Grid search
    const gridSearch = document.getElementById('gridSearch');
    if (gridSearch) {
      let _debounce;
      gridSearch.addEventListener('input', () => {
        clearTimeout(_debounce);
        _debounce = setTimeout(() => _facilityGrid.setQuickFilter(gridSearch.value), 200);
      });
    }

    // Global header search mirrors grid search
    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
      globalSearch.addEventListener('input', () => {
        if (gridSearch) gridSearch.value = globalSearch.value;
        _loadFacilities(globalSearch.value.trim());
      });
    }

    // Columns panel
    const btnShowHide = document.getElementById('btnShowHideColumns');
    if (btnShowHide) {
      btnShowHide.addEventListener('click', () => _facilityGrid.toggleColumnsPanel(btnShowHide));
    }

    // Clear filters + sort
    const btnClearFilters = document.getElementById('btnClearFilters');
    if (btnClearFilters) {
      btnClearFilters.addEventListener('click', () => {
        _facilityGrid.clearFilters();
        if (gridSearch) gridSearch.value = '';
        Toast.info('Filters cleared', 'All filters and sort order have been reset.');
      });
    }

    // ── Export dropdown ───────────────────────────────────────────────────────
    const btnExport  = document.getElementById('btnExport');
    const exportMenu = document.getElementById('exportMenu');

    if (btnExport && exportMenu) {
      btnExport.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = exportMenu.getAttribute('aria-hidden') !== 'true';
        exportMenu.setAttribute('aria-hidden', isOpen ? 'true' : 'false');
      });

      document.addEventListener('click', (e) => {
        if (!exportMenu.contains(e.target) && e.target !== btnExport) {
          exportMenu.setAttribute('aria-hidden', 'true');
        }
      });

      const _getFormat = () => {
        const r = document.querySelector('input[name="exportFmt"]:checked');
        return r ? r.value : 'csv';
      };

      document.getElementById('btnPartialExport')?.addEventListener('click', () => {
        exportMenu.setAttribute('aria-hidden', 'true');
        _triggerAsyncExport('partial', _getFormat());
      });

      document.getElementById('btnFullExport')?.addEventListener('click', () => {
        exportMenu.setAttribute('aria-hidden', 'true');
        _triggerAsyncExport('full', _getFormat());
      });
    }

    // Sidebar toggle
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar        = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        sidebar.classList.toggle('collapsed');
        document.getElementById('mainContent')?.classList.toggle('sidebar-collapsed');
        setTimeout(() => _facilityGrid?.getApi().sizeColumnsToFit(), 200);
      });
    }
  }

  // ── Public init ────────────────────────────────────────────────────────────

  async function init() {
    _facilityGrid = new GridManager(
      'facilityGrid',
      _buildFacilityColumns(),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    await _loadFacilities();

    Toast.success(
      'H1 Schedule loaded',
      `${(_allFacilities || []).length} credit exposures ready.`,
      undefined, 3000
    );
  }

  return { init };

}());
