/* v1.4.27 · « Mon app » livreur : espace mobile-first façon application (recherche téléphone, plage de dates,
   filtre par statut, changement de statut en liste métier, scan, tiroir), installable en PWA.
   v1.4.27 « Journée » : stats du jour (total / ouverts / COD à collecter / taux), filtres rapides
   (Aujourd'hui · En tournée · Retards), itinéraire Google Maps (multi-étapes et par colis), bouton
   « Notifier » WhatsApp par statut, manifest de tournée imprimable, bannière de rappel (programmés du
   jour + retards > 48 h). 100 % côté client : aucun endpoint supplémentaire ;
   les colis viennent du bootstrap déjà limité au livreur.
   v1.5.0 « Équipe » : un chef d'équipe (= livreur dont d'autres livreurs sont rattachés via
   « Chef d'équipe » dans sa fiche) voit aussi les colis de son équipe — filtre par livreur,
   réaffectation d'un colis à un membre, synthèse par membre. Les relevés restent par livreur. */
(function () {
  const VIEW = 'driver-app';
  const isDriver = () => typeof S !== 'undefined' && S && S.user && S.user.role === 'livreur';
  const smallScreen = () => typeof matchMedia !== 'undefined' && matchMedia('(max-width: 820px)').matches;
  /* v1.13.0 : sommes-nous dans l'application installée (APK livreur, PWA en plein écran) ?
     Dans ce cas l'interface se présente comme une vraie application : pas de barre de site,
     pas de barre d'outils interne. ?app=1 permet de le prévisualiser dans un navigateur. */
  const APP_MODE = (typeof navigator !== 'undefined' && /ORIENTAL24APP\//.test(navigator.userAgent || '')) ||
    (typeof navigator !== 'undefined' && navigator.standalone === true) ||
    (typeof matchMedia !== 'undefined' && matchMedia('(display-mode: standalone)').matches) ||
    (typeof location !== 'undefined' && /(^|[?&])app=1(&|$)/.test(location.search || ''));
  const setAppShell = (on) => { if (typeof document !== 'undefined' && document.body) document.body.classList.toggle('o24-app', !!on); };
  const iso = (d) => d.toISOString().slice(0, 10);
  const frDay = (s) => new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(s + 'T12:00:00'));

  if (typeof titles !== 'undefined') titles[VIEW] = 'Mon app livreur';

  const state = { q: '', from: '', to: '', status: '', quick: '', driver: '' };
  /* v1.5.0 : membres de l'équipe (visibles dans le bootstrap quand l'utilisateur est chef). */
  const members = () => (S.users || []).filter((u) => u.role === 'livreur' && u.team_lead_id === S.user.id && u.active);
  function resetRange() { const t = new Date(), f = new Date(Date.now() - 59 * 86400000); state.from = iso(f); state.to = iso(t); }
  resetRange();

  const digits = (s) => String(s || '').replace(/\D/g, '');
  const dayOf = (p) => String(p.created_at || '').slice(0, 10);
  const CLOSED = ['Livré', 'Retourné', 'Refusé', 'Annulé'];
  const TOURNEE = ['Reçu par le livreur', 'En livraison', 'Programmé', 'Reporté'];
  const tard = (p) => ((p.status === 'Programmé' && p.next_attempt_at && p.next_attempt_at < new Date().toISOString()) ||
    (TOURNEE.filter((s) => s !== 'Programmé' && s !== 'Reporté').includes(p.status) && (Date.now() - new Date(p.updated_at || p.created_at).getTime()) > 48 * 3600000));
  function quickOk(p) {
    if (state.quick === 'today') return dayOf(p) === iso(new Date());
    if (state.quick === 'tournee') return TOURNEE.includes(p.status);
    if (state.quick === 'retards') return tard(p);
    if (state.quick === 'ouverts') return !CLOSED.includes(p.status);
    return true;
  }

  function filtered() {
    const q = digits(state.q);
    return S.parcels.filter((p) => {
      if (!quickOk(p)) return false;
      if (state.driver && p.driver_id !== state.driver) return false;
      if (q && !digits(p.phone).includes(q)) return false;
      const d = dayOf(p);
      if (state.from && d < state.from) return false;
      if (state.to && d > state.to) return false;
      if (state.status && p.status !== state.status) return false;
      return true;
    }).sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
  }
  const rangeLabel = () => (!state.from && !state.to) ? 'Toutes les dates' : `${frDay(state.from)} → ${frDay(state.to)}`;

  /* Stats du jour (tous calculs sur les colis du livreur, sans serveur). */
  function stats() {
    const open = S.parcels.filter((p) => !CLOSED.includes(p.status));
    const tried = S.parcels.filter((p) => ['Livré', 'Retourné', 'Refusé'].includes(p.status));
    const livres = tried.filter((p) => p.status === 'Livré').length;
    return {
      total: S.parcels.length,
      ouverts: open.length,
      cod: open.reduce((n, p) => n + (+p.amount || 0), 0),
      taux: tried.length ? Math.round((livres / tried.length) * 100) + '%' : '—',
      plan: S.parcels.filter((p) => p.status === 'Programmé' && (p.next_attempt_at || '').slice(0, 10) === iso(new Date())).length,
      retards: S.parcels.filter(tard).length,
    };
  }
  const mapsAddr = (p) => `${p.address}, ${p.city}, Maroc`;
  /* Itinéraire Maps : traçage multi-étapes depuis la position GPS du livreur (pas de clé API). */
  window.daItinUrl = () => {
    const rows = filtered().filter((p) => !CLOSED.includes(p.status)).slice(0, 10);
    if (!rows.length) return '';
    const dest = encodeURIComponent(mapsAddr(rows[rows.length - 1]));
    const wps = rows.slice(0, -1).map((p) => encodeURIComponent(mapsAddr(p))).join('%7C');
    return 'https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=' + dest + (wps ? '&waypoints=' + wps : '');
  };
  window.daItin = () => { const u = daItinUrl(); if (u) window.open(u, '_blank'); else toast('Aucun colis à tracer pour ces filtres.', true); };

  const TAG = (s) => (s === 'Livré' ? 'good' : ['Retourné', 'Refusé'].includes(s) ? 'warn' : s === 'Créé' ? 'info' : 'blue');

  function card(p) {
    return `<button class="da-card" onclick="daOpen(${p.id})">
      <div class="da-card-top"><span class="tracking">${esc(p.tracking)}</span><span class="tag ${TAG(p.status)}">${esc(p.status)}</span></div>
      <div class="da-card-main"><b>${esc(p.recipient)}</b><span class="sub">${icon('phone')} ${esc(p.phone)} · ${esc(p.city)}</span></div>
      <div class="da-card-foot"><strong>${money(p.amount)} <small>MAD</small></strong><span class="sub">${esc(p.product || 'Colis')}</span></div>
    </button>`;
  }

  /* v1.13.0 : l'écran livreur a son propre rendu, il n'héritait donc pas des
     annonces de l'administration. On les affiche en tête de liste (l'annonce
     « application » avec son lien de téléchargement arrive jusqu'au livreur). */
  async function daNotices() {
    const host = document.getElementById('content');
    if (!host || !isDriver() || typeof api !== 'function') return;
    let rows = [];
    try { rows = await api('/announcements'); } catch (e) { return; }
    if (!isDriver()) return;
    const da = document.querySelector('#content .da');
    if (!da) return;
    const html = (typeof announcementMarkup === 'function') ? announcementMarkup(Array.isArray(rows) ? rows : []) : '';
    let box = da.querySelector('.da-notices');
    if (!html) { if (box) box.remove(); return; }
    if (!box) { box = document.createElement('div'); box.className = 'da-notices'; da.prepend(box); }
    box.innerHTML = html;
  }

  function render() {
    const node = document.getElementById('content');
    if (!node || !isDriver()) return;
    setAppShell(APP_MODE);
    const rows = filtered();
    const st = stats();
    const statuses = [{ s: '', label: 'Tous les colis', n: S.parcels.length }].concat(
      S.statuses.map((x) => ({ s: x, label: x, n: S.parcels.filter((p) => p.status === x).length })).filter((x) => x.n > 0));
    node.innerHTML = `<div class="da">
      <header class="da-top">
        <button class="icon-btn" onclick="openDaDrawer()" aria-label="Menu">${icon('menu')}</button>
        <span class="da-version">v ${esc((typeof RUNTIME !== 'undefined' && RUNTIME.version) || '')}</span>
        <span class="spacer"></span>
        <button class="icon-btn" onclick="daPos()" aria-label="Transmettre ma position">${icon('search')}</button>
        <button class="icon-btn" onclick="daVehicle()" aria-label="Mon véhicule connecté">${icon('truck')}</button>
        <button class="icon-btn" onclick="daItin()" aria-label="Itinéraire">${icon('pin')}</button>
        <button class="icon-btn" onclick="openScanner()" aria-label="Scanner un colis">${icon('scan')}</button>
      </header>
      <button class="da-update" id="da-update" hidden>${icon('alert')} Une nouvelle version est prête — touchez pour mettre à jour</button>
      ${(st.plan || st.retards) ? `<div class="da-banner" role="alert">
        ${st.plan ? `<button class="seg" onclick="daQuick('plan')">${icon('calendar')} ${st.plan} programmé(s) aujourd’hui</button>` : ''}
        ${st.retards ? `<button class="seg warn" onclick="daQuick('retards')">${icon('clock')} ${st.retards} colis en retard (+48 h)</button>` : ''}
      </div>` : ''}
      <div class="da-stats">
        <button class="da-stat" onclick="daReset()"><small>Total colis</small><b>${st.total}</b></button>
        <button class="da-stat" onclick="daQuick('ouverts')"><small>Ouverts</small><b>${st.ouverts}</b></button>
        <button class="da-stat" onclick="daQuick('ouverts')"><small>COD à collecter</small><b>${money(st.cod)} <i>MAD</i></b></button>
        <span class="da-stat"><small>Taux de réussite</small><b>${st.taux}</b></span>
      </div>
      <div class="da-kchips">
        <button class="da-chip sm ${state.quick === '' ? 'sel' : ''}" onclick="daQuick('')">Tous</button>
        <button class="da-chip sm ${state.quick === 'today' ? 'sel' : ''}" onclick="daQuick('today')">${icon('calendar')} Aujourd’hui</button>
        <button class="da-chip sm ${state.quick === 'tournee' ? 'sel' : ''}" onclick="daQuick('tournee')">${icon('truck')} En tournée</button>
        <button class="da-chip sm ${state.quick === 'retards' ? 'sel warn' : ''}" onclick="daQuick('retards')">${icon('clock')} Retards${st.retards ? ` (${st.retards})` : ''}</button>
      </div>
      <div class="da-search">${icon('search')}<input id="da-q" inputmode="tel" placeholder="Recherche par numéro de téléphone…" value="${esc(state.q)}" oninput="daFilter('q',this.value)">
        <button class="icon-btn" onclick="daRangeModal()" aria-label="Plage et dates">${icon('sliders')}</button></div>
      <div class="da-chips">
        <button class="da-chip active" onclick="daRangeModal()">${icon('calendar')} ${esc(rangeLabel())}</button>
        <button class="da-chip" onclick="daStatusSheet()">${icon('chevron','down')} ${esc(state.status || 'Tous les colis')}</button>
        ${state.driver ? `<button class="da-chip ghost sel" onclick="daDriver('')" title="Tout l'équipe">${icon('users')} ${esc(memberName(state.driver))} ${icon('close')}</button>` : ''}
        ${(state.q || state.status) ? `<button class="da-chip ghost" onclick="daReset()" title="Effacer les filtres">${icon('close')} Effacer</button>` : ''}
      </div>
      <div class="da-list">${rows.length ? rows.map(card).join('') : `<p class="da-empty">Aucun colis sur cette période.<br><small>Changez la plage de dates, le statut ou le filtre rapide pour voir plus.</small></p>`}</div>
    </div>
    ${APP_MODE ? `<div class="da-fab">
      <button class="fab-scan" type="button" onclick="openScanner()" aria-label="Scanner un colis">${icon('scan')}</button>
      <button class="fab-menu" type="button" onclick="openDaDrawer()" aria-label="Menu du livreur">${icon('menu')}</button>
    </div>` : ''}
    <div class="da-drawer" id="da-drawer" hidden>
      <div class="da-drawer-panel">
        <div class="da-drawer-head"><span class="avatar orange">${initials(S.user.name)}</span><div><b>${esc(S.user.name)}</b><button class="link" onclick="closeDrawer();navigate('profile')">Voir le profil</button></div><button class="icon-btn" onclick="closeDrawer()" aria-label="Fermer">${icon('close')}</button></div>
        <nav class="da-drawer-menu">
          <button onclick="closeDrawer()">${icon('truck')} Mes colis</button>
          ${members().length ? `<button onclick="closeDrawer();daTeam()">${icon('users')} Mon équipe (${members().length})</button>` : ''}
          <button onclick="closeDrawer();daDayClose()">${icon('wallet')} Fin de journée</button>
          <button onclick="closeDrawer();navigate('driver-finance')">${icon('wallet')} Caisse &amp; commissions</button>
          <button onclick="closeDrawer();daVehicle()">${icon('truck')} Mon véhicule connecté</button>
          <button onclick="closeDrawer();navigate('print')">${icon('print')} Impression d’étiquettes</button>
          <button onclick="closeDrawer();daManifest()">${icon('file')} Manifest du jour (PDF)</button>
          <button onclick="closeDrawer();navigate('parcels')">${icon('grid')} Vue classique (ordinateur)</button>
          <button class="danger" onclick="logout()">${icon('logout')} Se déconnecter</button>
        </nav>
        <small class="da-drawer-foot">ORIENTAL24 · app livreur · v ${esc((typeof RUNTIME !== 'undefined' && RUNTIME.version) || '')}</small>
      </div>
    </div>`;
    ensurePwa();
    daNotices();
  }

  /* v1.5.0 : écran équipe du chef — synthèse par membre, filtre par livreur. */
  const memberName = (id) => { const m = members().find((u) => u.id === id); return m ? m.name : (id === S.user.id ? 'Moi' : 'Sans affectation'); };
  window.daDriver = (id) => { state.driver = id || ''; render(); };
  window.daTeam = () => {
    const list = members();
    if (!list.length) return;
    /* v1.5.2 : trié par livrés 7 j — médaillé du meilleur membre, stats par ligne. */
    const ranked = list.map((u) => ({ u, r: driverRankRows(7).find((x) => x.id === u.id) || { lv7: 0, today: 0, taux: null, retards: 0 } }))
      .sort((a, b) => b.r.lv7 - a.r.lv7 || a.u.name.localeCompare(b.u.name));
    const row = (e, i) => {
      const u = e.u, r = e.r;
      const open = S.parcels.filter((p) => p.driver_id === u.id && !CLOSED.includes(p.status));
      const cod = open.reduce((n, p) => n + (+p.amount || 0), 0);
      const live = S.parcels.filter((p) => p.driver_id === u.id && TOURNEE.includes(p.status)).length;
      return `<button class="da-sheet-row da-status-row" onclick="closeModal();daDriver(${u.id})">
        <span class="da-status-ic" style="font-size:15px;width:auto;min-width:28px">${leaderMedal(i)}</span>
        <span class="da-status-label">${esc(u.name)}<small>Aujourd’hui ${r.today} · 7 j : ${r.lv7} livré(s)${r.taux === null ? '' : ' (' + r.taux + '%)'}${r.retards ? ' · ' + r.retards + ' retard(s)' : ''} · ${open.length} ouvert(s) · ${live} en tournée</small></span>
        <b style="text-align:right;line-height:1.25">${money(cod)}<small style="display:block;font-weight:500">MAD</small></b></button>`;
    };
    modal('Mon équipe', `
      <p class="form-hint" style="margin-bottom:8px">${list.length} livreur(s) rattaché(s), classés sur 7 jours glissants (« Livré » = date de mise à jour). Touchez un membre pour voir ses colis. Les montants sont le COD encore à collecter.</p>
      <div class="da-sheet">${ranked.map(row).join('')}</div>
      <p class="form-hint" style="margin:10px 2px 0">Admin rattache les livreurs depuis « Clients / fiche livreur → Chef d’équipe ». Les relevés et la caisse restent <b>par livreur</b> : chacun encaisse et rend sa caisse.</p>`, true);
  };
  /* v1.5.3 « Fin de journée » : caisse du jour pour moi (et mon équipe si chef) — calcul à l’instant, lecture seule. */
  window.daDayClose = async () => {
    let rows;
    try { rows = await api('/driver-days/me'); } catch (e) { toast(e.message, true); return; }
    const chip = (r) => !r.close ? '<span class="tag">Ouverte</span>' : (r.close.status === 'Rouvert' ? '<span class="tag purple">Rouverte</span>' : (r.variance_cents ? `<span class="tag bad">Écart ${centMoney(Math.abs(r.variance_cents))} MAD</span>` : '<span class="tag good">Clôturée</span>'));
    modal('Fin de journée · ' + new Date().toLocaleDateString('fr-FR'), `
      <p class="form-hint" style="margin-bottom:8px">Caisse du jour <b>calculée à l’instant</b> : l’Admin clôture et constate la remise de fin de tournée. Ce récapitulatif ne déclenche aucun paiement.</p>
      <div class="da-sheet">${rows.map((r) => `<div class="da-sheet-row da-status-row" style="cursor:default">
        <span class="da-status-ic">${icon('user')}</span>
        <span class="da-status-label">${esc(r.driver)}${r.driver_id === S.user.id ? ' (moi)' : ''}<small>${r.livres} livré(s) · ${r.retournes} ret. · ${r.refuses} ref. · COD <b>${centMoney(r.cod_cents)} MAD</b> · commissions ${r.barême ? centMoney(r.commission_cents) + ' MAD' : 'sans barème'} → attendu <b>${centMoney(r.expected_cents)} MAD</b>${r.close && r.close.status === 'Clôturé' ? ' · reçu ' + centMoney(r.received_cents) + ' MAD' : ''}</small></span>
        ${chip(r)}</div>`).join('')}</div>
      <p class="form-hint" style="margin:10px 2px 0">Attendu = COD des colis « Livré » aujourd’hui${rows[0] && rows[0].mode === 'net' ? ', moins la commission (règlement net)' : ''}. Le rapprochement complet reste dans « Caisse & commissions ».</p>`, true);
  };
  window.daReassign = async (id, did) => {
    const p = S.parcels.find((x) => x.id === id);
    if (!p) return;
    await api409(
      (f) => api('/parcels/' + id, 'PATCH', { driver_id: Number(did), revision: f ? f.ops_revision : (p.ops_revision || 0) }),
      async () => ({ ops_revision: (await api('/parcels/' + id)).parcel.ops_revision }));
    await saved('Réaffectation enregistrée → ' + memberName(Number(did)));
    render();
  };
  window.daFilter = (k, v) => { state[k] = v; render(); };
  window.daReset = () => { state.q = ''; state.status = ''; state.quick = ''; state.driver = ''; resetRange(); render(); };
  window.daQuick = (q) => {
    if (q === 'plan') { state.status = 'Programmé'; state.quick = 'today'; state.from = ''; state.to = ''; }
    else state.quick = q;
    render();
  };
  /* Manifest de tournée imprimable (« Enregistrer au format PDF » depuis la boîte d’impression). */
  window.daManifest = () => {
    const rows = filtered().filter((p) => !CLOSED.includes(p.status));
    if (!rows.length) { toast('Aucun colis à rover pour ces filtres.', true); return; }
    const w = window.open('', '_blank');
    if (!w) { toast('Autorisez les fenêtres surgissantes pour imprimer le manifest.', true); return; }
    const cod = rows.reduce((n, p) => n + (+p.amount || 0), 0);
    const today = new Intl.DateTimeFormat('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(new Date());
    w.document.write(`<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Manifest de tournée — ORIENTAL24</title><style>
      body{font-family:Arial,sans-serif;color:#111827;margin:24px;font-size:12px}
      h1{font-size:18px;margin:0} h2{font-size:11px;color:#6b7280;font-weight:400;margin:2px 0 16px}
      table{width:100%;border-collapse:collapse} th{background:#0b1526;color:#fff;text-align:left;font-size:10px;text-transform:uppercase}
      th,td{border:1px solid #d1d5db;padding:5px 7px;vertical-align:top} tr:nth-child(even) td{background:#f6f8fb}
      .tag{display:inline-block;border:1px solid #94a3b8;border-radius:999px;padding:1px 7px;font-size:10px}
      .tot{margin-top:10px;font-size:13px}.sig{margin-top:34px;display:flex;gap:60px;color:#374151}
      @media print{button{display:none}}</style></head><body>
      <h1>ORIENTAL24 · Manifest de tournée</h1>
      <h2>${esc(S.user.name)} · ${today} · ${rows.length} colis à livrer</h2>
      <table><thead><tr><th>#</th><th>Tracking</th><th>Destinataire</th><th>Téléphone</th><th>Adresse</th><th>Ville</th><th>Statut</th><th>COD à collecter</th></tr></thead><tbody>
      ${rows.map((p, i) => `<tr><td>${i + 1}</td><td>${esc(p.tracking)}</td><td>${esc(p.recipient)}</td><td>${esc(p.phone)}</td><td>${esc(p.address)}</td><td>${esc(p.city)}</td><td><span class="tag">${esc(p.status)}</span></td><td>${money(p.amount)} MAD</td></tr>`).join('')}
      </tbody></table>
      <p class="tot"><b>Total COD attendu : ${money(cod)} MAD</b> · ${rows.length} colis</p>
      <div class="sig"><span>Signature du livreur : ____________________</span><span>Signature de l’émetteur : ____________________</span></div>
      <button onclick="window.print()" style="margin-top:18px;padding:8px 14px;border:0;border-radius:8px;background:#f97316;color:#fff;font-weight:700">Imprimer / PDF</button>
    </body></html>`);
    w.document.close(); w.focus();
  };
  window.daRangeModal = () => {
    modal('Plage de dates', `<div class="form-grid">
      <div class="field"><label for="da-from">Du</label><input type="date" id="da-from" value="${state.from}"></div>
      <div class="field"><label for="da-to">Au</label><input type="date" id="da-to" value="${state.to}"></div>
      <div class="form-actions"><button class="btn" onclick="closeModal();daSetRange('','')">Tout voir</button><button class="btn primary" onclick="daApplyRange()">Appliquer</button></div></div>`, true);
  };
  window.daApplyRange = () => { daSetRange(document.getElementById('da-from').value, document.getElementById('da-to').value); };
  window.daSetRange = (f, t) => { if (f && t && f > t) [f, t] = [t, f]; state.from = f; state.to = t; closeModal(); render(); };
  window.daStatusSheet = () => {
    const statuses = [{ s: '', label: 'Tous les colis' }].concat(S.statuses.map((st) => ({ s: st, label: st })));
    modal('Filtrer par statut', `<div class="da-sheet">${statuses.map((x) => {
      const n = S.parcels.filter((p) => !x.s || p.status === x.s).length;
      return `<button class="da-sheet-row ${state.status === x.s ? 'sel' : ''}" onclick="daSetStatus('${esc(x.s)}')"><span>${esc(x.label)}</span><b>${n}</b></button>`;
    }).join('')}</div>`, true);
  };
  window.daSetStatus = (s) => { state.status = s; closeModal(); render(); };
  /* v1.4.26 : feuille « Changer le statut » — liste métier du livreur demandée (dates pour Reporté/Programmé,
     motif pour Refusé/Annulé, « Pas de réponse » = Reporté + motif standard), le tout sur l'endpoint existant ;
     les cibles impossibles pour un livreur depuis l'état actuel restent visibles mais grisées. */
  const DA_STATUS_OPTS = [
    { key: 'reporte', label: 'Reporté', status: 'Reporté', date: true, icon: 'clock', sub: 'nouvelle date' },
    { key: 'programme', label: 'Programmé', status: 'Programmé', date: true, reason: 'appointment', icon: 'calendar', sub: 'rendez-vous + date' },
    { key: 'receptionne', label: 'Réceptionné', status: 'Réceptionné', icon: 'box' },
    { key: 'recu', label: 'Reçu par le livreur', status: 'Reçu par le livreur', icon: 'user' },
    { key: 'livre', label: 'Livré', status: 'Livré', cod: true, icon: 'check' },
    { key: 'refuse', label: 'Refusé', status: 'Refusé', motif: 'required', danger: true, icon: 'close', sub: 'motif requis' },
    { key: 'tournee', label: 'En livraison', status: 'En livraison', icon: 'truck' },
    { key: 'retourne', label: 'Retourné', status: 'Retourné', icon: 'return' },
    { key: 'annule', label: 'Annulé', status: 'Annulé', motif: 'required', danger: true, icon: 'alert', sub: 'motif requis' },
    { key: 'noresponse', label: 'Pas de réponse', status: 'Reporté', prefill: 'Pas de réponse du destinataire', icon: 'phone', sub: '→ Reporté' },
  ];
  window.daStatusPick = (id) => {
    const p = S.parcels.find((x) => x.id === id);
    if (!p) return;
    const trans = (S.status_policy && S.status_policy.driver_transitions) || {};
    const allowed = new Set(trans[p.status] || []);
    const locked = p.financial_locked || p.invoice_id || p.operations_locked;
    const rows = DA_STATUS_OPTS.map((o) => {
      const cur = o.label === p.status;
      const ok = !cur && !locked && allowed.has(o.status);
      return `<button class="da-sheet-row da-status-row${cur ? ' sel' : ''}${o.danger ? ' danger' : ''}" ${ok ? `onclick="daApplyStatus(${p.id},'${o.key}')"` : 'disabled'}>
        <span class="da-status-ic ${o.danger ? 'danger' : ''}">${icon(o.icon)}</span>
        <span class="da-status-label">${esc(o.label)}${o.sub ? `<small>${esc(o.sub)}</small>` : ''}</span>
        ${cur ? '<b class="da-actuel">actuel</b>' : `<b>${icon('chevron')}</b>`}
      </button>`;
    }).join('');
    const hint = locked
      ? 'Ce colis est figé (relevé livreur, facture ou opérations) : aucune modification de statut.'
      : !allowed.size
        ? `Colis clôturé : aucune action possible depuis « ${p.status} ». Contactez l’administration.`
        : 'Seules les actions possibles pour un livreur depuis cet état sont actives.';
    modal('Changer le statut', `
      <div class="full form-hint" style="margin-bottom:8px">${esc(p.tracking)} · État actuel : <b>${esc(p.status)}</b></div>
      <div class="da-sheet">${rows}</div>
      <p class="form-hint" style="margin:10px 2px 0">${hint}</p>`, true);
  };
  window.daApplyStatus = (id, key) => {
    const p = S.parcels.find((x) => x.id === id);
    const o = DA_STATUS_OPTS.find((x) => x.key === key);
    if (!p || !o) return;
    const frDay = (v) => v ? new Intl.DateTimeFormat('fr-FR').format(new Date(v + 'T12:00:00')) : '';
    modal('Confirmer : ' + o.label, form(
      `<input type="hidden" name="status" value="${esc(o.status)}">${o.reason ? `<input type="hidden" name="reason_code" value="${o.reason}">` : ''}
       <div class="full form-hint">${esc(p.tracking)} · ${esc(p.status)} → <b>${esc(o.label)}</b></div>
       ${p.otp_required && o.key === 'livre' ? `<div class="field full"><label for="f-otp">Code reçu par le client *</label><input id="f-otp" name="otp" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="one-time-code" required placeholder="4 chiffres"></div>` : ''}
       ${o.cod ? `<div class="full form-hint orange">« Livré » confirme que le montant de ${money(p.amount)} MAD a été collecté auprès du destinataire.</div>` : ''}
       ${o.date ? `<div class="field full"><label for="f-next_at">Date *</label><input type="date" id="f-next_at" name="next_at" required min="${iso(new Date())}"></div>` : ''}
       ${o.prefill ? textarea('note', 'Motif', o.prefill) : textarea('note', o.motif === 'required' ? 'Motif' : 'Motif / commentaire (optionnel)', '', o.motif === 'required')}
       ${o.key === 'noresponse' ? `<div class="full form-hint">Sera enregistré comme « Reporté » avec ce motif (l’ancien rendez-vous est retiré).</div>` : ''}`,
      'Confirmer'));
    bindForm(async (d) => {
      const payload = { status: d.status, note: d.note, revision: p.ops_revision || 0 };
      if (d.otp) payload.otp = String(d.otp).replace(/\D/g, '');
      if (d.reason_code) payload.reason_code = d.reason_code;
      if (o.key === 'programme') payload.next_attempt_at = d.next_at + 'T12:00';
      if (o.key === 'reporte') payload.note = 'Reporté au ' + frDay(d.next_at) + (d.note ? ' · ' + d.note : '');
      try {
        await api409(
          (f) => api('/parcels/' + id, 'PATCH', { ...payload, revision: f ? f.ops_revision : payload.revision }),
          async () => ({ ops_revision: (await api('/parcels/' + id)).parcel.ops_revision }));
      } catch (e) { toast(e.message || 'Mise à jour refusée', true); return; }
      await saved('Statut mis à jour : ' + o.label);
      daPos(true);   // v1.8.0 : à chaque étape, la position suit la tournée
      render();
      if (o.key === 'livre') daPodModal(id);   // v1.4.28 : proposition photo / signature après une livraison
    });
  };
  /* v1.4.28 : preuve de livraison — photo (caméra du téléphone, compressée) ou signature tactile du
     destinataire. Optionnel : « Passer » n'enregistre rien. */
  window.daPodModal = (id) => {
    const p = S.parcels.find((x) => x.id === id);
    if (!p) return;
    modal('Preuve de livraison', `
      <div class="full form-hint" style="margin-bottom:8px">${esc(p.tracking)} · ${esc(p.recipient)}</div>
      <div class="da-sheet">
        <label class="da-sheet-row da-status-row" style="cursor:pointer">
          <span class="da-status-ic">${icon('scan')}</span>
          <span class="da-status-label">Ajouter une photo<small>colis / lieux au moment de la remise</small></span>
          <input type="file" accept="image/*" capture="environment" style="display:none" onchange="podUpload(${p.id},'photo',this).then(()=>closeModal()).catch((e)=>toast(e.message,true))">
        </label>
        <button class="da-sheet-row da-status-row" onclick="podSig(${p.id})">
          <span class="da-status-ic">${icon('edit')}</span>
          <span class="da-status-label">Signature du destinataire<small>sur l’écran</small></span>
          <b>${icon('chevron')}</b>
        </button>
        <button class="da-sheet-row" onclick="closeModal()"><span class="da-status-label">Passer<small>aucune preuve pour ce colis</small></span></button>
      </div>
      <p class="form-hint" style="margin:10px 2px 0">Optionnel, recommandé pour sécuriser l’encaissement. Les preuves restent visibles dans la fiche du colis.</p>`, true);
  };
  window.daOpen = (id) => {
    const p = S.parcels.find((x) => x.id === id);
    if (!p) return;
    const phone = digits(p.phone), wa = phone.startsWith('212') ? phone : '212' + phone.replace(/^0/, '');
    modal(`${esc(p.tracking)} <span class="tag ${TAG(p.status)}" style="margin-left:6px">${esc(p.status)}</span>`, `
      <div class="detail-grid"><div><div class="detail-info">
        <h3 style="font-size:16px">${esc(p.recipient)}</h3>
        <p class="muted" style="font-size:13px">${esc(p.address)}<br>${esc(p.city)} · ${esc(p.phone)}</p>
        <div class="detail-line"><span>À collecter</span><strong>${money(p.amount)} MAD</strong></div>
        <div class="detail-line"><span>Statut</span><span>${esc(p.status)}</span></div>
        ${members().length ? `<div class="detail-line"><span>Livreur</span><select id="da-driver" onchange="daReassign(${p.id},this.value)" style="max-width:190px;padding:6px 9px;border:1px solid #d7deea;border-radius:9px;background:#fff">${[{ id: S.user.id, name: 'Moi — ' + S.user.name }, ...members()].map((u) => `<option value="${u.id}" ${p.driver_id === u.id ? 'selected' : ''}>${esc(u.name)}</option>`).join('')}</select></div>` : ''}
        <div class="flex" style="flex-wrap:wrap;margin-top:10px">
          <a class="btn sm" href="tel:${esc(p.phone)}">${icon('phone')} Appeler</a>
          <a class="btn sm" target="_blank" rel="noopener" href="https://wa.me/${wa}?text=${encodeURIComponent('Bonjour ' + p.recipient + ', ORIENTAL24 : votre colis ' + p.tracking)}">${icon('chat')} WhatsApp</a>
          <a class="btn sm" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&travelmode=driving&destination=${encodeURIComponent(mapsAddr(p))}">${icon('pin')} Itinéraire</a>
          <a class="btn sm" target="_blank" rel="noopener" href="https://wa.me/${wa}?text=${encodeURIComponent('Bonjour ' + p.recipient + ', ORIENTAL24 : votre colis ' + p.tracking + ' — statut actuel : ' + p.status + '.')}">${icon('chat')} Notifier</a>
          <button class="btn primary sm" onclick="closeModal();daStatusPick(${p.id})">${icon('edit')} Changer le statut</button>
          <button class="btn sm" onclick="closeModal();daMsgSheet(${p.id})">${icon('bell')} Prévenir le client</button>
          <button class="btn sm" onclick="closeModal();parcelDetail(${p.id})">${icon('eye')} Fiche complète</button>
        </div></div></div>`, true);
  };
  window.openDaDrawer = () => { const d = document.getElementById('da-drawer'); if (d) { d.hidden = false; } };
  window.closeDrawer = () => { const d = document.getElementById('da-drawer'); if (d) d.hidden = true; };

  /* PWA : manifest + worker côté serveur uniquement (jamais dans la démo file://). */
  function ensurePwa() {
    if (typeof opsOffline !== 'undefined' && opsOffline) return;
    if (typeof navigator === 'undefined' || !('serviceWorker' in navigator)) return;
    if (typeof location !== 'undefined' && location.protocol === 'file:') return;
    if (!document.querySelector('link[rel="manifest"]')) {
      const l = document.createElement('link'); l.rel = 'manifest'; l.href = '/static/manifest-driver.json'; document.head.appendChild(l);
      const m = document.createElement('meta'); m.name = 'theme-color'; m.content = '#0b1526'; document.head.appendChild(m);
    }
    navigator.serviceWorker.register('/static/sw-driver.js').then((reg) => {
      reg.addEventListener('updatefound', () => {
        const w = reg.installing; if (!w) return;
        w.addEventListener('statechange', () => { if (w.state === 'installed' && navigator.serviceWorker.controller) daShowUpdate(reg); });
      });
      if (reg.waiting && navigator.serviceWorker.controller) daShowUpdate(reg);
    }).catch(() => {});
  }
  function daShowUpdate(reg) {
    const b = document.getElementById('da-update'); if (!b) return;
    b.hidden = false;
    b.onclick = () => { if (reg.waiting) reg.waiting.postMessage('skip'); };
  }
  if (typeof navigator !== 'undefined' && 'serviceWorker' in navigator) {
    navigator.serviceWorker.addEventListener('controllerchange', () => location.reload());
  }

  /* Branchements : vue dédiée + accueil par défaut du livreur sur petit écran. */
  const baseRenderView = renderView;
  renderView = async function () {
    if (APP_MODE && isDriver() && typeof view !== 'undefined' && (view === 'dashboard' || view === '')) view = VIEW;
    if (typeof view !== 'undefined' && view === VIEW) {
      if (!isDriver()) { view = 'dashboard'; return baseRenderView.apply(this, arguments); }
      document.getElementById('breadcrumb-title').textContent = titles[VIEW];
      try { await refresh(); } catch (e) {}
      render();
      return;
    }
    setAppShell(false);
    return baseRenderView.apply(this, arguments);
  };
  const baseEnterApp = enterApp;
  enterApp = async function () {
    await baseEnterApp.apply(this, arguments);
    if (isDriver() && smallScreen() && view === 'dashboard') navigate(VIEW);
  };
})();
/* v1.8.0 « Tour de contrôle » : transmission de la position du livreur.
   GPS du navigateur si disponible, sinon centre de la ville du colis en retard (démo terrain). */
window.daPos=(silent)=>{
  const send=(lat,lng,approx)=>{api('/driver/position','POST',{lat,lng}).then(()=>{if(!silent)toast(approx?'Position transmise (centre de ville — GPS indisponible).':'Position transmise ✓');}).catch((e)=>{if(!silent)toast(e.message||'Position refusée',true);});};
  const fallback=()=>{const p=S.parcels.find((x)=>x.status==='En livraison')||S.parcels.find((x)=>x.status==='Programmé')||S.parcels[0];
    const g=(typeof TOUR_GEO!=='undefined'&&p&&p.city)?TOUR_GEO[p.city]:null;
    if(!g){if(!silent)toast('Position GPS indisponible et ville inconnue.',true);return;}
    send(Math.round((g[0]+(Math.random()-0.5)*0.05)*10000)/10000,Math.round((g[1]+(Math.random()-0.5)*0.05)*10000)/10000,true);};
  if(!navigator.geolocation){fallback();return;}
  navigator.geolocation.getCurrentPosition((c)=>send(Math.round(c.coords.latitude*10000)/10000,Math.round(c.coords.longitude*10000)/10000,false),fallback,{timeout:4000,maximumAge:30000});
};
/* v1.8.1 « Messagerie guidée » : messages prêts à l'emploi au client (enregistrés + visibles sur le suivi public). */
const DA_MSGS=[['near','Je suis proche de votre adresse','📍'],['eta10','J’arrive dans environ 10 minutes','⏱️'],['patience','Merci de patienter, je suis en route','🛵']];
window.daMsgSheet=(id)=>{
  const p=S.parcels.find(x=>x.id===id);if(!p)return;
  modal('Prévenir le client',`<div class="full form-hint" style="margin-bottom:8px">${esc(p.tracking)} · ${esc(p.recipient)} — le message s’affiche sur son suivi et dans l’historique du colis.</div>
   <div class="da-sheet">${DA_MSGS.map(([code,label,emo])=>`<button type="button" class="da-sheet-row da-status-row" onclick="daMsgSend(${id},'${code}')">
     <span class="da-status-ic">${emo}</span><span class="da-status-label">${esc(label)}</span><b>${icon('chevron')}</b></button>`).join('')}</div>`);
};
window.daMsgSend=async(id,code)=>{
  const r=await api('/parcels/'+id+'/messages','POST',{code});
  closeModal();
  toast('Message envoyé au client : '+r.text);
  if(r.links&&r.links.whatsapp){
    modal('Message enregistré',`<p class="form-hint" style="margin-bottom:10px">Message au client : <b>${esc(r.text)}</b><br>Transmettez-le aussi par canal direct (l'appareil ouvre WhatsApp ou SMS) :</p>
     <div class="flex" style="gap:8px;flex-wrap:wrap">
      <a class="btn sm primary" target="_blank" rel="noopener" href="${r.links.whatsapp}">📲 WhatsApp</a>
      <a class="btn sm" target="_blank" rel="noopener" href="${r.links.sms}">✉️ SMS</a>
      <button class="btn sm" type="button" onclick="closeModal()">Fermer</button></div>`);
  }
};

/* v1.10.0 « Flotte connectée » : véhicule du livreur (usure prédictive, batterie, état, télémétrie). */
window.daVehicle=async()=>{
  let v,al;try{[v,al]=await Promise.all([api('/vehicles'),api('/vehicles/alerts')])}catch(e){toast(e.message||'Flotte indisponible',true);return}
  const r=(v.rows||[])[0];
  if(!r){modal('Mon véhicule',`<p class="muted">Aucun véhicule ne vous est affecté — l’administrateur déclare la flotte depuis le module Flotte &amp; relais.</p>`);return}
  const m=(v.maintenance||[]).find(x=>x.id===r.id)||{};
  const alerts=(al.alerts||[]).filter(a=>a.vehicle_id===r.id);
  modal('Mon véhicule connecté',`
   <p class="form-hint">${esc(r.label)} · ${esc(r.type_label||r.type)} ${r.plate?'· '+esc(r.plate):''} — état <b>${esc(r.state||'disponible')}</b> · CO₂ ${r.co2_per_km!=null?esc(String(r.co2_per_km)):'?'} kg/km</p>
   <div class="stats" style="grid-template-columns:1fr 1fr 1fr">
    ${stat('Compteur',String(Math.round(r.km||0)),'km','truck','navy')}
    ${stat('Batterie',r.battery_pct!=null?String(Math.round(r.battery_pct)):'—','%','box',(r.battery_pct||100)<20?'orange':'green')}
    ${stat('Usure',String(m.wear_score||0),'%','alert',(m.wear_score||0)>=80?'orange':'green')}</div>
   ${(m.reasons||[]).length?`<p style="color:#f59e0b;font-size:12px">⚠️ ${esc((m.reasons||[]).join(' · '))}</p>`:''}
   ${alerts.length?`<p style="color:#f87171;font-size:12px">🔔 ${alerts.map(a=>esc(a.text)).join(' · ')}</p>`:''}
   <div class="flex" style="gap:6px;flex-wrap:wrap;margin-top:8px">
    <button class="btn sm" type="button" onclick="daVState(${r.id},'disponible')">🟢 Disponible</button>
    <button class="btn sm primary" type="button" onclick="daVState(${r.id},'en_tournee')">🚚 En tournée</button>
    <button class="btn sm" type="button" onclick="daVState(${r.id},'maintenance')">🔧 Maintenance</button>
    <button class="btn sm" type="button" onclick="daVTelemetry(${r.id})">📡 Compteur / batterie</button></div>`,true);
};
window.daVState=async(id,st)=>{try{await api('/vehicles/'+id,'PATCH',{state:st});toast('État : '+st);closeModal();}catch(e){toast(e.message,true)}};
window.daVTelemetry=async(id)=>{
  const km=prompt('Kilométrage actuel :','0');if(km===null)return;
  const b=prompt('Batterie % (vide si N/A) :','');if(b===null)return;
  try{await api('/vehicles/'+id+'/telemetry','POST',{km:Number(km)||0,battery_pct:b===''?null:Number(b)});toast('Télémétrie envoyée ✓');closeModal();}
  catch(e){toast(e.message,true)}
};
