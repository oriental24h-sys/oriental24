/* Le bouton « Confirmer la remise à zéro » doit VRAIMENT soumettre.
   Simule le DOM réel (jsdom) : modal, zone contenteditable, mot de passe, clic.
   Trois scénarios reproduits depuis les captures de l'utilisateur :
   - autofill e-mail, autofill téléphone → zone vidée automatiquement ;
   - bouton toujours cliquable (jamais `disabled`), même phrase vide ;
   - phrase correcte + mot de passe → appel POST /admin/data-reset. */
const fs = require('node:fs');
const assert = require('node:assert/strict');
let JSDOM = null;
try { ({ JSDOM } = require('jsdom')); } catch (e) {
  console.log('jsdom absent : test DOM sauté (npm install jsdom pour l’exécuter)');
  process.exit(0);
}

const source = fs.readFileSync('static/data-reset.js', 'utf8');

async function boot() {
  const dom = new JSDOM('<!doctype html><html><body><div id="modal-root"></div></body></html>', {
    url: 'https://oriental24.test/',
    runScripts: 'outside-only',
    pretendToBeVisual: true,
  });
  const w = dom.window;
  const calls = [];
  // Doublures minimales de l'application.
  w.esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  w.icon = () => '<svg></svg>';
  w.heading = (t, s, a = '') => `<div><h1>${t}</h1>${a}</div>`;
  // `drLoad` fait un GET d'aperçu : on ne compte que les POST de confirmation.
  w.api = async (url, method, body) => {
    calls.push({ url, method, body });
    return method === 'POST'
      ? { message: 'ok', leftovers: {} }
      : { before: {}, tables: 0, kept: [], demo: false, armed: false, phrase: 'REMETTRE A ZERO' };
  };
  const posts = () => calls.filter((c) => c.method === 'POST');
  w.toast = () => {};
  w.closeModal = () => { w.document.getElementById('modal-root').innerHTML = ''; };
  w.refresh = async () => {};
  w.navigate = () => {};
  w.renderView = async () => {};
  w.globalSearchVersion = 0;
  w.drState = null;
  w.modal = (title, body) => {
    w.document.getElementById('modal-root').innerHTML =
      `<div class="modal-backdrop"><section class="modal"><div class="modal-header"><h2>${title}</h2></div>` +
      `<div class="modal-body">${body}</div></section></div>`;
  };
  w.form = (body, label = 'Enregistrer') =>
    `<form id="modal-form"><div class="form-error" role="alert"></div><div class="form-grid">${body}</div>` +
    `<div class="form-actions"><button type="button">Annuler</button>` +
    `<button class="btn primary" type="submit">${label}</button></div></form>`;
  w.input = (name, label, value = '', type = 'text', required = true, extra = '') =>
    `<div class="field"><label>${label}</label><input id="f-${name}" name="${name}" type="${type}" value="${value}" ${extra}></div>`;
  // Copie fidèle de bindForm() de l'application : l'erreur est écrite dans
  // `.form-error` et le bouton est réactivé.
  w.bindForm = (handler, id = 'modal-form') => {
    const f = w.document.getElementById(id);
    f.onsubmit = async (e) => {
      e.preventDefault();
      const b = f.querySelector('[type=submit]');
      if (b) b.disabled = true;
      const err = f.querySelector('.form-error');
      if (err) err.style.display = 'none';
      try {
        const data = Object.fromEntries(new w.FormData(f));
        for (const x of f.querySelectorAll('[type=checkbox]')) data[x.name] = x.checked;
        await handler(data);
      } catch (error) {
        if (err) { err.textContent = error.message; err.style.display = 'block'; }
        else w.toast(error.message, true);
      } finally {
        if (b) b.disabled = false;
      }
    };
  };
  w.eval(source);
  return { dom, w, calls };
}

(async () => {
  // ---------- 1) autofill e-mail : la zone est vidée automatiquement ----------
  {
    const { w } = await boot();
    await w.dataResetOpen(false);
    const box = w.document.getElementById('dr-phrase');
    assert(box, 'zone de confirmation absente');
    assert.equal(box.getAttribute('contenteditable'), 'true', 'la zone doit être contenteditable');
    assert.equal(w.document.querySelector('#modal-form input[name="phrase"]'), null, 'aucun input autofillable ne doit exister');
    box.textContent = 'oriental24h@gmail.com';
    box.dispatchEvent(new w.Event('input', { bubbles: true }));
    // le bouton reste cliquable
    const submit = w.document.querySelector('#modal-form [type=submit]');
    assert.equal(submit.disabled, false, 'le bouton ne doit jamais être désactivé');
    // nettoyage programmé
    await new Promise((r) => setTimeout(r, 80));
    assert.equal(String(box.textContent).trim(), '', 'un e-mail dans la zone doit être effacé automatiquement');
    assert(/vidé automatiquement/i.test(w.document.getElementById('dr-phrase-help').textContent),
      'le motif du nettoyage doit être affiché');
  }

  // ---------- 2) autofill téléphone ----------
  {
    const { w } = await boot();
    await w.dataResetOpen(true);
    const box = w.document.getElementById('dr-phrase');
    box.textContent = '063961804';
    box.dispatchEvent(new w.Event('input', { bubbles: true }));
    await new Promise((r) => setTimeout(r, 80));
    assert.equal(String(box.textContent).trim(), '', 'un numéro de téléphone doit être effacé automatiquement');
  }

  // ---------- 3) clic réel : phrase vide → message clair, aucun appel réseau ----------
  {
    const { w, calls } = await boot();
    await w.dataResetOpen(false);
    // Mot de passe saisi, phrase laissée vide : c'est notre message qui doit guider.
    w.document.getElementById('f-password').value = 'Oriental24!Demo';
    const submit = w.document.querySelector('#modal-form [type=submit]');
    submit.click();
    await new Promise((r) => setTimeout(r, 30));
    assert.equal(calls.filter((c) => c.method === 'POST').length, 0,
      'aucun POST ne doit partir avec une phrase vide');
    const error = w.document.querySelector('.form-error');
    assert(error && /phrase ne correspond pas/i.test(error.textContent),
      'le clic doit expliquer que la phrase ne correspond pas');
    assert.equal(submit.disabled, false, 'le bouton doit rester utilisable après l’erreur');
  }

  // ---------- 4) clic réel : phrase correcte + mot de passe → POST ----------
  {
    const { w, calls } = await boot();
    await w.dataResetOpen(false);
    const box = w.document.getElementById('dr-phrase');
    box.textContent = 'remettre a zéro';
    box.dispatchEvent(new w.Event('input', { bubbles: true }));
    w.document.getElementById('f-password').value = 'Oriental24!Demo';
    w.document.querySelector('#modal-form [type=submit]').click();
    await new Promise((r) => setTimeout(r, 60));
    const posts = calls.filter((c) => c.method === 'POST');
    assert.equal(posts.length, 1, 'le clic doit envoyer exactement un POST');
    assert.equal(posts[0].url, '/admin/data-reset');
    assert.equal(posts[0].body.confirmation, 'remettre a zéro');
    assert.equal(posts[0].body.password, 'Oriental24!Demo');
    assert.equal(posts[0].body.keep_accounts, true);
    assert.equal(posts[0].body.reseed_demo, false);
  }

  // ---------- 5) le bouton n'est jamais désactivé dans le code source ----------
  assert(!/submit\.disabled\s*=\s*true/.test(source), 'le code désactive encore le bouton');

  console.log('Bouton « Confirmer la remise à zéro » : clic réel OK (4 scénarios)');
})();
