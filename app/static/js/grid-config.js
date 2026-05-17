/**
 * grid-config.js — Reusable AG Grid factory and column definition helpers.
 *
 * Responsibilities:
 *  - GridManager class: wraps agGrid.createGrid(), manages lifecycle.
 *  - ColumnHelper:      builds typed column definitions.
 *  - CellRenderer:      provides common cell rendering functions.
 *
 * All code is namespaced under the global `GridConfig` object.
 */

// ── Cell renderers ─────────────────────────────────────────────────────────────

const CellRenderer = (function () {

  /**
   * Render a status string as a coloured chip.
   * @param {Object} params - AG Grid cell params.
   * @returns {HTMLElement}
   */
  function status(params) {
    const val = (params.value || '').toString();
    const key = val.toLowerCase().replace(/\s+/g, '-');
    const el  = document.createElement('span');
    el.className = `status-chip chip-${key}`;
    el.innerHTML = `<span class="status-dot"></span>${val}`;
    return el;
  }

  /**
   * Render a risk rating with colour-coded background.
   * @param {Object} params
   * @returns {HTMLElement}
   */
  function riskRating(params) {
    const val = (params.value || '').toString();
    const key = val.replace(/[^a-z]/gi, '').toLowerCase().slice(0, 3);  // aaa, aa, a, bbb, bb, b
    const el  = document.createElement('span');
    el.className = `risk-chip risk-${key}`;
    el.textContent = val;
    return el;
  }

  /**
   * Render a utilisation percentage with an inline progress bar.
   * @param {Object} params
   * @returns {HTMLElement}
   */
  function utilisation(params) {
    const pct  = parseFloat(params.value) || 0;
    const color = pct >= 90 ? '#c0392b' : pct >= 70 ? '#c47a00' : '#1b7a3e';
    const el   = document.createElement('div');
    el.className = 'util-bar-wrap';
    el.innerHTML = `
      <div class="util-bar">
        <div class="util-bar-fill" style="width:${Math.min(pct,100)}%;background:${color};"></div>
      </div>
      <span class="util-pct">${pct.toFixed(1)}%</span>
    `;
    return el;
  }

  /**
   * Render a monetary amount with locale formatting.
   * @param {Object} params
   * @returns {string}
   */
  function money(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '–';
    const n = parseFloat(params.value);
    return isNaN(n) ? params.value : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  /**
   * Render a drill-down trigger link for a count value.
   * Returns a plain span if value is zero.
   *
   * @param {Object} params
   * @param {Function} clickHandler  - Called with (params) when clicked.
   * @returns {HTMLElement}
   */
  function drillDownLink(params, clickHandler) {
    const val = parseInt(params.value, 10) || 0;
    if (val === 0) {
      const span = document.createElement('span');
      span.className = 'text-muted';
      span.textContent = '0';
      return span;
    }
    const a = document.createElement('a');
    a.href      = 'javascript:void(0)';
    a.className = 'drill-link';
    a.textContent = val.toLocaleString();
    a.addEventListener('click', (e) => {
      e.stopPropagation();
      clickHandler(params);
    });
    return a;
  }

  return { status, riskRating, utilisation, money, drillDownLink };

}());


// ── Column helpers ─────────────────────────────────────────────────────────────

const ColumnHelper = (function () {

  /** Common defaults shared by all columns. */
  const _base = {
    sortable:   true,
    filter:     true,
    resizable:  true,
    minWidth:   80,
  };

  /**
   * Plain text column.
   * @param {string} field
   * @param {string} header
   * @param {Object} extra  - Overrides / additions.
   */
  function text(field, header, extra = {}) {
    return { ..._base, field, headerName: header, filter: 'agTextColumnFilter', ...extra };
  }

  /**
   * Numeric column (right-aligned, number filter).
   * @param {string} field
   * @param {string} header
   * @param {Object} extra
   */
  function number(field, header, extra = {}) {
    return {
      ..._base,
      field,
      headerName:    header,
      filter:        'agNumberColumnFilter',
      type:          'numericColumn',
      ...extra,
    };
  }

  /**
   * Date column with date filter.
   */
  function date(field, header, extra = {}) {
    return { ..._base, field, headerName: header, filter: 'agDateColumnFilter', ...extra };
  }

  /**
   * Money column — right-aligned, formatted with CellRenderer.money.
   */
  function money(field, header, extra = {}) {
    return {
      ...number(field, header),
      cellRenderer:  CellRenderer.money,
      cellClass:     'cell-numeric text-right',
      headerClass:   'ag-right-aligned-header',
      ...extra,
    };
  }

  /**
   * Status chip column.
   */
  function statusChip(field, header, extra = {}) {
    return {
      ...text(field, header),
      cellRenderer: CellRenderer.status,
      ...extra,
    };
  }

  return { text, number, date, money, statusChip };

}());


// ── Grid manager ───────────────────────────────────────────────────────────────

class GridManager {
  /**
   * Wraps an AG Grid instance for a given container element.
   *
   * @param {string}   containerId - DOM element ID to mount the grid in.
   * @param {Object[]} columnDefs  - AG Grid column definitions.
   * @param {Object}   [options]   - Additional AG Grid options.
   */
  constructor(containerId, columnDefs, options = {}) {
    this._containerId = containerId;
    this._columnDefs  = columnDefs;
    this._options     = options;
    this._api         = null;    // AG Grid GridApi
  }

  /**
   * Create and mount the AG Grid instance.
   * @returns {GridManager} this (chainable)
   */
  init() {
    const container = document.getElementById(this._containerId);
    if (!container) throw new Error(`Grid container '${this._containerId}' not found in DOM.`);

    const gridOptions = {
      columnDefs:    this._columnDefs,
      rowData:       [],

      defaultColDef: {
        sortable:    true,
        filter:      true,
        resizable:   true,
        minWidth:    80,
        filterParams: { buttons: ['reset', 'apply'], closeOnApply: true },
      },

      // Pagination
      pagination:              true,
      paginationPageSize:      25,
      paginationPageSizeSelector: [10, 25, 50, 100],

      // UX
      animateRows:             true,
      enableCellTextSelection: true,
      suppressMenuHide:        false,
      tooltipShowDelay:        400,

      // Callbacks
      onGridReady:             (e) => this._onGridReady(e),

      ...this._options,
    };

    this._api = agGrid.createGrid(container, gridOptions);
    return this;
  }

  // ── Data management ──────────────────────────────────────────────────────────

  /**
   * Replace the grid's row data.
   * @param {Object[]} rows
   */
  setData(rows) {
    this._api.setGridOption('rowData', rows);
  }

  /**
   * Apply a quick-filter string across all visible columns.
   * @param {string} text
   */
  setQuickFilter(text) {
    this._api.setGridOption('quickFilterText', text);
  }

  /** Remove all active column filters. */
  clearFilters() {
    this._api.setFilterModel(null);
  }

  /** Export visible data as CSV via AG Grid's built-in exporter. */
  exportCsv(filename = 'export.csv') {
    this._api.exportDataAsCsv({ fileName: filename });
  }

  /** Show/hide the columns tool panel. */
  toggleColumnsPanel() {
    const panel = this._api.getOpenedToolPanel();
    if (panel === 'columns') {
      this._api.closeToolPanel();
    } else {
      this._api.openToolPanel('columns');
    }
  }

  /** Return the raw GridApi for advanced use. */
  getApi() {
    return this._api;
  }

  // ── Internal callbacks ────────────────────────────────────────────────────────

  _onGridReady(event) {
    // Defer one frame so the browser has computed the container's final width
    // before AG Grid distributes column space. Without this, grids inside
    // freshly-injected DOM (e.g. modals) can measure a 0-px container.
    requestAnimationFrame(() => event.api.sizeColumnsToFit());
  }

}
