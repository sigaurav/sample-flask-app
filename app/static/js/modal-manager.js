/**
 * modal-manager.js — Stack-based modal system.
 *
 * Supports unlimited nesting of drill-down modals.
 * Each open() call pushes a new modal on the stack; close() pops it.
 *
 * Exported as the global `ModalManager` object (IIFE module pattern).
 */
const ModalManager = (function () {

  /** @type {HTMLElement[]} Stack of currently open backdrop elements. */
  const _stack = [];

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Open a new modal.
   *
   * @param {Object}   config
   * @param {string}   config.title      - Modal title text.
   * @param {string[]} [config.breadcrumb] - Hierarchy trail, e.g. ['Dashboard','Facility','Obligors'].
   *                                        Last item is highlighted. Replaces subtitle when provided.
   * @param {string}   [config.subtitle] - Fallback subtitle if no breadcrumb.
   * @param {Function} config.onMount    - Called with (panel, backdrop) after the panel is in the DOM.
   * @param {string}   [config.id]       - Optional ID to retrieve the modal later.
   * @returns {HTMLElement}              - The backdrop element.
   */
  function open(config) {
    const { title, breadcrumb = null, subtitle = '', onMount, id } = config;

    // ── Build the backdrop
    const backdrop = document.createElement('div');
    backdrop.className = 'modal-backdrop';
    if (id) backdrop.dataset.modalId = id;

    // Depth 1 = first modal, 2 = second, etc.
    const depth = _stack.length + 1;
    backdrop.dataset.depth = depth;

    // Explicit z-index so each successive modal is visually in front of all previous ones.
    // CSS nth-of-type cannot do this reliably when other divs exist in <body>.
    backdrop.style.zIndex = 1100 + (depth - 1) * 100;

    // ── Build the panel
    backdrop.innerHTML = _buildPanelHtml(title, subtitle, breadcrumb);
    document.body.appendChild(backdrop);

    // Block scroll on body when any modal is open
    document.body.style.overflow = 'hidden';

    // Click outside panel → close this modal
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) close(backdrop);
    });

    // Escape key → close topmost modal only
    const _escHandler = function (e) {
      if (e.key === 'Escape' && _stack[_stack.length - 1] === backdrop) {
        close(backdrop);
      }
    };
    backdrop._escHandler = _escHandler;
    document.addEventListener('keydown', _escHandler);

    // Wire the close button inside the panel
    backdrop.querySelector('.modal-close-btn')
      .addEventListener('click', () => close(backdrop));

    // Push on stack before calling onMount so nesting works
    _stack.push(backdrop);

    // Animate in (double-rAF ensures the browser has painted the element before
    // starting the transition, preventing it from being skipped)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => backdrop.classList.add('show'));
    });

    // Let the caller populate the modal body
    if (typeof onMount === 'function') {
      const panel = backdrop.querySelector('.modal-panel');
      onMount(panel, backdrop);
    }

    return backdrop;
  }

  /**
   * Close a specific modal (or the topmost one if omitted).
   * @param {HTMLElement} [backdrop] - The backdrop element to close.
   */
  function close(backdrop) {
    const target = backdrop || _stack[_stack.length - 1];
    if (!target) return;

    // Remove escape handler
    if (target._escHandler) document.removeEventListener('keydown', target._escHandler);

    target.classList.remove('show');

    setTimeout(() => {
      if (target.parentNode) target.parentNode.removeChild(target);
      const idx = _stack.indexOf(target);
      if (idx !== -1) _stack.splice(idx, 1);

      // Restore scroll when no modals are open
      if (_stack.length === 0) document.body.style.overflow = '';
    }, 280);
  }

  /** Close all open modals at once. */
  function closeAll() {
    [..._stack].reverse().forEach(close);
  }

  /**
   * Return the number of currently open modals.
   * @returns {number}
   */
  function depth() {
    return _stack.length;
  }

  // ── HTML builder ───────────────────────────────────────────────────────────

  function _buildPanelHtml(title, subtitle, breadcrumb) {
    let headerDetail = '';

    if (breadcrumb && breadcrumb.length > 0) {
      const parts = breadcrumb.map((label, i) => {
        const esc = _esc(label);
        const isLast = i === breadcrumb.length - 1;
        return isLast
          ? `<span class="modal-crumb modal-crumb-active">${esc}</span>`
          : `<span class="modal-crumb">${esc}</span><span class="modal-crumb-sep">›</span>`;
      }).join('');
      headerDetail = `<nav class="modal-trail" aria-label="breadcrumb">${parts}</nav>`;
    } else if (subtitle) {
      headerDetail = `<div class="modal-subtitle">${_esc(subtitle)}</div>`;
    }

    return `
      <div class="modal-panel" role="dialog" aria-modal="true" aria-label="${_esc(title)}">
        <div class="modal-header">
          <div class="modal-header-left">
            <div class="modal-title">${_esc(title)}</div>
            ${headerDetail}
          </div>
          <div class="modal-header-actions">
            <button class="modal-close-btn" title="Close" aria-label="Close modal">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                   stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        </div>
        <div class="modal-body" id="modal-body-${_uid()}"></div>
      </div>
    `;
  }

  // ── Utilities ──────────────────────────────────────────────────────────────

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  let _counter = 0;
  function _uid() { return ++_counter; }

  // ── Public surface ─────────────────────────────────────────────────────────

  return { open, close, closeAll, depth };

}());


// ── Toast notification utility ─────────────────────────────────────────────────

const Toast = (function () {

  /**
   * Show a toast notification.
   *
   * @param {string} title              - Bold heading text.
   * @param {string} [message]          - Supporting detail text.
   * @param {'success'|'error'|'warning'|'info'} [type] - Visual style.
   * @param {number} [durationMs]       - Auto-dismiss delay in ms (0 = manual).
   */
  function show(title, message = '', type = 'info', durationMs = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const icons = {
      success: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1b7a3e" stroke-width="2.5"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>`,
      error:   `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#c0392b" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
      warning: `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#c47a00" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
      info:    `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#1565c0" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <div class="toast-icon">${icons[type] || icons.info}</div>
      <div class="toast-body">
        <div class="toast-title">${title}</div>
        ${message ? `<div class="toast-msg">${message}</div>` : ''}
      </div>
    `;

    container.appendChild(toast);
    requestAnimationFrame(() => {
      requestAnimationFrame(() => toast.classList.add('show'));
    });

    if (durationMs > 0) {
      setTimeout(() => dismiss(toast), durationMs);
    }

    return toast;
  }

  function dismiss(toast) {
    toast.classList.remove('show');
    toast.classList.add('hide');
    setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
  }

  return {
    success: (t, m, ms)  => show(t, m, 'success', ms),
    error:   (t, m, ms)  => show(t, m, 'error',   ms),
    warning: (t, m, ms)  => show(t, m, 'warning',  ms),
    info:    (t, m, ms)  => show(t, m, 'info',     ms),
  };

}());
