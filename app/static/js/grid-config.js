/**
 * grid-config.js — Custom table grid factory and column definition helpers.
 *
 * Responsibilities:
 *  - GridManager class:        custom HTML table grid (no external dependencies).
 *  - buildColumnsFromSchema(): converts JSON schema descriptors to column defs.
 *  - CellRenderer:             provides common cell rendering functions.
 *
 * FR Y-14Q enhancements over baseline:
 *  - Multi-column sorting with priority ordering (Ctrl+click to add).
 *  - Date column filters (wfDateFilter).
 *  - Categorical filters (col.values array → checkbox list).
 *  - Reliable resize→sort isolation: pixel-distance guard on th click.
 *  - getFilterSortState() for async export job specs.
 */

//  Cell renderers ─

const CellRenderer = (function () {

  function money(params) {
    if (params.value === null || params.value === undefined || params.value === '') return '–';
    const n = parseFloat(params.value);
    return isNaN(n) ? params.value : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function date(params) {
    const v = params.value;
    if (v === null || v === undefined || v === '') return '';
    const s = String(v).trim();
    // Already yyyy-mm-dd (possibly with trailing time component)
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    // Parse and reformat using UTC parts to avoid timezone-shift off-by-one
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const yyyy = d.getUTCFullYear();
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
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
    a.href = 'javascript:void(0)';
    a.className = 'drill-link';
    a.textContent = val.toLocaleString();
    a.addEventListener('click', (e) => {
      e.stopPropagation();
      clickHandler(params);
    });
    return a;
  }

  // Rolando's Addition of Row Actions
  function rowActions(params) {
    const wrap = document.createElement('div')
    wrap.className = 'row-action-cell';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'row-select-checkbox';

    cb.checked = params.grid ? params.grid.isRowSelected(params.data) : false;

    cb.addEventListener('click', function (e) {
      e.stopPropagation();
      if (params.grid) {
        params.grid.toggleRowSelected(params.data, cb.checked);
        params.grid._render();
      }
    });

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'row-action-btn';
    btn.title = 'Row Actions';
    btn.innerHTML = '...';
    btn.addEventListener('click', function (e) {
      e.stopPropagation();

      if (
        params.grid &&
        params.grid._options &&
        typeof params.grid._options.onRowAction === 'function'
      ) {
        let selectedRows = params.grid.getSelectedRows();

        if (selectedRows.length === 0) {
          params.grid.toggleRowSelected(params.data, true);

          cb.checked = true;
          const tr = btn.closest('tr');
          if (tr) {
            tr.classList.add('wf-tr-selected');
          }
          selectedRows = params.grid.getSelectedRows();
        }

        params.grid._options.onRowAction({
          action: 'menu',
          row: params.data,
          selectedRows: selectedRows,
          anchor: btn,
          grid: params.grid,
        });
      }
    });


    wrap.appendChild(cb);
    wrap.appendChild(btn);
    return wrap;
  }

  return { money, date, drillDownLink, rowActions };

}());


//  Schema-driven column builder 

/**
 * Build GridManager column definitions from a schema descriptor array.
 *
 * @param {Object[]} schema        - Array from GET /api/schema/<entity_type>.
 * @param {Object}   drillHandlers - Map of drill_target → click handler closure.
 *                                   e.g. { obligations: (p) => DrillDown.open('facilities', 'obligations', p.data, ...) }
 * @returns {Object[]} Column defs ready to pass to new GridManager(id, colDefs, opts).
 */
function buildColumnsFromSchema(schema, drillHandlers, options) {
  drillHandlers = drillHandlers || {};
  options = options || {};
  var filterMap = {
    text: 'wfTextFilter',
    number: 'wfNumberFilter',
    money: 'wfNumberFilter',
    date: 'wfDateFilter',
    drill: 'wfNumberFilter',
  };

  // ROlando's Addition
  var actionCol = {
    field: '__row_actions',
    headerName: 'Action',
    sortable: false,
    resizable: false,
    filter: false,
    width: 80,
    minWidth: 80,
    pinned: 'left',
    cellClass: 'row-action-cell-wrap',
    cellRenderer: CellRenderer.rowActions,
  };

  var cols = schema.map(function (col) {
    var base = {
      field: col.field,
      headerName: col.label,
      sortable: true,
      resizable: true,
      filter: filterMap[col.type] || 'wfTextFilter',
      minWidth: col.minWidth || 80,
    };

    if (col.width) base.width = col.width;
    if (col.flex) base.flex = col.flex;
    if (col.pinned) base.pinned = col.pinned;
    if (col.hide) base.hide = true;
    if (col.values) base.values = col.values;
    if (col.tooltip) base.tooltipField = col.field;
    if (col.wrap) { base.wrapText = true; base.cellClass = 'comment-text-cell'; }

    if (col.type === 'drill') {
      var target = col.drill_target;
      var handler = drillHandlers[target] || function () { };
      base.pinned = base.pinned || 'right';
      base.cellClass = 'drill-down-cell';
      base.cellRenderer = (function (h) {
        return function (p) { return CellRenderer.drillDownLink(p, h); };
      }(handler));

    } else if (col.type === 'money') {
      base.cellRenderer = CellRenderer.money;
      base.cellClass = 'cell-numeric';
      base._alignRight = true;

    } else if (col.type === 'date') {
      base.cellRenderer = CellRenderer.date;

    } else if (col.renderer && CellRenderer[col.renderer]) {
      base.cellRenderer = CellRenderer[col.renderer];
      if (col.type === 'number') { base.cellClass = 'cell-numeric'; base._alignRight = true; }
    }

    return base;
  });

  if (options.showRowActions) {
    cols = [actionCol].concat(cols);
  }
  return cols;
}


//  Grid manager ─

class GridManager {
  /**
   * Custom HTML table grid — drop-in replacement for the former WF Grid wrapper.
   *
   * @param {string}   containerId - DOM element ID to mount into.
   * @param {Object[]} columnDefs  - Column definitions (same shape as before).
   * @param {Object}   [options]   - paginationPageSize, paginationPageSizeSelector.
   */
  constructor(containerId, columnDefs, options = {}) {
    this._containerId = containerId;
    this._columnDefs = columnDefs;
    this._options = options;

    // Dataset state
    this._allData = [];
    this._filteredData = [];

    // Multi-column sort state: [{field, dir}] in priority order (index 0 = primary).
    this._sortState = options.initialSort ? [...options.initialSort] : [];

    // Pagination state
    this._page = 0;
    this._pageSize = options.paginationPageSize ?? 25;
    this._pageSizeOptions = options.paginationPageSizeSelector ?? [10, 25, 50, 100];

    // Filter state
    this._quickFilter = '';
    this._colFilters = new Map();   // field → { op, val }

    // Column visibility — initialise from col.hide
    this._hiddenCols = new Set(columnDefs.filter(c => c.hide).map(c => c.field));

    // UI state
    this._colPanel = null;   // open column-picker dropdown
    this._filterPopup = null;   // open column-filter popup

    // DOM ref for <colgroup>
    this._colgroup = null;

    // Column resize / reorder state
    this._colWidthOverrides = new Map();  // field → user-dragged px width
    this._dragSrcField = null;       // field being column-dragged
    this._didDrag = false;      // suppresses sort click after a drop

    // Resize tracking — per-header mousedown position for click-vs-drag detection.
    // A sort click is only fired when mouse has moved ≤ 4px since mousedown on th.
    this._thDownX = 0;
    this._thDownY = 0;

    // Server-side pagination mode (activated when options.queryFn is provided)
    this._serverMode = !!options.queryFn;
    this._queryFn = options.queryFn || null;
    this._totalRows = 0;

    // Row-selection state (row-action feature) — Map of rowId -> row object,
    // not just a Set of IDs, so getSelectedRows() works without depending on
    // _allData/_batchData (which only ever hold the currently-loaded window
    // in server-side pagination mode).
    this._selectedRows = new Map();
    this._pendingChanges = false;
    this._batchPages = 3;
    this._batchData = [];
    this._batchStartPage = 0;
    this._applyBtnEl = null;

    // DOM refs (set in _buildTable)
    this._container = null;
    this._wrapper = null;
    this._table = null;
    this._thead = null;
    this._tbody = null;
    this._pagBar = null;
  }

  //  Public lifecycle ─

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

  // Rolando's addition:
  setData(rows) {
    this._selectedRows.clear();
    this._allData = (rows || []).map(function (row, idx) {
      return Object.assign({ __wf_row_id: idx }, row);
    });

  }
  //  Public data API 

  setQuickFilter(text) {
    this._quickFilter = text || '';
    if (this._serverMode) {
      this._setPending(true);
      return;
    }
    this._page = 0;
    this._render();
  }

  clearFilters() {
    this._quickFilter = '';
    this._colFilters.clear();
    this._sortState = this._options.initialSort ? [...this._options.initialSort] : [];
    this._page = 0;
    if (this._serverMode) {
      this._serverFetch();
      return;
    }
    this._render();
  }

  applyFilters() {
    this._page = 0;
    if (this._serverMode) {
      this._serverFetch();
    } else {
      this._render();
    }
  }

  setApplyButton(el) {
    this._applyBtnEl = el;
  }

  /**
   * Return current filter and sort state for async export job specs.
   * The returned object is JSON-serialisable and can be POSTed directly.
   */
  getFilterSortState() {
    return {
      quick_filter: this._quickFilter,
      col_filters: Object.fromEntries(this._colFilters),
      sort_state: this._sortState.map(s => ({ field: s.field, dir: s.dir })),
    };
  }

  /** Compatibility shim — callers use getApi().sizeColumnsToFit() */
  getApi() {
    return { sizeColumnsToFit: () => this._recalcWidths() };
  }

  //  Column picker panel 

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

    //  Column search 
    const searchWrap = document.createElement('div');
    searchWrap.className = 'col-picker-search';
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.placeholder = 'Search columns…';
    searchInput.className = 'col-picker-search-input';
    searchWrap.appendChild(searchInput);
    panel.appendChild(searchWrap);

    const list = document.createElement('div');
    list.className = 'col-picker-list';

    //  Select All row ─
    const allItem = document.createElement('label');
    allItem.className = 'col-picker-item col-picker-select-all';

    const allCb = document.createElement('input');
    allCb.type = 'checkbox';

    const visibleDefs = this._columnDefs.filter(c => c.headerName || c.field);
    const allVisible = visibleDefs.every(c => !this._hiddenCols.has(c.field));
    const noneVisible = visibleDefs.every(c => this._hiddenCols.has(c.field));
    allCb.checked = allVisible;
    allCb.indeterminate = !allVisible && !noneVisible;

    const updateAllCb = () => {
      const cbs = list.querySelectorAll('input[type="checkbox"]:not(.col-picker-all-cb)');
      const checkedCount = [...cbs].filter(c => c.checked).length;
      allCb.checked = checkedCount === cbs.length;
      allCb.indeterminate = checkedCount > 0 && checkedCount < cbs.length;
    };

    allCb.className = 'col-picker-all-cb';
    allCb.addEventListener('change', () => {
      const targetState = allCb.checked;
      const cbs = list.querySelectorAll('input[type="checkbox"]:not(.col-picker-all-cb)');
      // Update _hiddenCols directly — dispatching individual change events is buggy
      // because updateAllCb() resets allCb.checked mid-loop, flipping targetState for
      // subsequent iterations and preventing re-select from working.
      if (targetState) {
        this._hiddenCols.clear();
      } else {
        visibleDefs.forEach(col => this._hiddenCols.add(col.field));
      }
      cbs.forEach(cb => { cb.checked = targetState; });
      this._render();
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
      cb.type = 'checkbox';
      cb.checked = !this._hiddenCols.has(col.field);
      cb.addEventListener('change', () => {
        if (cb.checked) this._hiddenCols.delete(col.field);
        else this._hiddenCols.add(col.field);
        updateAllCb();
        this._render();
      });

      item.appendChild(cb);
      item.appendChild(document.createTextNode(' ' + label));
      list.appendChild(item);
    });

    panel.appendChild(list);

    // Filter column items as user types in the search box
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.toLowerCase();
      list.querySelectorAll('.col-picker-item:not(.col-picker-select-all)').forEach(item => {
        item.style.display = item.textContent.trim().toLowerCase().includes(q) ? '' : 'none';
      });
    });

    document.body.appendChild(panel);
    this._colPanel = panel;

    setTimeout(() => searchInput.focus(), 0);

    const rect = anchorEl.getBoundingClientRect();
    panel.style.top = (rect.bottom + window.scrollY + 4) + 'px';
    panel.style.left = (rect.left + window.scrollX) + 'px';

    const onOutside = (e) => {
      if (!panel.contains(e.target) && e.target !== anchorEl) {
        panel.remove();
        this._colPanel = null;
        document.removeEventListener('mousedown', onOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutside), 0);
  }

  //  DOM construction (one-time) 

  _buildTable() {
    this._container.innerHTML = '';

    this._wrapper = document.createElement('div');
    this._wrapper.className = 'wf-table-wrapper';

    this._table = document.createElement('table');
    this._table.className = 'wf-table';

    this._colgroup = document.createElement('colgroup');
    this._thead = document.createElement('thead');
    this._tbody = document.createElement('tbody');
    this._table.appendChild(this._colgroup);
    this._table.appendChild(this._thead);
    this._table.appendChild(this._tbody);

    this._pagBar = document.createElement('div');
    this._pagBar.className = 'wf-pag-bar';

    this._wrapper.appendChild(this._table);
    this._container.appendChild(this._wrapper);
    this._container.appendChild(this._pagBar);
  }

  //  Render pipeline 

  _render() {
    if (this._serverMode) {
      this._renderServerPage();
      return;
    }
    this._applyFilters();
    this._applySort();
    const start = this._page * this._pageSize;
    const pageData = this._filteredData.slice(start, start + this._pageSize);
    this._buildHeaders();
    this._buildRows(pageData);
    this._buildPagination();
    this._recalcWidths();
  }

  _applyFilters() {
    let rows = this._allData;
    const q = this._quickFilter.trim().toLowerCase();

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
        const s = String(cell ?? '').toLowerCase();
        const sv = String(val).toLowerCase();
        switch (op) {
          case 'contains': return s.includes(sv);
          case 'equals': return s === sv;
          case 'startsWith': return s.startsWith(sv);
          case 'numEq': return parseFloat(cell) === parseFloat(val);
          case 'gt': return parseFloat(cell) > parseFloat(val);
          case 'gte': return parseFloat(cell) >= parseFloat(val);
          case 'lt': return parseFloat(cell) < parseFloat(val);
          case 'lte': return parseFloat(cell) <= parseFloat(val);
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

    // Pre-compute column type metadata once per sort key, not inside the comparator.
    const keyInfo = this._sortState.map(({ field, dir }) => {
      const col = this._columnDefs.find(c => c.field === field);
      return {
        field, dir,
        isNumeric: col && col.filter === 'wfNumberFilter',
        isDate: col && col.filter === 'wfDateFilter',
      };
    });

    this._filteredData.sort((a, b) => {
      for (const { field, dir, isNumeric, isDate } of keyInfo) {
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

        if (av < bv) return dir === 'asc' ? -1 : 1;
        if (av > bv) return dir === 'asc' ? 1 : -1;
      }
      return 0;
    });
  }

  _isAlignedRight(col) {
    return col._alignRight || col.filter === 'wfNumberFilter';
  }

  //  Header building 

  _buildHeaders() {
    this._thead.innerHTML = '';
    this._colgroup.innerHTML = '';
    const cols = this._visibleCols();
    cols.forEach(col => {
      const c = document.createElement('col');
      c.dataset.field = col.field;
      this._colgroup.appendChild(c);
    });

    const tr = document.createElement('tr');
    const leftOffsets = this._stickyOffsets('left');
    const rightOffsets = this._stickyOffsets('right');

    cols.forEach(col => {
      const th = document.createElement('th');
      th.className = 'wf-th';
      th.dataset.field = col.field;

      if (this._isAlignedRight(col)) th.classList.add('wf-th-right');

      if (col.pinned === 'left') {
        th.classList.add('wf-th-pinned-left');
        th.style.position = 'sticky';
        th.style.left = leftOffsets[col.field] + 'px';
        th.style.zIndex = '3';
      } else if (col.pinned === 'right') {
        th.classList.add('wf-th-pinned-right');
        th.style.position = 'sticky';
        th.style.right = rightOffsets[col.field] + 'px';
        th.style.zIndex = '3';
      }

      // Sort state for this column
      const sortIdx = this._sortState.findIndex(s => s.field === col.field);
      const sortEntry = sortIdx !== -1 ? this._sortState[sortIdx] : null;
      if (sortEntry) th.classList.add('wf-th-sorted');

      // Inner layout: label | sort icon | filter btn
      const inner = document.createElement('div');
      inner.className = 'wf-th-inner';

      const label = document.createElement('span');
      label.className = 'wf-th-label';
      label.textContent = col.headerName || col.field;
      inner.appendChild(label);

      // Sort icon — shows arrow + priority number when multi-sorting
      const sortIcon = document.createElement('span');
      sortIcon.className = 'wf-sort-icon';
      if (sortEntry) {
        const arrow = sortEntry.dir === 'asc' ? '↑' : '↓';
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
        filterBtn.title = 'Filter column';
        filterBtn.innerHTML = '<svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor"><path d="M10 18h4v-2h-4v2zM3 6v2h18V6H3zm3 7h12v-2H6v2z"/></svg>';
        if (this._colFilters.has(col.field)) filterBtn.classList.add('wf-filter-active');

        filterBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this._openFilterPopup(col, filterBtn);
        });
        inner.appendChild(filterBtn);
      }

      th.appendChild(inner);

      //  Resize handle 
      if (col.pinned !== 'right') {
        const handle = document.createElement('div');
        handle.className = 'wf-resize-handle';
        handle.setAttribute('draggable', 'false');
        handle.addEventListener('mousedown', (e) => {
          e.stopPropagation();
          e.preventDefault();

          const startX = e.clientX;
          const startW = th.offsetWidth;
          const startTableW = this._table.offsetWidth;
          const minW = col.minWidth ?? 50;
          const colEl = this._colgroup.querySelector(`col[data-field="${col.field}"]`);

          document.body.style.cursor = 'col-resize';
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
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            this._colWidthOverrides.set(col.field, Math.max(minW, startW + (ev.clientX - startX)));
            this._recalcWidths();
          };

          document.addEventListener('mousemove', onMove);
          document.addEventListener('mouseup', onUp);
        });
        th.appendChild(handle);
      }

      //  Column drag-to-reorder ─
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

      //  Sort click ─
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
    if (this._serverMode) {
      this._setPending(true);
      this._buildHeaders();
      return;
    }
    this._render();
  }

  //  Row building ─

  _buildRows(pageData) {
    this._tbody.innerHTML = '';

    if (pageData.length === 0) {
      const cols = this._visibleCols();
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.className = 'wf-no-rows';
      td.colSpan = cols.length || 1;
      td.textContent = 'No records match the current filters.';
      tr.appendChild(td);
      this._tbody.appendChild(tr);
      return;
    }

    const cols = this._visibleCols();
    const leftOffsets = this._stickyOffsets('left');
    const rightOffsets = this._stickyOffsets('right');

    pageData.forEach(row => {
      const tr = document.createElement('tr');
      tr.className = 'wf-tr';

      cols.forEach(col => {
        const td = document.createElement('td');
        td.className = 'wf-td';
        td.dataset.field = col.field;

        if (col.cellClass) {
          String(col.cellClass).split(/\s+/).forEach(c => c && td.classList.add(c));
        }

        if (this._isAlignedRight(col)) td.classList.add('wf-td-right');

        if (col.pinned === 'left') {
          td.classList.add('wf-td-pinned-left');
          td.style.position = 'sticky';
          td.style.left = leftOffsets[col.field] + 'px';
          td.style.zIndex = '2';
        } else if (col.pinned === 'right') {
          td.classList.add('wf-td-pinned-right');
          td.style.position = 'sticky';
          td.style.right = rightOffsets[col.field] + 'px';
          td.style.zIndex = '2';
        }

        if (col.tooltipField && row[col.tooltipField]) {
          td.title = String(row[col.tooltipField]);
        }

        if (col.wrapText) {
          td.style.whiteSpace = 'normal';
          td.style.height = 'auto';
          td.style.verticalAlign = 'top';
          td.style.paddingTop = '8px';
          td.style.paddingBottom = '8px';
        }

        const params = { value: row[col.field], data: row, colDef: col, grid: this };
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

  //  Pagination bar ─

  _buildPagination() {
    this._pagBar.innerHTML = '';

    const total = this._filteredData.length;
    const totalPages = Math.max(1, Math.ceil(total / this._pageSize));
    const start = total === 0 ? 0 : this._page * this._pageSize + 1;
    const end = Math.min(total, (this._page + 1) * this._pageSize);

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
      opt.value = n;
      opt.textContent = n;
      opt.selected = n === this._pageSize;
      sizeSelect.appendChild(opt);
    });
    sizeSelect.addEventListener('change', () => {
      this._pageSize = parseInt(sizeSelect.value, 10);
      this._page = 0;
      this._render();
    });
    controls.appendChild(sizeSelect);

    const mkBtn = (label, action, disabled) => {
      const btn = document.createElement('button');
      btn.className = 'wf-pag-btn';
      btn.textContent = label;
      btn.disabled = disabled;
      btn.addEventListener('click', () => { this._page = action(); this._render(); });
      return btn;
    };

    controls.appendChild(mkBtn('«', () => 0, this._page === 0));
    controls.appendChild(mkBtn('‹', () => this._page - 1, this._page === 0));

    const pageLabel = document.createElement('span');
    pageLabel.className = 'wf-pag-page';
    pageLabel.textContent = `Page ${this._page + 1} of ${totalPages}`;
    controls.appendChild(pageLabel);

    controls.appendChild(mkBtn('›', () => this._page + 1, this._page >= totalPages - 1));
    controls.appendChild(mkBtn('»', () => totalPages - 1, this._page >= totalPages - 1));

    this._pagBar.appendChild(controls);
  }

  //  Column width calculation ─

  _recalcWidths() {
    const containerWidth = this._container.clientWidth;
    if (!containerWidth) return;

    const cols = this._visibleCols();
    let fixedSum = 0, flexSum = 0;

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
    const widths = {};

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

    // Re-stamp sticky right offsets using the freshly computed widths so that
    // pinned-right columns don't overlap scrollable columns after a resize.
    let rightOffset = 0;
    [...cols].reverse().forEach(col => {
      if (col.pinned !== 'right') return;
      const px = rightOffset + 'px';
      this._table.querySelectorAll(
        `th[data-field="${col.field}"], td[data-field="${col.field}"]`
      ).forEach(el => { el.style.right = px; });
      rightOffset += widths[col.field];
    });
  }

  //  Column filter popup 

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

    const isNumeric = col.filter === 'wfNumberFilter';
    const isDate = col.filter === 'wfDateFilter';
    const isCategorical = Array.isArray(col.values) && col.values.length > 0;
    const current = this._colFilters.get(col.field) || {};

    const popup = document.createElement('div');
    popup.className = 'wf-col-filter-popup';

    const hdr = document.createElement('div');
    hdr.className = 'wf-cfp-header';
    hdr.textContent = 'Filter: ' + (col.headerName || col.field);
    popup.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'wf-cfp-body';

    let applyFn;  // set per filter type

    if (isCategorical) {
      //  Categorical filter — checkbox list 
      const selected = new Set(
        current.op === 'inList' ? String(current.val || '').split(',').map(v => v.trim()) : []
      );

      const listWrap = document.createElement('div');
      listWrap.style.cssText = 'max-height:160px;overflow-y:auto;display:flex;flex-direction:column;gap:4px';

      col.values.forEach(v => {
        const lbl = document.createElement('label');
        lbl.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer';
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = v;
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
      //  Date filter ─
      const dateOps = [['dateEq', 'On date'], ['dateBefore', 'Before'], ['dateAfter', 'After']];

      const opSel = document.createElement('select');
      opSel.className = 'wf-cfp-op';
      dateOps.forEach(([val, lbl]) => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = lbl;
        opt.selected = val === (current.op || 'dateEq');
        opSel.appendChild(opt);
      });

      const dateInput = document.createElement('input');
      dateInput.className = 'wf-cfp-val';
      dateInput.type = 'date';
      dateInput.value = current.val ?? '';
      dateInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyBtn.click(); });

      body.appendChild(opSel);
      body.appendChild(dateInput);

      applyFn = () => {
        const val = dateInput.value;
        if (val) this._colFilters.set(col.field, { op: opSel.value, val });
        else this._colFilters.delete(col.field);
      };

    } else {
      //  Text / numeric filter 
      const textOps = [['contains', 'Contains'], ['equals', 'Equals'], ['startsWith', 'Starts with']];
      const numericOps = [['numEq', '='], ['gt', '>'], ['gte', '≥'], ['lt', '<'], ['lte', '≤']];

      const opSel = document.createElement('select');
      opSel.className = 'wf-cfp-op';
      (isNumeric ? numericOps : textOps).forEach(([val, lbl]) => {
        const opt = document.createElement('option');
        opt.value = val;
        opt.textContent = lbl;
        opt.selected = val === (current.op || (isNumeric ? 'numEq' : 'contains'));
        opSel.appendChild(opt);
      });

      const valInput = document.createElement('input');
      valInput.className = 'wf-cfp-val';
      valInput.type = isNumeric ? 'number' : 'text';
      valInput.placeholder = 'Value…';
      valInput.value = current.val ?? '';
      valInput.addEventListener('keydown', e => { if (e.key === 'Enter') applyBtn.click(); });

      body.appendChild(opSel);
      body.appendChild(valInput);

      applyFn = () => {
        const val = valInput.value.trim();
        if (val !== '') this._colFilters.set(col.field, { op: opSel.value, val });
        else this._colFilters.delete(col.field);
      };

      setTimeout(() => valInput.focus(), 0);
    }

    popup.appendChild(body);

    const footer = document.createElement('div');
    footer.className = 'wf-cfp-footer';

    const clearBtn = document.createElement('button');
    clearBtn.className = 'wf-cfp-clear';
    clearBtn.textContent = 'Clear';
    clearBtn.addEventListener('click', () => {
      this._colFilters.delete(col.field);
      popup.remove();
      this._filterPopup = null;
      this._page = 0;
      if (this._serverMode) { this._setPending(true); }
      else { this._render(); }
    });

    const applyBtn = document.createElement('button');
    applyBtn.className = 'wf-cfp-apply';
    applyBtn.textContent = 'Apply';
    applyBtn.addEventListener('click', () => {
      applyFn();
      popup.remove();
      this._filterPopup = null;
      this._page = 0;
      if (this._serverMode) { this._setPending(true); }
      else { this._render(); }
    });

    footer.appendChild(clearBtn);
    footer.appendChild(applyBtn);
    popup.appendChild(footer);

    document.body.appendChild(popup);
    this._filterPopup = popup;

    const rect = anchorEl.getBoundingClientRect();
    popup.style.top = (rect.bottom + window.scrollY + 4) + 'px';
    popup.style.left = (rect.left + window.scrollX - 180) + 'px';

    const onOutside = (e) => {
      if (!popup.contains(e.target) && e.target !== anchorEl) {
        popup.remove();
        this._filterPopup = null;
        this._filterPopupField = null;
        document.removeEventListener('mousedown', onOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutside), 0);
  }

  //  Helpers 

  _visibleCols() {
    return this._columnDefs.filter(c => !this._hiddenCols.has(c.field));
  }

  _stickyOffsets(side) {
    const result = {};
    const cols = this._visibleCols();
    let offset = 0;
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


  // Rolando's Addition <STARTS_HERE>
  // For actions in the grid
  getRowId(row) {
    if (row.__wf_row_id !== undefined) return String(row.__wf_row_id);
    return JSON.stringify(row);
  }

  isRowSelected(row) {
    return this._selectedRows.has(this.getRowId(row));
  }

  // Updates a "N selected" indicator if the page provides one; a no-op otherwise.
  _updateSelectionToolbar() {
    const el = document.querySelector('#' + this._containerId + ' .selection-count');
    if (!el) return;
    const n = this._selectedRows.size;
    el.textContent = n > 0 ? `${n} selected` : '';
  }

  toggleRowSelected(row, checked) {
    const id = this.getRowId(row);
    if (checked) this._selectedRows.set(id, row); else this._selectedRows.delete(id);
    this._updateSelectionToolbar();
  }

  // Keyed by row ID (not the paginated _allData/_batchData buffers, which only
  // ever hold the currently-loaded window) so selections survive page/batch
  // navigation and server-side pagination mode correctly.
  getSelectedRows() {
    return Array.from(this._selectedRows.values());
  }

  clearSelectedRows() {
    this._selectedRows.clear();
    this._updateSelectionToolbar();
    this._render();
  }

  setRowSelected(row, selected) {
    const id = this.getRowId(row);
    selected ? this._selectedRows.set(id, row) : this._selectedRows.delete(id);
    this._updateSelectionToolbar();
  }

  // Rolando's Addition <ENDS_HERE> 
  //  Server-side pagination 

  _setPending(pending) {
    this._pendingChanges = pending;
    if (this._applyBtnEl) {
      this._applyBtnEl.classList.toggle('has-pending', pending);
    }
  }

  async _serverFetch() {
    this._setPending(false);
    const batchSize = this._pageSize * this._batchPages;
    const batchStartPage = Math.floor(this._page / this._batchPages) * this._batchPages;

    const spec = {
      page: batchStartPage / this._batchPages + 1,
      per_page: batchSize,
      sorts: this._sortState.map(s => ({ field: s.field, dir: s.dir })),
      col_filters: Object.fromEntries(this._colFilters),
      quick_filter: this._quickFilter,
    };

    try {
      const result = await this._queryFn(spec);
      this._batchData = result.data || [];
      this._batchStartPage = batchStartPage;
      this._totalRows = result.meta?.total || 0;
      this._renderServerPage();
    } catch (err) {
      console.error('Server fetch error:', err);
      if (typeof Toast !== 'undefined') {
        Toast.error('Failed to load data', err.message || 'Unknown error');
      }
    }
  }

  _renderServerPage() {
    const offsetInBatch = (this._page - this._batchStartPage) * this._pageSize;
    const pageData = this._batchData.slice(offsetInBatch, offsetInBatch + this._pageSize);
    this._buildHeaders();
    this._buildRows(pageData);
    this._buildServerPagination();
    this._recalcWidths();
  }

  _buildServerPagination() {
    this._pagBar.innerHTML = '';

    const total = this._totalRows;
    const totalPages = Math.max(1, Math.ceil(total / this._pageSize));
    const start = total === 0 ? 0 : this._page * this._pageSize + 1;
    const end = Math.min(total, (this._page + 1) * this._pageSize);

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
      opt.value = n;
      opt.textContent = n;
      opt.selected = n === this._pageSize;
      sizeSelect.appendChild(opt);
    });
    sizeSelect.addEventListener('change', () => {
      this._pageSize = parseInt(sizeSelect.value, 10);
      this._page = 0;
      this._serverFetch();
    });
    controls.appendChild(sizeSelect);

    const navTo = (targetPage) => {
      this._page = targetPage;
      const batchEnd = this._batchStartPage + this._batchPages;
      if (targetPage >= this._batchStartPage && targetPage < batchEnd) {
        this._renderServerPage();
      } else {
        this._serverFetch();
      }
    };

    const mkBtn = (label, targetPage, disabled) => {
      const btn = document.createElement('button');
      btn.className = 'wf-pag-btn';
      btn.textContent = label;
      btn.disabled = disabled;
      btn.addEventListener('click', () => navTo(targetPage));
      return btn;
    };

    controls.appendChild(mkBtn('«', 0, this._page === 0));
    controls.appendChild(mkBtn('‹', this._page - 1, this._page === 0));

    const pageLabel = document.createElement('span');
    pageLabel.className = 'wf-pag-page';
    pageLabel.textContent = `Page ${this._page + 1} of ${totalPages}`;
    controls.appendChild(pageLabel);

    controls.appendChild(mkBtn('›', this._page + 1, this._page >= totalPages - 1));
    controls.appendChild(mkBtn('»', totalPages - 1, this._page >= totalPages - 1));

    this._pagBar.appendChild(controls);
  }
}
