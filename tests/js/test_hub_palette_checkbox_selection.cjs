/* Palette Hub : la sélection par cases vaut sélection.
   Bug corrigé : cocher un colis dans « Colis du Hub » puis « Créer la palette »
   répondait « Scannez au moins un colis à envoyer » car seuls les scans partaient. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/logistics.js', 'utf8');
const start = src.indexOf('function hubPalettePickedItems');
const end = src.indexOf('function hubPaletteSelectAll');
assert(start > 0 && end > start, 'hubPalettePickedItems introuvable');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src.slice(start, end), ctx);
const pick = ctx.hubPalettePickedItems;

// 1) case cochée seule (aucun scan) : le colis part quand même
let items = pick([], [{ id: 1, tracking: 'EXAMPLE-001', decision: 'accept' }], [1]);
assert.equal(items.length, 1);
assert.equal(items[0].id, 1);
assert.equal(items[0].tracking, 'EXAMPLE-001');

// 2) scan + même colis coché : aucun doublon
items = pick([{ id: 2, tracking: 'CMD-2', decision: 'accept' }], [{ id: 2, tracking: 'CMD-2' }], [2]);
assert.equal(items.length, 1);

// 3) rendez-vous futur (decision confirm) : la coche vaut OUI
items = pick([], [{ id: 3, tracking: 'RDV-3', decision: 'confirm' }], [3]);
assert.equal(items[0].confirmed, true);

// 4) colis non éligible (blocked) : jamais forcé par une simple coche
items = pick([], [{ id: 4, tracking: 'BLK-4', decision: 'blocked' }], [4]);
assert.equal(items[0].decision, 'blocked');
assert.equal(items[0].forced, false);

// 5) identifiants invalides ignorés
items = pick([], [{ id: 5, tracking: 'X' }], ['abc', null, 5]);
assert.equal(items.length, 1);
assert.equal(items[0].id, 5);

// 6) la création lit réellement les cases cochées
const create = src.slice(src.indexOf('async function hubPaletteCreate'));
assert(create.includes("document.querySelectorAll('#hp-candidates .hp-pick:checked')"), 'la création ignore les cases cochées');
assert(create.includes('hubPalettePickedItems(d.scans,d.rows,checkedIds)'), 'la sélection scannée + cochée n’est pas fusionnée');
assert(create.includes('Scannez ou cochez au moins un colis à envoyer.'), 'message de refus non mis à jour');
assert(!create.includes('const parcel_ids=(d.scans||[]).map(p=>p.id);'), 'l’ancien chemin « scan uniquement » est encore actif');

// 7) le bouton s’active aussi quand une case est cochée
assert(src.includes('function hubPaletteRefreshCreateButton()'));
assert(src.includes('button.disabled=!(scanned||checked)'));
assert(src.includes('hubPaletteMaterializeChecked()'));

console.log('Sélection palette Hub (cases + scan) PASS');
