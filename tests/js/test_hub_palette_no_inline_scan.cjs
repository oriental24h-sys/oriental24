/* « Envoyer Palette » : plus de scan inline dans le formulaire.
   Demandé : retirer le bloc « Scanner le colis à envoyer » (input #hp-scan + bouton
   « Ajouter » + « Le serveur vérifie à l'instant… »). La palette d'envoi se compose
   uniquement avec la liste des colis présents au Hub de départ + « Sélectionner tout ».
   Les palettes retour, elles, gardent leur écran de scan après création. */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/logistics.js', 'utf8');

// --- 1) le formulaire « Envoyer Palette » ne contient plus aucun élément de scan ---
const from = src.indexOf('async function hubPaletteNew(');
const to = src.indexOf('function hubPaletteUpdateTargets(');
assert(from > 0 && to > from, 'hubPaletteNew introuvable');
const form = src.slice(from, to);

['hp-scan', 'hp-scan-add', 'Scanner le colis à envoyer', 'Scannez ou saisissez le tracking',
 'Le serveur vérifie à l’instant', 'hub-palette-scan'].forEach((dead) => {
  assert(!form.includes(dead), 'le formulaire d’envoi contient encore : ' + dead);
});

// --- 2) aucun code de scan inline ne survit ailleurs dans le fichier ---
['hp-scan', 'function hubPaletteScanAdd(', 'function hubPaletteScanPaint(',
 'function hubPaletteScanFeedback(', 'function hubPaletteRoute(',
 'hubPaletteScanRemove', 'hubPaletteScanClear', 'hubPaletteScanDecide'].forEach((dead) => {
  assert(!src.includes(dead), 'code de scan inline encore présent : ' + dead);
});

// --- 3) la demande précédente reste intacte : liste + sélection en masse ---
assert(form.includes('id="hp-candidates"'), 'la liste des colis du Hub a disparu du formulaire');
assert(form.includes('if(!returnPalette)hubPaletteLoadCandidates()'),
  'la liste n’est plus chargée à l’ouverture');
assert(src.includes('function hubPaletteSelectAll(checked)'), '« Sélectionner tout » a disparu');
assert(src.includes("document.querySelectorAll('#hp-candidates .hp-pick')"),
  '« Sélectionner tout » ne cible plus les cases de la liste');

// --- 4) la création repose uniquement sur les cases cochées ---
const createStart = src.indexOf('async function hubPaletteCreate');
const createEnd = src.indexOf('\nfunction ', createStart);
const create = src.slice(createStart, createEnd > 0 ? createEnd : src.length);
assert(create.includes("document.querySelectorAll('#hp-candidates .hp-pick:checked')"),
  'la création ignore les cases cochées');
assert(create.includes('Cochez au moins un colis à envoyer.'), 'message de refus non mis à jour');
assert(!create.includes('Scannez'), 'la création renvoie encore au scan');
assert(!create.includes('rescannez'), 'le message de trajet renvoie encore au scan');

// --- 5) palettes retour : l’écran de scan après création n’est pas touché ---
assert(create.includes("hubPaletteTab=d.purpose==='return_to_origin'?'a-recevoir':'retours'"),
  'la palette retour ne s’ouvre plus sur son écran');

console.log('Envoyer Palette : scan inline retiré PASS');
