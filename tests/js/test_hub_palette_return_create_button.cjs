/* Palette « Envoyer vers le Hub d'origine » : le bouton « Envoyer la palette » doit
   toujours rester actif. Bug corrigé : changer le Hub de destination appelait
   hubPaletteResetCandidates() qui désactivait #hp-create ; la palette retour se créant
   vide (les CMD arrivent au scan), plus rien ne pouvait la réactiver → clic sans effet. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/logistics.js', 'utf8');

// --- mini DOM : uniquement ce que le code touche ---
const nodes = {};
const make = (id) => (nodes[id] = { id, disabled: false, innerHTML: '', textContent: '', value: '', isConnected: true });
['hp-create', 'hp-candidates'].forEach(make);

const ctx = {
  document: {
    getElementById: (id) => nodes[id] || null,
    querySelectorAll: () => [],
  },
  hubPaletteDialog: null,
  hubPaletteScanFeedback: () => {},   // bruit visuel uniquement
};
vm.createContext(ctx);

// On extrait les fonctions concernées.
function grab(name) {
  const start = src.indexOf('function ' + name + '(');
  assert(start > 0, name + ' introuvable');
  let depth = 0, i = src.indexOf('{', start);
  const from = i;
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  return src.slice(start, i + 1);
}
vm.runInContext([grab('hubPaletteResetCandidates'), grab('hubPaletteRefreshCreateButton'), grab('hubPaletteDestinationChanged')].join('\n'), ctx);

// 1) palette de retour : reset ne doit PAS désactiver le bouton
ctx.hubPaletteDialog = { purpose: 'return_to_origin', scans: [], loadSerial: 0 };
ctx.hubPaletteResetCandidates();
assert.equal(nodes['hp-create'].disabled, false, 'retour : bouton désactivé après reset');

// 2) changement de destination en mode retour : bouton toujours actif
ctx.hubPaletteDialog = { purpose: 'return_to_origin', scans: [], loadSerial: 0 };
ctx.hubPaletteDestinationChanged();
assert.equal(nodes['hp-create'].disabled, false, 'retour : bouton désactivé après changement de destination');

// 3) le rafraîchissement de sélection ne désactive pas non plus une palette retour
ctx.hubPaletteDialog = { purpose: 'return_to_central', scans: [] };
ctx.hubPaletteRefreshCreateButton();
assert.equal(nodes['hp-create'].disabled, false, 'retour : bouton désactivé par le rafraîchissement');

// 4) palette standard : le bouton reste bloqué tant que rien n'est scanné/coché
ctx.hubPaletteDialog = { purpose: 'standard', scans: [] };
nodes['hp-create'].disabled = false;
ctx.hubPaletteResetCandidates();
assert.equal(nodes['hp-create'].disabled, true, 'standard : le bouton doit rester bloqué sans colis');

ctx.hubPaletteRefreshCreateButton();
assert.equal(nodes['hp-create'].disabled, true, 'standard : toujours bloqué sans scan');

// 5) dès qu'un colis est scanné, la palette standard s'active
ctx.hubPaletteDialog = { purpose: 'standard', scans: [{ id: 1 }] };
ctx.hubPaletteRefreshCreateButton();
assert.equal(nodes['hp-create'].disabled, false, 'standard : le bouton doit s’activer après un scan');

console.log('Palette retour : bouton « Envoyer la palette » toujours actif PASS');
