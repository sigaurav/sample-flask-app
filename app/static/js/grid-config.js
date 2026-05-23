/**
 * grid-config.js — Custom table grid factory and column definition helpers.
 *
 * Responsibilities:
 *  - GridManager class: custom HTML table grid (no external dependencies).
 *  - ColumnHelper:      builds typed column definitions.
 *  - CellRenderer:      provides common cell rendering functions.
 *
 * FR Y-14Q enhancements over baseline:
 *  - Multi-column sorting with priority ordering (Ctrl+click to add).
 *  - Date column filters (agDateColumnFilter).
 *  - Categorical filters (col.values array → checkbox list).
 *  - Reliable resize→sort isolation: pixel-distance guard on th click.
 *  - getFilterSortState() for async export job specs.
 */

// ── Cell renderers ─────────────────────────────────────────────────────────────

const CellRenderer = (function () {

  function status(params) {
    const val = (params.value || '').toString();
    const key = val.toLowerCase().replace(/\s+/g, '-');
    const el  = document.createElement('span');
    el.className = `status-chip chip-${key}`;
    el.innerHTML = `<span class="status-dot"></span>${val}`;
    return el;
  }

  function riskRating(params) {
    const val = (params.value || '').toString();
    const key = val.replace(/[^a-z]/gi, '').toLowerCase().slice(0, 3);
    const el  = document.createElement('span');
    el.className = `risk-chip risk-${key}`;
    el.textContent = val;
    return el;
  }

  function utilisation(params) {
    const pct   = parseFloat(params.value) || 0;
    const color = pct >= 90 ? '#c0392b' : pct >= 70 ? '#c47a00' : '#1b7a3e';
    const el    = document.createElement('div');
    el.className = 'util-bar-wrap';
    el.innerHTML = `
      <div class="util-bar">
        <div class="util-bar-fill" style="width:${Math.min(pct,100)}%;background:${color};"></div>
      </div>
      <span class="util-pct">${pct.toFixed(1)}%</span>
    `;
    return el;
  }

  function money(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '–';
    const n = parseFloat(params.value);
    return isNaN(n) ? params.value : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function drillDownLink(params, clickHandler) {
    const val = parseInt(params.value, 10) || 0;
    if (val === 0) {
      const span = document.createElement('span');
      span.className = 'text-muted';
      span.textContent = '0';
      return span;
    }
    const a = document.createElement('a');
    a.href        = 'javascript:void(0)';
    a.className   = 'drill-link';
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

  const _base = { sortable: true, filter: true, resizable: true, minWidth: 80 };

  function text(field, header, extra = {}) {
    return { ..._base, field, headerName: header, filter: 'agTextColumnFilter', ...extra };
  }

  function number(field, header, extra = {}) {
    return { ..._base, field, headerName: header, filter: 'agNumberColumnFilter', type: 'numericColumn', ...extra };
  }

  function date(field, header, extra = {}) {
    return { ..._base, field, headerName: header, filter: 'agDateColumnFilter', ...extra };
  }

  function money(field, header, extra = {}) {
    return {
      ...number(field, header),
      cellRenderer: CellRenderer.money,
      cellClass:    'cell-numeric',
      _alignRight:  true,
      ...extra,
    };
  }

  function statusChip(field, header, extra = {}) {
    return { ...text(field, header), cellRenderer: CellRenderer.status, ...extra };
  }

  return { text, number, date, money, statusChip };

}());


// ── Grid manager ───────────────────────────────────────────────────────────────

class GridManager {
  /**
   * Custom HTML table grid — drop-in replacement for the former AG Grid wrapper.
   *
   * @param {string}   containerId - DOM element ID to mount into.
   * @param {Object[]} columnDefs  - Column definitions (same shape as before).
   * @param {Object}   [options]   - paginationPageSize, paginationPageSizeSelector.
   */
  constructor(containerId, columnDefs, options = {}) {
    this._containerId = containerId;
    this._columnDefs  = columnDefs;
    this._options     = options;

    // Dataset state
    this._allData      = [];
    this._filteredData = [];

    // Multi-column sort state: [{field, dir}] in priority order (index 0 = primary).
    this._sortState = [];

    // Pagination state
    this._page     = 0;
    this._pageSize = options.paginationPageSize ?? 25;
    this._pageSizeOptions = options.paginationPageSizeSelector ?? [10, 25, 50, 100];

    // Filter state
    this._quickFilter = '';
    this._colFilters  = new Map();   // field → { op, val }

    // Column visibility — initialise from col.hide
    this._hiddenCols = new Set(columnDefs.filter(c => c.hide).map(c => c.field));

    // UI state
    this._colPanel     = null;   // open column-picker dropdown
    this._filterPopup  = null;   // open column-filter popup

    // DOM ref for <colgroup>
    this._colgroup = null;

    // Column resize / reorder state
    this._colWidthOverrides = new Map();  // field → user-dragged px width
    this._dragSrcField      = null;       // field being column-dragged
    this._didDrag           = false;      // suppresses sort click after a drop

    // Resize tracking — per-header mousedown position for click-vs-drag detection.
    // A sort click is only fired when mouse has moved ≤ 4px since mousedown on th.
    this._thDownX = 0;
    this._thDownY = 0;

    // DOM refs (set in _buildTable)
    this._container = null;
    this._wrapper   = null;
    this._table     = null;
    this._thead     = null;
    this._tbody     = null;
    this._pagBar    = null;
  }

  // ── Public lifecycle ─────────────────────────────────────────────────────────

  init() {
    this._container = document.getElementById(this._containerId);
    if (!this._container) throw new Error(`Grid container '${this._containerId}' not found.`);
    this._buildTable();
    this._render();
    requestAnimationFrame(() => this._recalcWidths());

    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(() => this._recalcWidths()).observe(this._container);
    }
    return this;
  }

  // ── Public data API ──────────────────────────────────────────────────────────

  setData(rows) {
    this._allData = rows || [];
    this._page    = 0;
    this._render();
  }

  setQuickFilter(text) {
    this._quickFilter = text || '';
    this._page = 0;
    this._render();
  }

  clearFilters() {
    this._quickFilter = '';
    this._colFilters.clear();
    this._sortState   = [];
    this._page        = 0;
    this._render();
  }

  exportCsv(filename = 'export.csv') {
    const cols   = this._visibleCols();
    const escape = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const header = cols.map(c => escape(c.headerName || c.field)).join(',');
    const body   = this._filteredData
      .map(row => cols.map(c => escape(row[c.field])).join(','))
      .join('\n');
    const blob = new Blob([header + '\n' + body], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a    = Object.assign(document.createElement('a'), { href: url, download: filename });
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Return current filter and sort state for async export job specs.
   * The returned object is JSON-serialisable and can be POSTed directly.
   */
  getFilterSortState() {
    return {
      quick_filter: this._quickFilter,
      col_filters:  Object.fromEntries(this._colFilters),
      sort_state:   this._sortState.map(s => ({ field: s.field, dir: s.dir })),
    };
  }

  /** Compatibility shim — callers use getApi().sizeColumnsToFit() */
  getApi() {
    return { sizeColumnsToFit: () => this._recalcWidths() };
  }

  // ── Column picker panel ──────────────────────────────────────────────────────

  toggleColumnsPanel(anchorEl) {
    if (this._colPanel) {
      this._colPanel.remove();
      this._colPanel = null;
      return;
    }

    const panel = document.createElement('div');
    panel.className = 'col-picker-panel';

    const header = document.createElement('div');
    header.className = 'col-picker-header';
    header.textContent = 'Show / Hide Columns';
    panel.appendChild(header);

    const list = document.createElement('div');
    list.className = 'col-picker-list';

    // ── Select All row ─────────────────────────────────────────────────────────
    const allItem = document.createElement('label');
    allItem.className = 'col-picker-item col-picker-select-all';

    const allCb = document.createElement('input');
    allCb.type = 'checkbox';

    const visibleDefs  = this._columnDefs.filter(c => c.headerName || c.field);
    const allVisible   = visibleDefs.every(c => !this._hiddenCols.has(c.field));
    const noneVisible  = visibleDefs.every(c =>  this._hiddenCols.has(c.field));
    allCb.checked       = allVisible;
    allCb.indeterminate = !allVisible && !noneVisible;

    const updateAllCb = () => {
      const cbs = list.querySelectorAll('input[type="checkbox"]:not(.col-picker-all-cb)');
      const checkedCount = [...cbs].filter(c => c.checked).length;
      allCb.checked       = checkedCount === cbs.length;
      allCb.indeterminate = checkedCount > 0 && checkedCount < cbs.length;
    };

    allCb.className = 'col-picker-all-cb';
    allCb.addEventListener('change', () => {
      const cbs = list.querySelectorAll('input[type="checkbox"]:not(.col-picker-all-cb)');
      cbs.forEach(cb => { cb.checked = allCb.checked; cb.dispatchEvent(new Event('change')); });
    });

    allItem.appendChild(allCb);
    allItem.appendChild(document.createTextNode(' Select All'));
    list.appendChild(allItem);

    const divider = document.createElement('div');
    divider.style.cssText = 'height:1px;background:#f0f0f0;margin:2px 0';
    list.appendChild(divider);

    this._columnDefs.forEach(col => {
      const label = col.headerName || col.field;
      if (!label) return;

      const item = document.createElement('label');
      item.className = 'col-picker-item';

      const cb = document.createElement('input');
      cb.type    = 'checkbox';
      cb.checked = !this._hiddenCols.has(col.field);
      cb.addEventListener('change', () => {
        if (cb.checked) this._hiddenCols.delete(col.field);
        else            this._hiddenCols.add(col.field);
        updateAllCb();
        this._render();
      });

      item.appendChild(cb);
      item.appendChild(document.createTextNode(' ' + label));
      list.appendChild(item);
    });

    panel.appendChild(list);
    document.body.appendChild(panel);
    this._colPanel = panel;

    const rect = anchorEl.getBoundingClientRect();
    panel.style.top  = (rect.bottom + window.scrollY + 4) + 'px';
    panel.style.left = (rect.left  + window.scrollX)      + 'px';

    const onOutside = (e) => {
      if (!panel.contains(e.target) && e.target !== anchorEl) {
        panel.remove();
        this._colPanel = null;
        document.removeEventListener('mousedown', onOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutside), 0);
  }

  // ── DOM construction (one-time) ──────────────────────────────────────────────

  _buildTable() {
    this._container.innerHTML = '';

    this._wrapper = document.createElement('div');
    this._wrapper.className = 'wf-table-wrapper';

    this._table = document.createElement('table');
    this._table.className = 'wf-table';

    this._colgroup = document.createElement('colgroup');
    this._thead    = document.createElement('thead');
    this._tbody    = document.createElement('tbody');
    this._table.appendChild(this._colgroup);
    this._table.appendChild(this._thead);
    this._table.appendChild(this._tbody);

    this._pagBar = document.createElement('div');
    this._pagBar.className = 'wf-pag-bar';

    this._wrapper.appendChild(this._table);
    this._container.appendChild(this._wrapper);
    this._container.appendChild(this._pagBar);
  }

  // ── Render pipeline ──────────────────────────────────────────────────────────

  _render() {
    this._applyFilters();
    this._applySort();
    const start    = this._page * this._pageSize;
    const pageData = this._filteredData.slice(start, start + this._pageSize);
    this._buildHeaders();
    this._buildRows(pageData);
    this._buildPagination();
    this._recalcWidths();
  }

  _applyFilters() {
    let rows = this._allData;
    const q  = this._quickFilter.trim().toLowerCase();

    if (q) {
      rows = rows.filter(row =>
        this._columnDefs.some(col => {
          if (this._hiddenCols.has(col.field)) return false;
          return String(row[col.field] ?? '').toLowerCase().includes(q);
        })
      );
    }

    this._colFilters.forEach(({ op, val }, field) => {
      if (val === '' || val === null || val === undefined) return;
      rows = rows.filter(row => {
        const cell = row[field];
        const s    = String(cell ?? '').toLowerCase();
        const sv   = String(val).toLowerCase();
        switch (op) {
          case 'contains':   return s.includes(sv);
          case 'equals':     return s === sv;
          case 'startsWith': return s.startsWith(sv);
          case 'numEq':      return parseFloat(cell) === parseFloat(val);
          case 'gt':         return parseFloat(cell) >  parseFloat(val);
          case 'gte':        return parseFloat(cell) >= parseFloat(val);
          case 'lt':         return parseFloat(cell) <  parseFloat(val);
          case 'lte':        return parseFloat(cell) <= parseFloat(val);
          // Date ops
          case 'dateEq': {
            const d = new Date(cell); const ref = new Date(val);
            return !isNaN(d) && !isNaN(ref) && d.toDateString() === ref.toDateString();
          }
          case 'dateBefore': {
            const d = new Date(cell); const ref = new Date(val);
            return !isNaN(d) && !isNaN(ref) && d < ref;
          }
          case 'dateAfter': {
            const d = new Date(cell); const ref = new Date(val);
            return !isNaN(d) && !isNaN(ref) && d > ref;
          }
          // Categorical — val is comma-separated accepted values
          case 'inList': {
            const accepted = new Set(val.split(',').map(v => v.trim().toLowerCase()));
            return accepted.has(s);
          }
          default: return true;
        }
      });
    });

    // Always copy so _applySort cannot mutate _allData in-place.
    // Do NOT reset _page here — page resets are the caller's responsibility
    // so that pagination button clicks (_page already set) are not overwritten.
    this._filteredData = [...rows];
  }

  // Multi-column sort: primary key first, then secondary, tertiary, etc.
  _applySort() {
    if (this._sortState.length === 0) return;

    this._filteredData.sort((a, b) => {
      for (const { field, dir } of this._sortState) {
        const col       = this._columnDefs.find(c => c.field === field);
        const isNumeric = col && (col.filter === 'agNumberColumnFilter' || col.type === 'numericColumn');
        const isDate    = col && col.filter === 'agDateColumnFilter';

        let av = a[field], bv = b[field];
        if (isNumeric) {
          av = parseFloat(av) || 0;
          bv = parseFloat(bv) || 0;
        } else if (isDate) {
          av = av ? new Date(av).getTime() : 0;
          bv = bv ? new Date(bv).getTime() : 0;
        } else {
          av = String(av ?? '').toLowerCase();
          bv = String(bv ?? '').toLowerCase();
        }

        if (av < bv) return dir === 'asc' ? -1 :  1;
        if (av > bv) return dir === 'asc' ?  1 : -1;
        // equal on this key → fall through to next sort key
      }
      return 0;
    });
  }

  // ── Header building ──────────────────────────────────────────────────────────

  _buildHeaders() {
    this._thead.innerHTML    = '';
    this._colgroup.innerHTML = '';
    this._visibleCols().forEach(col => {
      const c = document.createElement('col');
      c.dataset.field = col.field;
      this._colgroup.appendChild(c);
    });

    const tr = document.createElement('tr');
    const leftOffsets  = this._stickyOffsets('left');
    const rightOffsets = this._stickyOffsets('right');

    this._visibleCols().forEach(col => {
      const th = document.createElement('th');
      th.className     = 'wf-th';
      th.dataset.field = col.field;

      const isRight = col._alignRight || col.type === 'numericColumn' ||
                      col.filter === 'agNumberColumnFilter';
      if (isRight) th.classList.add('wf-th-right');

      if (col.pinned === 'left') {
        th.classList.add('wf-th-pinned-left');
        th.style.position = 'sticky';
        th.style.left     = leftOffsets[col.field] + 'px';
        th.style.zIndex   = '3';
      } else if (col.pinned === 'right') {
        th.classList.add('wf-th-pinned-right');
        th.style.position = 'sticky';
        th.style.right    = rightOffsets[col.field] + 'px';
        th.style.zIndex   = '3';
      }

      // Sort state for this column
      const sortIdx   = this._sortState.findIndex(s => s.field === col.field);
      const sortEntry = sortIdx !== -1 ? this._sortState[sortIdx] : null;
      if (sortEntry) th.classList.add('wf-th-sorted');

      // Inner layout: label | sort icon | filter btn
      const inner = document.createElement('div');
      inner.className = 'wf-th-inner';

      const label = document.createElement('span');
      label.className   = 'wf-th-label';
      label.textContent = col.headerName || col.field;
      inner.appendChild(label);

      // Sort icon — shows arrow + priority number when multi-sorting
      const sortIcon = document.createElement('span');
      sortIcon.className = 'wf-sort-icon';
      if (sortEntry) {
        const arrow    = sortEntry.dir === 'asc' ? '↑' : '↓';
        const showPrio = this._sortState.length > 1;
        sortIcon.innerHTML = showPrio
          ? `${arrow}<sup class="wf-sort-priority">${sortIdx + 1}</sup>`
          : arrow;
      }
      inner.appendChild(sortIcon);

      // Filter button
      if (col.filter && col.filter !== false) {
        const filterBtn = document.createElement('button');
        filterBtn.className = 'wf-filter-btn';
        filterBtn.title     = 'Filter column';
        filterBtn.innerHTML = '<svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>';
        if (this._colFilters.has(col.field)) filterBtn.classList.add('wf-filter-active');

        filterBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._openFilterPopup(col, filterBtn);
        });
        inner.appendChild(filterBtn);
      }

      th.appendChild(inner);

      // ── Resize handle ──────────────────────────────────────────────────────
      if (col.pinned !== 'right') {
        const handle = document.createElement('div');
        handle.className = 'wf-resize-handle';
        handle.setAttribute('draggable', 'false');
        handle.addEventListener('mousedown', (e) => {
          e.stopPropagation();
          e.preventDefault();

          const startX      = e.clientX;
          const startW      = th.offsetWidth;
          const startTableW = this._table.offsetWidth;
          const minW        = col.minWidth ?? 50;
          const colEl       = this._colgroup.querySelector(`col[data-field="${col.field}"]`);

          document.body.style.cursor     = 'col-resize';
          document.body.style.userSelect = 'none';

          // Disable sort click for this th for the duration of the drag.
          // _thDownX is intentionally set far away so the pixel guard fails.
          this._thDownX = -9999;

          const onMove = (ev) => {
            const newW = Math.max(minW, startW + (ev.clientX - startX));
            if (colEl) colEl.style.width = newW + 'px';
            this._table.style.width = (startTableW + newW - startW) + 'px';
          };

          const onUp = (ev) => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.body.style.cursor     = '';
            document.body.style.userSelect = '';
            this._colWidthOverrides.set(col.field, Math.max(minW, startW + (ev.clientX - startX)));
            this._recalcWidths();
          };

          document.addEventListener('mousemove', onMove);
          document.addEventListener('mouseup', onUp);
        });
        th.appendChild(handle);
      }

      // ── Column drag-to-reorder ─────────────────────────────────────────────
      th.setAttribute('draggable', 'true');
      th.addEventListener('dragstart', (e) => {
        // Modifier-key click = additive sort intent — cancel drag so _didDrag stays false.
        if (e.ctrlKey || e.metaKey || e.shiftKey) { e.preventDefault(); return; }
        this._dragSrcField = col.field;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', col.field);
        th.classList.add('wf-th-dragging');
      });
      th.addEventListener('dragend', () => {
        this._dragSrcField = null;
        // _didDrag intentionally not set here — Chrome does not fire `click` after a
        // real drag (mouse moved), so the pixel-distance guard in the click handler
        // is sufficient. Setting _didDrag here would suppress Ctrl+click sort.
        document.querySelectorAll('.wf-th-dragging, .wf-th-drag-over')
          .forEach(el => el.classList.remove('wf-th-dragging', 'wf-th-drag-over'));
      });
      th.addEventListener('dragover', (e) => {
        if (!this._dragSrcField || this._dragSrcField === col.field) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        th.classList.add('wf-th-drag-over');
      });
      th.addEventListener('dragleave', () => th.classList.remove('wf-th-drag-over'));
      th.addEventListener('drop', (e) => {
        e.preventDefault();
        th.classList.remove('wf-th-drag-over');
        if (this._dragSrcField && this._dragSrcField !== col.field) {
          this._moveColumn(this._dragSrcField, col.field);
        }
        this._dragSrcField = null;
      });

      // ── Sort click ─────────────────────────────────────────────────────────
      // Track mousedown position so we can distinguish click from drag.
      if (col.sortable !== false) {
        th.style.cursor = 'pointer';
        th.addEventListener('mousedown', (e) => {
          this._thDownX = e.clientX;
          this._thDownY = e.clientY;
          this._didDrag = false;   // reset before every new click interaction
        });
        th.addEventListener('click', (e) => {
          // Suppress sort if mouse moved > 4px since mousedown (resize / column-drag).
          const dx = Math.abs(e.clientX - this._thDownX);
          const dy = Math.abs(e.clientY - this._thDownY);
          if (dx > 4 || dy > 4) return;
          this._onSortClick(col.field, e.ctrlKey || e.metaKey || e.shiftKey);
        });
      }

      tr.appendChild(th);
    });

    this._thead.appendChild(tr);
  }

  /**
   * Handle a sort click on *field*.
   *
   * @param {string}  field    - Column field name.
   * @param {boolean} additive - Ctrl/Meta held → add to sort stack without
   *                             clearing existing sort columns.
   *
   * Cycle without additive (single-column):
   *   none → asc → desc → none
   *
   * Cycle with additive (multi-column, APPEND model):
   *   New column → appended at the end (becomes lowest-priority key)
   *   Existing column → cycles asc → desc → (removed from stack)
   *
   * Priority order = click order: first Ctrl+click = primary,
   * second = secondary, third = tertiary, etc.
   */
  _onSortClick(field, additive = false) {
    const existingIdx = this._sortState.findIndex(s => s.field === field);

    if (additive) {
      if (existingIdx !== -1) {
        // Column already in stack — cycle it in place
        const cur = this._sortState[existingIdx];
        if (cur.dir === 'asc') {
          this._sortState[existingIdx] = { field, dir: 'desc' };
        } else {
          this._sortState.splice(existingIdx, 1);
        }
      } else {
        // New column — append as next priority key
        this._sortState.push({ field, dir: 'asc' });
      }
    } else {
      // Replace entire sort state with single-column cycle
      if (existingIdx !== -1 && this._sortState.length === 1) {
        const cur = this._sortState[0];
        if (cur.dir === 'asc') {
          this._sortState = [{ field, dir: 'desc' }];
        } else {
          this._sortState = [];
        }
      } else {
        this._sortState = [{ field, dir: 'asc' }];
      }
    }

    this._page = 0;
    this._render();
  }

  // ── Row building ─────────────────────────────────────────────────────────────

  _buildRows(pageData) {
    this._tbody.innerHTML = '';

    if (pageData.length === 0) {
      const cols = this._visibleCols();
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.className   = 'wf-no-rows';
      td.colSpan     = cols.length || 1;
      td.textContent = 'No records match the current filters.';
      tr.appendChild(td);
      this._tbody.appendChild(tr);
      return;
    }

    const leftOffsets  = this._stickyOffsets('left');
    const rightOffsets = this._stickyOffsets('right');

    pageData.forEach(row => {
      const tr = document.createElement('tr');
      tr.className = 'wf-tr';

      this._visibleCols().forEach(col => {
        const td = document.createElement('td');
        td.className = 'wf-td';

        if (col.cellClass) {
          String(col.cellClass).split(/\s+/).forEach(c => c && td.classList.add(c));
        }

        const isRight = col._alignRight || col.type === 'numericColumn' ||
                        col.filter === 'agNumberColumnFilter';
        if (isRight) td.classList.add('wf-td-right');

        if (col.pinned === 'left') {
          td.classList.add('wf-td-pinned-left');
          td.style.position = 'sticky';
          td.style.left     = leftOffsets[col.field] + 'px';
          td.style.zIndex   = '2';
        } else if (col.pinned === 'right') {
          td.classList.add('wf-td-pinned-right');
          td.style.position = 'sticky';
          td.style.right    = rightOffsets[col.field] + 'px';
          td.style.zIndex   = '2';
        }

        if (col.tooltipField && row[col.tooltipField]) {
          td.title = String(row[col.tooltipField]);
        }

        if (col.wrapText) {
          td.style.whiteSpace    = 'normal';
          td.style.height        = 'auto';
          td.style.verticalAlign = 'top';
          td.style.paddingTop    = '8px';
          td.style.paddingBottom = '8px';
        }

        const params = { value: row[col.field], data: row, colDef: col };
        if (typeof col.cellRenderer === 'function') {
          const result = col.cellRenderer(params);
          if (result instanceof HTMLElement) td.appendChild(result);
          else td.textContent = result ?? '';
        } else {
          td.textContent = row[col.field] ?? '';
        }

        tr.appendChild(td);
      });

      this._tbody.appendChild(tr);
    });
  }

  // ── Pagination bar ───────────────────────────────────────────────────────────

  _buildPagination() {
    this._pagBar.innerHTML = '';

    const total      = this._filteredData.length;
    const totalPages = Math.max(1, Math.ceil(total / this._pageSize));
    const start      = total === 0 ? 0 : this._page * this._pageSize + 1;
    const end        = Math.min(total, (this._page + 1) * this._pageSize);

    // Active sort hint
    const sortHint = this._sortState.length > 0
      ? this._sortState.map(s => `${s.field} ${s.dir === 'asc' ? '↑' : '↓'}`).join(', ')
      : '';

    const info = document.createElement('span');
    info.className = 'wf-pag-info';
    info.innerHTML = `Rows ${start}–${end} of <strong>${total.toLocaleString()}</strong>` +
      (sortHint ? `<span class="wf-sort-hint"> · Sorted: ${sortHint}</span>` : '');
    this._pagBar.appendChild(info);

    const controls = document.createElement('div');
    controls.className = 'wf-pag-controls';

    const sizeLabel = document.createElement('label');
    sizeLabel.textContent = 'Rows per page:';
    sizeLabel.style.marginRight = '4px';
    controls.appendChild(sizeLabel);

    const sizeSelect = document.createElement('select');
    sizeSelect.className = 'wf-pag-size';
    this._pageSizeOptions.forEach(n => {
      const opt = document.createElement('option');
      opt.value    = n;
      opt.textContent = n;
      opt.selected = n === this._pageSize;
      sizeSelect.appendChild(opt);
    });
    sizeSelect.addEventListener('change', () => {
      this._pageSize = parseInt(sizeSelect.value, 10);
      this._page     = 0;
      this._render();
    });
    controls.appendChild(sizeSelect);

    const mkBtn = (label, action, disabled) => {
      const btn = document.createElement('button');
      btn.className   = 'wf-pag-btn';
      btn.textContent = label;
      btn.disabled    = disabled;
      btn.addEventListener('click', () => { this._page = action(); this._render(); });
      return btn;
    };

    controls.appendChild(mkBtn('«', () => 0,              this._page === 0));
    controls.appendChild(mkBtn('‹', () => this._page - 1, this._page === 0));

    const pageLabel = document.createElement('span');
    pageLabel.className   = 'wf-pag-page';
    pageLabel.textContent = `Page ${this._page + 1} of ${totalPages}`;
    controls.appendChild(pageLabel);

    controls.appendChild(mkBtn('›', () => this._page + 1,       this._page >= totalPages - 1));
    controls.appendChild(mkBtn('»', () => totalPages - 1,        this._page >= totalPages - 1));

    this._pagBar.appendChild(controls);
  }

  // ── Column width calculation ─────────────────────────────────────────────────

  _recalcWidths() {
    const containerWidth = this._container.clientWidth;
    if (!containerWidth) return;

    const cols     = this._visibleCols();
    let   fixedSum = 0, flexSum = 0;

    cols.forEach(col => {
      if (this._colWidthOverrides.has(col.field)) {
        fixedSum += this._colWidthOverrides.get(col.field);
      } else if (col.flex) {
        flexSum += col.flex;
      } else {
        fixedSum += col.width ?? col.minWidth ?? 80;
      }
    });

    const flexPool = Math.max(0, containerWidth - fixedSum);
    const widths   = {};

    cols.forEach(col => {
      if (this._colWidthOverrides.has(col.field)) {
        widths[col.field] = this._colWidthOverrides.get(col.field);
      } else if (col.flex) {
        widths[col.field] = Math.max(
          col.minWidth ?? 80,
          Math.floor((col.flex / (flexSum || 1)) * flexPool)
        );
      } else {
        widths[col.field] = col.width ?? col.minWidth ?? 80;
      }
    });

    // Close floor-rounding gap so table exactly fills the container.
    let totalColWidth = cols.reduce((s, c) => s + widths[c.field], 0);
    const gap = containerWidth - totalColWidth;
    if (gap > 0) {
      let expandIdx = -1;
      for (let i = cols.length - 1; i >= 0; i--) {
        const c = cols[i];
        if (c.flex && !this._colWidthOverrides.has(c.field) && c.pinned !== 'right') {
          expandIdx = i; break;
        }
      }
      if (expandIdx === -1) {
        for (let i = cols.length - 1; i >= 0; i--) {
          if (cols[i].pinned !== 'right') { expandIdx = i; break; }
        }
      }
      if (expandIdx !== -1) {
        widths[cols[expandIdx].field] += gap;
        totalColWidth = containerWidth;
      }
    }

    this._table.style.width = totalColWidth + 'px';

    this._colgroup.querySelectorAll('col').forEach((colEl, i) => {
      const col = cols[i];
      if (col) colEl.style.width = widths[col.field] + 'px';
    });
  }

  // ── Column filter popup ──────────────────────────────────────────────────────

  _openFilterPopup(col, anchorEl) {
    if (this._filterPopup) {
      this._filterPopup.remove();
      this._filterPopup = null;
      if (this._filterPopupField === col.field) {
        this._filterPopupField = null;
        return;
      }
    }
    this._filterPopupField = col.field;

    const isNumeric      = col.filter === 'agNumberColumnFilter';
    const isDate         = col.filter === 'agDateColumnFilter';
    const isCategorical  = Array.isArray(col.values) && col.values.length > 0;
    const current        = this._colFilters.get(col.field) || {};

    const popup = document.createElement('div');
    popup.className = 'wf-col-filter-popup';

    const hdr = document.createElement('div');
    hdr.className   = 'wf-cfp-header';
    hdr.textContent = 'Filter: ' + (col.headerName || col.field);
    popup.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'wf-cfp-body';

    let applyFn;  // set per filter type

    if (isCategorical) {
      // ── Categorical filter — checkbox list ──────────────────────────────────
      const selected = new Set(
        current.op === 'inList' ? String(current.val || '').split(',').map(v => v.trim()) : []
      );

      const listWrap = document.createElement('div');
      listWrap.style.cssText = 'max-height:160px;overflow-y:auto;display:flex;flex-direction:column;gap:4px';

      col.values.forEach(v => {
        const lbl = document.createElement('label');
        lbl.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer';
        const cb = document.createElement('input');
        cb.type    = 'checkbox';
        cb.value   = v;
        cb.checked = selected.has(String(v));
        cb.style.accentColor = '#D71E28';
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(v));
        listWrap.appendChild(lbl);
      });

      body.appendChild(listWrap);
      applyFn = () => {
        const checked = [...listWrap.querySelectorAll('input:checked')].map(c => c.value);
        if (checked.length > 0 && checked.length < col.values.length) {
          this._colFilters.set(col.field, { op: 'inList', val: checked.join(',') });
        } else {
          this._colFilters.delete(col.field);
        }
      };

    } else if (isDate) {
      // ── Date filter ─────────────────────────────────────────────────────────
      const dateOps = [['dateEq','On date'],['dateBefore','Before'],['dateAfter','After']];

      const opSel = document.createElement('select');
      opSel.className = 'wf-cfp-op';
      dateOps.forEach(([val, lbl]) => {
        const opt = document.createElement('option');
        opt.value       = val;
        opt.textContent = lbl;
        opt.selected    = val === (current.op || 'dateEq');
        opSel.appendChild(opt);
      });

      const dateInput = document.createElement('input');
      dateInput.className = 'wf-cfp-val';
      dateInput.type      = 'date';
      dateInput.value     = current.val ?? '';
      dateInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyBtn.click(); });

      body.appendChild(opSel);
      body.appendChild(dateInput);

      applyFn = () => {
        const val = dateInput.value;
        if (val) this._colFilters.set(col.field, { op: opSel.value, val });
        else     this._colFilters.delete(col.field);
      };

    } else {
      // ── Text / numeric filter ────────────────────────────────────────────────
      const textOps    = [['contains','Contains'],['equals','Equals'],['startsWith','Starts with']];
      const numericOps = [['numEq','Equals'],['gt','Greater than'],['gte','≥'],
                          ['lt','Less than'],['lte','≤']];

      const opSel = document.createElement('select');
      opSel.className = 'wf-cfp-op';
      (isNumeric ? numericOps : textOps).forEach(([val, lbl]) => {
        const opt = document.createElement('option');
        opt.value       = val;
        opt.textContent = lbl;
        opt.selected    = val === (current.op || (isNumeric ? 'numEq' : 'contains'));
        opSel.appendChild(opt);
      });

      const valInput = document.createElement('input');
      valInput.className   = 'wf-cfp-val';
      valInput.type        = isNumeric ? 'number' : 'text';
      valInput.placeholder = 'Value…';
      valInput.value       = current.val ?? '';
      valInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyBtn.click(); });

      body.appendChild(opSel);
      body.appendChild(valInput);

      applyFn = () => {
        const val = valInput.value.trim();
        if (val !== '') this._colFilters.set(col.field, { op: opSel.value, val });
        else            this._colFilters.delete(col.field);
      };

      setTimeout(() => valInput.focus(), 0);
    }

    popup.appendChild(body);

    const footer = document.createElement('div');
    footer.className = 'wf-cfp-footer';

    const clearBtn = document.createElement('button');
    clearBtn.className   = 'wf-cfp-clear';
    clearBtn.textContent = 'Clear';
    clearBtn.addEventListener('click', () => {
      this._colFilters.delete(col.field);
      popup.remove();
      this._filterPopup = null;
      this._page = 0;
      this._render();
    });

    const applyBtn = document.createElement('button');
    applyBtn.className   = 'wf-cfp-apply';
    applyBtn.textContent = 'Apply';
    applyBtn.addEventListener('click', () => {
      applyFn();
      popup.remove();
      this._filterPopup = null;
      this._page = 0;
      this._render();
    });

    footer.appendChild(clearBtn);
    footer.appendChild(applyBtn);
    popup.appendChild(footer);

    document.body.appendChild(popup);
    this._filterPopup = popup;

    const rect = anchorEl.getBoundingClientRect();
    popup.style.top  = (rect.bottom + window.scrollY + 4) + 'px';
    popup.style.left = (rect.left   + window.scrollX - 180) + 'px';

    const onOutside = (e) => {
      if (!popup.contains(e.target) && e.target !== anchorEl) {
        popup.remove();
        this._filterPopup      = null;
        this._filterPopupField = null;
        document.removeEventListener('mousedown', onOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutside), 0);
  }

  // ── Helpers ──────────────────────────────────────────────────────────────────

  _visibleCols() {
    return this._columnDefs.filter(c => !this._hiddenCols.has(c.field));
  }

  _stickyOffsets(side) {
    const result   = {};
    const cols     = this._visibleCols();
    let   offset   = 0;
    const colWidth = (col) =>
      this._colWidthOverrides.get(col.field) ?? col.width ?? col.minWidth ?? 80;

    if (side === 'left') {
      cols.forEach(col => {
        if (col.pinned === 'left') { result[col.field] = offset; offset += colWidth(col); }
      });
    } else {
      [...cols].reverse().forEach(col => {
        if (col.pinned === 'right') { result[col.field] = offset; offset += colWidth(col); }
      });
    }
    return result;
  }

  _moveColumn(srcField, tgtField) {
    const srcIdx = this._columnDefs.findIndex(c => c.field === srcField);
    const tgtIdx = this._columnDefs.findIndex(c => c.field === tgtField);
    if (srcIdx === -1 || tgtIdx === -1 || srcIdx === tgtIdx) return;
    const [col] = this._columnDefs.splice(srcIdx, 1);
    this._columnDefs.splice(tgtIdx, 0, col);
    this._render();
  }
}
