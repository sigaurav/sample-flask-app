/**
 * entity-page.js — Generic standalone entity page.
 *
 * Call EntityPage.init('facilities') / EntityPage.init('obligations') / etc.
 * from the page template.  All entity-specific behaviour is driven by
 * APP_CONFIG.entities.  Uses server-side pagination via POST /api/<entity>.
 *
 * Depends on: api-utils.js, grid-config.js, drill-down.js, context-bar.js
 */
const EntityPage = (function () {

  function _getLabelForRow(rowData, entityType) {
    const cfg = (APP_CONFIG.entities || {})[entityType] || {};
    const labelField = cfg.label_field || (cfg.pk || [])[0];
    return (labelField && rowData[labelField]) ? String(rowData[labelField]) : '';
  }

  function _getActivePredicate(entityType) {
    const cfg = ((APP_CONFIG.entities || {})[entityType] || {}).active_filter;
    if (cfg) return r => r[cfg.field] === cfg.value;
    return () => false;
  }

  async function _getSchema(entityType) {
    try {
      const r = await ApiUtils.get(`/api/schema/${entityType}`, false);
      return r.data || [];
    } catch (_) {
      return [];
    }
  }

  async function init(entityType) {
    const schema = await _getSchema(entityType);
    const entityCfg = (APP_CONFIG.entities || {})[entityType] || {};
    const children = entityCfg.children || {};
    const pkCols = entityCfg.pk || [];

    const drillHandlers = {};
    Object.keys(children).forEach(childEntity => {
      drillHandlers[childEntity] = childEntity === 'investigation_tracker'
        ? (p) => JiraInvestigations.open(entityType, p.data)
        : (p) => DrillDown.open(
            entityType, childEntity, p.data,
            _getLabelForRow(p.data, entityType),
          );
    });

    /* Rolando' addition. */
    const colDefs = buildColumnsFromSchema(schema, drillHandlers, {
      showRowActions: entityCfg.enable_row_action === true
    });


    const queryFn = async (spec) => {
      const ctx = ContextBar.getContext();
      spec.period_dt = ctx.period_dt || '';
      const resp = await ApiUtils.post(`/api/${entityType}`, spec);
      ApiUtils.updateKpi(resp.meta);
      return resp;
    };

    // Rolando updates below statement
    const grid = new GridManager(
      entityType + 'Grid',
      colDefs,
      {
        paginationPageSize: 25,
        paginationPageSizeSelector: [10, 25, 50, 100],
        initialSort: pkCols.map(f => ({ field: f, dir: 'asc' })),
        queryFn,
        onRowAction: (ctx) => showRowActionMenu(ctx, entityType),
      },
    ).init();

    const applyBtn = document.getElementById('btnApplyFilters');
    if (applyBtn) {
      grid.setApplyButton(applyBtn);
      applyBtn.addEventListener('click', () => grid.applyFilters());
    }

    ApiUtils.wireGridToolbar(grid);
    ApiUtils.wireExportDropdown(
      grid, entityType,
      entityType.charAt(0).toUpperCase() + entityType.slice(1),
    );

    const ctx = ContextBar.getContext();
    if (ctx.period_dt) {
      grid.applyFilters();
    } else {
      Toast.info(
        'Select report date',
        'Enter a report date in the bar above, then click Load Data.',
        undefined, 5000,
      );
    }
  }

  // Code below here is added by rolando, this reconstruction might be faulty. Cross Validdate
  function showRowActionMenu(ctx, entityType) {
    const existing = document.querySelector('.row-action-menu');
    if (existing) {
      existing.remove();
    }

    const selectedRows = Array.isArray(ctx.selectedRows)
      ? ctx.selectedRows
      : [];

    const records = selectedRows.length > 0
      ? selectedRows
      : ctx.row
        ? [ctx.row]
        : [];

    if (records.length === 0) {
      Toast.warning(
        'No record selected',
        'Unable to identify the selected record.'
      );
      return;
    }

    const menu = document.createElement('div');
    menu.className = 'row-action-menu';

    const openInvestigationBtn = document.createElement('button');
    openInvestigationBtn.type = 'button';
    openInvestigationBtn.className = 'row-action-menu-item';
    openInvestigationBtn.textContent = 'Open Investigation';

    openInvestigationBtn.addEventListener('click', function () {
      menu.remove();
      openInvestigationModal(
        entityType,
        records,
        ctx.grid
      );
    });

    menu.appendChild(openInvestigationBtn);

    document.body.appendChild(menu);

    const rect = ctx.anchor.getBoundingClientRect();

    menu.style.top =
      rect.bottom + window.scrollY + 4 + 'px';

    menu.style.left =
      rect.left + window.scrollX - 160 + 'px';

    const onOutside = function (e) {
      if (
        !menu.contains(e.target) &&
        e.target !== ctx.anchor
      ) {
        menu.remove();
        document.removeEventListener(
          'mousedown',
          onOutside
        );
      }
    };

    setTimeout(function () {
      document.addEventListener(
        'mousedown',
        onOutside
      );
    }, 0);
  }

  function _markdownToJiraMarkup(markdown) {
    let text = String(markdown || '')
      .replace(/\r\n/g, '\n');

    const tokens = [];

    function stash(value) {
      const token =
        `@@JIRA_TOKEN_${tokens.length}@@`;

      tokens.push({
        token,
        value
      });

      return token;
    }

    function restoreTokens(value) {
      tokens.forEach(function (entry) {
        value = value.replaceAll(
          entry.token,
          entry.value
        );
      });

      return value;
    }

    // Protect fenced code blocks first so formatting inside code is not converted.
    text = text.replace(
      /```([a-zA-Z0-9_-]+)?[ \t]*\n([\s\S]*?)```/g,
      function (_, lang, code) {
        const language = lang ? `{${lang}}` : '';
        const cleanCode = code.replace(/\n+$/, '');

        return stash(
          `{code${language}}\n${cleanCode}\n{code}`
        );
      }
    );

    // Protect inline code before bold/italic/list conversion.
    text = text.replace(
      /`([^`\n]+)`/g,
      function (_, code) {
        return stash(`{{${code}}}`);
      }
    );

    // Links: [text](url) -> [text|url]
    text = text.replace(
      /\[([^\]]+)\]\((https?:\/\/[^\s]+|mailto:[^)]+)\)/g,
      '[$1|$2]'
    );

    // Headings
    text = text.replace(/^###### (.*)$/gm, 'h6. $1');
    text = text.replace(/^##### (.*)$/gm, 'h5. $1');
    text = text.replace(/^#### (.*)$/gm, 'h4. $1');
    text = text.replace(/^### (.*)$/gm, 'h3. $1');
    text = text.replace(/^## (.*)$/gm, 'h2. $1');
    text = text.replace(/^# (.*)$/gm, 'h1. $1');

    // Bold + italic combination FIRST
    text = text.replace(
      /\*\*\*([^\n]+?)\*\*\*/g,
      function (_, value) {
        return stash(`_*${value}*_`);
      }
    );

    // Markdown bold -> Jira bold
    text = text.replace(
      /\*\*([^\n]+?)\*\*/g,
      function (_, value) {
        return `*${value}*`;
      }
    );

    // Markdown italic -> Jira italic
    text = text.replace(
      /\*([^\n*]+?)\*/g,
      function (_, value) {
        return `_${value}_`;
      }
    );

    // -----------------------------------------------------
    // Remaining list conversion section is partially blurred
    // -----------------------------------------------------

    // TODO: ordered list conversion

    // TODO: unordered list conversion

    // TODO: blockquote conversion

    // TODO: horizontal rule conversion

    // TODO: escape handling (image unreadable)

    // Restore protected code blocks / inline code
    text = restoreTokens(text);

    return text;
  }

  async function openInvestigationModal(entityType, records, grid) {
    const recordCount = records.length;
    let assigneesByEmail = {};

    const bodyHtml = `
            <div class="investigation-modal">

                <div class="form-row">
                    <label for="investigation-priority">Priority</label>

                    <select
                        id="investigation-priority"
                        class="investigation-input"
                    >
                        <option value="">Select priority</option>
                        <option value="Highest">Highest</option>
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                        <option value="Lowest">Lowest</option>
                    </select>
                </div>

                <div class="form-row">
                    <label for="investigation-summary">
                        Summary
                    </label>

                    <input
                        type="text"
                        id="investigation-summary"
                        class="investigation-input"
                        placeholder="Enter investigation summary"
                    />
                </div>

                <div class="form-row">
                    <label for="investigation-assignee">
                        Assignee
                    </label>

                    <select
                        id="investigation-assignee"
                        class="investigation-input investigation-fwidth"
                    >
                        <option value="">
                            Loading assignees...
                        </option>
                    </select>
                </div>

                <div class="form-row investigation-description-row">
                    <label for="investigation-description">
                        Description
                    </label>

                    <textarea
                        id="investigation-description"
                        class="investigation-textarea"
                        placeholder="Enter investigation description"
                    ></textarea>
                </div>

                <div class="form-row investigation-acceptance-row">
                    <label for="investigation-acceptancecriteria">
                        Acceptance Criteria
                    </label>

                    <textarea
                        id="investigation-acceptancecriteria"
                        class="investigation-textarea"
                        placeholder="Enter acceptance criteria"
                    ></textarea>
                </div>

                <div class="modal-footer">

                    <div class="modal-footer-left">
                        <span class="record-count">
                            ${recordCount} record(s) included
                        </span>
                    </div>

                    <div class="modal-footer-right">

                        <button
                            type="button"
                            class="btn btn-ghost investigation-cancel-btn"
                        >
                            Cancel
                        </button>

                        <button
                            type="button"
                            class="btn btn-primary investigation-submit-btn"
                        >
                            Submit
                        </button>

                    </div>

                </div>

            </div>
        `;

    ModalManager.open({
      title: 'Open Investigation',

      onMount: async function (panel, backdrop) {

        panel.querySelector('.modal-body').innerHTML = bodyHtml;

        let descriptionEditor = null;
        let acceptanceCriteriaEditor = null;

        const investigationEditorToolbar = [
          'bold',
          'italic',
          'heading',
          '|',
          'unordered-list',
          'ordered-list',
          '|',
          'quote',
          'code',
          'link',
          '|',
          'preview'
        ];

        descriptionEditor = new EasyMDE({
          element: panel.querySelector(
            '#investigation-description'
          ),

          spellChecker: false,
          status: false,
          minHeight: '180px',
          autofocus: false,
          toolbar: investigationEditorToolbar
        });

        acceptanceCriteriaEditor = new EasyMDE({
          element: panel.querySelector(
            '#investigation-acceptancecriteria'
          ),

          spellChecker: false,
          status: false,
          minHeight: '180px',
          autofocus: false,
          toolbar: investigationEditorToolbar
        });

        // ----------------------------------------------------
        // Load assignees
        // ----------------------------------------------------

        const assigneeSelect = panel.querySelector(
          '#investigation-assignee'
        );

        try {
          const response = await ApiUtils.get(
            '/jira/assignees'
          );

          assigneeSelect.innerHTML =
            '<option value="">Select assignee</option>';

          (response?.records || []).forEach(function (user) {
            assigneesByEmail[user.assignee_emailaddress] = user;

            const option = document.createElement('option');

            option.value = user.assignee_emailaddress;

            option.textContent =
              user.assignee_name ||
              user.assignee_emailaddress;

            assigneeSelect.appendChild(option);
          });

        } catch (err) {

          assigneeSelect.innerHTML =
            '<option value="">Unable to load assignees</option>';

          Toast.error(
            'Unable to load assignees.',
            err?.message || 'Unknown error'
          );
        }

        panel.querySelector(
          '.investigation-cancel-btn'
        ).addEventListener('click', function () {
          ModalManager.close();
        });

        panel.querySelector(
          '.investigation-submit-btn'
        ).addEventListener('click', async function () {

          const priority = panel.querySelector(
            '#investigation-priority'
          ).value.trim();

          const summary = panel.querySelector(
            '#investigation-summary'
          ).value.trim();

          const assigneeEmail = panel.querySelector(
            '#investigation-assignee'
          ).value;
          const assignee = assigneesByEmail[assigneeEmail];

          const description =
            descriptionEditor.value().trim();

          const acceptanceCriteria =
            acceptanceCriteriaEditor.value().trim();

          if (!priority) {
            Toast.warning(
              'Priority is required.',
              'Please select a priority.'
            );
            return;
          }

          if (!summary) {
            Toast.warning(
              'Summary is required.',
              'Please enter a summary.'
            );
            return;
          }

          if (!assignee) {
            Toast.warning(
              'Assignee is required.',
              'Please select an assignee.'
            );
            return;
          }

          const payload = {
            entityType,
            records,
            priority,
            summary,
            assignee,

            description_data:
              _markdownToJiraMarkup(description),

            acceptancecriteria_data:
              _markdownToJiraMarkup(
                acceptanceCriteria
              )
          };

          const submitButton = panel.querySelector(
            '.investigation-submit-btn'
          );

          submitButton.disabled = true;
          submitButton.textContent = 'Creating...';

          try {

            const response =
              await ApiUtils.post(
                '/jira/investigation/create',
                payload
              );

            ModalManager.close();

            Toast.success(
              'Investigation created successfully.',
              response?.issueKey
                ? `Issue ${response.issueKey} created.`
                : 'Jira issue created successfully.'
            );

            if (
              grid &&
              typeof grid.applyFilters === 'function'
            ) {
              await grid.applyFilters();
            }

          } catch (err) {

            Toast.error(
              'Unable to create investigation.',
              err?.message ||
              'Unexpected error occurred.'
            );

          } finally {

            submitButton.disabled = false;
            submitButton.textContent = 'Submit';
          }

        });

      }

    });

  }

  return { init };

}());
