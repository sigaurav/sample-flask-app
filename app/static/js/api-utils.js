/**
 * api-utils.js — HTTP fetch utility, loading overlay, export helpers, and
 * shared toolbar wiring used by every page grid module.
 *
 * HTTP / export API:
 *  - get(url, showLoader)
 *  - buildUrl(base, params)
 *  - createExportJob(spec)
 *  - downloadExport(jobId)
 *  - triggerExportJob(spec, typeLabel, entityLabel)
 *  - triggerGridExport(grid, entityType, entityLabel, exportType, fileFormat)
 *
 * Shared DOM wiring (eliminates duplication across app.js / obligations.js / property.js):
 *  - wireGridToolbar(grid, reloadFn)
 *  - wireExportDropdown(grid, entityType, entityLabel)
 *
 * Depends on: ExportTracker (export-tracker.js), Toast (base.html inline).
 * Exported as the global `ApiUtils` object (IIFE module pattern).
 */
const ApiUtils = (function () {

  const LOADING_DEBOUNCE_MS = 200;

  let _pendingRequests = 0;
  let _loadingTimer    = null;

  // ── Loading overlay management ─────────────────────────────────────────────

  function _showLoading() {
    _pendingRequests++;
    if (_loadingTimer !== null) return;
    _loadingTimer = setTimeout(() => {
      const el = document.getElementById('loadingOverlay');
      if (el) el.classList.add('active');
    }, LOADING_DEBOUNCE_MS);
  }

  function _hideLoading() {
    _pendingRequests = Math.max(0, _pendingRequests - 1);
    if (_pendingRequests > 0) return;
    clearTimeout(_loadingTimer);
    _loadingTimer = null;
    const el = document.getElementById('loadingOverlay');
    if (el) el.classList.remove('active');
  }

  // ── Query context helpers ─────────────────────────────────────────────────

  function _withContext(url) {
    try {
      const ctx = JSON.parse(localStorage.getItem('wf_query_context') || '{}');
      if (!ctx.fic_mis_date) return url;
      const sep = url.includes('?') ? '&' : '?';
      return url + sep + 'fic_mis_date=' + encodeURIComponent(ctx.fic_mis_date);
    } catch (_) { return url; }
  }

  // ── Core GET wrapper ──────────────────────────────────────────────────────

  async function get(url, showLoader = true) {
    if (showLoader) _showLoading();
    try {
      const resp = await fetch(_withContext(url), {
        method:  'GET',
        headers: { 'Accept': 'application/json' },
      });

      const json = await resp.json();

      if (!resp.ok || json.success === false) {
        const err         = new Error(json.error || `HTTP ${resp.status}`);
        err.status        = resp.status;
        err.serverMessage = json.error || '';
        throw err;
      }

      return json;
    } finally {
      if (showLoader) _hideLoading();
    }
  }

  // ── Core POST wrapper ─────────────────────────────────────────────────────

  async function post(url, body, showLoader = true) {
    if (showLoader) _showLoading();
    try {
      const resp = await fetch(url, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body:    JSON.stringify(body),
      });

      const json = await resp.json();

      if (!resp.ok || json.success === false) {
        const err         = new Error(json.error || `HTTP ${resp.status}`);
        err.status        = resp.status;
        err.serverMessage = json.error || '';
        throw err;
      }

      return json;
    } finally {
      if (showLoader) _hideLoading();
    }
  }

  // ── URL builder ────────────────────────────────────────────────────────────

  function buildUrl(base, params = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    if (!qs) return base;
    return base + (base.includes('?') ? '&' : '?') + qs;
  }

  // ── Legacy sync download (drill-down modal exports) ────────────────────────

  function downloadFile(url) {
    _showLoading();
    const a = document.createElement('a');
    a.href  = url;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(_hideLoading, 1200);
  }

  // ── Async export API ───────────────────────────────────────────────────────

  /**
   * Create an async export job on the backend.
   *
   * @param {Object} spec - Export job specification:
   *   {
   *     entity_type:   'facilities' | 'obligations' | 'property',
   *     export_type:   'partial' | 'full',
   *     schedule_type: 'H1' | 'H2' | 'all',
   *     file_format:   'csv' | 'excel' | 'parquet',
   *     entity_id:     string | null,   // optional scope
   *     filters:       { col_filters: {}, quick_filter: '' },
   *     sorts:         [{field, dir}],
   *   }
   * @returns {Promise<{job_id: string, status: string}>}
   */
  async function createExportJob(spec) {
    const resp = await fetch('/api/exports', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body:    JSON.stringify(spec),
    });
    const json = await resp.json();
    if (!resp.ok || json.success === false) {
      throw new Error(json.error || `Export job creation failed (HTTP ${resp.status})`);
    }
    return json.data;   // { job_id, status }
  }

  /**
   * Trigger download of a completed export file.
   *
   * @param {string} jobId - Job ID whose file should be downloaded.
   */
  function downloadExport(jobId) {
    downloadFile(`/api/internal/exports/${jobId}/download`);
  }

  // ── Shared export triggers ─────────────────────────────────────────────────

  /**
   * Create an export job from a ready-made spec, show a toast, and register
   * the job with ExportTracker. Used by both page grids and drill-down modals.
   *
   * @param {Object} spec        - Full export spec (see createExportJob).
   * @param {string} typeLabel   - 'Partial' or 'Full'.
   * @param {string} entityLabel - Display name, e.g. 'Facilities', 'Obligors'.
   */
  async function triggerExportJob(spec, typeLabel, entityLabel) {
    try {
      const job = await createExportJob(spec);
      Toast.info(`${typeLabel} export queued`, `Preparing ${spec.file_format.toUpperCase()} file…`);
      ExportTracker.track(job.job_id, `${typeLabel} ${entityLabel} Export`);
    } catch (err) {
      Toast.error('Export error', err.message || 'Failed to start export.');
    }
  }

  /**
   * Build an export spec from a GridManager's current filter/sort state,
   * then call triggerExportJob. Used by page-level grids (no entity_id scope).
   *
   * @param {GridManager} grid        - The page grid instance.
   * @param {string}      entityType  - Backend entity key, e.g. 'facilities'.
   * @param {string}      entityLabel - Display name, e.g. 'Facilities'.
   * @param {string}      exportType  - 'partial' | 'full'.
   * @param {string}      fileFormat  - 'csv' | 'excel' | 'parquet'.
   */
  async function triggerGridExport(grid, entityType, entityLabel, exportType, fileFormat) {
    const state     = grid.getFilterSortState();
    const typeLabel = exportType === 'partial' ? 'Partial' : 'Full';
    await triggerExportJob({
      entity_type:   entityType,
      export_type:   exportType,
      schedule_type: 'H1',
      file_format:   fileFormat,
      filters:       exportType === 'partial'
        ? { col_filters: state.col_filters, quick_filter: state.quick_filter }
        : {},
      sorts: exportType === 'partial' ? state.sort_state : [],
    }, typeLabel, entityLabel);
  }

  // ── Shared KPI strip ──────────────────────────────────────────────────────

  /**
   * Update the kpiTotal and kpiActive counters in the page header strip.
   *
   * @param {Array}    records  - Full dataset currently loaded in the grid.
   * @param {Function} activeFn - Predicate that returns true for "active" records,
   *                              e.g. r => r.status === 'Active'.
   */
  function updateKpi(records, activeFn) {
    const el = (id) => document.getElementById(id);
    if (el('kpiTotal'))  el('kpiTotal').textContent  = records.length.toLocaleString();
    if (el('kpiActive')) el('kpiActive').textContent = records.filter(activeFn).length.toLocaleString();
  }

  // ── Shared toolbar wiring ──────────────────────────────────────────────────

  /**
   * Wire the standard grid toolbar controls shared by every page:
   * grid search (debounced), global header search, clear-filters button,
   * column-visibility button, and sidebar toggle.
   *
   * @param {GridManager} grid     - The page grid instance.
   * @param {Function}    reloadFn - Page-specific data-load function; called
   *                                 with the current search string on globalSearch input.
   */
  function wireGridToolbar(grid, reloadFn) {
    const gridSearch = document.getElementById('gridSearch');
    if (gridSearch) {
      let _t;
      gridSearch.addEventListener('input', () => {
        clearTimeout(_t);
        _t = setTimeout(() => grid.setQuickFilter(gridSearch.value), 200);
      });
    }

    const globalSearch = document.getElementById('globalSearch');
    if (globalSearch) {
      globalSearch.addEventListener('input', () => {
        if (gridSearch) gridSearch.value = globalSearch.value;
        reloadFn(globalSearch.value.trim());
      });
    }

    document.getElementById('btnShowHideColumns')?.addEventListener('click', (e) => {
      grid.toggleColumnsPanel(e.currentTarget);
    });

    document.getElementById('btnClearFilters')?.addEventListener('click', () => {
      grid.clearFilters();
      if (gridSearch) gridSearch.value = '';
      Toast.info('Filters cleared', 'All filters and sort order have been reset.');
    });

    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
      sidebarToggle.addEventListener('click', () => {
        document.getElementById('sidebar')?.classList.toggle('collapsed');
        document.getElementById('mainContent')?.classList.toggle('sidebar-collapsed');
        setTimeout(() => grid.getApi().sizeColumnsToFit(), 200);
      });
    }
  }

  /**
   * Wire the export dropdown button, click-outside-to-close behaviour,
   * format radio group, and partial/full export buttons.
   *
   * @param {GridManager} grid        - The page grid instance.
   * @param {string}      entityType  - Backend entity key, e.g. 'facilities'.
   * @param {string}      entityLabel - Display name, e.g. 'Facilities'.
   */
  function wireExportDropdown(grid, entityType, entityLabel) {
    const btnExport  = document.getElementById('btnExport');
    const exportMenu = document.getElementById('exportMenu');
    if (!btnExport || !exportMenu) return;

    btnExport.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = exportMenu.getAttribute('aria-hidden') !== 'true';
      exportMenu.setAttribute('aria-hidden', open ? 'true' : 'false');
    });

    document.addEventListener('click', (e) => {
      if (!exportMenu.contains(e.target) && e.target !== btnExport)
        exportMenu.setAttribute('aria-hidden', 'true');
    });

    const _fmt = () =>
      (document.querySelector('input[name="exportFmt"]:checked') || {}).value || 'csv';

    document.getElementById('btnPartialExport')?.addEventListener('click', () => {
      exportMenu.setAttribute('aria-hidden', 'true');
      triggerGridExport(grid, entityType, entityLabel, 'partial', _fmt());
    });

    document.getElementById('btnFullExport')?.addEventListener('click', () => {
      exportMenu.setAttribute('aria-hidden', 'true');
      triggerGridExport(grid, entityType, entityLabel, 'full', _fmt());
    });
  }

  // ── Public surface ─────────────────────────────────────────────────────────

  return {
    get, post, buildUrl, createExportJob, downloadExport,
    triggerExportJob, triggerGridExport,
    wireGridToolbar, wireExportDropdown,
    updateKpi,
  };

}());
