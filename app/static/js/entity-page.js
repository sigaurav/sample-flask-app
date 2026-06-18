/**
 * entity-page.js — Generic standalone entity page.
 *
 * Replaces app.js, obligations.js, and property.js with a single reusable module.
 * Call EntityPage.init('facilities') / EntityPage.init('obligations') / etc. from
 * the page template.  All entity-specific behaviour is driven by APP_CONFIG.entities.
 *
 * Depends on: api-utils.js, grid-config.js, drill-down.js, context-bar.js
 */
const EntityPage = (function () {

  function _getLabelForRow(rowData, entityType) {
    const cfg        = (APP_CONFIG.entities || {})[entityType] || {};
    const labelField = cfg.label_field || (cfg.pk || [])[0];
    return (labelField && rowData[labelField]) ? String(rowData[labelField]) : '';
  }

  function _getActivePredicate(entityType) {
    const cfg = ((APP_CONFIG.entities || {})[entityType] || {}).active_filter;
    if (cfg) return r => r[cfg.field] === cfg.value;
    return () => false;
  }

  async function _getSchema(entityType) {
    try {
      const r = await ApiUtils.get(`/api/schema/${entityType}`, false);
      return r.data || [];
    } catch (_) {
      return [];
    }
  }

  async function _loadData(entityType, grid, search = '') {
    const ctx = ContextBar.getContext();
    if (!ctx.fic_mis_date) {
      grid.setData([]);
      ApiUtils.updateKpi([], () => false);
      return false;
    }
    try {
      const url  = ApiUtils.buildUrl(`/api/${entityType}`, { per_page: APP_CONFIG.maxPageSize, search });
      const resp = await ApiUtils.get(url);
      const data = resp.data || [];
      grid.setData(data);
      ApiUtils.updateKpi(data, _getActivePredicate(entityType));
      setTimeout(() => grid.getApi().sizeColumnsToFit(), 50);
    } catch (err) {
      Toast.error(
        `Failed to load ${entityType}`,
        err.message || 'Ensure the server is running.',
      );
      console.error(`${entityType} load error:`, err);
    }
  }

  async function init(entityType) {
    const schema   = await _getSchema(entityType);
    const entityCfg = (APP_CONFIG.entities || {})[entityType] || {};
    const children  = entityCfg.children || {};
    const pkCols    = entityCfg.pk || [];

    const drillHandlers = {};
    Object.keys(children).forEach(childEntity => {
      drillHandlers[childEntity] = (p) => DrillDown.open(
        entityType, childEntity, p.data,
        _getLabelForRow(p.data, entityType),
      );
    });

    const grid = new GridManager(
      entityType + 'Grid',
      buildColumnsFromSchema(schema, drillHandlers),
      {
        paginationPageSize:         25,
        paginationPageSizeSelector: [10, 25, 50, 100],
        initialSort: pkCols.map(f => ({ field: f, dir: 'asc' })),
      },
    ).init();

    ApiUtils.wireGridToolbar(grid, (search) => _loadData(entityType, grid, search));
    ApiUtils.wireExportDropdown(
      grid, entityType,
      entityType.charAt(0).toUpperCase() + entityType.slice(1),
    );

    const loaded = await _loadData(entityType, grid);
    if (loaded === false) {
      Toast.info(
        'Select report date',
        'Enter a report date in the bar above, then click Load Data.',
        undefined, 5000,
      );
    }
  }

  return { init };

}());
