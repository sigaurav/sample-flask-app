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
  let _schema     = null;

  // ── Schema fetch ───────────────────────────────────────────────────────────

  async function _getSchema() {
    if (_schema) return _schema;
    try {
      const r = await ApiUtils.get('/api/schema/obligors', false);
      _schema = r.data || [];
    } catch (_) {
      _schema = [];
    }
    return _schema;
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadObligors(search = '') {
    const ctx = ContextBar.getContext();
    if (!ctx.sor || !ctx.fic_mis_date) {
      _allRecords = [];
      _grid.setData([]);
      ApiUtils.updateKpi([], () => false);
      return false;
    }
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
    const schema = await _getSchema();
    _grid = new GridManager(
      'obligorsGrid',
      buildColumnsFromSchema(schema, {
        transactions: (p) => DrillDown.openTransactions(
          p.data.obligor_id, p.data.obligor_name,
          p.data.facility_id, p.data.facility_id,
        ),
      }),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    const loaded = await _loadObligors();

    if (loaded !== false) {
      Toast.success(
        'H1 Counterparties loaded',
        `${(_allRecords || []).length} counterparties ready.`,
        undefined, 3000
      );
    } else {
      Toast.info('Select query context', 'Choose a SOR and Date in the bar above, then click Load Data.', undefined, 5000);
    }
  }

  return { init };

}());
