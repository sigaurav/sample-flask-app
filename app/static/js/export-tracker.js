/**
 * export-tracker.js — real-time export job status panel.
 *
 * Panel is created on page load in a minimized state. It expands
 * automatically when ExportTracker.track() is called for the first job
 * in the session. Once all jobs reach a terminal state the panel
 * auto-minimizes. No history is loaded from the server — the panel
 * only shows jobs submitted in the current browser session.
 *
 * Internal route used:
 *   GET /api/internal/exports/<id>/status  — per-job status polling
 *   GET /api/internal/exports/<id>/download — triggered on COMPLETED
 *
 * Depends on: api-utils.js (ApiUtils.downloadExport)
 */
const ExportTracker = (function () {

  const POLL_MS = 3000;

  // Map<jobId, { jobId, label, data: jobData | null, downloaded: bool }>
  const _jobs = new Map();

  let _pollTimer = null;
  let _panel     = null;
  let _collapsed = true;   // panel starts minimized in every new session

  // ── Entity type → display label ────────────────────────────────────────────

  // Updated naming Conventions
  const _ENTITY_LABEL = {
    facilities:   'Facilities',
    obligors:     'Obligors',
    transactions: 'Exposure Events',
    comments:     'Comments',
  };

  function _jobLabel(data) {
    const type   = data.export_type
      ? data.export_type.charAt(0).toUpperCase() + data.export_type.slice(1)
      : 'Full';
    const entity = _ENTITY_LABEL[data.entity_type] || data.entity_type || 'Export';
    return `${type} ${entity} Export`;
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Register a newly submitted job and expand the panel.
   * @param {string} jobId  - job_id returned by the server
   * @param {string} label  - human-readable label, e.g. "Full Facilities Export"
   */
  function track(jobId, label) {
    if (!_jobs.has(jobId)) {
      _jobs.set(jobId, { jobId, label, data: null, downloaded: false });
    }
    _ensurePanel();
    // Auto-expand so the user sees the new job immediately
    if (_collapsed) {
      _collapsed = false;
      _panel.classList.remove('exp-tracker-collapsed');
      _panel.querySelector('.exp-tracker-toggle').textContent = '−';
    }
    _render();
    _startPolling();
  }

  // ── Panel lifecycle ────────────────────────────────────────────────────────

  function _ensurePanel() {
    if (_panel) return;

    _panel = document.createElement('div');
    _panel.className = 'exp-tracker exp-tracker-collapsed';   // start minimized
    _panel.innerHTML =
      '<div class="exp-tracker-header">' +
        '<span class="exp-tracker-title">' +
          '<span>Export Jobs</span>' +
          '<span class="exp-tracker-badge" id="expTrackerBadge" style="display:none">0</span>' +
        '</span>' +
        '<button class="exp-tracker-toggle" title="Expand">+</button>' +
      '</div>' +
      '<div class="exp-tracker-body"></div>';

    _panel.querySelector('.exp-tracker-toggle').addEventListener('click', _toggleCollapse);

    _render();   // paint empty state before appending
    document.body.appendChild(_panel);
  }

  function _toggleCollapse() {
    _collapsed = !_collapsed;
    _panel.classList.toggle('exp-tracker-collapsed', _collapsed);
    _panel.querySelector('.exp-tracker-toggle').textContent = _collapsed ? '+' : '−';
    _panel.querySelector('.exp-tracker-toggle').title       = _collapsed ? 'Expand' : 'Collapse';
  }

  // ── Polling ────────────────────────────────────────────────────────────────

  function _startPolling() {
    if (_pollTimer !== null) return;
    _pollTimer = setInterval(_pollAll, POLL_MS);
  }

  function _stopPolling() {
    if (_pollTimer === null) return;
    clearInterval(_pollTimer);
    _pollTimer = null;
  }

  async function _pollAll() {
    const active = [..._jobs.values()].filter(
      j => !j.data || j.data.status === 'QUEUED' || j.data.status === 'RUNNING'
    );

    if (active.length === 0) {
      _stopPolling();
      // Auto-minimize once all jobs in this session are terminal
      if (!_collapsed) {
        _collapsed = true;
        _panel.classList.add('exp-tracker-collapsed');
        _panel.querySelector('.exp-tracker-toggle').textContent = '+';
        _panel.querySelector('.exp-tracker-toggle').title       = 'Expand';
      }
      return;
    }

    await Promise.all(active.map(_pollOne));
    _render();
  }

  async function _pollOne(entry) {
    try {
      const resp = await fetch(`/api/internal/exports/${entry.jobId}/status`, {
        headers: { 'Accept': 'application/json' },
      });
      const json = await resp.json();
      if (json.data) {
        entry.data = json.data;
        if (entry.data.status === 'COMPLETED' && !entry.downloaded) {
          entry.downloaded = true;
          ApiUtils.downloadExport(entry.jobId);
        }
      }
    } catch (err) {
      console.warn('ExportTracker poll error:', err);
    }
  }

  // ── Rendering ──────────────────────────────────────────────────────────────

  function _render() {
    if (!_panel) return;

    const body = _panel.querySelector('.exp-tracker-body');
    body.innerHTML = '';

    const entries = [..._jobs.values()].reverse();   // newest first

    if (entries.length === 0) {
      const empty = document.createElement('div');
      empty.className   = 'exp-tracker-empty';
      empty.textContent = 'No exports made in this session.';
      body.appendChild(empty);
    } else {
      entries.forEach(e => body.appendChild(_buildCard(e)));
    }

    const active = entries.filter(
      e => !e.data || e.data.status === 'QUEUED' || e.data.status === 'RUNNING'
    ).length;
    const badge = _panel.querySelector('#expTrackerBadge');
    if (badge) {
      badge.style.display    = entries.length > 0 ? '' : 'none';
      badge.textContent      = active > 0 ? active : entries.length;
      badge.style.background = active > 0 ? '#D71E28' : '#4caf50';
    }
  }

  function _buildCard(entry) {
    const card = document.createElement('div');
    card.className = 'exp-card';

    const status = entry.data?.status || 'QUEUED';

    const statusClass = {
      QUEUED:    'exp-status-queued',
      RUNNING:   'exp-status-running',
      COMPLETED: 'exp-status-done',
      FAILED:    'exp-status-fail',
    }[status] || 'exp-status-queued';

    const statusIcon = {
      QUEUED:    '⏳',
      RUNNING:   '⚙',
      COMPLETED: '✓',
      FAILED:    '✕',
    }[status] || '⏳';

    const fmt = entry.data?.file_format
      ? `<span class="exp-fmt-badge">${_esc(entry.data.file_format.toUpperCase())}</span>`
      : '';

    const rows = entry.data?.row_count != null
      ? `<span class="exp-meta">${Number(entry.data.row_count).toLocaleString()} rows</span>`
      : '';

    const dur = entry.data?.duration_seconds != null
      ? `<span class="exp-meta">${Number(entry.data.duration_seconds).toFixed(1)}s</span>`
      : '';

    const errHtml = status === 'FAILED' && entry.data?.error_message
      ? `<div class="exp-error">${_esc(String(entry.data.error_message).slice(0, 140))}</div>`
      : '';

    card.innerHTML =
      `<div class="exp-card-header">` +
        `<span class="exp-label">${_esc(entry.label)}</span>${fmt}` +
      `</div>` +
      `<div class="exp-card-status">` +
        `<span class="exp-status-badge ${statusClass}">${statusIcon} ${status}</span>` +
        rows + dur +
      `</div>` +
      errHtml;

    if (status === 'RUNNING') {
      const bar = document.createElement('div');
      bar.className = 'exp-progress';
      bar.innerHTML = '<div class="exp-progress-bar"></div>';
      card.appendChild(bar);
    }

    return card;
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Boot ───────────────────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', _ensurePanel);

  // ── Public surface ─────────────────────────────────────────────────────────

  return { track };

}());
