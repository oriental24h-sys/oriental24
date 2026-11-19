/* Remise à zéro des données — réservé à l'Administrateur.
   Deux verrous côté client (phrase exacte + mot de passe), trois côté serveur.
   Aucune sauvegarde : la décision est explicite, la confirmation est donc
   volontairement lente et l'écran affiche les compteurs avant/après. */
let drState = null;

/* Comparaison tolérante : casse, accents et espaces multiples ignorés.
   « remettre à zéro » = « REMETTRE A ZERO ». */
function drPhraseKey(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[\s\u00a0]+/g, ' ')
    .trim()
    .toUpperCase();
}
const DR_PHRASE = 'REMETTRE A ZERO';

/* Vide la zone de confirmation (utilisée aussi après une erreur du serveur). */
function boxSafeClear() {
  const box = document.getElementById('dr-phrase');
  if (!box) return;
  box.textContent = '';
  box.focus({ preventScroll: true });
}

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
    (d.deployment ? `<div class="card" style="border-color:#e9edf3">
      <div class="flex" style="gap:10px;align-items:center;flex-wrap:wrap;font-size:13px">
        <span class="badge" style="background:${d.deployment.mode === 'production' ? '#e8f0fe;color:#1a4fa0' : '#fff4e5;color:#8a4b00'}">
          ${d.deployment.mode === 'production' ? 'Production' : 'Demonstration'}</span>
        <span class="sub">Base : <b>${esc(d.deployment.database)}</b></span>
        <span class="sub">Interrupteur ORIENTAL24_ALLOW_DATA_RESET : <b>${d.deployment.allowed ? 'ouvert' : 'ferme'}</b></span>
      </div>
    </div>` : '') +
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
                   : (d.armed ? 'Deploiement arme : la remise a zero peut s’executer.'
                              : 'Production : ORIENTAL24_ALLOW_DATA_RESET=1 n’est pas lue par ce service.')}</p>
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
  /* Zone de confirmation en `contenteditable` : un navigateur ne peut pas la
     pré-remplir (ni e-mail, ni téléphone, ni adresse enregistrée). C'est le seul
     moyen fiable — `autocomplete="off"` est ignoré par Chrome/Safari dès qu'un
     champ mot de passe voisin existe. */
  const phraseBox = `<div class="field full">
    <label id="dr-phrase-label" for="dr-phrase">Tapez exactement ${DR_PHRASE} *</label>
    <div id="dr-phrase" class="dr-phrase-input" contenteditable="true" role="textbox" tabindex="0"
         aria-labelledby="dr-phrase-label" aria-multiline="false" autocapitalize="characters"
         autocorrect="off" spellcheck="false" data-gramm="false" data-lpignore="true"
         data-1p-ignore data-form-type="other" translate="no"></div>
    <p class="form-hint" id="dr-phrase-help" aria-live="polite">La casse, les accents et les espaces multiples sont ignorés : « remettre a zero » fonctionne aussi.</p>
  </div>`;
  const pwField = `<div class="field full"><label for="f-password">Votre mot de passe administrateur *</label>
    <input id="f-password" name="password" type="password" value="" required autocomplete="current-password"
           data-lpignore="true" data-1p-ignore data-form-type="other"></div>`;
  modal(
    wipeAccounts ? 'Tout vider (comptes inclus)' : 'Vider les données métier',
    form(
      `<div class="full form-hint" style="border-left:4px solid #b3261e;padding-left:12px"><b>Action définitive, sans sauvegarde.</b> ${intro}</div>
       ${phraseBox}
       ${pwField}
       ${d.demo ? `<label class="full flex" style="gap:8px;align-items:center"><input type="checkbox" name="reseed" style="width:auto"> Réinjecter le jeu de démonstration juste après</label>` : ''}`,
      'Confirmer la remise à zéro',
    ).replace('<button type="submit" class="btn primary">', '<button type="submit" class="btn primary" style="background:#b3261e;border-color:#b3261e">'),
  );
  // Style de la zone : même apparence qu'un champ, mais sans autofill possible.
  let scrubLater = () => {};   // rempli plus bas, utilisé par l'écouteur focus
  const box = document.getElementById('dr-phrase');
  if (box) {
    box.style.cssText = 'width:100%;min-height:42px;padding:11px 14px;border:1px solid var(--line,#e9edf3);' +
      'border-radius:8px;background:#fff;font:inherit;letter-spacing:.02em;line-height:1.4;white-space:pre-wrap;' +
      'overflow-wrap:anywhere;outline:none;cursor:text';
    box.textContent = '';
    box.addEventListener('focus', () => {
      box.style.borderColor = 'var(--orange,#ff7618)';
      if (!box.textContent.trim()) scrubLater();
    });
    box.addEventListener('blur', () => { box.style.borderColor = 'var(--line,#e9edf3)'; });
    // Entrée valide directement (pas de retour à la ligne dans une phrase de contrôle).
    box.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const submit = document.querySelector('#modal-form [type=submit]');
        if (submit && !submit.disabled) document.getElementById('modal-form').requestSubmit();
      }
    });
    // Le collage peut amener du HTML (gras, liens) : on force le texte brut.
    box.addEventListener('paste', (e) => {
      e.preventDefault();
      const text = (e.clipboardData || window.clipboardData).getData('text');
      document.execCommand('insertText', false, String(text).replace(/[\r\n]+/g, ' '));
    });
  }
  const phraseInput = document.getElementById('dr-phrase');
  const pwInput = document.getElementById('f-password');
  const submit = document.querySelector('#modal-form [type=submit]');
  /* Le bouton n'est JAMAIS désactivé : un bouton grisé qui « ne fait rien » est
     incompréhensible. Il reste cliquable et c'est le message d'erreur qui guide. */
  const sync = () => {
    const current = drPhraseKey(phraseInput.textContent);
    const ok = current === DR_PHRASE;
    if (submit) {
      submit.disabled = false;
      submit.removeAttribute('aria-disabled');
      submit.style.opacity = ok ? '' : '0.82';
    }
    const help = document.getElementById('dr-phrase-help');
    if (help) {
      help.className = ok ? 'form-hint green' : 'form-hint';
      help.textContent = ok
        ? '✓ Phrase reconnue — cliquez sur « Confirmer la remise à zéro ».'
        : 'Tapez les trois mots (la casse, les accents et les espaces multiples sont ignorés).';
    }
  };
  // Un remplissage automatique a pu glisser un e-mail ou un téléphone dans la
  // zone malgré `contenteditable` : on la vide immédiatement, sans rien demander.
  const scrub = () => {
    const value = String(box.textContent || '');
    if (value.includes('@') || /^[+\d][\d\s().-]{4,}$/.test(value.trim())) {
      box.textContent = '';
      box.dispatchEvent(new Event('input', { bubbles: true }));
      const help = document.getElementById('dr-phrase-help');
      if (help) {
        help.className = 'form-hint';
        help.textContent = 'Champ vidé automatiquement : un e-mail ou un numéro y avait été inséré. ' +
          'Tapez « ' + DR_PHRASE + ' ».';
      }
      return true;
    }
    return false;
  };
  scrubLater = scrub;
  if (box && submit) {
    // Plusieurs passes : certains navigateurs remplissent après le rendu.
    [0, 60, 220, 600, 1200].forEach((delay) => setTimeout(() => { if (box.isConnected) scrub(); }, delay));
  }
  if (phraseInput && submit) {
    phraseInput.addEventListener('input', sync);
    pwInput.addEventListener('input', sync);
    sync();
    phraseInput.focus({ preventScroll: true });
  }
  bindForm(async (payload) => {
    const typed = String(document.getElementById('dr-phrase')?.textContent || '').trim();
    if (typed.includes('@') || /^[+\d][\d\s().-]{5,}$/.test(typed)) {
      boxSafeClear();
      throw new Error('La zone contenait une adresse e-mail ou un numéro de téléphone : elle a été vidée. ' +
                      'Tapez « ' + DR_PHRASE + ' » puis confirmez.');
    }
    if (drPhraseKey(typed) !== DR_PHRASE) {
      throw new Error('La phrase ne correspond pas. Tapez exactement « ' + DR_PHRASE + ' ».');
    }
    const body = {
      confirmation: typed,
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
