/* Ticket d'une palette ENVOYÉE par mon Hub vers le Central :
   la nature doit être RAMASSAGE (vert) — pas RÉCEPTION. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const logistics = fs.readFileSync('static/logistics.js', 'utf8');
const bonPrint = fs.readFileSync('static/bon-print.js', 'utf8');

// 1) côté logistique : une palette dont la source est mon Hub => RAMASSAGE
assert(/const sending=!isPickup&&myHubId&&Number\(d\.source_hub_id\)===myHubId/.test(logistics),
  'la détection « envoi » a disparu');
assert(/sending\?'RAMASSAGE':'RÉCEPTION'/.test(logistics),
  'la nature d’un envoi n’est pas RAMASSAGE');
assert(!/sending\?'ENVOI'/.test(logistics), 'l’envoi porte encore la nature ENVOI');
assert(logistics.includes('Bon de ramassage · envoi vers le Central'),
  'titre du bon d’envoi incorrect');
assert(logistics.includes('CMD ramassées à mon Hub, expédiées vers le Hub Central pour tri'),
  'note du bon d’envoi manquante');

// 2) côté impression : RAMASSAGE est bien vert, RÉCEPTION bleu, RETOUR rouge
const m = bonPrint.match(/const natureColor=\{([^}]*)\}/);
assert(m, 'natureColor introuvable');
const ctx = {};
vm.createContext(ctx);
vm.runInContext('const natureColor={' + m[1] + '};this.map=natureColor;', ctx);
const colors = ctx.map;
assert.equal(colors.RAMASSAGE.toLowerCase(), '#1d7d3f', 'RAMASSAGE doit être vert');
assert.equal(colors.RÉCEPTION.toLowerCase(), '#1b4ed8', 'RÉCEPTION doit être bleu');
assert.equal(colors.RETOUR.toLowerCase(), '#b3261e', 'RETOUR doit être rouge');

// 3) un bon de ramassage porte bien le titre « Bon de ramassage »
const t = logistics.match(/title:[^,]*$/m);
assert(logistics.includes("nature==='RAMASSAGE'?'Bon de ramassage'"), 'titre RAMASSAGE absent');

console.log('Ticket des envois : RAMASSAGE vert (pas RÉCEPTION) PASS');
