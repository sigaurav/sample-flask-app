/**
 * entity-page.js — Generic standalone entity page.
 *
 * Call EntityPage.init('facilities') / EntityPage.init('obligations') / etc.
 * from the page template.  All entity-specific behaviour is driven by
 * APP_CONFIG.entities.  Uses server-side pagination via POST /api/<entity>/query.
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

  async function init(entityType) {
    const schema    = await _getSchema(entityType);
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

    const queryFn = async (spec) => {
      const ctx = ContextBar.getContext();
      spec.fic_mis_date = ctx.fic_mis_date || '';
      const resp = await ApiUtils.post(`/api/${entityType}/query`, spec);
      ApiUtils.updateKpi(resp.data || [], _getActivePredicate(entityType));
      return resp;
    };

    const grid = new GridManager(
      entityType + 'Grid',
      buildColumnsFromSchema(schema, drillHandlers),
      {
        paginationPageSize:         25,
        paginationPageSizeSelector: [10, 25, 50, 100],
        initialSort: pkCols.map(f => ({ field: f, dir: 'asc' })),
        queryFn,
      },
    ).init();

    const applyBtn = document.getElementById('btnApplyFilters');
    if (applyBtn) {
      grid.setApplyButton(applyBtn);
      applyBtn.addEventListener('click', () => grid.applyFilters());
    }

    ApiUtils.wireGridToolbar(grid, () => {});
    ApiUtils.wireExportDropdown(
      grid, entityType,
      entityType.charAt(0).toUpperCase() + entityType.slice(1),
    );

    const ctx = ContextBar.getContext();
    if (ctx.fic_mis_date) {
      grid.applyFilters();
    } else {
      Toast.info(
        'Select report date',
        'Enter a report date in the bar above, then click Load Data.',
        undefined, 5000,
      );
    }
  }

  return { init };

}());
