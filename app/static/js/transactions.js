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

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadTransactions(search = '') {
    try {
      const url  = ApiUtils.buildUrl('/api/transactions', { per_page: 1000, search });
      const resp = await ApiUtils.get(url);
      _allRecords = resp.data || [];
      _grid.setData(_allRecords);
      ApiUtils.updateKpi(_allRecords, r => r.status === 'Completed');
      setTimeout(() => _grid.getApi().sizeColumnsToFit(), 50);
    } catch (err) {
      Toast.error('Failed to load exposure events', err.message || 'Ensure the server is running.');
      console.error('Transactions load error:', err);
    }
  }

  // ── Toolbar wiring ─────────────────────────────────────────────────────────

  function _wireToolbar() {
    ApiUtils.wireGridToolbar(_grid, _loadTransactions);
    ApiUtils.wireExportDropdown(_grid, 'transactions', 'Exposure Events');
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
