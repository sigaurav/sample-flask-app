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
  let _schema        = null;

  // ── Schema fetch ───────────────────────────────────────────────────────────

  async function _getSchema() {
    if (_schema) return _schema;
    try {
      const r = await ApiUtils.get('/api/schema/facilities', false);
      _schema = r.data || [];
    } catch (_) {
      _schema = [];
    }
    return _schema;
  }

  // ── Data loading ───────────────────────────────────────────────────────────

  async function _loadFacilities(search = '') {
    const ctx = ContextBar.getContext();
    if (!ctx.sor || !ctx.fic_mis_date) {
      _allFacilities = [];
      _facilityGrid.setData([]);
      ApiUtils.updateKpi([], () => false);
      return false;
    }
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
    const schema = await _getSchema();
    _facilityGrid = new GridManager(
      'facilityGrid',
      buildColumnsFromSchema(schema, {
        obligors: (p) => DrillDown.openObligors(p.data.facility_id, p.data.facility_name),
      }),
      { paginationPageSize: 25, paginationPageSizeSelector: [10, 25, 50, 100] }
    ).init();

    _wireToolbar();
    const loaded = await _loadFacilities();

    if (loaded !== false) {
      Toast.success(
        'H1 Schedule loaded',
        `${(_allFacilities || []).length} credit exposures ready.`,
        undefined, 3000
      );
    } else {
      Toast.info('Select query context', 'Choose a SOR and Date in the bar above, then click Load Data.', undefined, 5000);
    }
  }

  return { init };

}());
