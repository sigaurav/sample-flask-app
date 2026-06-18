const ContextBar = (function () {
  const CTX_KEY = 'wf_query_context';

  function getContext() {
    try { return JSON.parse(localStorage.getItem(CTX_KEY) || '{}'); }
    catch (_) { return {}; }
  }

  function saveContext(ctx) {
    localStorage.setItem(CTX_KEY, JSON.stringify(ctx));
  }

  function _updateStatus(ctx) {
    const el = document.getElementById('ctx-status');
    if (!el) return;
    if (ctx.fic_mis_date) {
      el.textContent = ctx.fic_mis_date;
      el.className   = 'context-bar-status has-context';
    } else {
      el.textContent = 'Enter a report date, then click Load Data';
      el.className   = 'context-bar-status';
    }
  }

  // Auto-insert dashes while typing: 2026 → 2026- → 2026-06- → 2026-06-11
  function _autoFormatDate(input) {
    input.addEventListener('input', function (e) {
      let v = e.target.value.replace(/\D/g, '');
      if (v.length > 4)  v = v.slice(0, 4) + '-' + v.slice(4);
      if (v.length > 7)  v = v.slice(0, 7) + '-' + v.slice(7);
      if (v.length > 10) v = v.slice(0, 10);
      e.target.value = v;
      e.target.classList.toggle('has-value', v.length > 0);
    });
  }

  (function init() {
    const dateIn  = document.getElementById('ctx-date');
    const loadBtn = document.getElementById('ctx-load-btn');
    if (!dateIn || !loadBtn) return;

    // Restore last-used context
    const saved = getContext();
    if (saved.fic_mis_date) {
      dateIn.value = saved.fic_mis_date;
      dateIn.classList.add('has-value');
    }
    _updateStatus(saved);
    _autoFormatDate(dateIn);

    loadBtn.addEventListener('click', function () {
      const ctx = { fic_mis_date: dateIn.value.trim() };
      if (!ctx.fic_mis_date) {
        if (typeof Toast !== 'undefined') {
          Toast.warning('Query context required', 'Please enter a report date before loading data.');
        }
        return;
      }
      // Basic YYYY-MM-DD validation
      if (!/^\d{4}-\d{2}-\d{2}$/.test(ctx.fic_mis_date)) {
        if (typeof Toast !== 'undefined') {
          Toast.warning('Invalid date', 'Date must be in YYYY-MM-DD format, e.g. 2024-01-31');
        }
        return;
      }
      saveContext(ctx);
      window.location.reload();
    });
  })();

  return { getContext: getContext, saveContext: saveContext };
}());
