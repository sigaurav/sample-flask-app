/**
 * drill-down.js — Generic multi-level drill-down orchestrator.
 *
 * Reads the full entity graph from APP_CONFIG.entities at call-time, so adding
 * new entities or changing FK columns only requires a config change — no edits here.
 *
 * Uses server-side pagination via POST /api/<parent>/<child>/query.
 *
 * Public API:
 *   DrillDown.open(parentEntity, childEntity, rowData, parentLabel, grandparentLabel?)
 */
const DrillDown = (function () {

  const _schemaCache = {};

  // ── Schema cache ──────────────────────────────────────────────────────────

  async function _fetchSchema(entityType) {
    if (_schemaCache[entityType]) return _schemaCache[entityType];
    try {
      const r = await ApiUtils.get('/api/schema/' + entityType, false);
      _schemaCache[entityType] = r.data || [];
    } catch (_) {
      _schemaCache[entityType] = [];
    }
    return _schemaCache[entityType];
  }

  // ── Label helpers ─────────────────────────────────────────────────────────

  function _getLabelForRow(rowData, entityType) {
    const cfg        = (APP_CONFIG.entities || {})[entityType] || {};
    const labelField = cfg.label_field || (cfg.pk || [])[0];
    return (labelField && rowData[labelField]) ? String(rowData[labelField]) : '';
  }

  // ── Public: open a child entity in a modal ────────────────────────────────

  function open(parentEntity, childEntity, rowData, parentLabel, grandparentLabel) {
    const entities  = APP_CONFIG.entities || {};
    const childCfg  = (entities[parentEntity] || {}).children || {};
    const fkCols    = (childCfg[childEntity]  || {}).fk || [];
    const fkValues  = Object.fromEntries(fkCols.map(col => [col, rowData[col]]));
    const display   = parentLabel || _getLabelForRow(rowData, parentEntity);

    const breadcrumb = grandparentLabel
      ? ['Credit Facilities', grandparentLabel, display, _capitalize(childEntity)]
      : ['Credit Facilities', display, _capitalize(childEntity)];

    ModalManager.open({
      title:   _capitalize(childEntity),
      breadcrumb,
      onMount: (panel) => _mountModal(panel, parentEntity, childEntity, fkValues, display),
    });
  }

  // ── Modal mount ───────────────────────────────────────────────────────────

  async function _mountModal(panel, parentEntity, childEntity, fkValues, parentLabel) {
    const safeId = _safeId(Object.values(fkValues).join('-'));
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml(childEntity, Object.values(fkValues).join('-'));

    const schema        = await _fetchSchema(childEntity);
    const grandchildren = ((APP_CONFIG.entities || {})[childEntity] || {}).children || {};

    const drillHandlers = {};
    Object.keys(grandchildren).forEach(grandchild => {
      drillHandlers[grandchild] = (p) => open(
        childEntity, grandchild, p.data,
        _getLabelForRow(p.data, childEntity),
        parentLabel,
      );
    });

    const childPkCols = ((APP_CONFIG.entities || {})[childEntity] || {}).pk || [];

    const queryFn = async (spec) => {
      spec.fic_mis_date = (ContextBar.getContext()).fic_mis_date || '';
      spec.entity_key   = fkValues;
      return ApiUtils.post(`/api/${parentEntity}/${childEntity}/query`, spec);
    };

    const mgr = new GridManager(
      `drill-grid-${childEntity}-${safeId}`,
      buildColumnsFromSchema(schema, drillHandlers),
      {
        paginationPageSize:         10,
        paginationPageSizeSelector: [10, 25, 50, 100],
        initialSort: childPkCols.map(f => ({ field: f, dir: 'asc' })),
        queryFn,
      },
    );
    mgr.init();
    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    _wireModalToolbar(body, mgr);
    _wireModalExport(body, mgr, childEntity, JSON.stringify(fkValues), _capitalize(childEntity));

    mgr.applyFilters();
  }

  // ── Shared helpers ────────────────────────────────────────────────────────

  function _capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  function _safeId(id) {
    return String(id).replace(/[^a-z0-9]/gi, '-');
  }

  function _buildModalBodyHtml(entityType, entityId) {
    const safeId = _safeId(entityId);
    return `
      <div class="modal-toolbar">
        <div class="modal-toolbar-left">
          <div class="modal-search">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input type="text" class="modal-search-input" placeholder="Search…" aria-label="Search" />
          </div>
          <button class="btn btn-primary modal-apply-btn" title="Apply sort and filter selection">Apply Filters</button>
          <button class="btn btn-outline modal-clear-btn" title="Clear all filters and search">Clear</button>
        </div>
        <div class="modal-toolbar-right">
          <button class="btn btn-outline modal-columns-btn" title="Show or hide columns">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
              <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/>
              <line x1="8" y1="18" x2="21" y2="18"/>
              <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/>
              <line x1="3" y1="18" x2="3.01" y2="18"/>
            </svg>
            Columns
          </button>
          <div class="export-dropdown">
            <button class="btn btn-primary export-trigger modal-export-trigger" title="Export options">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                <polyline points="7 10 12 15 17 10"/>
                <line x1="12" y1="15" x2="12" y2="3"/>
              </svg>
              Export
              <svg class="export-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="11" height="11">
                <polyline points="6 9 12 15 18 9"/>
              </svg>
            </button>
            <div class="export-menu modal-export-menu" aria-hidden="true">
              <div class="export-menu-header">Export Options</div>
              <button class="export-menu-item modal-export-partial">
                <div class="export-menu-item-title">Partial Export</div>
                <div class="export-menu-item-desc">Current filtered view</div>
              </button>
              <div class="export-menu-divider"></div>
              <button class="export-menu-item modal-export-full">
                <div class="export-menu-item-title">Full Export</div>
                <div class="export-menu-item-desc">All records for this entity</div>
              </button>
              <div class="export-menu-format">
                <span>Format:</span>
                <label><input type="radio" name="modalExportFmt" value="csv" checked> CSV</label>
                <label><input type="radio" name="modalExportFmt" value="excel"> Excel</label>
                <label><input type="radio" name="modalExportFmt" value="parquet"> Parquet</label>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-grid-wrap">
        <div id="drill-grid-${entityType}-${safeId}" class="wf-grid modal-grid"></div>
      </div>
      <div class="modal-footer">
        <div class="modal-footer-left">
          <span class="record-count" id="record-count-${entityType}-${safeId}"></span>
        </div>
        <div class="modal-footer-right">
          <button class="btn btn-ghost" onclick="ModalManager.close()">Close</button>
        </div>
      </div>
    `;
  }

  function _wireModalToolbar(body, mgr) {
    const searchEl = body.querySelector('.modal-search-input');
    if (searchEl) {
      searchEl.addEventListener('input', () => mgr.setQuickFilter(searchEl.value));
    }

    const applyBtn = body.querySelector('.modal-apply-btn');
    if (applyBtn) {
      mgr.setApplyButton(applyBtn);
      applyBtn.addEventListener('click', () => mgr.applyFilters());
    }

    body.querySelector('.modal-columns-btn')?.addEventListener('click', (e) => {
      mgr.toggleColumnsPanel(e.currentTarget);
    });
    body.querySelector('.modal-clear-btn')?.addEventListener('click', () => {
      mgr.clearFilters();
      if (searchEl) searchEl.value = '';
      Toast.info('Filters cleared', 'All filters and sort order have been reset.');
    });
  }

  function _wireModalExport(body, mgr, entityType, entityId, entityLabel) {
    const trigger = body.querySelector('.modal-export-trigger');
    const menu    = body.querySelector('.modal-export-menu');
    if (!trigger || !menu) return;

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = menu.getAttribute('aria-hidden') !== 'true';
      menu.setAttribute('aria-hidden', open ? 'true' : 'false');
    });
    document.addEventListener('click', (e) => {
      if (!document.body.contains(menu)) return;
      if (!menu.contains(e.target) && e.target !== trigger)
        menu.setAttribute('aria-hidden', 'true');
    });

    const _fmt = () =>
      (body.querySelector('[name="modalExportFmt"]:checked') || {}).value || 'csv';

    body.querySelector('.modal-export-partial')?.addEventListener('click', async () => {
      menu.setAttribute('aria-hidden', 'true');
      const state = mgr.getFilterSortState();
      await ApiUtils.triggerExportJob({
        entity_type: entityType, entity_id: entityId,
        export_type: 'partial', schedule_type: 'H1',
        file_format: _fmt(),
        filters: { col_filters: state.col_filters, quick_filter: state.quick_filter },
        sorts: state.sort_state,
      }, 'Partial', entityLabel);
    });

    body.querySelector('.modal-export-full')?.addEventListener('click', async () => {
      menu.setAttribute('aria-hidden', 'true');
      await ApiUtils.triggerExportJob({
        entity_type: entityType, entity_id: entityId,
        export_type: 'full', schedule_type: 'H1',
        file_format: _fmt(),
        filters: {}, sorts: [],
      }, 'Full', entityLabel);
    });
  }

  return { open };

}());
