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
    if (ctx.sor && ctx.fic_mis_date) {
      el.textContent = '✔ ' + ctx.sor + ' / ' + ctx.fic_mis_date;
      el.className   = 'context-bar-status has-context';
    } else {
      el.textContent = 'Select SOR and Date, then click Load Data';
      el.className   = 'context-bar-status';
    }
  }

  (function init() {
    const sorSel  = document.getElementById('ctx-sor');
    const dateIn  = document.getElementById('ctx-date');
    const loadBtn = document.getElementById('ctx-load-btn');
    if (!sorSel || !dateIn || !loadBtn) return;

    (window.APP_CONFIG?.enabledSors || []).forEach(function (s) {
      const o = document.createElement('option');
      o.value = o.textContent = s;
      sorSel.appendChild(o);
    });

    const saved = getContext();
    if (saved.sor)          sorSel.value = saved.sor;
    if (saved.fic_mis_date) dateIn.value  = saved.fic_mis_date;
    _updateStatus(saved);

    loadBtn.addEventListener('click', function () {
      const ctx = { sor: sorSel.value, fic_mis_date: dateIn.value };
      if (!ctx.sor || !ctx.fic_mis_date) {
        if (typeof Toast !== 'undefined') {
          Toast.warning('Query context required', 'Please select both a SOR and a date before loading data.');
        }
        return;
      }
      saveContext(ctx);
      window.location.reload();
    });
  })();

  return { getContext: getContext, saveContext: saveContext };
}());
