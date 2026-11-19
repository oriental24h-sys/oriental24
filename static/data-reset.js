/* Remise à zéro des données — réservé à l'Administrateur.
   Deux verrous côté client (phrase exacte + mot de passe), trois côté serveur.
   Aucune sauvegarde : la décision est explicite, la confirmation est donc
   volontairement lente et l'écran affiche les compteurs avant/après. */
let drState = null;

function drRows(block) {
  if (!block) return '';
  return Object.entries(block)
    .map(([key, info]) => {
      const n = Number(info.rows || 0);
      return `<tr class="${n ? '' : 'sub'}"><td>${esc(info.label || key)}</td><td class="mono" style="text-align:right">${n}</td></tr>`;
    })
    .join('');
}

async function drLoad(force) {
  if (drState && !force) return drState;
  drState = await api('/admin/data-reset');
  return drState;
}

async function dataResetView() {
  const d = await drLoad(true);
  const total = Object.values(d.before || {}).reduce((n, x) => n + Number(x.rows || 0), 0);
  return (
    heading(
      'Remise à zéro',
      'Vider les commandes, les bons d’envoi et de réception, les factures et toute la finance.',
      `<button class="btn" onclick="dataResetRefresh()">${icon('refresh')}Actualiser les compteurs</button>`,
    ) +
    `<div class="card" style="border-color:var(--red,#b3261e)">
      <div class="flex" style="align-items:flex-start;gap:18px;flex-wrap:wrap">
        <span class="stat-icon" style="background:#fdecea;color:#b3261e">${icon('alert')}</span>
        <div style="flex:1;min-width:260px">
          <h3>Opération irréversible — aucune sauvegarde automatique</h3>
          <p class="sub">Toutes les commandes (CMD), palettes, bons d’envoi et de réception, factures, relevés,
          mouvements de caisse, scans, retours et historiques seront supprimés. Les Hubs, villes, tarifs,
          motifs et paramètres sont conservés.</p>
          <p class="sub"><b>${d.tables}</b> tables seront vidées · <b>${total}</b> lignes métier actuellement.
          ${d.demo ? 'Mode démonstration : le jeu de démonstration peut être réinjecté juste après.'
                   : (d.armed ? 'Déploiement armé (ORIENTAL24_ALLOW_DATA_RESET=1).'
                              : 'Production : ajoutez ORIENTAL24_ALLOW_DATA_RESET=1 sur Railway avant de lancer.')}</p>
        </div>
      </div>
      <div class="flex" style="gap:12px;margin-top:16px;flex-wrap:wrap">
        <button class="btn" onclick="dataResetOpen(false)">Vider les données métier</button>
        <button class="btn" style="border-color:#b3261e;color:#b3261e" onclick="dataResetOpen(true)">Tout vider (comptes clients &amp; livreurs inclus)</button>
      </div>
    </div>
    <div class="card">
      <h3>Compteurs actuels</h3>
      <div class="grid-2" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px">
        <table class="table"><tbody>${drRows(d.before)}</tbody></table>
        <div>
          <h4 style="margin-top:0">Conservé après l’opération</h4>
          <p class="sub">${esc((d.kept || []).join(' · '))}</p>
          <h4>Après la remise à zéro</h4>
          <p class="sub">Les commandes, bons, factures et lignes financières repartent de zéro. Les compteurs du
          menu se recalculent au rechargement. Si un fichier SQLite existe déjà côté serveur, redémarrez le
          service pour repartir d’un état propre en mémoire.</p>
        </div>
      </div>
    </div>`
  );
}

async function dataResetRefresh() {
  drState = null;
  await renderView();
  toast('Compteurs actualisés');
}

async function dataResetOpen(wipeAccounts) {
  let d;
  try {
    d = await drLoad(true);
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const intro = wipeAccounts
    ? 'Tous les comptes sauf l’administrateur seront supprimés, ainsi que leurs barèmes et profils. Hubs, villes et tarifs restent.'
    : 'Les comptes (clients, livreurs, responsables de Hub, supports) sont conservés.';
  modal(
    wipeAccounts ? 'Tout vider (comptes inclus)' : 'Vider les données métier',
    form(
      `<div class="full form-hint" style="border-left:4px solid #b3261e;padding-left:12px"><b>Action définitive, sans sauvegarde.</b> ${intro}</div>
       ${input('phrase', 'Tapez exactement REMETTRE A ZERO', '', 'text', true, 'autocomplete="off" spellcheck="false"')}
       ${input('password', 'Votre mot de passe administrateur', '', 'password', true, 'autocomplete="current-password"')}
       ${d.demo ? `<label class="full flex" style="gap:8px;align-items:center"><input type="checkbox" name="reseed" style="width:auto"> Réinjecter le jeu de démonstration juste après</label>` : ''}`,
      'Confirmer la remise à zéro',
    ).replace('<button type="submit" class="btn primary">', '<button type="submit" class="btn primary" style="background:#b3261e;border-color:#b3261e">'),
  );
  bindForm(async (payload) => {
    const body = {
      confirmation: payload.phrase,
      password: payload.password,
      keep_accounts: !wipeAccounts,
      reseed_demo: d.demo ? !!payload.reseed : false,
    };
    const report = await api('/admin/data-reset', 'POST', body);
    closeModal();
    toast(report.message || 'Remise à zéro terminée');
    drState = null;
    globalSearchVersion++;
    await refresh();
    navigate('data-reset');
  });
}
