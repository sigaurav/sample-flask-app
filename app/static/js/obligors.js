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
        filter:       'wfTextFilter',
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
        filter:       'wfNumberFilter',
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

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadObligors(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/obligors', { per_page: 1000, search });
      const resp = await ApiUtils.get(url);
      _allRecords = resp.data || [];
      _grid.setData(_allRecords);
      ApiUtils.updateKpi(_allRecords, r => r.status === 'Active');
      setTimeout(() => _grid.getApi().sizeColumnsToFit(), 50);
    } catch (err) {
      Toast.error('Failed to load counterparties', err.message || 'Ensure the server is running.');
      console.error('Obligors load error:', err);
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {
    ApiUtils.wireGridToolbar(_grid, _loadObligors);
    ApiUtils.wireExportDropdown(_grid, 'obligors', 'Obligors');
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
