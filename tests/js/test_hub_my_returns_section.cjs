/* « Mes retours » : section dédiée chez le Hub.
   Demandé : tous les retours réceptionnés par le Hub apparaissent dans cette section,
   y restent CMD par CMD jusqu'à la remise au client, puis disparaissent après
   « Remis au client ». Et la séparation « retour réceptionné » / « retour envoyé »
   doit être visible en permanence dans l'onglet Retours.

   Bug d'avant : la section était peinte par un setTimeout(…,0) fragile (absente si le
   DOM n'était pas encore inséré), réservée aux agents, et les deux blocs de palettes
   n'apparaissaient que s'il y avait au moins une palette. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const src = fs.readFileSync('static/logistics.js', 'utf8');

// ---------- 1) la section est rendue dans la carte du Hub, toujours ----------
const viewStart = src.indexOf('function hubPalletsView(');
const viewEnd = src.indexOf('async function hubMyReturnsPaint(');
assert(viewStart > 0 && viewEnd > viewStart, 'hubPalletsView introuvable');
const view = src.slice(viewStart, viewEnd);

assert(view.includes('const myReturnsHost=(tab===\'retours\'||tab===\'a-recevoir\')?\'<div id="hub-my-returns"></div>\':\'\';'),
  'la section « Mes retours » n’est plus réservée aux onglets Retours / Retours du Central');
assert(view.includes('${myReturnsHost}${table}</section>'),
  'la section « Mes retours » n’est pas rendue dans la carte, avant les palettes');
assert(view.includes('if(myReturnsHost)hubMyReturnsSchedule();'),
  'la section n’est plus peinte après insertion du DOM');
assert(!view.includes('setTimeout(hubMyReturnsPaint,0)'),
  'l’ancien setTimeout fragile est encore actif');

// ---------- 2) la séparation réceptionné / envoyé est toujours visible ----------
assert(view.includes("const splitReturn=tab==='retours'&&agent;"),
  'la séparation réceptionné / envoyé dépend encore du contenu (elle disparaît quand c’est vide)');
assert(view.includes('Palettes de retour reçues du Hub Central'), 'bloc « reçues du Central » absent');
assert(view.includes('Palettes de retour envoyées au Hub Central'), 'bloc « envoyées au Central » absent');

// ---------- 3) comportement réel de la section ----------
function grab(name) {
  const asyncIdx = src.indexOf('async function ' + name + '(');
  const start = asyncIdx >= 0 ? asyncIdx : src.indexOf('function ' + name + '(');
  assert(start > 0, name + ' introuvable');
  let depth = 0, i = src.indexOf('{', start);
  for (; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') { depth--; if (depth === 0) break; }
  }
  return src.slice(start, i + 1);
}

const nodes = {};
const host = { isConnected: true, innerHTML: '' };
nodes['hub-my-returns'] = host;

let fixture = { rows: [], state_labels: {} };

const ctx = {
  document: { getElementById: (id) => nodes[id] || null },
  S: { user: { role: 'agent', agent_hub_id: 4 } },
  api: async () => fixture,
  esc: (v) => String(v === undefined || v === null ? '' : v),
  icon: (n) => '[' + n + ']',
  opsDate: (v) => String(v || '—'),
  simpleTable: (head, rows) => 'TABLE{' + head.join('|') + '}' + rows.map((r) => 'ROW{' + r.join('~') + '}').join(''),
  empty: (t, s) => 'EMPTY{' + t + '|' + s + '}',
};
vm.createContext(ctx);
vm.runInContext('let hubMyReturnsSerial=0,hubMyReturnsToken=0;' + grab('hubMyReturnsPaint') + '\n' + grab('hubMyReturnsSchedule'), ctx);

(async () => {
  // 3a) retours reçus au Hub + retours envoyés : deux blocs séparés
  fixture = {
    rows: [
      { id: 11, tracking: 'RT-RECU-1', recipient: 'Client A', city: 'Agadir', status: 'Retourné', return_state: 'recu_hub_origine', flow: 'received', days: 2, received_at: '2026-10-30 10:00:00' },
      { id: 12, tracking: 'RT-ENVOYE-2', recipient: 'Client B', city: 'Rabat', status: 'Retourné', return_state: 'envoye', flow: 'sent', days: 1, updated_at: '2026-10-31 09:00:00' },
    ],
    state_labels: { recu_hub_origine: 'Retour reçu en Hub origine', envoye: 'Retour envoyé vers le Hub Central' },
  };
  await ctx.hubMyReturnsPaint();
  let html = host.innerHTML;
  assert(html.includes('Mes retours'), 'le titre « Mes retours » est absent');
  assert(html.includes('Reçus à mon Hub · à remettre au client'), 'le bloc « reçus » est absent');
  assert(html.includes('Envoyés vers le Hub Central · pas encore réceptionnés'), 'le bloc « envoyés » est absent');
  const recuBlock = html.slice(html.indexOf('Reçus à mon Hub'), html.indexOf('Envoyés vers le Hub Central'));
  const envoyeBlock = html.slice(html.indexOf('Envoyés vers le Hub Central'));
  assert(recuBlock.includes('RT-RECU-1'), 'le retour réceptionné n’est pas dans le bloc « reçus »');
  assert(!recuBlock.includes('RT-ENVOYE-2'), 'un retour envoyé est affiché comme réceptionné');
  assert(envoyeBlock.includes('RT-ENVOYE-2'), 'le retour envoyé n’est pas dans le bloc « envoyés »');
  // la remise au client n’est proposée que sur un retour physiquement reçu
  assert(recuBlock.includes('hubMyReturnHandover(11,'), 'bouton « Remis au client » absent sur le retour reçu');
  assert(!envoyeBlock.includes('hubMyReturnHandover(12,'), 'bouton « Remis au client » proposé sur un retour non reçu');

  // 3b) la CMD sort de la section dès qu’elle est remise au client (relue du serveur)
  fixture = {
    rows: [{ id: 12, tracking: 'RT-ENVOYE-2', recipient: 'Client B', city: 'Rabat', status: 'Retourné', return_state: 'envoye', days: 1, updated_at: '2026-10-31 09:00:00' }],
    state_labels: { envoye: 'Retour envoyé vers le Hub Central' },
  };
  await ctx.hubMyReturnsPaint();
  html = host.innerHTML;
  assert(!html.includes('RT-RECU-1'), 'la CMD remise au client reste affichée dans « Mes retours »');
  assert(html.includes('Aucun retour reçu à votre Hub'), 'l’état vide du bloc « reçus » est absent');

  // 3c) section vide : elle reste affichée (le flux est explicite)
  fixture = { rows: [], state_labels: {} };
  await ctx.hubMyReturnsPaint();
  html = host.innerHTML;
  assert(html.includes('Mes retours'), 'la section disparaît quand il n’y a aucun retour');
  assert(html.includes('Aucun retour en route'), 'l’état vide du bloc « envoyés » est absent');

  // ---------- 4) le serveur fait bien sortir une CMD remise au client ----------
  const py = fs.readFileSync('logistics.py', 'utf8');
  const route = py.slice(py.indexOf("@app.get(P + '/my-returns')"), py.indexOf("@app.post(P + '/my-returns/<int:pid>/handover')"));
  assert(route.includes("p.return_state='recu_hub_origine'"),
    'la famille « reçus au Hub » n’est plus filtrée sur l’état reçu en Hub origine');
  const recvFamily = route.slice(route.indexOf('where_recv = ['), route.indexOf('args_recv = []'));
  const sentFamily = route.slice(route.indexOf('where_sent = ['), route.indexOf('args_sent = ['));
  assert(!recvFamily.includes('remis_client') && !sentFamily.includes('remis_client'),
    'la liste « Mes retours » accepte encore un retour déjà remis au client');
  assert(sentFamily.includes("'envoye','transit_origine','recu_entrepot'"), 'famille « envoyés » incomplète');
  // deux familles explicites côté serveur
  assert(route.includes("finish(rows_recv, 'received') + finish(rows_sent, 'sent')"),
    'le serveur ne sépare pas « reçu au Hub » et « envoyé vers le Central »');
  assert(route.includes("sd.source_hub_id=?"), 'les retours envoyés ne sont pas rattachés au Hub expéditeur');
  assert(route.includes('received=len(rows_recv), sent=len(rows_sent)'), 'compteurs reçus/envoyés absents');
  const handover = py.slice(py.indexOf('def ops_my_return_handover'), py.indexOf("@app.get(P+'/palette-candidates')"));
  assert(handover.includes("UPDATE parcels SET return_state='remis_client'"), '« Remis au client » ne change pas l’état du retour');
  assert(handover.includes('parcel_physically_at_hub'), '« Remis au client » ne vérifie pas la présence physique au Hub');

  console.log('Mes retours : section Hub + sortie après remise au client PASS');
})().catch((e) => { console.error(e); process.exit(1); });
