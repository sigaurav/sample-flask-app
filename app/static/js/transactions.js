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
  let _schema     = null;

  // ── Schema fetch ───────────────────────────────────────────────────────────

  async function _getSchema() {
    if (_schema) return _schema;
    try {
      const r = await ApiUtils.get('/api/schema/transactions', false);
      _schema = r.data || [];
    } catch (_) {
      _schema = [];
    }
    return _schema;
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadTransactions(search = '') {
    const ctx = ContextBar.getContext();
    if (!ctx.sor || !ctx.fic_mis_date) {
      _allRecords = [];
      _grid.setData([]);
      ApiUtils.updateKpi([], () => false);
      return false;
    }
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
    const schema = await _getSchema();
    _grid = new GridManager(
      'transactionsGrid',
      buildColumnsFromSchema(schema, {
        comments: (p) => DrillDown.openComments(
          p.data.transaction_id, p.data.transaction_type,
          p.data.reference_number, p.data.obligor_id,
        ),
      }),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    const loaded = await _loadTransactions();

    if (loaded !== false) {
      Toast.success(
        'H1 Exposure Events loaded',
        `${(_allRecords || []).length} exposure events ready.`,
        undefined, 3000
      );
    } else {
      Toast.info('Select query context', 'Choose a SOR and Date in the bar above, then click Load Data.', undefined, 5000);
    }
  }

  return { init };

}());
