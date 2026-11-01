/* « Envoyer Palette » doit lister les CMD présentes au Hub de départ dès l'ouverture,
   avec « Sélectionner tout ». Bug corrigé : la liste (#hp-candidates) n'existait pas
   dans le formulaire d'envoi et n'était chargée qu'au changement de Hub de destination ;
   l'écran affichait « Aucun colis scanné pour le moment » et obligeait à scanner. */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/logistics.js', 'utf8');

// 1) le formulaire d'envoi contient la zone de liste
assert(src.includes('id="hp-candidates"'), 'zone #hp-candidates absente du formulaire');

// 2) la liste est chargée à l'ouverture pour une palette standard
assert(/if\(!returnPalette\)hubPaletteLoadCandidates\(\)/.test(src),
  'la liste n’est pas chargée à l’ouverture du formulaire d’envoi');

// 3) le changement du Hub de départ recharge aussi la liste
assert(/hubPaletteResetCandidates\(\);\s*\n\s*if\(d\.purpose==='standard'\)hubPaletteLoadCandidates\(\)/.test(src),
  'le changement de Hub de départ ne recharge pas la liste');

// 4) « Sélectionner tout » porte bien sur les cases de la liste
assert(src.includes('hubPaletteSelectAll'), 'aucune fonction de sélection en masse');
assert(/#hp-candidates \.hp-pick/.test(src), 'la sélection en masse ne cible pas #hp-candidates .hp-pick');

// 5) un rechargement ne vide plus la sélection déjà cochée
assert(!/if\(\(d\.scans\|\|\[\]\)\.length\)\{d\.scans=\[\]\}/.test(src),
  'le rechargement de la liste réinitialise encore scans/sélection');

// 6) la création utilise bien les cases cochées
assert(src.includes("document.querySelectorAll('#hp-candidates .hp-pick:checked')"),
  'la création de palette ignore les cases cochées');

// 7) message explicite quand le trajet n'a aucun colis éligible
assert(src.includes('Trajet possible : Hub secondaire → Hub Central'),
  'aucun message d’aide quand la liste est vide');

console.log('Palette Envoi : liste des CMD + Sélectionner tout PASS');
