/* « Nouveau colis » : le bloc de saisie libre de la ville a été retiré.
   Il ne doit plus rester que le sélecteur « Ville de livraison ». */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/app.js', 'utf8');

// 1) le bloc n'est plus rendu dans le formulaire
assert(!src.includes('Ou tapez la ville (faute de frappe ou arabe acceptés)'),
  'le bloc « Ou tapez la ville » est encore rendu');
assert(!src.includes('id="city-free-input"'), 'le champ city-free-input est encore rendu');
// le texte peut rester dans la fonction partagée (autre écran) mais pas dans le formulaire
const regularStart = src.indexOf('function newParcelRegular()');
const regularBody = src.slice(regularStart, src.indexOf('async function parcelDetail', regularStart));
assert(!regularBody.includes('La ville est reconnue automatiquement'),
  'le texte « La ville est reconnue automatiquement » est encore dans Nouveau colis');

// 2) la fonction de liaison n'est plus appelée dans « Nouveau colis »
assert(!/bindCityFreeInput\(\)/.test(regularBody), 'Nouveau colis appelle encore bindCityFreeInput');

// 3) le sélecteur de ville reste bien présent
assert(src.includes('select("city_id", "Ville de livraison"'), 'le sélecteur de ville a disparu');

// 4) la fonction reste disponible pour « Modifier la commande » (autre écran)
assert(src.includes('function bindCityFreeInput()'), 'la fonction partagée a été supprimée à tort');

console.log('Nouveau colis : bloc de saisie libre de la ville retiré PASS');
