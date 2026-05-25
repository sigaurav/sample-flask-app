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

  // ── Level 2: Obligors for a Facility ──────────────────────────────────────

  /**
   * Open the obligors drill-down modal for a given facility.
   *
   * @param {string} facilityId   - Parent facility identifier.
   * @param {string} facilityName - Display name for the modal title and breadcrumb.
   */
  function openObligors(facilityId, facilityName) {
    ModalManager.open({
      title:      'Counterparties',
      breadcrumb: ['Credit Exposures', facilityName, 'Counterparties'],
      onMount:    (panel) => _mountObligorModal(panel, facilityId, facilityName),
    });
  }

  function _mountObligorModal(panel, facilityId, facilityName) {
    const safeId = _safeId(facilityId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('obligors', facilityId);

    const columnDefs = _obligorColumns(facilityId, facilityName);
    const mgr = new GridManager(`drill-grid-obligors-${safeId}`, columnDefs, {
      paginationPageSize: 20,
    });
    mgr.init();

    // Refit columns after modal CSS animation (300 ms) has settled.
    // Cannot rely on _onGridReady alone because the browser may not have
    // completed layout when the grid first initialises inside the modal.
    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    // Wire search
    const searchEl = body.querySelector('.modal-search-input');
    if (searchEl) searchEl.addEventListener('input', () => mgr.setQuickFilter(searchEl.value));

    _wireModalExport(body, mgr, 'obligors', facilityId, 'Counterparties');

    _loadAndRender(mgr, `/api/facilities/${facilityId}/obligors`, body, `record-count-obligors-${safeId}`);
  }

  function _obligorColumns(facilityId, facilityName) {
    return [
      ColumnHelper.text('obligor_id',   'Obligor ID',   { width: 120, pinned: 'left' }),
      ColumnHelper.text('obligor_name', 'Obligor Name', { width: 180 }),
      ColumnHelper.text('obligor_type', 'Obligor Type', { width: 140 }),
      ColumnHelper.text('industry',     'Industry',     { width: 150 }),
      ColumnHelper.text('sub_industry', 'Sub-Industry', { width: 150, hide: true }),
      ColumnHelper.text('country',      'Country',      { width: 100, hide: true }),
      ColumnHelper.number('credit_score', 'Credit Score', { width: 110, hide: true }),
      ColumnHelper.money('exposure_amount',    'Exposure Amount',   { width: 130 }),
      ColumnHelper.money('outstanding_amount', 'Outstanding Amount',{ width: 130 }),
      // Status column — hidden per product decision; restore by removing this comment block
      // ColumnHelper.statusChip('status', 'Status', { width: 110 }),
      ColumnHelper.text('risk_grade',   'Risk Grade',   { width: 110, hide: true }),
      ColumnHelper.date('review_date',  'Review Date',  { width: 110, hide: true }),
      // Drill-down to exposure events
      {
        headerName: 'Transactions',
        field:      'transaction_count',
        width:      120,
        sortable:   true,
        filter:     'agNumberColumnFilter',
        cellClass:  'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          openTransactions(p.data.obligor_id, p.data.obligor_name, facilityId, facilityName);
        }),
      },
    ];
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

  function _mountTransactionModal(panel, obligorId, obligorName, facilityId) {
    const safeId = _safeId(obligorId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('transactions', obligorId);

    const columnDefs = _transactionColumns(obligorId, obligorName);
    const mgr = new GridManager(`drill-grid-transactions-${safeId}`, columnDefs, {
      paginationPageSize: 20,
    });
    mgr.init();

    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    const searchEl = body.querySelector('.modal-search-input');
    if (searchEl) searchEl.addEventListener('input', () => mgr.setQuickFilter(searchEl.value));

    _wireModalExport(body, mgr, 'transactions', obligorId, 'Exposure Events');

    _loadAndRender(mgr, `/api/obligors/${obligorId}/transactions`, body, `record-count-transactions-${safeId}`);
  }

  function _transactionColumns(obligorId, obligorName) {
    return [
      ColumnHelper.text('transaction_id',   'Transaction ID',   { width: 125, pinned: 'left' }),
      ColumnHelper.text('reference_number', 'Reference',       { width: 130, hide: true }),
      ColumnHelper.text('transaction_type', 'Transaction Type',{ width: 150 }),
      ColumnHelper.money('amount',          'Amount',          { width: 130 }),
      ColumnHelper.text('currency',         'Currency',        { width:  70 }),
      ColumnHelper.date('transaction_date', 'Transaction Date',{ width: 110 }),
      ColumnHelper.date('value_date',       'Value Date',     { width: 110, hide: true }),
      // Status column — hidden per product decision; restore by removing this comment block
      // ColumnHelper.statusChip('status', 'Status', { width: 110 }),
      ColumnHelper.text('created_by',       'Created By',     { width: 120, hide: true }),
      ColumnHelper.text('approved_by',      'Approved By',    { width: 120, hide: true }),
      ColumnHelper.text('description',      'Description',    { width: 220, tooltipField: 'description' }),
      // Drill-down to comments
      {
        headerName: 'Comments',
        field:      'comment_count',
        width:      110,
        sortable:   true,
        filter:     'agNumberColumnFilter',
        cellClass:  'drill-down-cell',
        cellRenderer: (params) => CellRenderer.drillDownLink(params, (p) => {
          openComments(
            p.data.transaction_id,
            p.data.transaction_type,
            p.data.reference_number,
            obligorName,
          );
        }),
      },
    ];
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
      breadcrumb: [obligorName || 'Counterparty', txnType, 'Analyst Comments'],
      onMount:    (panel) => _mountCommentModal(panel, transactionId),
    });
  }

  function _mountCommentModal(panel, transactionId) {
    const safeId = _safeId(transactionId);
    const body   = panel.querySelector('.modal-body');
    body.innerHTML = _buildModalBodyHtml('comments', transactionId);

    const columnDefs = _commentColumns();
    const mgr = new GridManager(`drill-grid-comments-${safeId}`, columnDefs, {
      paginationPageSize: 15,
    });
    mgr.init();

    setTimeout(() => mgr.getApi().sizeColumnsToFit(), 320);

    const searchEl = body.querySelector('.modal-search-input');
    if (searchEl) searchEl.addEventListener('input', () => mgr.setQuickFilter(searchEl.value));

    _wireModalExport(body, mgr, 'comments', transactionId, 'Comments');

    _loadAndRender(mgr, `/api/transactions/${transactionId}/comments`, body, `record-count-comments-${safeId}`);
  }

  function _commentColumns() {
    return [
      ColumnHelper.text('comment_id',   'Comment ID',  { width: 120, pinned: 'left' }),
      ColumnHelper.text('comment_type', 'Type',        { width: 130 }),
      {
        headerName:   'Comment',
        field:        'comment_text',
        width:         280,
        wrapText:      true,
        autoHeight:    true,
        cellClass:     'comment-text-cell',
        filter:        'agTextColumnFilter',
      },
      ColumnHelper.text('author',       'Author',      { width: 140 }),
      ColumnHelper.text('department',   'Department',  { width: 140, hide: true }),
      // Status column — hidden per product decision; restore by removing this comment block
      // ColumnHelper.statusChip('status', 'Status', { width: 110 }),
      {
        headerName:   'Priority',
        field:        'priority',
        width:         110,
        filter:        'agTextColumnFilter',
        cellRenderer: (params) => {
          const val = (params.value || '').toLowerCase();
          const el  = document.createElement('span');
          el.className = `status-chip chip-${val}`;
          el.innerHTML = `<span class="status-dot"></span>${params.value}`;
          return el;
        },
      },
      ColumnHelper.date('created_date', 'Created Date', { width: 120, hide: true }),
    ];
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
        </div>
        <div class="modal-toolbar-right">
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

  // ── Async export helpers ───────────────────────────────────────────────────

  async function _triggerModalExport(spec, label, entityLabel) {
    try {
      const job = await ApiUtils.createExportJob(spec);
      Toast.info(`${label} export queued`, `Preparing ${spec.file_format.toUpperCase()} file…`);
      await ApiUtils.pollUntilComplete(job.job_id, (status) => {
        if (status === 'COMPLETED') {
          ApiUtils.downloadExport(job.job_id);
          Toast.success('Export ready', `${label} ${entityLabel} export downloaded.`);
        } else if (status === 'FAILED') {
          Toast.error('Export failed', 'Check the server log for details.');
        } else if (status === 'TIMEOUT') {
          Toast.warning('Export delayed', 'Job still processing — retry later.');
        }
      });
    } catch (err) {
      Toast.error('Export error', err.message || 'Failed to start export.');
    }
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
      await _triggerModalExport({
        entity_type: entityType, entity_id: entityId,
        export_type: 'partial', schedule_type: 'H1', source_type: 'csv',
        file_format: _fmt(),
        filters: { col_filters: state.col_filters, quick_filter: state.quick_filter },
        sorts: state.sort_state,
      }, 'Partial', entityLabel);
    });

    body.querySelector('.modal-export-full')?.addEventListener('click', async () => {
      menu.setAttribute('aria-hidden', 'true');
      await _triggerModalExport({
        entity_type: entityType, entity_id: entityId,
        export_type: 'full', schedule_type: 'H1', source_type: 'csv',
        file_format: _fmt(),
        filters: {}, sorts: [],
      }, 'Full', entityLabel);
    });
  }

  // ── Public surface ─────────────────────────────────────────────────────────

  return { openObligors, openTransactions, openComments };

}());
