/**
 * jira-investigations.js — "Investigations" drill-down for the Facilities grid.
 *
 * Opens a two-pane modal: a list of Jira tickets filed against the clicked
 * facility on top (30%), full ticket detail for the selected one on the
 * bottom (70%) — populated only after a ticket is clicked. Reuses the
 * existing generic child-entity endpoint to fetch investigation_tracker
 * rows, and JiraService.search_jira_issues (via GET /jira/issues) for live
 * Jira data — no new Jira-calling logic here.
 *
 * Public API:
 *   JiraInvestigations.open(parentEntity, rowData)
 */
const JiraInvestigations = (function () {

  // Rough status → color-family mapping. Falls back to neutral for anything
  // unrecognized (custom workflow statuses vary a lot between Jira projects).
  const STATUS_COLOR_MAP = [
    { match: /done|closed|resolved|complete/i,        cls: 'jira-status-done' },
    { match: /progress|review|testing/i,               cls: 'jira-status-progress' },
    { match: /block|cancel|reject/i,                   cls: 'jira-status-blocked' },
    { match: /to ?do|open|new|backlog/i,                cls: 'jira-status-todo' },
  ];

  function _statusClass(status) {
    const hit = STATUS_COLOR_MAP.find(s => s.match.test(status || ''));
    return hit ? hit.cls : 'jira-status-default';
  }

  function _getLabelForRow(rowData, entityType) {
    const cfg = (APP_CONFIG.entities || {})[entityType] || {};
    const labelField = cfg.label_field || (cfg.pk || [])[0];
    return (labelField && rowData[labelField]) ? String(rowData[labelField]) : '';
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function _ticketUrl(jiraKey) {
    const base = (APP_CONFIG.jiraBaseUrl || '').replace(/\/+$/, '');
    return base ? `${base}/browse/${encodeURIComponent(jiraKey)}` : null;
  }

  const EXTERNAL_LINK_ICON = `
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
      <polyline points="15 3 21 3 21 9"/>
      <line x1="10" y1="14" x2="21" y2="3"/>
    </svg>`;

  const META_ICONS = {
    priority: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/></svg>`,
    assignee: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    created: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
    updated: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15-6.7L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15 6.7L3 16"/></svg>`,
  };

  function _formatDate(value) {
    if (!value) return '—';
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  }

  function _initials(name) {
    if (!name) return '?';
    const base = String(name).split('@')[0].replace(/[._]+/g, ' ').trim();
    const parts = base.split(/\s+/).filter(Boolean);
    if (parts.length === 0) return '?';
    return (parts[0][0] + (parts[1] ? parts[1][0] : '')).toUpperCase();
  }

  //  Public: open the modal ─

  function open(parentEntity, rowData) {
    const entities = APP_CONFIG.entities || {};
    const childRel = ((entities[parentEntity] || {}).children || {}).investigation_tracker || {};
    const fkCols   = childRel.fk || [];
    const fkValues = Object.fromEntries(fkCols.map(col => [col, rowData[col]]));
    const display  = _getLabelForRow(rowData, parentEntity);

    ModalManager.open({
      title: 'Investigations',
      breadcrumb: ['Credit Facilities', display, 'Investigations'],
      onMount: (panel) => _mountModal(panel, parentEntity, fkValues),
    });
  }

  //  Modal mount ─

  async function _mountModal(panel, parentEntity, fkValues) {
    panel.classList.add('jira-investigations-modal');

    const body = panel.querySelector('.modal-body');
    body.innerHTML = _buildBodyHtml();

    const listPane   = body.querySelector('.jira-issue-list-pane');
    const detailPane = body.querySelector('.jira-issue-detail-pane');

    _renderEmptyDetail(detailPane);
    listPane.innerHTML = '<div class="jira-pane-status">Loading investigations…</div>';

    let trackerRows;
    try {
      const ctx  = ContextBar.getContext();
      const resp = await ApiUtils.post(`/api/${parentEntity}/investigation_tracker`, {
        entity_key: fkValues,
        period_dt:  ctx.period_dt || '',
        page: 1, per_page: 50,
      });
      trackerRows = resp.data || [];
    } catch (err) {
      listPane.innerHTML = `<div class="jira-pane-status jira-pane-error">Unable to load investigations: ${_esc(err.message || 'Unknown error')}</div>`;
      return;
    }

    if (trackerRows.length === 0) {
      listPane.innerHTML = '<div class="jira-pane-status">No investigations found for this facility.</div>';
      return;
    }

    const jiraKeys = [...new Set(trackerRows.map(r => r.jira_key).filter(Boolean))];

    let issues = [];
    try {
      const resp = await ApiUtils.get(`/jira/issues?keys=${encodeURIComponent(jiraKeys.join(','))}`);
      issues = (resp && resp.data) || [];
    } catch (err) {
      listPane.innerHTML = `<div class="jira-pane-status jira-pane-error">Unable to load Jira details: ${_esc(err.message || 'Unknown error')}</div>`;
      return;
    }

    const issuesByKey = Object.fromEntries(issues.map(i => [i.key, i]));

    // Pair each tracker row with its live Jira issue, if found. A tracker
    // row whose jira_key doesn't resolve (e.g. demo data pointed at a key
    // that doesn't exist in the connected Jira project) is still listed,
    // with a "not found" placeholder in the detail pane, rather than dropped.
    const rows = trackerRows.map(t => ({
      tracker: t,
      issue: issuesByKey[t.jira_key] || null,
    }));

    _renderList(listPane, detailPane, rows);
  }

  //  Rendering ─

  function _renderList(listPane, detailPane, rows) {
    listPane.innerHTML = '';
    rows.forEach((row) => {
      const issue      = row.issue;
      const statusText = issue ? (issue.status || '') : 'Not found';
      const url        = _ticketUrl(row.tracker.jira_key);

      const el = document.createElement('div');
      el.className = 'jira-issue-row';
      el.innerHTML = `
        <div class="jira-issue-row-top">
          <span class="jira-issue-key">
            ${_esc(row.tracker.jira_key || '')}
            ${url ? `<a href="${_esc(url)}" target="_blank" rel="noopener" class="jira-issue-link" title="Open in Jira" onclick="event.stopPropagation()">${EXTERNAL_LINK_ICON}</a>` : ''}
          </span>
          <span class="jira-status-badge ${_statusClass(statusText)}">${_esc(statusText)}</span>
        </div>
        <div class="jira-issue-summary">${_esc(issue ? (issue.summary || '') : '')}</div>
      `;
      el.addEventListener('click', () => {
        listPane.querySelectorAll('.jira-issue-row').forEach(r => r.classList.remove('active'));
        el.classList.add('active');
        _renderDetail(detailPane, row);
      });
      listPane.appendChild(el);
    });
  }

  function _renderEmptyDetail(detailPane) {
    detailPane.innerHTML = `
      <div class="jira-empty-detail">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
          <line x1="9" y1="15" x2="15" y2="15"/>
          <line x1="9" y1="11" x2="13" y2="11"/>
        </svg>
        <div class="jira-empty-detail-title">No investigation selected</div>
        <div class="jira-empty-detail-subtitle">Choose an investigation from the list above to view its details.</div>
      </div>
    `;
  }

  function _renderDetail(detailPane, row) {
    const issue = row.issue;

    if (!issue) {
      detailPane.innerHTML = `
        <div class="jira-empty-detail">
          <div class="jira-empty-detail-title">Issue not found</div>
          <div class="jira-empty-detail-subtitle">
            Jira issue "${_esc(row.tracker.jira_key || '')}" could not be found
            (it may not exist in the connected Jira project).
          </div>
        </div>
      `;
      return;
    }

    const url = _ticketUrl(issue.key);

    detailPane.innerHTML = `
      <div class="jira-issue-detail-header">
        <span class="jira-issue-key jira-issue-key-lg">
          ${_esc(issue.key || '')}
          ${url ? `<a href="${_esc(url)}" target="_blank" rel="noopener" class="jira-issue-link" title="Open in Jira">${EXTERNAL_LINK_ICON}</a>` : ''}
        </span>
        <span class="jira-status-badge ${_statusClass(issue.status)}">${_esc(issue.status || '')}</span>
      </div>
      <div class="jira-issue-detail-title">${_esc(issue.summary || '')}</div>

      <div class="jira-issue-detail-meta">
        <div class="jira-issue-detail-meta-item">
          <div class="jira-meta-icon">${META_ICONS.priority}</div>
          <div class="jira-meta-text">
            <span class="jira-issue-detail-meta-label">Priority</span>
            <span class="jira-issue-detail-meta-value">${_esc(issue.priority || '—')}</span>
          </div>
        </div>
        <div class="jira-issue-detail-meta-item">
          <div class="jira-meta-icon jira-meta-avatar">${_esc(_initials(issue.assignee))}</div>
          <div class="jira-meta-text">
            <span class="jira-issue-detail-meta-label">Assignee</span>
            <span class="jira-issue-detail-meta-value" title="${_esc(issue.assignee || '')}">${_esc(issue.assignee || '—')}</span>
          </div>
        </div>
        <div class="jira-issue-detail-meta-item">
          <div class="jira-meta-icon">${META_ICONS.created}</div>
          <div class="jira-meta-text">
            <span class="jira-issue-detail-meta-label">Created</span>
            <span class="jira-issue-detail-meta-value">${_esc(_formatDate(issue.created))}</span>
          </div>
        </div>
        <div class="jira-issue-detail-meta-item">
          <div class="jira-meta-icon">${META_ICONS.updated}</div>
          <div class="jira-meta-text">
            <span class="jira-issue-detail-meta-label">Updated</span>
            <span class="jira-issue-detail-meta-value">${_esc(_formatDate(issue.updated))}</span>
          </div>
        </div>
      </div>

      <div class="jira-issue-detail-section">
        <div class="jira-issue-detail-section-title">Description</div>
        <div class="jira-issue-detail-description">${issue.description ? _esc(issue.description) : '<span class="text-muted">No description provided.</span>'}</div>
      </div>

      ${issue.acceptancecriteria ? `
      <div class="jira-issue-detail-section">
        <div class="jira-issue-detail-section-title">Acceptance Criteria</div>
        <div class="jira-issue-detail-description">${_esc(issue.acceptancecriteria)}</div>
      </div>` : ''}
    `;
  }

  function _buildBodyHtml() {
    return `
      <div class="jira-issue-list-pane"></div>
      <div class="jira-issue-detail-pane"></div>
    `;
  }

  return { open };

}());
