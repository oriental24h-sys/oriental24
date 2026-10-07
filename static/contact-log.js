/* v1.20.1 « Journal des contacts » — appels et messages WhatsApp du livreur dans la chronologie.

   Objectif : AUCUNE étape à répéter pour le livreur.
   • Il appuie sur « Appeler » : le composeur s'ouvre, une barre affiche le chrono.
   • Au retour dans l'application (ou sur « Terminer l'appel »), la trace part TOUTE SEULE dans la
     « Chronologie d'activité » du colis : « Livreur <nom> : appel au destinataire <qui> (<num>)
     · durée 1:23 ».
   • Un bandeau propose ensuite, en un seul geste : Sans réponse / Occupé / À rappeler /
     Modifier… / Supprimer — sans rien bloquer si le livreur ne touche à rien.
   • Chaque message WhatsApp préparé depuis le terrain est inscrit de la même façon :
     « Livreur <nom> : message WhatsApp au destinataire <qui> (<num>) : « texte » ».

   Aucune API payante : l'application ouvre le composeur (`tel:`) ou WhatsApp (`wa.me`). */
(function () {
  'use strict';
  var PEND = 'o24-cl-pend', QUEUE = 'o24-cl-queue';
  var barTimer = null, saving = false, toastTimer = null, edit = null;

  function lsGet(k, def) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : def; } catch (e) { return def; } }
  function lsSet(k, v) { try { v === null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch (e) { } }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function fmt(sec) { sec = Math.max(0, Math.round(Number(sec) || 0)); var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60; return (h ? h + ':' + pad(m) + ':' + pad(s) : m + ':' + pad(s)); }
  function hhmm(d) { d = d ? new Date(d) : new Date(); if (isNaN(d)) d = new Date(); return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  function iso(ts) { var d = new Date(ts), z = pad; return d.getFullYear() + '-' + z(d.getMonth() + 1) + '-' + z(d.getDate()) + 'T' + z(d.getHours()) + ':' + z(d.getMinutes()) + ':' + z(d.getSeconds()); }
  function me() { return (typeof S !== 'undefined' && S && S.user) ? S.user : (typeof localUser !== 'undefined' ? localUser : null); }
  function canLog() { var u = me(); return !!u && ['admin', 'livreur', 'agent'].indexOf(u.role) !== -1; }
  function toastMsg(t, bad) { if (typeof toast === 'function') { try { toast(t, !!bad); return; } catch (e) { } } (bad ? console.warn : console.log)(t); }
  function parcelOf(id) {
    try {
      if (typeof S !== 'undefined' && S && S.parcels) { var a = S.parcels.filter(function (p) { return p.id === id; })[0]; if (a) return a; }
      if (typeof localDemo !== 'undefined' && localDemo && localDemo.parcels) return localDemo.parcels.filter(function (p) { return p.id === id; })[0] || null;
    } catch (e) { }
    return null;
  }

  /* ---------- file d'attente hors connexion ---------- */
  function enqueue(payload) { var q = lsGet(QUEUE, []); q.push(payload); if (q.length > 50) q = q.slice(-50); lsSet(QUEUE, q); }
  function send(payload) {
    if (typeof api !== 'function') { enqueue(payload); return Promise.resolve(null); }
    return api('/parcels/' + payload.parcel_id + '/contact-log', 'POST', payload).catch(function (e) {
      var m = String(e && e.message || '');
      if (/réseau|reseau|serveur ne répond|Failed to fetch|NetworkError|Load failed|recharg/i.test(m)) { enqueue(payload); return null; }
      throw e;
    });
  }
  function flush() {
    var q = lsGet(QUEUE, []); if (!q.length || typeof api !== 'function') return Promise.resolve(0);
    var rest = [], done = 0;
    return q.reduce(function (chain, payload) {
      return chain.then(function () {
        return api('/parcels/' + payload.parcel_id + '/contact-log', 'POST', payload).then(function () { done++; }, function () { rest.push(payload); });
      });
    }, Promise.resolve()).then(function () {
      lsSet(QUEUE, rest);
      if (done) toastMsg(done + ' contact(s) transmis à la chronologie ✓');
      return done;
    });
  }
  window.o24ClFlush = flush;

  /* ---------- barre « appel en cours » ---------- */
  function bar() {
    var b = document.getElementById('o24-cl-bar');
    if (!b) {
      b = document.createElement('div');
      b.id = 'o24-cl-bar'; b.className = 'o24cl-bar'; b.hidden = true;
      b.innerHTML = '<span class="o24cl-dot"></span><div class="o24cl-txt"><b>Appel en cours</b><small id="o24-cl-live">0:00</small></div>' +
        '<button type="button" class="o24cl-stop" onclick="o24ClStop()">Terminer l\'appel</button>' +
        '<button type="button" class="o24cl-x" aria-label="Annuler le suivi de l\'appel" onclick="o24ClCancel()">✕</button>';
      document.body.appendChild(b);
    }
    return b;
  }
  function barShow(p) {
    var b = bar(); b.hidden = false;
    var who = b.querySelector('.o24cl-txt b');
    if (who) who.textContent = (p.recipient ? 'Appel · ' + p.recipient : 'Appel en cours');
    tick();
    if (!barTimer) barTimer = setInterval(tick, 1000);
  }
  function barHide() { var b = document.getElementById('o24-cl-bar'); if (b) b.hidden = true; if (barTimer) { clearInterval(barTimer); barTimer = null; } }
  function tick() {
    var p = lsGet(PEND, null), live = document.getElementById('o24-cl-live');
    if (!p || !live) return;
    live.textContent = fmt((Date.now() - p.t) / 1000) + ' · enregistrement automatique au retour';
  }

  /* ---------- bandeau d'action (correction en un geste, sans obligation) ---------- */
  function actionToast(seconds, traceId, note) {
    closeActionToast();
    var el = document.createElement('div');
    el.id = 'o24-cl-act'; el.className = 'o24cl-act';
    el.innerHTML = '<div class="o24cl-act-top"><span class="o24cl-ok">✓</span><div><b>Appel ' + fmt(seconds) +
      ' enregistré dans la chronologie</b><small id="o24-cl-act-note"></small></div></div>' +
      '<div class="o24cl-act-btns">' +
      '<button type="button" data-out="sans_reponse">☎ Sans réponse</button>' +
      '<button type="button" data-out="occupe">⏱ Occupé</button>' +
      '<button type="button" data-out="rappeler">↻ À rappeler</button>' +
      '<button type="button" data-edit="1">Modifier…</button>' +
      '<button type="button" class="o24cl-del" data-del="1">Supprimer</button>' +
      '<button type="button" class="o24cl-x" data-close="1" aria-label="Fermer">✕</button></div>';
    document.body.appendChild(el);
    var small = el.querySelector('#o24-cl-act-note');
    if (small) small.textContent = note || 'Livreur ' + ((me() || {}).name || '') + ' — durée mesurée automatiquement';
    el.addEventListener('click', function (ev) {
      var t = ev.target.closest ? ev.target.closest('button') : null;
      if (!t) return;
      if (t.dataset.close) { closeActionToast(); return; }
      if (t.dataset.out) { setOutcome(traceId, t.dataset.out, t); return; }
      if (t.dataset.del) { removeTrace(traceId); return; }
      if (t.dataset.edit) { closeActionToast(); openSheet(traceId, seconds); return; }
    });
    toastTimer = setTimeout(closeActionToast, 18000);
  }
  function closeActionToast() {
    if (toastTimer) { clearTimeout(toastTimer); toastTimer = null; }
    var el = document.getElementById('o24-cl-act');
    if (el) el.remove();
  }
  function setOutcome(traceId, outcome, btn) {
    var labels = { sans_reponse: 'sans réponse', occupe: 'occupé', rappeler: 'à rappeler' };
    if (!traceId) { toastMsg('Résultat non modifiable hors connexion pour l’instant.', true); return; }
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    (typeof api === 'function' ? api('/parcels/' + traceId.pid + '/contact-log/' + traceId.id, 'PATCH', { outcome: outcome })
      : Promise.resolve(o24ClOfflinePatch(traceId.pid, traceId.id, { outcome: outcome })))
      .then(function () {
        toastMsg('Appel marqué « ' + (labels[outcome] || outcome) + ' » ✓ chronologie à jour');
        closeActionToast();
        refreshOpenParcel(traceId.pid);
      })
      .catch(function (e) { toastMsg(e.message || 'Correction refusée', true); if (btn) { btn.disabled = false; btn.textContent = labels[outcome]; } });
  }
  function removeTrace(traceId) {
    if (!traceId) { closeActionToast(); return; }
    (typeof api === 'function' ? api('/parcels/' + traceId.pid + '/contact-log/' + traceId.id, 'DELETE')
      : Promise.resolve(o24ClOfflineDel(traceId.pid, traceId.id)))
      .then(function () { toastMsg('Trace supprimée'); closeActionToast(); refreshOpenParcel(traceId.pid); })
      .catch(function (e) { toastMsg(e.message || 'Suppression refusée', true); });
  }

  /* ---------- enregistrement automatique de l'appel ---------- */
  function autoSave(p, force) {
    var seconds = Math.max(0, Math.round((Date.now() - p.t) / 1000));
    if (seconds > 4 * 3600) { lsSet(PEND, null); barHide(); toastMsg('Suivi d’appel expiré (4 h) — aucun enregistrement.', true); return; }
    if (!force && seconds < 5) { barShow(p); return; }        // < 5 s : simple sortie de l'application
    if (saving) return;
    saving = true;
    lsSet(PEND, null); barHide();
    var payload = { parcel_id: p.id, kind: 'appel', phone: p.phone || '', recipient: p.recipient || '',
      duration_s: seconds, outcome: 'abouti', started_at: iso(p.t) };
    send(payload).then(function (r) {
      saving = false;
      var traceId = r && r.id ? { pid: p.id, id: r.id } : null;
      if (!r) {
        toastMsg('Appel ' + fmt(seconds) + ' enregistré hors connexion · transmis dès le retour du réseau.');
        return;
      }
      actionToast(seconds, traceId, (r.note || ''));
      refreshOpenParcel(p.id);
    }).catch(function (e) { saving = false; toastMsg(e.message || 'Enregistrement impossible', true); });
  }

  window.o24ClCall = function (el) {                       // clic sur « Appeler »
    try {
      if (!el || !canLog()) return true;
      var id = Number(el.dataset.clId || 0); if (!id) return true;
      var p = parcelOf(id) || {};
      var pend = { id: id, t: Date.now(), phone: el.dataset.clPhone || p.phone || '', recipient: el.dataset.clName || p.recipient || '' };
      lsSet(PEND, pend); barShow(pend);
    } catch (e) { }
    return true;
  };
  window.o24ClStop = function () {                          // « Terminer l'appel » : enregistre tout de suite
    var p = lsGet(PEND, null);
    if (!p) { barHide(); return; }
    autoSave(p, true);
  };
  window.o24ClCancel = function () { lsSet(PEND, null); barHide(); toastMsg('Suivi d\'appel annulé — aucune trace'); };
  window.o24ClReturn = function () {                        // retour du composeur dans l'application
    var p = lsGet(PEND, null); if (!p || saving) return;
    autoSave(p, false);
  };

  /* ---------- feuille de correction (facultative) ---------- */
  function openSheet(traceId, seconds) {
    var pid = traceId ? traceId.pid : 0;
    edit = traceId ? { pid: pid, id: traceId.id } : null;
    var p = parcelOf(pid) || {};
    var html = '<div class="o24cl">' +
      '<p class="o24cl-who">' + (p.recipient ? String(p.recipient) : 'Destinataire') + (p.phone ? ' · ' + String(p.phone) : '') + '</p>' +
      '<p class="o24cl-hint">La trace est déjà dans la chronologie du colis. Corrigez la durée ou le résultat si besoin — enregistrement immédiat.</p>' +
      '<div class="o24cl-dur"><label for="o24-cl-dur">Durée de l\'appel</label>' +
      '<input id="o24-cl-dur" value="' + fmt(seconds || 0) + '" inputmode="numeric" autocomplete="off">' +
      '<div class="o24cl-quick"><button type="button" data-off="-15">−15 s</button><button type="button" data-off="15">+15 s</button></div></div>' +
      '<div class="o24cl-chips" id="o24-cl-out">' + chips('abouti') + '</div>' +
      '<div class="o24cl-acts"><button type="button" class="btn primary" onclick="o24ClSave()">Enregistrer la correction</button>' +
      '<button type="button" class="btn" onclick="o24ClDrop()">Fermer</button></div>' +
      '<p class="o24cl-foot">La chronologie affiche : date, heure, durée et résultat de l\'appel.</p></div>';
    if (typeof modal === 'function') { try { modal('Corriger l\'appel', html); afterSheet(); return; } catch (e) { } }
    var root = document.getElementById('modal-root') || document.body;
    root.innerHTML = '<div class="modal-backdrop" onclick="if(event.target===this)o24ClDrop()"><div class="modal o24cl-modal"><div class="modal-body">' + html + '</div></div></div>';
    afterSheet();
  }
  function chips(sel) {
    var list = [['abouti', '✓ Appel abouti'], ['sans_reponse', '☎ Sans réponse'], ['occupe', '⏱ Occupé'], ['rappeler', '↻ À rappeler'], ['annule', '✕ Annulé']];
    return list.map(function (o) { return '<button type="button" class="o24cl-chip' + (o[0] === sel ? ' on' : '') + '" data-o="' + o[0] + '">' + o[1] + '</button>'; }).join('');
  }
  function afterSheet() {
    var box = document.getElementById('o24-cl-out');
    if (box) box.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('.o24cl-chip') : null; if (!b) return;
      [].forEach.call(box.querySelectorAll('.o24cl-chip'), function (x) { x.classList.remove('on'); });
      b.classList.add('on');
    });
    [].forEach.call(document.querySelectorAll('.o24cl-quick button'), function (b) {
      b.addEventListener('click', function () {
        var inp = document.getElementById('o24-cl-dur'); if (!inp) return;
        var cur = parseDur(inp.value); if (cur === null) cur = 0;
        inp.value = fmt(Math.max(0, cur + Number(b.dataset.off)));
      });
    });
  }
  function parseDur(v) {
    var t = String(v || '').trim().replace(',', '.').replace(/\s/g, '');
    var m = /^(\d+):([0-5]?\d)$/.exec(t); if (m) return Number(m[1]) * 60 + Number(m[2]);
    m = /^(\d+)(?:min|m)?(?:([0-5]?\d)(?:s|sec)?)?$/.exec(t);
    if (m) return Number(m[1]) * 60 + (m[2] ? Number(m[2]) : 0);
    return null;
  }
  function closeSheet() {
    edit = null;
    if (typeof closeModal === 'function') { try { closeModal(); return; } catch (e) { } }
    var root = document.getElementById('modal-root'); if (root) root.innerHTML = '';
  }
  window.o24ClDrop = function () { closeSheet(); };
  window.o24ClSave = function () {
    if (!edit) { closeSheet(); return; }
    var inp = document.getElementById('o24-cl-dur');
    var seconds = parseDur(inp ? inp.value : '');
    if (seconds === null || seconds < 0 || seconds > 14400) { toastMsg('Durée illisible : saisissez par exemple 1:23 ou 83.', true); return; }
    var on = document.querySelector('#o24-cl-out .o24cl-chip.on');
    var body = { duration_s: seconds, outcome: on ? on.dataset.o : 'abouti' };
    var pid = edit.pid, tid = edit.id;
    closeSheet();
    (typeof api === 'function' ? api('/parcels/' + pid + '/contact-log/' + tid, 'PATCH', body)
      : Promise.resolve(o24ClOfflinePatch(pid, tid, body)))
      .then(function (r) {
        toastMsg('Appel corrigé : ' + fmt(seconds) + (body.outcome === 'abouti' ? '' : ' · ' + body.outcome.replace('_', ' ')) + ' ✓');
        refreshOpenParcel(pid);
      })
      .catch(function (e) { toastMsg(e.message || 'Correction refusée', true); });
  };

  /* ---------- WhatsApp ---------- */
  window.o24ClWa = function (el) {                           // clic sur un bouton WhatsApp
    try {
      if (!el || !canLog()) return true;
      var id = Number(el.dataset.clId || 0); if (!id) return true;
      var p = parcelOf(id) || {};
      var payload = { parcel_id: id, kind: 'whatsapp', phone: el.dataset.clPhone || p.phone || '',
        recipient: el.dataset.clName || p.recipient || '', message: el.dataset.clMsg || '' };
      send(payload).then(function (r) {
        if (!r) { toastMsg('Message WhatsApp enregistré hors connexion · transmis dès le retour du réseau.'); return; }
        toastMsg('WhatsApp ' + hhmm(r.created_at || Date.now()) + ' ✓ inscrit dans la chronologie');
        refreshOpenParcel(id);
      }).catch(function (e) { toastMsg(e.message || 'Enregistrement impossible', true); });
    } catch (e) { }
    return true;
  };
  window.o24ClWaFor = function (id, mode) {
    var p = parcelOf(id); if (!p) return true;
    var txt = 'Bonjour ' + p.recipient + ', ORIENTAL24 : votre colis ' + p.tracking + (mode === 'notify' ? ' — statut actuel : ' + p.status + '.' : '');
    return window.o24ClWa({ dataset: { clId: String(id), clPhone: p.phone || '', clName: p.recipient || '', clMsg: txt } });
  };
  window.parcelWaButton = function (p, label) {
    try {
      if (!p || !p.phone || !canLog()) return '';
      var num = String(p.phone).replace(/[^\d]/g, '');
      if (!num) return '';
      var wa = num.indexOf('212') === 0 ? num : '212' + num.replace(/^0/, '');
      var msg = 'Bonjour ' + p.recipient + ', ORIENTAL24 : votre colis ' + p.tracking;
      return '<a class="btn sm" style="margin-left:8px" target="_blank" rel="noopener" href="https://wa.me/' + wa + '?text=' +
        encodeURIComponent(msg) + '" data-cl-id="' + p.id + '" data-cl-phone="' + esc(p.phone) + '" data-cl-name="' + esc(p.recipient) +
        '" data-cl-msg="' + esc(msg) + '" onclick="return o24ClWa(this)">' + icon('chat') + (label || 'WhatsApp') + '</a>';
    } catch (e) { return ''; }
  };
  function refreshOpenParcel(id) {
    try {
      if (typeof parcelDetail === 'function' && window.__o24ClOpen === id) parcelDetail(id);
    } catch (e) { }
  }
  window.__o24ClOpen = null;

  /* ---------- miroir démo (HTML hors serveur) ---------- */
  function offlineNote(kind, actor, d, dur, res) {
    var who = (d.recipient ? 'destinataire ' + String(d.recipient).slice(0, 80) : 'destinataire') +
      (d.phone ? ' (' + String(d.phone).slice(0, 25) + ')' : '');
    var lead = actor ? 'Livreur ' + actor + ' : ' : '';
    if (kind === 'whatsapp') {
      var m = String(d.message || '').slice(0, 300);
      return lead + 'message WhatsApp au ' + who + (m ? ' : « ' + m + ' »' : '');
    }
    return lead + 'appel au ' + who + (res ? ' · ' + res + (dur ? ' (' + fmt(dur) + ')' : '') : (dur ? ' · durée ' + fmt(dur) : ' · durée non mesurée'));
  }
  function offlineEvent(id, u, kind, note, t) {
    localDemo.events = localDemo.events || [];
    var evId = localDemo.events.reduce(function (mx, e) { return Math.max(mx, Number(e.id) || 0); }, 0) + 1;
    localDemo.events.unshift({ id: evId, parcel_id: id, actor_id: u.id, status: (kind === 'appel' ? 'Appel client' : 'WhatsApp client'),
      note: note, created_at: t, actor: u.name });
    return evId;
  }
  window.o24ClOffline = function (id, d, u) {
    if (typeof localDemo === 'undefined' || !localDemo || !localDemo.parcels) throw new Error('Démo indisponible.');
    var p = (localDemo.parcels.filter(function (x) { return x.id === id; })[0]) || null;
    if (!p) throw new Error('Colis introuvable.');
    if (!u || ['admin', 'livreur', 'agent'].indexOf(u.role) === -1) throw new Error('Accès non autorisé.');
    var kind = String(d.kind || '').toLowerCase();
    if (kind !== 'appel' && kind !== 'whatsapp') throw new Error('Type de contact invalide : « appel » ou « whatsapp » attendu.');
    var dur = (d.duration_s === null || d.duration_s === undefined || d.duration_s === '') ? null : Math.round(Number(d.duration_s));
    if (dur !== null && (!isFinite(dur) || dur < 0 || dur > 14400)) throw new Error('Durée d\'appel invalide.');
    var res = { abouti: '', sans_reponse: 'sans réponse', occupe: 'occupé', rappeler: 'à rappeler', annule: 'appel annulé' }[String(d.outcome || 'abouti')] || '';
    var t = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(String(d.started_at || '')) ? d.started_at : iso(Date.now());
    var note = offlineNote(kind, u.name, d, dur, res);
    localDemo.contact_logs = localDemo.contact_logs || [];
    var evId = offlineEvent(id, u, kind, note, t);
    var rowId = localDemo.contact_logs.reduce(function (mx, r) { return Math.max(mx, Number(r.id) || 0); }, 0) + 1;
    localDemo.contact_logs.unshift({ id: rowId, parcel_id: id, actor_id: u.id, kind: kind, phone: String(d.phone || '').slice(0, 25),
      recipient: String(d.recipient || '').slice(0, 80), duration_s: dur, outcome: String(d.outcome || 'abouti'),
      message: String(d.message || '').slice(0, 300), created_at: t, event_id: evId });
    return { ok: true, id: rowId, event_id: evId, status: (kind === 'appel' ? 'Appel client' : 'WhatsApp client'), note: note,
      created_at: t, duration_s: dur, duration_label: (dur === null ? '' : fmt(dur)) };
  };
  window.o24ClOfflinePatch = function (id, cid, d) {
    var u = me(), row = (localDemo.contact_logs || []).filter(function (r) { return r.id === Number(cid) && r.parcel_id === id; })[0];
    if (!row) throw new Error('Trace introuvable.');
    if (u && u.role !== 'admin' && row.actor_id !== u.id) throw new Error('Seul l’auteur ou un administrateur peut modifier cette trace.');
    if ('duration_s' in d) {
      var dur = (d.duration_s === null || d.duration_s === '') ? null : Math.round(Number(d.duration_s));
      if (dur !== null && (!isFinite(dur) || dur < 0 || dur > 14400)) throw new Error('Durée d\'appel invalide.');
      row.duration_s = dur;
    }
    if ('outcome' in d) row.outcome = String(d.outcome);
    if ('message' in d) row.message = String(d.message || '').slice(0, 300);
    var res = { abouti: '', sans_reponse: 'sans réponse', occupe: 'occupé', rappeler: 'à rappeler', annule: 'appel annulé' }[row.outcome] || '';
    var actor = (localDemo.users.filter(function (x) { return x.id === row.actor_id; })[0] || {}).name || '';
    var note = offlineNote(row.kind, actor, { recipient: row.recipient, phone: row.phone, message: row.message }, row.duration_s, res);
    var ev = (localDemo.events || []).filter(function (e) { return e.id === row.event_id; })[0];
    if (ev) ev.note = note;
    return { ok: true, id: row.id, note: note, duration_s: row.duration_s, outcome: row.outcome,
      duration_label: row.duration_s === null ? '' : fmt(row.duration_s) };
  };
  window.o24ClOfflineDel = function (id, cid) {
    var u = me(), row = (localDemo.contact_logs || []).filter(function (r) { return r.id === Number(cid) && r.parcel_id === id; })[0];
    if (!row) throw new Error('Trace introuvable.');
    if (u && u.role !== 'admin' && row.actor_id !== u.id) throw new Error('Seul l’auteur ou un administrateur peut supprimer cette trace.');
    localDemo.contact_logs = localDemo.contact_logs.filter(function (r) { return r.id !== Number(cid); });
    localDemo.events = (localDemo.events || []).filter(function (e) { return e.id !== row.event_id; });
    return { ok: true, deleted: Number(cid) };
  };
  window.o24ClOfflineRoute = function (url, method, d) {
    var parts = new URL(url, 'https://local.test').pathname.split('/').filter(Boolean);
    var id = Number(parts[1]), nid = Number(parts[3]);
    if (method === 'POST') return o24ClOffline(id, d, me());
    if (method === 'PATCH') return o24ClOfflinePatch(id, nid, d);
    if (method === 'DELETE') return o24ClOfflineDel(id, nid);
    return {};
  };

  /* ---------- démarrage ---------- */
  function boot() {
    var p = lsGet(PEND, null);
    if (p) {
      var s = Math.round((Date.now() - p.t) / 1000);
      if (s > 4 * 3600) lsSet(PEND, null);
      else if (s >= 5) window.o24ClReturn();
      else barShow(p);
    }
    if (typeof api === 'function') {
      setTimeout(flush, 6000);
      window.addEventListener('online', function () { flush(); });
    }
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) window.o24ClReturn(); });
  window.addEventListener('focus', function () { window.o24ClReturn(); });
  window.addEventListener('pageshow', function () { window.o24ClReturn(); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
  var _pd = window.parcelDetail;
  if (typeof _pd === 'function') {
    window.parcelDetail = function (id) { window.__o24ClOpen = id; return _pd.apply(this, arguments); };
  }
})();
