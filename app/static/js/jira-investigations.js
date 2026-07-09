/**
 * jira-investigations.js — "Investigations" drill-down for the Facilities grid.
 *
 * Opens a two-pane modal: a list of Jira tickets filed against the clicked
 * facility on top, full ticket detail for the selected one on the bottom.
 * Reuses the existing generic child-entity endpoint to fetch investigation_tracker
 * rows, and JiraService.search_jira_issues (via GET /jira/issues) for live
 * Jira data — no new Jira-calling logic here.
 *
 * Public API:
 *   JiraInvestigations.open(parentEntity, rowData)
 */
const JiraInvestigations = (function () {

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
    const body = panel.querySelector('.modal-body');
    body.innerHTML = _buildBodyHtml();

    const listPane   = body.querySelector('.jira-issue-list-pane');
    const detailPane = body.querySelector('.jira-issue-detail-pane');

    listPane.innerHTML = '<div class="text-muted">Loading investigations…</div>';

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
      listPane.innerHTML = `<div class="text-muted">Unable to load investigations: ${_esc(err.message || 'Unknown error')}</div>`;
      return;
    }

    if (trackerRows.length === 0) {
      listPane.innerHTML = '<div class="text-muted">No investigations found for this facility.</div>';
      return;
    }

    const jiraKeys = [...new Set(trackerRows.map(r => r.jira_key).filter(Boolean))];

    let issues = [];
    try {
      const resp = await ApiUtils.get(`/jira/issues?keys=${encodeURIComponent(jiraKeys.join(','))}`);
      issues = (resp && resp.data) || [];
    } catch (err) {
      listPane.innerHTML = `<div class="text-muted">Unable to load Jira details: ${_esc(err.message || 'Unknown error')}</div>`;
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
    rows.forEach((row, idx) => {
      const issue      = row.issue;
      const statusText = issue ? (issue.status || '') : 'Not found in Jira';

      const el = document.createElement('div');
      el.className = 'jira-issue-row';
      el.innerHTML = `
        <div class="jira-issue-row-main">
          <span class="jira-issue-key">${_esc(row.tracker.jira_key || '')}</span>
          <span class="jira-issue-summary">${_esc(issue ? (issue.summary || '') : '')}</span>
        </div>
        <span class="jira-issue-status-badge">${_esc(statusText)}</span>
      `;
      el.addEventListener('click', () => {
        listPane.querySelectorAll('.jira-issue-row').forEach(r => r.classList.remove('active'));
        el.classList.add('active');
        _renderDetail(detailPane, row);
      });
      listPane.appendChild(el);

      if (idx === 0) {
        el.classList.add('active');
        _renderDetail(detailPane, row);
      }
    });
  }

  function _renderDetail(detailPane, row) {
    const issue = row.issue;

    if (!issue) {
      detailPane.innerHTML = `
        <div class="text-muted">
          Jira issue "${_esc(row.tracker.jira_key || '')}" could not be found
          (it may not exist in the connected Jira project).
        </div>
      `;
      return;
    }

    detailPane.innerHTML = `
      <div class="jira-issue-detail-header">
        <span class="jira-issue-key">${_esc(issue.key || '')}</span>
        <span class="jira-issue-status-badge">${_esc(issue.status || '')}</span>
      </div>
      <div class="jira-issue-detail-title">${_esc(issue.summary || '')}</div>
      <div class="jira-issue-detail-row"><strong>Priority:</strong> ${_esc(issue.priority || '')}</div>
      <div class="jira-issue-detail-row"><strong>Assignee:</strong> ${_esc(issue.assignee || '')}</div>
      <div class="jira-issue-detail-row"><strong>Created:</strong> ${_esc(issue.created || '')}</div>
      <div class="jira-issue-detail-row"><strong>Updated:</strong> ${_esc(issue.updated || '')}</div>
      <div class="jira-issue-detail-description">${_esc(issue.description || '')}</div>
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
