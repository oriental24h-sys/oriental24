/* v1.4.21 · « Palette du jour » : le brouillon d'aujourd'hui de chaque société se remplit tout seul. Le serveur
   (POST /api/partner-palettes/daily-draft) ramasse automatiquement les commandes enregistrées le jour même
   (statut Créé, jamais reçues ni affectées) au premier lancement puis toutes les 10 minutes et à minuit. Le
   brouillon réutilise le hub de la société (palette la plus récente) ; premier jour = choix du hub une fois puis
   mémorisé. Une fois envoyée, la palette reste celle du jour ; les nouvelles commandes vont dans celle de demain. */
(function () {
  const REF_PREFIX = 'Palette du jour';
  const TICK_MS = 10 * 60 * 1000;
  const societyId = () => (typeof S !== 'undefined' && S && S.user && S.user.role === 'client' && S.user.client_type === 'societe_livraison' ? S.user.id : null);
  const today = () => new Date().toISOString().slice(0, 10);
  const inApp = () => typeof S !== 'undefined' && S && S.user;
  const visible = () => typeof view !== 'undefined' && (view === 'parcels' || view === 'partner-palettes');

  async function sync(opts) {
    opts = opts || {};
    const soc = societyId(); if (!soc) return;
    const payload = {};
    if (opts.hubId != null) payload.destination_hub_id = Number(opts.hubId);
    try {
      const r = await api('/partner-palettes/daily-draft', 'POST', payload);
      if (societyId() !== soc) return null;
      if (opts.toast && r.added > 0) toast(r.added === 1 ? 'Une commande ajoutée à la palette du jour.' : r.added + ' commandes ajoutées à la palette du jour.');
      return r;
    } catch (e) { if (opts.hubId != null) throw e; return null; }
  }

  function scheduleNext() {
    clearTimeout(sync._t);
    const now = new Date(), midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1, 0, 0, 15) - now;
    sync._t = setTimeout(() => { sync({ toast: true }).then(scheduleNext); }, Math.max(Math.min(TICK_MS, midnight), 5000));
  }
  window.dailyPaletteSync = sync;

  async function callDaily(hubId) {
    try {
      const r = await api('/partner-palettes/daily-draft', 'POST', hubId != null ? { destination_hub_id: Number(hubId) } : {});
      return { ok: true, result: r };
    } catch (e) {
      if (/hub de réception de la palette du jour/i.test(e.message || '')) return { askHub: true };
      throw e;
    }
  }
  async function hubModal(hubs) {
    return new Promise((resolve) => {
      modal('Choisir le hub de réception de votre palette du jour', `<p style="line-height:1.9;font-size:13px">Votre première palette du jour a besoin d’un hub ORIENTAL24. Ce choix sera repris automatiquement ensuite.</p><form id="ldp-form"><div class="form-grid"><div class="field full"><label for="ldp-hub">Hub de réception</label><select id="ldp-hub">${hubs.map(h => `<option value="${h.id}">${esc(h.name)} · ${esc(h.city)}</option>`).join('')}</select></div></div><div class="form-actions"><button type="button" class="btn" id="ldp-cancel">Plus tard</button><button type="submit" class="btn primary">${icon('check')}Valider</button></div></form>`, true);
      const f = document.getElementById('ldp-form');
      f.querySelector('#ldp-cancel').onclick = () => { closeModal(); resolve(null); };
      f.onsubmit = (e) => { e.preventDefault(); const h = hubs.find(h => h.id === Number(f.querySelector('#ldp-hub').value)); closeModal(); resolve(h || null); };
    });
  }
  async function ensureSync(forceHub) {
    let r = await callDaily(null);
    if (r.ok) return r.result;
    if (!r.askHub) return null;
    if (!forceHub && sync._hubAskedDay === today()) return { id: null, reason: 'Premier jour : choisissez votre hub de réception (bouton Actualiser) pour démarrer la palette du jour.' };
    sync._hubAskedDay = today();
    const cfg = await api('/partner-palettes/config').catch(() => null);
    if (!cfg || !cfg.hubs || !cfg.hubs.length) { toast('Aucun hub de réception actif : contactez ORIENTAL24.', true); return null; }
    const picked = await hubModal(cfg.hubs);
    if (!picked) return null;
    try { const r2 = await api('/partner-palettes/daily-draft', 'POST', { destination_hub_id: picked.id }); toast('Palette du jour vers ' + picked.name + '.'); return r2; }
    catch (e) { toast(e.message, true); return null; }
  }

  /* Badge latéral : nombre de colis du brouillon du jour, à côté de « Palettes partenaires ». */
  function updateSidebarBadge(d) {
    if (!societyId()) return;
    const btn = document.querySelector('.nav-item[data-nav="partner-palettes"]');
    if (!btn) return;
    let b = btn.querySelector('.daily-badge');
    const n = d && d.status === 'Préparé' ? (d.count || 0) : 0;
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement('span'); b.className = 'nav-count daily-badge'; btn.appendChild(b); }
    b.textContent = n;
    b.title = 'Colis dans la palette du jour (brouillon à envoyer)';
  }
  function tag(status) { return status === 'Préparé' ? 'warn' : status === 'En transit' ? 'blue' : status === 'Partiellement reçu' ? 'blue' : status === 'Reçu' ? 'good' : 'info'; }
  function drawEmpty(node, dayTxt, note) {
    node.innerHTML = `<div class="card daily-palette-empty"><div class="flex between"><div><h3>Palette du jour</h3><p class="sub">${dayTxt} · votre envoi quotidien vers ORIENTAL24</p><p class="form-hint" style="margin:10px 0 0">${note || 'Les commandes que vous saisissez aujourd’hui (statut Créé) rejoindront la palette tout au long de la journée.'}</p></div><button type="button" class="btn" data-ldp="refresh">${icon('refresh')}Actualiser</button></div></div>`;
  }
  function draw(node, d, hint) {
    const dayTxt = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
    node.innerHTML = `<div class="card daily-palette-card">
  <div class="flex between" style="align-items:center"><div><h3>Palette du jour · ${esc(new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long' }).format(new Date()))}</h3><p class="sub">${esc(d.reference)} · ${esc(d.destination_name)}${d.transport ? ' · ' + esc(d.transport) : ''}</p></div><span class="tag ${tag(d.status)}">${esc(d.status)}</span></div>
  <div class="pp-progress" style="margin-top:14px"><strong>${d.count}<small> colis</small></strong><div><b>ajoutés automatiquement à votre palette</b><span>${d.status === 'Préparé' ? 'Brouillon : confirmez l’envoi quand votre transport part.' : d.status === 'Reçu' ? 'Réceptionnée à ' + esc(d.destination_name) + '.' : (d.remaining ? d.remaining + ' restant(s) à recevoir' : 'Aucun colis attendu') + (d.missing ? ' · ' + d.missing + ' manquant(s)' : '')}</span></div></div>
  <div class="daily-palette-list">${d.lines.length ? d.lines.map(l => `<div class="daily-palette-line"><span class="tracking">${esc(l.tracking)}</span><b>${esc(l.recipient)}</b><small>${esc(l.city)}</small><span class="tag ${l.received_at ? 'good' : l.missing_at ? 'warn' : 'blue'}">${l.received_at ? 'Reçu' : l.missing_at ? 'Manquant' : d.status === 'Préparé' ? 'Programmé' : 'À recevoir'}</span></div>`).join('') : '<p class="sub" style="padding:14px 16px">Aucune commande pour l’instant : elle apparaîtra ici dès saisie.</p>'}</div>
  <div class="pp-actions">${d.status === 'Préparé' ? `<button type="button" class="btn primary" data-ldp="dispatch">${icon('truck')}Confirmer l’envoi</button>` : `<button type="button" class="btn" data-ldp="open">${icon('eye')}Ouvrir la palette</button>`}<button type="button" class="btn" data-ldp="refresh">${icon('refresh')}Actualiser</button><span class="sub">Ajout automatique des commandes du jour, jusque minuit.</span></div>${hint ? `<p class="form-hint orange">${esc(hint)}</p>` : ''}
</div>`;
  }

  async function renderDailyPalette(node, forceHub) {
    if (!node.isConnected || !societyId()) return;
    try {
      const rows = (await api('/partner-palettes?size=100')).rows;
      const mineToday = (r) => r.partner_reference === `${REF_PREFIX} · ${today()}`;
      const active = rows.find(r => mineToday(r) && ['Préparé', 'En transit', 'Partiellement reçu'].includes(r.status));
      let hint = null, doc = null;
      if (!active) {
        const r = await ensureSync(forceHub);
        if (!node.isConnected) return;
        if (r && r.id) { doc = r; hint = r.added ? 'Vos commandes du jour ont été ajoutées automatiquement.' : null; }
        else { drawEmpty(node, new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()), r && r.reason ? r.reason : null); updateSidebarBadge(null); bind(); return; }
      }
      if (!doc) doc = await api('/partner-palettes/' + active.id);
      if (!node.isConnected) return;
      if (doc.reason && doc.status !== 'Préparé') hint = doc.reason;
      draw(node, doc, hint);
      updateSidebarBadge(doc);
      bind();
      function bind() {
        const b1 = node.querySelector('[data-ldp=refresh]'); if (b1) b1.onclick = () => renderDailyPalette(node, true);
        const b2 = node.querySelector('[data-ldp=open],[data-ldp=dispatch]');
        if (b2) b2.onclick = () => { if (typeof openPartnerPalette === 'function') openPartnerPalette(doc ? doc.id : active.id); };
      }
    } catch (e) { if (node.isConnected) node.innerHTML = `<div class="card"><p class="form-hint orange">${esc(e.message || e)}</p></div>`; }
  }

  function mountDailyPalette() {
    if (!societyId() || !inApp() || !visible()) { const old = document.querySelector('#daily-palette'); if (old) old.remove(); return; }
    const content = document.getElementById('content'); if (!content) return;
    let node = content.querySelector('#daily-palette');
    if (!node) { node = document.createElement('section'); node.id = 'daily-palette'; node.className = 'daily-palette'; content.insertBefore(node, content.firstChild); }
    renderDailyPalette(node);
  }
  window.dailyPaletteMount = mountDailyPalette;

  /* Branchements : après chaque rendu de vue Société et à l'ouverture d'une palette (scan manuel conservé). */
  const landingBaseRenderView = renderView;
  renderView = async function () {
    const r = await landingBaseRenderView.apply(this, arguments);
    if (typeof view !== 'undefined' && (view === 'parcels' || view === 'partner-palettes')) mountDailyPalette();
    return r;
  };
  const landingBaseOpenPP = typeof openPartnerPalette === 'function' ? openPartnerPalette : null;
  if (landingBaseOpenPP) openPartnerPalette = async function (id) { const r = await landingBaseOpenPP.apply(this, arguments); if (societyId()) setTimeout(mountDailyPalette, 350); return r; };
  const landingBaseRefresh = refresh;
  refresh = async function () { const r = await landingBaseRefresh.apply(this, arguments); if (societyId()) scheduleNext(); return r; };
  const landingBaseCloseModal = typeof closeModal === 'function' ? closeModal : null;
  if (landingBaseCloseModal) closeModal = function () { const r = landingBaseCloseModal.apply(this, arguments); if (societyId()) setTimeout(mountDailyPalette, 50); return r; };
  if (societyId()) scheduleNext();
})();
