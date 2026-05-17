/**
 * api-utils.js — HTTP fetch utility and loading/error helpers.
 *
 * Provides a thin wrapper around the browser Fetch API that:
 *  - Manages the global loading overlay
 *  - Throws enriched errors for non-2xx responses
 *  - Handles JSON parsing consistently
 *
 * Exported as the global `ApiUtils` object (IIFE module pattern).
 */
const ApiUtils = (function () {

  /** Milliseconds before the loading overlay is shown (prevents flash on fast calls). */
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

  // ── Core fetch wrapper ─────────────────────────────────────────────────────

  /**
   * Perform an HTTP GET and return the parsed JSON response body.
   *
   * @param {string}  url            - Absolute or relative URL.
   * @param {boolean} [showLoader]   - Whether to display the loading overlay (default: true).
   * @returns {Promise<any>}         - Resolves with response.data on success.
   * @throws {Error}                 - With .status and .serverMessage on failure.
   */
  async function get(url, showLoader = true) {
    if (showLoader) _showLoading();
    try {
      const resp = await fetch(url, {
        method:  'GET',
        headers: { 'Accept': 'application/json' },
      });

      const json = await resp.json();

      if (!resp.ok || json.success === false) {
        const err       = new Error(json.error || `HTTP ${resp.status}`);
        err.status      = resp.status;
        err.serverMessage = json.error || '';
        throw err;
      }

      return json;                     // caller gets { success, data, meta }
    } finally {
      if (showLoader) _hideLoading();
    }
  }

  // ── URL builder ────────────────────────────────────────────────────────────

  /**
   * Build a query string from a params object, omitting falsy values.
   *
   * @param {string}  base   - Base URL path.
   * @param {Object}  params - Key/value pairs to append.
   * @returns {string}
   */
  function buildUrl(base, params = {}) {
    const qs = Object.entries(params)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    return qs ? `${base}?${qs}` : base;
  }

  // ── Export trigger ─────────────────────────────────────────────────────────

  /**
   * Trigger a file download by navigating to an export URL.
   *
   * Creates a hidden <a> element, clicks it, then removes it — this
   * causes the browser to download the file without leaving the page.
   *
   * @param {string} url - Export endpoint URL (already includes ?format=…).
   */
  function downloadFile(url) {
    _showLoading();
    const a = document.createElement('a');
    a.href  = url;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    // Hide loader after a short delay (the download starts asynchronously)
    setTimeout(_hideLoading, 1200);
  }

  // ── Public surface ─────────────────────────────────────────────────────────

  return { get, buildUrl, downloadFile };

}());
