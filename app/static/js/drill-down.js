/**
 * drill-down.js — Multi-level drill-down orchestrator.
 *
 * Hierarchy:
 *   Facility  →  Obligors  →  Transactions  →  Comments
 *
 * Each level:
 *  1. Opens a ModalManager modal with a breadcrumb trail.
 *  2. Builds an AG Grid inside it using GridManager.
 *  3. Fetches data from the API and loads it.
 *  4. Wires export buttons and (optionally) the next drill-down level.
 *
 * Exported as the global `DrillDown` object.
 */
const DrillDown = (function () {

  // ── Schema cache (per entity, fetched once per page load) ─────────────────

  const _schemaCache = {};

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

  // ── Level 2: Obligors for a Facility ──────────────────────────────────────

  /**
   * Open the obligors drill-down modal for a given facility.
   *
   * @param {string} facilityId   - Parent facility identifier.
   * @param {string} facilityName - Display name for the modal title and breadcrumb.
   */
  function openObligors(facilityId, facilityName) {
    ModalManager.open({ // Updated naming Conventions
      title:      'Obligors',
      breadcrumb: ['Credit Exposures', facilityName, 'Obligors'],
      onMount:    (panel) => _mountObligorModal(panel, facilityId, facilityName),
    });
  }

  async function _mountObligorModal(panel, facilityId, facilityName) {
    const safeId = _safeId(facilityId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('obligors', facilityId);

    const schema     = await _fetchSchema('obligors');
    const columnDefs = buildColumnsFromSchema(schema, {
      transactions: function (p) {
        openTransactions(p.data.obligor_id, p.data.obligor_name, facilityId, facilityName);
      },
    });

    const mgr = new GridManager(`drill-grid-obligors-${safeId}`, columnDefs, {
      paginationPageSize: 20,
    });
    mgr.init();

    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    _wireModalToolbar(body, mgr);
    _wireModalExport(body, mgr, 'obligors', facilityId, 'Obligors');

    _loadAndRender(mgr, `/api/facilities/${facilityId}/obligors`, body, `record-count-obligors-${safeId}`);
  }

  // ── Level 3: Transactions for an Obligor ──────────────────────────────────

  /**
   * Open the transactions drill-down modal for a given obligor.
   *
   * @param {string} obligorId    - Parent obligor identifier.
   * @param {string} obligorName  - Display name.
   * @param {string} facilityId   - Grandparent facility ID.
   * @param {string} facilityName - Grandparent facility name (for breadcrumb).
   */
  function openTransactions(obligorId, obligorName, facilityId, facilityName) {
    ModalManager.open({
      title:      'Exposure Events',
      breadcrumb: ['Credit Exposures', facilityName || facilityId, obligorName, 'Exposure Events'],
      onMount:    (panel) => _mountTransactionModal(panel, obligorId, obligorName, facilityId),
    });
  }

  async function _mountTransactionModal(panel, obligorId, obligorName, facilityId) {
    const safeId = _safeId(obligorId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('transactions', obligorId);

    const schema     = await _fetchSchema('transactions');
    const columnDefs = buildColumnsFromSchema(schema, {
      comments: function (p) {
        openComments(
          p.data.transaction_id, p.data.transaction_type,
          p.data.reference_number, obligorName,
        );
      },
    });

    const mgr = new GridManager(`drill-grid-transactions-${safeId}`, columnDefs, {
      paginationPageSize: 20,
    });
    mgr.init();

    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    _wireModalToolbar(body, mgr);
    _wireModalExport(body, mgr, 'transactions', obligorId, 'Exposure Events');

    _loadAndRender(mgr, `/api/obligors/${obligorId}/transactions`, body, `record-count-transactions-${safeId}`);
  }

  // ── Level 4: Comments for a Transaction ──────────────────────────────────

  /**
   * Open the comments drill-down modal for a given transaction.
   *
   * @param {string} transactionId  - Parent transaction identifier.
   * @param {string} txnType        - Transaction type label.
   * @param {string} reference      - Reference number.
   * @param {string} obligorName    - Parent obligor name (for breadcrumb).
   */
  function openComments(transactionId, txnType, reference, obligorName) {
    ModalManager.open({
      title:      'Analyst Comments',
      breadcrumb: [obligorName || 'Obligor', txnType, 'Analyst Comments'], // Updated naming Conventions
      onMount:    (panel) => _mountCommentModal(panel, transactionId),
    });
  }

  async function _mountCommentModal(panel, transactionId) {
    const safeId = _safeId(transactionId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('comments', transactionId);

    const schema     = await _fetchSchema('comments');
    const columnDefs = buildColumnsFromSchema(schema, {});

    const mgr = new GridManager(`drill-grid-comments-${safeId}`, columnDefs, {
      paginationPageSize: 15,
    });
    mgr.init();

    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    _wireModalToolbar(body, mgr);
    _wireModalExport(body, mgr, 'comments', transactionId, 'Comments');

    _loadAndRender(mgr, `/api/transactions/${transactionId}/comments`, body, `record-count-comments-${safeId}`);
  }

  function _safeId(id) {
    return id.replace(/[^a-z0-9]/gi, '-');
  }

  // ── Shared helpers ────────────────────────────────────────────────────────

  /**
   * Build the inner HTML of a modal body section.
   * Includes toolbar (search + export) and an AG Grid container.
   *
   * @param {string} entityType  - 'obligors'|'transactions'|'comments'
   * @param {string} entityId    - Parent entity ID (used for unique DOM IDs).
   * @returns {string}           HTML string.
   */
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
          <span class="record-count" id="record-count-${entityType}-${safeId}">Loading…</span>
        </div>
        <div class="modal-footer-right">
          <button class="btn btn-ghost" onclick="ModalManager.close()">Close</button>
        </div>
      </div>
    `;
  }

  /**
   * Fetch data from *apiUrl* and populate the GridManager.
   * Updates the record count label and shows toast on error.
   *
   * @param {GridManager} mgr          - The grid to populate.
   * @param {string}      apiUrl       - Endpoint to call.
   * @param {HTMLElement} bodyEl       - Modal body element.
   * @param {string}      countLabelId - ID of the record-count span.
   */
  async function _loadAndRender(mgr, apiUrl, bodyEl, countLabelId) {
    try {
      const resp = await ApiUtils.get(
        ApiUtils.buildUrl(apiUrl, { per_page: 500 }),
        false   // don't show global overlay inside a modal
      );

      mgr.setData(resp.data || []);

      const totalLabel = bodyEl.querySelector(`#${countLabelId}`);
      if (totalLabel && resp.meta) {
        totalLabel.innerHTML = `Showing <strong>${resp.data.length}</strong> of <strong>${resp.meta.total}</strong> records`;
      }
    } catch (err) {
      Toast.error('Failed to load data', err.message || 'Unknown error');
      console.error('DrillDown fetch error:', err);
    }
  }

  // ── Shared modal toolbar wiring ────────────────────────────────────────────

  function _wireModalToolbar(body, mgr) {
    const searchEl = body.querySelector('.modal-search-input');
    if (searchEl) {
      searchEl.addEventListener('input', () => mgr.setQuickFilter(searchEl.value));
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

  // ── Modal export wiring ────────────────────────────────────────────────────

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

  // ── Public surface ─────────────────────────────────────────────────────────

  return { openObligors, openTransactions, openComments };

}());
