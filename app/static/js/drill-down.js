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
      title:      'Obligors',
      breadcrumb: ['Dashboard', facilityName, 'Obligors'],
      onMount:    (panel) => _mountObligorModal(panel, facilityId, facilityName),
    });
  }

  function _mountObligorModal(panel, facilityId, facilityName) {
    const safeId = facilityId.replace(/[^a-z0-9]/gi, '-');
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

    // Wire export buttons
    body.querySelectorAll('.modal-export-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        ApiUtils.downloadFile(`/api/export/facilities/${facilityId}/obligors?format=${fmt}`);
        Toast.success('Export started', `Downloading obligors as ${fmt.toUpperCase()}`);
      });
    });

    _loadAndRender(mgr, `/api/facilities/${facilityId}/obligors`, body, `record-count-obligors-${safeId}`);
  }

  function _obligorColumns(facilityId, facilityName) {
    return [
      ColumnHelper.text('obligor_id',   'Obligor ID',   { width: 110, pinned: 'left' }),
      ColumnHelper.text('obligor_name', 'Name',         { width: 180 }),
      ColumnHelper.text('obligor_type', 'Type',         { width: 140 }),
      ColumnHelper.text('industry',     'Industry',     { width: 150 }),
      ColumnHelper.text('sub_industry', 'Sub-Industry', { width: 150, hide: true }),
      ColumnHelper.text('country',      'Country',      { width: 100, hide: true }),
      ColumnHelper.number('credit_score', 'Credit Score', { width: 110, hide: true }),
      ColumnHelper.money('exposure_amount',    'Exposure',    { width: 130 }),
      ColumnHelper.money('outstanding_amount', 'Outstanding', { width: 130 }),
      ColumnHelper.statusChip('status', 'Status',       { width: 110 }),
      ColumnHelper.text('risk_grade',   'Risk Grade',   { width: 110, hide: true }),
      ColumnHelper.date('review_date',  'Review Date',  { width: 110, hide: true }),
      // Drill-down to transactions
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
      title:      'Transactions',
      breadcrumb: ['Dashboard', facilityName || facilityId, obligorName, 'Transactions'],
      onMount:    (panel) => _mountTransactionModal(panel, obligorId, obligorName, facilityId),
    });
  }

  function _mountTransactionModal(panel, obligorId, obligorName, facilityId) {
    const safeId = obligorId.replace(/[^a-z0-9]/gi, '-');
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

    body.querySelectorAll('.modal-export-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        ApiUtils.downloadFile(`/api/export/obligors/${obligorId}/transactions?format=${fmt}`);
        Toast.success('Export started', `Downloading transactions as ${fmt.toUpperCase()}`);
      });
    });

    _loadAndRender(mgr, `/api/obligors/${obligorId}/transactions`, body, `record-count-transactions-${safeId}`);
  }

  function _transactionColumns(obligorId, obligorName) {
    return [
      ColumnHelper.text('transaction_id',   'Txn ID',      { width: 125, pinned: 'left' }),
      ColumnHelper.text('reference_number', 'Reference',   { width: 130, hide: true }),
      ColumnHelper.text('transaction_type', 'Type',        { width: 150 }),
      ColumnHelper.money('amount',          'Amount',      { width: 130 }),
      ColumnHelper.text('currency',         'Currency',    { width:  80 }),
      ColumnHelper.date('transaction_date', 'Txn Date',    { width: 110 }),
      ColumnHelper.date('value_date',       'Value Date',  { width: 110, hide: true }),
      ColumnHelper.statusChip('status',     'Status',      { width: 110 }),
      ColumnHelper.text('created_by',       'Created By',  { width: 120, hide: true }),
      ColumnHelper.text('approved_by',      'Approved By', { width: 120, hide: true }),
      ColumnHelper.text('description',      'Description', { width: 220, tooltipField: 'description' }),
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
      breadcrumb: [obligorName || 'Obligor', txnType, 'Analyst Comments'],
      onMount:    (panel) => _mountCommentModal(panel, transactionId),
    });
  }

  function _mountCommentModal(panel, transactionId) {
    const safeId = transactionId.replace(/[^a-z0-9]/gi, '-');
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

    body.querySelectorAll('.modal-export-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const fmt = btn.dataset.format;
        ApiUtils.downloadFile(`/api/export/transactions/${transactionId}/comments?format=${fmt}`);
        Toast.success('Export started', `Downloading comments as ${fmt.toUpperCase()}`);
      });
    });

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
      ColumnHelper.statusChip('status', 'Status',      { width: 110 }),
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
    const safeId = entityId.replace(/[^a-z0-9]/gi, '-');
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
          <span class="export-label">Export</span>
          <button class="btn btn-export modal-export-btn" data-format="csv">CSV</button>
          <button class="btn btn-export modal-export-btn" data-format="excel">Excel</button>
          <button class="btn btn-export modal-export-btn" data-format="parquet">Parquet</button>
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

      // Refit after data arrives (container is definitely laid out by now)
      setTimeout(() => mgr.getApi().sizeColumnsToFit(), 50);

      const totalLabel = bodyEl.querySelector(`#${countLabelId}`);
      if (totalLabel && resp.meta) {
        totalLabel.innerHTML = `Showing <strong>${resp.data.length}</strong> of <strong>${resp.meta.total}</strong> records`;
      }
    } catch (err) {
      Toast.error('Failed to load data', err.message || 'Unknown error');
      console.error('DrillDown fetch error:', err);
    }
  }

  // ── Public surface ─────────────────────────────────────────────────────────

  return { openObligors, openTransactions, openComments };

}());
