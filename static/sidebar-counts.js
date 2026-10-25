/* Pending work, not unread visits. Never replace page data during background polling. */
(function () {
  let cached = {}, owner = null, timer = null, busy = false;
  const identity = () => typeof S !== 'undefined' && S?.user ? `${S.user.id}:${S.user.role}:${S.csrf}` : null;
  function paint() {
    document.querySelectorAll('.sidebar [data-nav]').forEach(btn => {
      btn.querySelectorAll('.nav-count').forEach(b => b.remove());
      const n = cached[btn.dataset.nav];
      const label = btn.querySelector('span')?.textContent || btn.dataset.nav;
      btn.title = label; btn.setAttribute('aria-label', label);
      if (!Number.isSafeInteger(n) || n <= 0) return;
      const badge = document.createElement('span');
      badge.className = 'nav-count pending-count';
      badge.textContent = String(n); badge.setAttribute('data-no-translate', '');
      badge.title = `${n} élément(s) à traiter`;
      btn.appendChild(badge);
      btn.title = `${label} · ${n} à traiter`;
      btn.setAttribute('aria-label', btn.title);
    });
  }
  async function load() {
    const who = identity();
    if (!who || (typeof opsOffline !== 'undefined' && opsOffline)) return;
    if (owner !== who) { owner = who; cached = {}; paint(); }
    if (busy) { schedule(); return; }
    busy = true;
    try {
      const data = await api('/sidebar-counts', 'GET', undefined, true);
      if (identity() !== who) return;
      cached = data.counts || {}; paint();
    } catch (_) { /* Keep last known values on a transient network failure. */ }
    finally { busy = false; }
  }
  function schedule() { clearTimeout(timer); timer = setTimeout(load, 200); }
  const baseShell = shell;
  shell = function (...args) {
    const result = baseShell.apply(this, args);
    if (owner !== identity()) { owner = identity(); cached = {}; }
    paint(); schedule(); return result;
  };
  const baseApi = api;
  api = async function (url, method = 'GET', ...args) {
    const result = await baseApi.call(this, url, method, ...args);
    if (!['GET','HEAD'].includes(method.toUpperCase()) || url === '/bootstrap') schedule();
    return result;
  };
  setInterval(() => { if (document.visibilityState === 'visible' && document.querySelector('.sidebar')) load(); }, 30000);
  document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') schedule(); });
  if (document.querySelector('.sidebar')) schedule();
})();
