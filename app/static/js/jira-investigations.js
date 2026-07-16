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

  function _formatSize(bytes) {
    if (bytes === null || bytes === undefined) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  const ATTACHMENT_ICON = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
    </svg>`;

  const DOWNLOAD_ICON = `
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>`;

  const TABS = [
    { id: 'details',     label: 'Details' },
    { id: 'comments',    label: 'Comments' },
    { id: 'history',     label: 'History' },
    { id: 'attachments', label: 'Attachments' },
  ];

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

    // Per-row state: which tab is active, and a cache of already-fetched
    // tab data so switching tabs (or re-selecting this ticket later) doesn't
    // re-hit the Jira API. Comments/History/Attachments each require their
    // own dedicated per-issue call (unlike Details, which comes from the
    // bulk list call) so they're only fetched the first time their tab opens.
    if (!row._activeTab) row._activeTab = 'details';
    if (!row._tabCache) row._tabCache = { comments: null, history: null, attachments: null };

    detailPane.innerHTML = `
      <div class="jira-issue-detail-header">
        <span class="jira-issue-key jira-issue-key-lg">
          ${_esc(issue.key || '')}
          ${url ? `<a href="${_esc(url)}" target="_blank" rel="noopener" class="jira-issue-link" title="Open in Jira">${EXTERNAL_LINK_ICON}</a>` : ''}
        </span>
        <span class="jira-status-badge ${_statusClass(issue.status)}">${_esc(issue.status || '')}</span>
      </div>
      <div class="jira-issue-detail-title">${_esc(issue.summary || '')}</div>

      <div class="jira-detail-tabs" role="tablist">
        ${TABS.map(t => `<button type="button" class="jira-detail-tab-btn${t.id === row._activeTab ? ' active' : ''}" data-tab="${t.id}">${t.label}</button>`).join('')}
      </div>

      <div class="jira-detail-tab-content"></div>
    `;

    detailPane.querySelectorAll('.jira-detail-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.dataset.tab === row._activeTab) return;
        row._activeTab = btn.dataset.tab;
        detailPane.querySelectorAll('.jira-detail-tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        _renderTabContent(detailPane, row);
      });
    });

    _renderTabContent(detailPane, row);
  }

  function _renderTabContent(detailPane, row) {
    const container = detailPane.querySelector('.jira-detail-tab-content');
    const tab = row._activeTab;
    const issue = row.issue;

    if (tab === 'details') {
      container.innerHTML = _buildDetailsTabHtml(issue);
      return;
    }

    const endpoints = {
      comments:    `/jira/issues/${encodeURIComponent(row.tracker.jira_key)}/comments`,
      history:     `/jira/issues/${encodeURIComponent(row.tracker.jira_key)}/history`,
      attachments: `/jira/issues/${encodeURIComponent(row.tracker.jira_key)}/attachments`,
    };
    const renderers = {
      comments:    (c, data) => _renderComments(c, data, row),
      history:     _renderHistory,
      attachments: _renderAttachments,
    };

    _renderAsyncTab(container, row, tab, endpoints[tab], renderers[tab]);
  }

  async function _renderAsyncTab(container, row, tabKey, url, renderFn) {
    if (row._tabCache[tabKey]) {
      renderFn(container, row._tabCache[tabKey]);
      return;
    }

    container.innerHTML = '<div class="jira-pane-status">Loading…</div>';

    try {
      const resp = await ApiUtils.get(url);
      const data = (resp && resp.data) || [];
      row._tabCache[tabKey] = data;

      // The user may have switched tabs (or tickets, which rebuilds this
      // container entirely) while this request was in flight.
      if (row._activeTab !== tabKey) return;
      renderFn(container, data);
    } catch (err) {
      if (row._activeTab !== tabKey) return;
      container.innerHTML = `<div class="jira-pane-status jira-pane-error">Unable to load ${tabKey}: ${_esc(err.message || 'Unknown error')}</div>`;
    }
  }

  function _buildDetailsTabHtml(issue) {
    return `
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

  function _renderComments(container, comments, row) {
  const issueKey = row.tracker.jira_key;

  // Build existing comments HTML
  const commentsHtml = (!comments || comments.length === 0)
    ? '<div class="jira-pane-status">No comments yet.</div>'
    : comments.map(c => `
        <div class="jira-comment-card">
          <div class="jira-comment-header">
            <span class="jira-avatar">${_esc((c.author || '?')[0].toUpperCase())}</span>
            <span class="jira-comment-author">${_esc(c.author || 'Unknown')}</span>
            <span class="jira-comment-date">${_esc(_formatDate(c.created))}</span>
          </div>
          <div class="jira-comment-body">${_esc(c.body || '')}</div>
        </div>
      `).join('');

  // Render comments list + add comment box
  container.innerHTML = `
    <div class="jira-comments-list" id="jira-comments-list-${_esc(issueKey)}">
      ${commentsHtml}
    </div>
    <div class="jira-add-comment">
      <textarea
        id="jira-new-comment-${_esc(issueKey)}"
        placeholder="Add a comment..."
      ></textarea>
      <div class="jira-add-comment-actions">
        <button class="jira-comment-cancel-btn" id="jira-comment-cancel-${_esc(issueKey)}">
          Clear
        </button>
        <button class="jira-comment-submit-btn" id="jira-comment-submit-${_esc(issueKey)}">
          Save
        </button>
      </div>
    </div>
  `;

  // Wire up Clear button
  container
    .querySelector(`#jira-comment-cancel-${_esc(issueKey)}`)
    .addEventListener('click', function () {
      container.querySelector(`#jira-new-comment-${_esc(issueKey)}`).value = '';
    });

  // Wire up Save button
  container
    .querySelector(`#jira-comment-submit-${_esc(issueKey)}`)
    .addEventListener('click', async function () {
      const textarea   = container.querySelector(`#jira-new-comment-${_esc(issueKey)}`);
      const submitBtn  = this;
      const commentText = textarea.value.trim();

      if (!commentText) {
        textarea.focus();
        return;
      }

      // Disable button while submitting
      submitBtn.disabled = true;
      submitBtn.textContent = 'Saving...';

      try {
        const resp = await fetch(`/jira/issues/${encodeURIComponent(issueKey)}/comments`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ comment: commentText }),
        });

        const respBody = await resp.json().catch(() => ({}));

        if (!resp.ok) {
          throw new Error(respBody.error || 'Failed to save comment');
        }

        // Re-fetch rather than hand-building a placeholder card: this
        // guarantees the real author/timestamp from Jira (not "You"/"Just
        // now") and keeps row._tabCache.comments in sync, so switching
        // tabs and back doesn't show a stale list missing this comment.
        textarea.value = '';
        row._tabCache.comments = null;
        await _renderAsyncTab(
          container,
          row,
          'comments',
          `/jira/issues/${encodeURIComponent(issueKey)}/comments`,
          (c, data) => _renderComments(c, data, row),
        );

      } catch (err) {
        alert('Error: ' + err.message);
      } finally {
        submitBtn.disabled    = false;
        submitBtn.textContent = 'Save';
      }
    });
  }

  function _renderHistory(container, history) {
    if (!history || history.length === 0) {
      container.innerHTML = '<div class="jira-pane-status">No history recorded.</div>';
      return;
    }

    container.innerHTML = `
      <div class="jira-history-timeline">
        ${history.map(h => `
          <div class="jira-history-entry">
            <div class="jira-history-dot"></div>
            <div class="jira-history-body">
              <div class="jira-history-meta">
                <span class="jira-history-author">${_esc(h.author || 'Unknown')}</span>
                <span class="jira-history-date">${_esc(_formatDate(h.created))}</span>
              </div>
              ${(h.items || []).map(item => `
                <div class="jira-history-change">
                  Changed <strong>${_esc(item.field || '')}</strong> from
                  <span class="jira-history-from">${item.from ? _esc(item.from) : '<em>empty</em>'}</span> to
                  <span class="jira-history-to">${item.to ? _esc(item.to) : '<em>empty</em>'}</span>
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    `;
  }

  function _renderAttachments(container, attachments) {
    if (!attachments || attachments.length === 0) {
      container.innerHTML = '<div class="jira-pane-status">No attachments.</div>';
      return;
    }

    container.innerHTML = attachments.map(a => {
      const base = (APP_CONFIG.jiraBaseUrl || '').replace(/\/+$/, '');
      const downloadUrl = `${base}/secure/attachment/${encodeURIComponent(a.id)}/${encodeURIComponent(a.filename || '')}`;
      return `
        <div class="jira-attachment-row">
          <div class="jira-meta-icon">${ATTACHMENT_ICON}</div>
          <div class="jira-attachment-info">
            <span class="jira-attachment-filename">${_esc(a.filename || 'Untitled')}</span>
            <span class="jira-attachment-meta">${_esc(_formatSize(a.size))} · ${_esc(a.author || 'Unknown')} · ${_esc(_formatDate(a.created))}</span>
          </div>
          <a href="${_esc(downloadUrl)}" target="_blank" rel="noopener"
            class="jira-attachment-download" title="Download ${_esc(a.filename || '')}">
           ${DOWNLOAD_ICON}
          </a>
        </div>
      `;
    }).join('');
  }

  function _buildBodyHtml() {
    return `
      <div class="jira-issue-list-pane"></div>
      <div class="jira-issue-detail-pane"></div>
    `;
  }

  return { open };

}());
