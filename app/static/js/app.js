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
        filter:       'wfNumberFilter',
        sortable:     true,
        cellRenderer: CellRenderer.utilisation,
      },
      /* Status column — hidden per product decision; restore by removing this comment block
      {
        headerName:   'Status',
        field:        'status',
        width:        118,
        filter:       'wfTextFilter',
        cellRenderer: CellRenderer.status,
        values:       ['Active', 'Inactive', 'Under Review', 'Closed', 'Watch List'],
      },
      */
      {
        headerName:   'Risk Rating',
        field:        'risk_rating',
        width:        105,
        filter:       'wfTextFilter',
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

      // Pinned right — drill-down to obligors
      { // Updated naming Conventions
        headerName: 'Obligors',
        field:      'obligor_count',
        width:      118,
        pinned:     'right',
        sortable:   true,
        resizable:  true,
        filter:     'wfNumberFilter',
        cellClass:  'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          DrillDown.openObligors(p.data.facility_id, p.data.facility_name);
        }),
      },
    ];
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadFacilities(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/facilities', { per_page: 500, search });
      const resp = await ApiUtils.get(url);

      _allFacilities = resp.data || [];
      _facilityGrid.setData(_allFacilities);
      ApiUtils.updateKpi(_allFacilities, f => f.status === 'Active');

      setTimeout(() => _facilityGrid.getApi().sizeColumnsToFit(), 50);

    } catch (err) {
      Toast.error('Failed to load exposures', err.message ||
        'Ensure the server is running and data has been generated.');
      console.error('Facility load error:', err);
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {
    ApiUtils.wireGridToolbar(_facilityGrid, _loadFacilities);
    ApiUtils.wireExportDropdown(_facilityGrid, 'facilities', 'Facilities');
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
