/**
 * api-utils.js — HTTP fetch utility, loading overlay, and async export helpers.
 *
 * FR Y-14Q additions:
 *  - createExportJob(spec)             POST /api/exports → {job_id, status}
 *  - pollUntilComplete(jobId, cb)      Polls status until COMPLETED/FAILED
 *  - downloadExport(jobId)             GET /api/exports/<id>/download
 *
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

  // ── Core GET wrapper ──────────────────────────────────────────────────────

  async function get(url, showLoader = true) {
    if (showLoader) _showLoading();
    try {
      const resp = await fetch(url, {
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

  // ── URL builder ────────────────────────────────────────────────────────────

  function buildUrl(base, params = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    return qs ? `${base}?${qs}` : base;
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
   *     entity_type:   'facilities' | 'obligors' | 'transactions' | 'comments',
   *     export_type:   'partial' | 'full',
   *     schedule_type: 'H1' | 'H2' | 'all',
   *     source_type:   'csv' | 'excel' | 'dremio' | 'sqlserver',
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
   * Poll export job status until the job completes or times out.
   *
   * @param {string}   jobId        - Job ID returned by createExportJob.
   * @param {Function} onUpdate     - Called on each status change: (status, jobData) => void.
   *                                  Also called on COMPLETED / FAILED / TIMEOUT.
   * @param {Object}   [opts]
   * @param {number}   opts.maxAttempts  - Max polling iterations (default: 30).
   * @param {number}   opts.intervalMs   - Polling interval in ms (default: 2000).
   */
  async function pollUntilComplete(jobId, onUpdate, opts = {}) {
    const maxAttempts = opts.maxAttempts ?? 30;
    const intervalMs  = opts.intervalMs  ?? 2000;

    for (let i = 0; i < maxAttempts; i++) {
      await _sleep(intervalMs);
      try {
        const resp = await fetch(`/api/exports/${jobId}/status`, {
          headers: { 'Accept': 'application/json' },
        });
        const json = await resp.json();
        const jobData = json.data || {};
        const status  = jobData.status || 'UNKNOWN';

        onUpdate(status, jobData);

        if (status === 'COMPLETED' || status === 'FAILED') return;

      } catch (err) {
        console.warn('Export poll error:', err);
      }
    }

    // Timed out
    onUpdate('TIMEOUT', null);
  }

  /**
   * Trigger download of a completed export file.
   *
   * @param {string} jobId - Job ID whose file should be downloaded.
   */
  function downloadExport(jobId) {
    downloadFile(`/api/exports/${jobId}/download`);
  }

  // ── Private helpers ────────────────────────────────────────────────────────

  function _sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  // ── Public surface ─────────────────────────────────────────────────────────

  return { get, buildUrl, createExportJob, pollUntilComplete, downloadExport };

}());
