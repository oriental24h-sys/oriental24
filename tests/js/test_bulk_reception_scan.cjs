/* « Réceptionner la sélection » ouvre l'écran de SCAN au lieu de tout réceptionner.
   On scanne les colis physiquement présents ; seuls les scannés sont réceptionnés,
   les autres restent « restant(s) » sur leur palette. */
const fs = require('node:fs');
const assert = require('node:assert/strict');

const reception = fs.readFileSync('static/reception-collection.js', 'utf8');
const logistics = fs.readFileSync('static/logistics.js', 'utf8');
const partner = fs.readFileSync('static/partner-palettes.js', 'utf8');

// 1) l'écran de scan groupé existe
assert(reception.includes('async function openBulkReceptionScan('), 'openBulkReceptionScan absente');

// 2) l'écran charge chaque palette cochée via l'API de réception
assert(reception.includes("api('/reception-collection/'+kind+'/'+Number(it.id))"),
  'l’écran ne charge pas les palettes sélectionnées');

// 3) la validation envoie UNIQUEMENT les lignes scannées (line_ids)
assert(/line_ids:lines\.map\(l=>l\.lineId\)/.test(reception),
  'la validation n’envoie pas la liste des colis scannés');

// 4) un colis hors sélection est refusé côté écran
assert(reception.includes('Hors sélection'), 'aucun contrôle « hors sélection »');

// 5) les doubles scans sont détectés
assert(reception.includes('DOUBLE — déjà scanné'), 'aucune détection de double scan');

// 6) le reste par palette est affiché
assert(reception.includes("'+rest+' restant(s)'") || reception.includes("rest+' restant(s)'"),
  'le reste par palette n’est pas affiché');

// 7) le bouton du Hub ouvre le scan (plus de réception automatique)
assert(logistics.includes("openBulkReceptionScan(items.map(x=>({kind:'transfer',id:x.id})))"),
  'le bouton du Hub ne passe pas par le scan');
assert(!logistics.includes('bulkReceptionStart('), 'le Hub appelle encore la réception automatique');

// 8) même comportement pour les palettes partenaires
assert(partner.includes("openBulkReceptionScan(items.map(x=>({kind:'partner',id:x.id})))"),
  'les palettes partenaires ne passent pas par le scan');

// 9) l'ancienne réception automatique a été retirée
assert(!reception.includes('function bulkReceptionStart('), 'bulkReceptionStart (auto) est encore présent');

console.log('Réception de la sélection : écran de scan + réception partielle PASS');
