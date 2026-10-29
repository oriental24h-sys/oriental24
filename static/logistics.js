/* ORIENTAL24 — operational workflows. These routes require the real server. */
let opsConfig=null,opsDoc=null,opsParcel=null,opsTab='all',opsPeriod={from:'',to:''},hubDriverRows=[],hubPaletteTab='default',hubPaletteDialog=null,hubPaletteUnknownRows=[],hubPaletteUnknownHubs=[];
const opsKinds={pickup:'Bon de ramassage',return:'Bon de retour',transfer:'Palette inter-hub'};
const opsOffline=typeof OFFLINE_SEED!=='undefined';
window.opsOffline=opsOffline;
if(!opsOffline){
 menu.splice(2,0,['EXPLOITATION',[
  ['documents','file','Documents & transferts'],
  ['hub-dashboard','chart','Activité de mon Hub',['agent']],
  ['hub-invoices','file','Factures COD des Hubs',['admin','agent']],
  ['hub-driver-statements','file','Relevés des livreurs',['agent']],
  ['hub-cod','wallet','Caisse COD des Hubs',['admin','agent']],
  ['fulfillment','box','Préparation stock',['admin','client','agent']],
  ['stock-analytics','chart','Analyse produits',['admin','client']],
  ['ops-settings','settings','Hubs & motifs',['admin']],
  ['ops-analytics','chart','Activité enregistrée',['admin']],
  ['account-dossiers','shield','Dossiers comptes']
 ]]);
 Object.assign(titles,{documents:'Documents & transferts','hub-dashboard':'Activité de mon Hub','hub-invoices':'Factures COD des Hubs','hub-driver-statements':'Relevés des livreurs','hub-cod':'Caisse COD des Hubs','ops-settings':'Hubs & motifs','ops-analytics':'Activité enregistrée',notifications:'Notifications internes',fulfillment:'Préparation des commandes','account-dossiers':'Dossiers administratifs','stock-analytics':'Analyse produits'});
}
const opsDate=v=>!v?'—':/[zZ]$|[+-]\d{2}:\d{2}$/.test(v)?new Date(v).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca',dateStyle:'medium',timeStyle:'short'}):`${v.slice(8,10)}/${v.slice(5,7)}/${v.slice(0,4)} ${v.slice(11,16)} (serveur)`;
/* v1.5.9 « ETA palette » : heure d'arrivée estimée (hypothèse navette quotidienne : départ + 24 h), calculée localement. */
const OPS_ETA_HOURS=24;
function opsEtaAt(d){
 if(!d||!d.dispatched_at||['Reçu','Annulé'].includes(d.status))return null;
 const t=new Date(d.dispatched_at);if(!Number.isFinite(t.getTime()))return null;
 t.setHours(t.getHours()+OPS_ETA_HOURS);return t;
}
const opsEtaChip=d=>{
 if(d?.status==='Départ partiel')return `<span class="tag warn">${icon('scan')}Sortie ${d.departure_scanned}/${d.count}</span>`;
 const eta=opsEtaAt(d);if(!eta)return `<span class="sub">${d?.status==='Annulé'?'Bon annulé':'Départ à déclarer'}</span>`;
 const late=eta.getTime()<Date.now();
 return `<span class="tag ${late?'warn':'blue'} ops-eta-chip" title="Hypothèse navette quotidienne : départ + 24 h">${icon('clock')}ETA ${opsDate(eta.toISOString())}${late?' · en retard':''}</span>`;
};
const opsEcartChip=d=>d?.status==='Départ partiel'?`<span class="tag warn ops-ecart-tag">${icon('scan')}Sortie ${d.departure_scanned}/${d.count}</span>`:d&&['En transit','Partiellement reçu'].includes(d.status)&&d.received<d.count?`<span class="tag warn ops-ecart-tag">${icon('alert')}Écart −${d.count-d.received}</span>`:d&&['Reçu','Clôturé'].includes(d.status)?'<span class="tag good">Écart 0</span>':`<span class="sub">${d&&d.status==='Annulé'?'Bon annulé':'À déclarer'}</span>`;
const opsTag=s=>`<span class="tag ${['Reçu','Livré'].includes(s)?'good':s==='Annulé'?'bad':['Partiellement reçu','Départ partiel'].includes(s)?'warn':'blue'}">${esc(s)}</span>`;
async function opsLoadConfig(){opsConfig=await api('/logistics/config');return opsConfig}
function opsDocsView(rows){
 const visible=rows.filter(d=>opsTab==='all'||d.kind===opsTab);return heading('Documents & transferts','Des colis identifiés, un départ déclaré, une réception contrôlée.',`${S.user.role==='admin'?`<button class="btn primary" onclick="newOpsDocument()">${icon('plus')}Préparer un document</button>`:''}<button class="btn" onclick="findOpsDocument()">${icon('scan')}Rechercher / scanner un bon</button>`)+`<div class="demo-notice">Bons internes de démonstration. Une réception ne déclenche aucun paiement. Le transporteur du document et le livreur final du colis peuvent être différents.</div><section class="stats">${stat('Documents affichés',rows.length,'','file','blue','500 derniers de votre périmètre')}${stat('Préparés',rows.filter(d=>d.status==='Préparé').length,'','box','','Prêts à déclarer au départ')}${stat('Départs / réceptions en cours',rows.filter(d=>['Départ partiel','En transit','Partiellement reçu'].includes(d.status)).length,'','truck','purple','Scans de sortie ou réception à terminer')}${stat('Reçus intégralement',rows.filter(d=>d.status==='Reçu').length,'','checkcircle','green','Tous les colis ont été scannés')}${stat('Écarts à contrôler',rows.filter(d=>['En transit','Partiellement reçu'].includes(d.status)&&d.received<d.count).reduce((n,d)=>n+(d.count-d.received),0),'','alert','bad','Colis annoncés mais pas encore physiquement scannés')}</section><section class="card"><div class="tabs">${[['all','Tous'],['pickup','Ramassages'],['return','Retours'],...(S.user.role==='client'?[]:[['transfer','Transferts']])].map(([v,t])=>`<button class="${opsTab===v?'active':''}" onclick="opsTab='${v}';renderView()">${t}</button>`).join('')}</div>${simpleTable(['Document','Parties / Trajet','Colis reçus','Écart théorique / physique','ETA','État',''],visible.map(d=>[`<button class="tracking" onclick="openOpsDocument(${d.id})">${esc(d.reference)}</button><span class="sub">${opsKinds[d.kind]} · ${date(d.created_at)}</span>`,`${esc(d.source_name)} → ${esc(d.destination_name)}<span class="sub">${esc(d.client_name||'Multi-clients')} · ${esc(d.driver_name||'Transporteur non affecté')}</span>`,`<strong>${d.received} / ${d.count}</strong>`,opsEcartChip(d),opsEtaChip(d),opsTag(d.status),`<div class="pal-row">${paletteRowActions(d.kind==='pickup'?'pickup':d.kind==='return'?'return':'transfer',d.id,'openOpsDocument('+d.id+')')}</div>`]))}</section>`;
}

/* Réception groupée des palettes : cocher plusieurs palettes → UNE seule validation. */
function hubPaletteFusCount(){
 const boxes=[...document.querySelectorAll('.hp-fus')],sel=boxes.filter(x=>x.checked);
 const b=document.getElementById('hp-bulk-btn');
 if(b){b.innerHTML=icon('scan')+'Réceptionner la sélection ('+sel.length+')';b.disabled=!sel.length}
 document.querySelectorAll('.hp-fus-all').forEach(a=>{a.checked=!!boxes.length&&sel.length===boxes.length;a.indeterminate=sel.length>0&&sel.length<boxes.length});
}
function hubPaletteFusAll(on){document.querySelectorAll('.hp-fus').forEach(x=>{x.checked=!!on});hubPaletteFusCount()}
function hubPaletteBulkReception(){
 if(!['admin','agent'].includes(S?.user?.role))return;
 const ids=new Set([...document.querySelectorAll('.hp-fus:checked')].map(x=>Number(x.value)));
 const items=hubLiveRows.filter(r=>ids.has(Number(r.id))).map(r=>({id:r.id,reference:r.reference,remaining:Number(r.remaining||0)}));
 if(!items.length){toast('Cochez au moins une palette à réceptionner.',true);return}
 bulkReceptionStart('transfer',items);
}
function hubPaletteQuery(){return new URLSearchParams({tab:hubPaletteTab}).toString()}
async function hubPaletteTabSet(tab){hubPaletteTab=tab;await renderView()}
function hubPalettePurposeLabel(d){return ({standard:'Palette inter-Hub',return_to_central:'Retour vers Hub Central',return_to_origin:'Retour vers Hub d’origine'}[d.palette_purpose]||'Palette inter-Hub')}
let hubLiveRows=[];
function hubPalletsView(data){
 hubLiveRows=data.rows||[];
 const rows=data.rows||[],agent=S.user.role==='agent',hubId=Number(S.user.agent_hub_id)||0,tab=data.tab||hubPaletteTab;
 const active=rows.filter(d=>['Préparé','Départ partiel','En transit','Partiellement reçu'].includes(d.status));
 const pending=rows.filter(d=>['Départ partiel','En transit','Partiellement reçu'].includes(d.status));
 const incoming=rows.filter(d=>(!agent||Number(d.destination_hub_id)===hubId)&&['Départ partiel','En transit','Partiellement reçu'].includes(d.status));
 const tabs=[['default','Default'],['retours','Retours'],['a-recevoir','Retours du Central']];
 const admin=S.user.role==='admin',centralId=Number(data.central_hub_id)||0;
 const receiveAction=`<button class="btn" onclick="hubPaletteReception()">${icon('scan')}Reception Palette</button>`;
 const actions=tab==='default'?`${receiveAction}<button class="btn primary" onclick="hubPaletteNew('standard')">${icon('truck')}Envoyer Palette</button>`:
   tab==='retours'?(admin?`${receiveAction}<button class="btn" onclick="hubPaletteReviewUnknown()">${icon('alert')}Origines inconnues · Revue Admin</button><button class="btn danger" onclick="hubPaletteNew('return_to_central')">${icon('truck')}Envoyer Retour au Central</button><button class="btn primary" onclick="hubPaletteNew('return_to_origin')">${icon('layers')}Envoyer vers le Hub d’origine</button>`:hubId===centralId?`${receiveAction}<button class="btn primary" onclick="hubPaletteNew('return_to_origin')">${icon('layers')}Envoyer vers le Hub d’origine</button>`:`<button class="btn danger" onclick="hubPaletteNew('return_to_central')">${icon('truck')}Envoyer Retour au Central</button><button class="btn primary" onclick="hubReturnsReception()">${icon('scan')}Réception des retours Hub</button>`):tab==='a-recevoir'?receiveAction:'';
 const purposeNote=tab==='retours'?(hubId===centralId&&!admin?'Les retours reçus du réseau sont triés ici. Un colis ne peut repartir qu’au Hub attesté par son historique physique; les origines incertaines restent bloquées pour vérification Admin.':'Les colis refusés ou retournés remontent au Hub Central; ils repartent ensuite uniquement vers leur Hub d’origine attesté.'):
   tab==='a-recevoir'?'Cette file contient les retours triés par le Hub Central vers leur Hub d’origine. Les détails du colis ne sont visibles qu’après sa réception physique.':'Le réseau conserve une étoile autour du Hub Central : un Hub secondaire ne transfère jamais directement vers un autre Hub secondaire.';
 const receivable=d=>!!(d.destination_hub_id&&(!agent||Number(d.destination_hub_id)===hubId)&&pending.includes(d)&&['En transit','Partiellement reçu','Départ partiel'].includes(d.status));
 const allBox=rows.some(receivable)?`<label class="hp-fuscell" title="Tout sélectionner / tout désélectionner les palettes à recevoir"><input type="checkbox" class="hp-fus-all" onchange="hubPaletteFusAll(this.checked)"></label>`:'';
 const table=rows.length?simpleTable([allBox,'Palette','Trajet','Transport · suivi','Colis','Lots','Créée le','État',''],rows.map(d=>[
   receivable(d)?`<label class="hp-fuscell" title="Sélectionner pour la réception groupée"><input type="checkbox" class="hp-fus" value="${d.id}" onchange="hubPaletteFusCount()"></label>`:'<span class="hp-fuscell"></span>',
   `<strong>${esc(d.reference)}</strong><span class="sub">${esc(hubPalettePurposeLabel(d))}</span>`,
   `${esc(d.source_name||'—')} → ${esc(d.destination_name||'—')}`,
   `${esc(d.transport||'—')}<span class="sub">${esc(d.tracking_code||'—')}</span>`,
   `<strong>${d.received||0} / ${d.count||0}</strong><span class="sub">${Math.max(0,d.remaining||0)} restant(s)</span>`,
   d.lots||'—',opsDate(d.created_at),opsTag(d.status),
   `<div class="hp-row-actions" style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">${paletteRowActions('transfer',d.id,'openOpsDocument('+d.id+')')}<button class="btn sm" onclick="openOpsDocument(${d.id})">${d.destination_hub_id&&(!agent||Number(d.destination_hub_id)===hubId)&&pending.includes(d)?'Ouvrir / recevoir':'Ouvrir'} ${icon('arrow')}</button>${d.status==='Préparé'&&!d.dispatched_at&&(!agent||Number(d.source_hub_id)===hubId)?`<button class="btn sm" onclick="hubPaletteAddCmd(${d.id},'${esc(d.palette_purpose||'standard')}')" title="Ajouter des CMD à cette palette : le scan s’ouvre">${icon('plus')}CMD</button><button class="btn sm danger" onclick="hubPaletteDelete(${d.id},'${esc(d.reference)}',${Number(d.revision)||1})" title="Supprimer cette palette non validée">Supprimer</button>`:''}</div>`
 ])):empty(tab==='retours'?'Aucun retour dans cette sélection':tab==='a-recevoir'?'Aucune palette à recevoir':'Aucune palette inter-Hub','Les palettes autorisées pour votre périmètre apparaîtront ici.');
 if((tab==='retours'||tab==='a-recevoir')&&agent)setTimeout(hubMyReturnsPaint,0);
 const bar=document.getElementById('hp-bulk-btn');if(bar){bar.disabled=true;bar.innerHTML=icon('scan')+'Réceptionner la sélection (0)';}document.querySelectorAll('.hp-fus-all').forEach(a=>{a.checked=false;a.indeterminate=false});
 return heading('Palettes',agent?`${esc(data.hub?.name||'Mon Hub')} · transferts et retours qui impliquent ce Hub.`:'Transferts et retours inter-Hubs · administrateur.',`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button>`)+
 `<div class="pp-explainer"><span class="stat-icon">${icon('layers')}</span><div><b>${esc(purposeNote)}</b>${tab==='default'?'<p>Transferts normaux des CMD : d’un Hub vers le Hub Central, ou du Hub Central vers un Hub. Aucune règle de retour ne s’applique ici.':'<p>Au scan de départ du retour, chaque colis passe à « Vers Hub Central ». Il devient « Retourné » uniquement après sa réception physique par Admin ou le responsable du Hub Central. Les montants des relevés déjà émis ne sont pas recalculés; une origine inconnue n’est jamais déduite de la ville.</p>'}</div></div>
 <section class="stats">${stat('Palettes affichées',rows.length,'','layers','blue',tab==='default'?'Périmètre autorisé':tab==='retours'?'Flux de retour':'Retours dirigés vers l’origine')}${stat('À traiter',active.length,'','truck','purple','Préparées, départs ou réceptions en cours')}${stat('Colis restant(s)',rows.reduce((n,d)=>n+(d.remaining||0),0),'','box','orange','Résumé de palette, sans détail hors Hub')}${stat('À recevoir',incoming.length,'','scan',incoming.length?'warn':'green','Destinées à votre Hub')}</section>
 ${(tab==='retours'||tab==='a-recevoir')?`<div id="hub-my-returns"></div>`:''}
 <section class="card"><div class="pc-tabs">${tabs.map(([id,label])=>`<button type="button" class="pc-tab ${tab===id?'on':''}" onclick="hubPaletteTabSet('${id}')">${label}</button>`).join('')}</div>${tab==='a-recevoir'?`<div class="full form-hint"><b>Palettes de retour envoyées par le Hub Central vers ${esc(data.hub?.name||'mon Hub')}</b> — réceptionnez-les pour que les colis passent dans « Mes retours », puis remettez-les au client.</div>`:''}<div class="pc-actions-row">${actions}</div><div class="hp-bulk-bar"><button type="button" class="btn primary" id="hp-bulk-btn" onclick="hubPaletteBulkReception()" disabled>${icon('scan')}Réceptionner la sélection (0)</button><span class="sub" id="hp-bulk-count">Cochez les palettes arrivées à votre Hub : tous leurs colis sont réceptionnés en une seule validation.</span></div>${table}</section>`;
}
async function hubReturnsReception(){
 if(S.user.role!=='agent'){toast('Réception des retours réservée au Responsable de Hub.',true);return}
 try{
  const data=await api('/logistics/palettes?tab=a-recevoir'),hubId=Number(S.user.agent_hub_id)||0;
  const rows=(data.rows||[]).filter(d=>Number(d.destination_hub_id)===hubId&&['Départ partiel','En transit','Partiellement reçu'].includes(d.status));
  if(!rows.length){toast('Aucun retour en transit vers votre Hub.');return}
  modal('Réception des retours Hub',`<p class="form-hint">Ces retours ont été triés par le Hub Central et voyagent vers votre Hub. Ouvrez-en un puis scannez chaque colis réellement remis : le colis passera à <b>Retour reçu en Hub origine</b> et restera dans <b>Mes retours</b> jusqu’à sa remise au client.</p>${simpleTable(['Palette','Trajet','Colis','État',''],rows.map(d=>[
    `<strong>${esc(d.reference)}</strong><span class="sub">${esc(hubPalettePurposeLabel(d))}</span>`,
    `${esc(d.source_name||'—')} → ${esc(d.destination_name||'—')}`,
    `<strong>${d.received||0} / ${d.count||0}</strong><span class="sub">${Math.max(0,d.remaining||0)} restant(s)</span>`,
    opsTag(d.status),
    `<button class="btn sm primary" onclick="closeModal();openReceptionCollection('transfer',${d.id})">${icon('scan')}Réceptionner</button>`
 ]))}`);
 }catch(e){toast(e.message,true)}
}
async function hubMyReturnsPaint(){
 const host=document.getElementById('hub-my-returns');if(!host||S.user.role!=='agent')return;
 host.innerHTML='<section class="card ops-margin"><div class="card-head"><div><h3>Retours du Hub Central · à remettre au client</h3><p>Chargement…</p></div></div></section>';
 try{
  const data=await api('/logistics/my-returns');
  if(!host.isConnected)return;
  const rows=data.rows||[];
  const label={recu_hub_origine:'Retour reçu en Hub origine',transit_origine:'Retour transit vers origine',recu_entrepot:'Retour reçu en entrepôt',envoye:'Retour envoyé vers le Central'};
  host.innerHTML=`<section class="card ops-margin"><div class="card-head"><div><h3>Retours du Hub Central · à remettre au client</h3><p>Colis de retour arrivés à ${esc(data.hub_name||'votre Hub')} : remettez-les au client puis cliquez « Remis au client ».</p></div><span class="tag">${rows.length} retour${rows.length>1?'s':''}</span></div>${rows.length?simpleTable(['Colis','Client / Ville','État du retour','Reçu le','Depuis',''],rows.map(r=>[
    `<strong>${esc(r.tracking)}</strong><span class="sub">${esc(r.status)}</span>`,
    `${esc(r.recipient||'—')}<span class="sub">${esc(r.city||'')}</span>`,
    `<span class="tag ${r.return_state==='recu_hub_origine'?'good':'warn'}">${esc(label[r.return_state]||r.return_state)}</span>`,
    opsDate(r.received_at||r.updated_at),
    r.days+' j',
    `<div style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end"><button class="btn sm" onclick="parcelDetail(${r.id})">Ouvrir ${icon('arrow')}</button>${r.return_state==='recu_hub_origine'?`<button class="btn sm primary" onclick="hubMyReturnHandover(${r.id},'${esc(r.tracking)}')">${icon('check')}Remis au client</button>`:''}</div>`
   ])):empty('Aucun retour au Hub','Les retours réceptionnés depuis le Hub Central apparaîtront ici.')}</section>`;
 }catch(e){if(host.isConnected)host.innerHTML=`<section class="card ops-margin"><div class="card-head"><div><h3>Mes retours</h3></div></div><p class="sub">${esc(e.message)}</p></section>`}
}
async function hubMyReturnHandover(id,tracking){
 if(!['admin','agent'].includes(S?.user?.role))return;
 const ctx=ppContext('Remise au client · '+tracking);
 ctx.node.querySelector('.modal-body').innerHTML=`<p class="form-hint">Confirmez la remise physique du colis <b>${esc(tracking)}</b> au client. La ligne sort de « Mes retours » et l’opération est tracée.</p><label class="field full"><span>Note (facultatif)</span><input id="mrh-note" maxlength="300" placeholder="Nom de la personne, référence de reçu…"></label><div class="form-error" id="mrh-error" style="display:none"></div><div class="form-actions"><button class="btn" onclick="closeModal()">Annuler</button><button class="btn primary" id="mrh-go">Remis au client</button></div>`;
 const go=ctx.node.querySelector('#mrh-go'),err=ctx.node.querySelector('#mrh-error');
 go.onclick=async()=>{
  if(go.disabled)return;go.disabled=true;err.style.display='none';
  try{
   await api('/logistics/my-returns/'+Number(id)+'/handover','POST',{confirmed:true,note:(ctx.node.querySelector('#mrh-note')?.value||'').trim()});
   if(!ctx.current())return;closeModal();toast('Colis '+tracking+' remis au client');await renderView();
  }catch(e){if(ctx.current()){err.textContent=e.message;err.style.display='block';go.disabled=false}}
 };
}
async function hubPaletteReception(){
 try{
  const data=await api('/logistics/palettes?tab='+encodeURIComponent(hubPaletteTab)),agent=S.user.role==='agent',hubId=Number(S.user.agent_hub_id)||0;
  const rows=(data.rows||[]).filter(d=>(!agent||Number(d.destination_hub_id)===hubId)&&['Départ partiel','En transit','Partiellement reçu'].includes(d.status));
  if(!rows.length){toast('Aucune palette en transit vers votre Hub.');return}
  modal('Reception Palette',`<p class="form-hint">Ouvrez le bon, vérifiez le trajet et scannez chaque colis réellement arrivé. Le manifeste affiche les colis expédiés. Seul le scan de réception les enregistre physiquement au Hub destinataire.</p>${simpleTable(['Référence','Origine → destination','Colis','État',''],rows.map(d=>[`<strong>${esc(d.reference)}</strong><span class="sub">${esc(hubPalettePurposeLabel(d))}</span>`,`${esc(d.source_name)} → ${esc(d.destination_name)}`,`${d.received||0} / ${d.count||0}`,opsTag(d.status),`<button class="btn sm primary" onclick="closeModal();openOpsDocument(${d.id})">Ouvrir</button>`]))}`);
 }catch(e){toast(e.message,true)}
}
async function hubPaletteReviewUnknown(){
 try{
  const result=await api('/logistics/palette-candidates?mode=unresolved_origin');
  hubPaletteUnknownRows=result.rows||[];hubPaletteUnknownHubs=result.available_hubs||[];
  if(!hubPaletteUnknownRows.length){toast('Aucun retour reçu au Central avec une origine numérique inconnue.');return}
  const rows=hubPaletteUnknownRows.map(p=>[
    `<strong>${esc(p.tracking)}</strong><span class="sub">${esc(p.recipient)} · ${esc(p.city||'')}</span>`,
    `${esc(p.status)} · réception Central vérifiée`,
    p.physical_evidence?.length?p.physical_evidence.map(e=>`${esc(e.hub_name)} · ${e.events.map(x=>esc(x.type)+' '+opsDate(x.at)).join(' / ')}`).join('<span class="sub"></span>'):'<span class="tag warn">Aucune trace numérique antérieure</span>',
    `<button class="btn sm primary" onclick="hubPaletteResolveOrigin(${p.id})">Revoir l’origine</button>`
  ]);
  modal('Origines inconnues · Revue Admin',`<div class="form-hint orange">Les retours ci-dessous sont physiquement au Hub Central, mais aucun Hub d’origine n’est enregistré sans ambiguïté. La ville du colis n’est jamais utilisée comme preuve. Si une trace physique n’apparaît pas, une référence papier/scan doit être vérifiée et consignée.</div>${simpleTable(['Colis · destinataire','Statut','Traces de garde physique',''],rows)}`);
 }catch(e){toast(e.message,true)}
}
function hubPaletteResolveOrigin(pid){
 const row=hubPaletteUnknownRows.find(x=>Number(x.id)===Number(pid));if(!row)return;
 const evidence=row.physical_evidence||[],hubs=hubPaletteUnknownHubs||[];
 const options=hubs.map(h=>{const e=evidence.find(x=>Number(x.hub_id)===Number(h.id));return [h.id,`${h.name}${h.city?' · '+h.city:''}${e?' · preuve numérique '+e.events.map(x=>x.type+' '+opsDate(x.at)).join(' / '):' · aucune trace numérique'}`]});
 if(!options.length){toast('Aucun Hub actif différent du Central n’est disponible.',true);return}
 modal('Confirmer le Hub d’origine · '+row.tracking,form(`${select('hub_id','Hub retenu après contrôle physique',options)}${input('evidence_reference','Référence du reçu, scan ou registre','', 'text',true,'minlength="3" maxlength="160"')}${textarea('reason','Motif détaillé de la revue Admin','',true)}<div class="full form-hint orange">Si le système n’a pas de trace numérique au Hub choisi, fournissez la référence d’un reçu/registre physique vérifiable. Toute revue manuelle est journalisée avec l’acteur, la preuve et l’ancien/nouveau Hub. Une origine sans preuve n’est pas envoyée automatiquement.</div><label class="full check-label"><input type="checkbox" name="manual_physical_review" required> J’ai vérifié une preuve de garde physique; si elle est hors système, la référence ci-dessus permet de la retrouver.</label><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme cette revue Admin et l’affectation à l’origine retenue.</label>`,'Enregistrer la revue'));
 bindForm(async d=>{const result=await api('/logistics/parcels/'+pid+'/origin-review','POST',{hub_id:Number(d.hub_id),reason:d.reason,evidence_reference:d.evidence_reference,manual_physical_review:d.manual_physical_review===true,confirmed:d.confirmed===true});hubPaletteTab='retours';await saved('Origine documentée · '+(result.evidence_reference||''))});
}
async function hubPaletteNew(purpose='standard'){
 try{
  const cfg=await opsLoadConfig(),agent=S.user.role==='agent',myHub=Number(S.user.agent_hub_id)||0,central=Number(cfg.central_hub_id)||0;
  const activeHubs=(cfg.hubs||[]).filter(h=>h.active),targets=(cfg.palette_targets||[]).filter(h=>h.id!==central||h.active!==false);
  if(!central||!cfg.central_hub?.active){toast('Configurez un Hub Central actif avant de préparer une palette.',true);return}
  if(agent&&(!myHub||!activeHubs.some(h=>Number(h.id)===myHub))){toast('Aucun Hub actif rattaché à votre compte.',true);return}
  if(agent&&purpose==='return_to_central'&&myHub===central){toast('Le Hub Central ne peut pas envoyer un retour vers lui-même.',true);return}
  if(agent&&purpose==='return_to_origin'&&myHub!==central){toast('Le tri vers le Hub d’origine est réservé au Hub Central.',true);return}
  const sourceChoices=purpose==='return_to_origin'?activeHubs.filter(h=>Number(h.id)===central):purpose==='return_to_central'?activeHubs.filter(h=>Number(h.id)!==central):activeHubs;
  if(!sourceChoices.length){toast('Aucun Hub actif autorisé pour ce type de palette.',true);return}
  const fixedSource=purpose==='return_to_origin'?central:(agent?myHub:null);
  const sourceHub=sourceChoices.find(h=>Number(h.id)===fixedSource)||(cfg.central_hub||{});
  let fixedDestination=purpose==='return_to_central'?central:null;
  if(agent&&myHub!==central&&purpose==='standard')fixedDestination=central;
  let defaultSource=fixedSource||sourceHub.id;
  let destList=targets.filter(h=>Number(h.id)!==Number(defaultSource));
  if(purpose==='return_to_central')destList=targets.filter(h=>Number(h.id)===central);
  if(purpose==='return_to_origin')destList=targets.filter(h=>Number(h.id)!==central);
  if(purpose==='standard'&&Number(defaultSource)!==central)destList=targets.filter(h=>Number(h.id)===central);
  if(purpose==='standard'&&Number(defaultSource)===central)destList=targets.filter(h=>Number(h.id)!==central);
  const destOptions=destList.map(h=>[h.id,`${h.name}${h.city?' · '+h.city:''}`]);
  if(fixedDestination)destOptions.splice(0,destOptions.length,...targets.filter(h=>Number(h.id)===fixedDestination).map(h=>[h.id,`${h.name}${h.city?' · '+h.city:''}`]));
  if(!destOptions.length){toast('Aucun Hub de destination autorisé.',true);return}
  hubPaletteDialog={purpose,cfg,agent,myHub,central,sourceHubs:sourceChoices,targets,fixedSource,fixedDestination,defaultSource};
  const title=purpose==='standard'?'Envoyer Palette':purpose==='return_to_central'?'Envoyer Retour au Central':'Envoyer vers le Hub d’origine';
  const sourceControl=fixedSource?`<input id="hp-source" type="hidden" value="${fixedSource}"><div class="full form-hint">Départ : <b>${esc(sourceHub.name||cfg.central_hub.name)}</b></div>`:`<label class="field"><span>Hub de départ</span><select id="hp-source" onchange="hubPaletteUpdateTargets()">${sourceChoices.map(h=>`<option value="${h.id}" ${Number(h.id)===Number(defaultSource)?'selected':''}>${esc(h.name)} · ${esc(h.city||'')}</option>`).join('')}</select></label>`;
  const destinationControl=fixedDestination?`<input id="hp-destination" type="hidden" value="${fixedDestination}"><div class="full form-hint">Destination : <b>${esc((targets.find(h=>Number(h.id)===fixedDestination)||cfg.central_hub).name)}</b></div>`:`<label class="field"><span>Hub de destination</span><select id="hp-destination" onchange="hubPaletteResetCandidates();hubPaletteLoadCandidates()">${destOptions.map(([id,label])=>`<option value="${id}">${esc(label)}</option>`).join('')}</select></label>`;
  hubPaletteDialog.scans=[];
  // Palette retour : le formulaire ne demande que les informations d'envoi.
  // « Envoyer la palette » ouvre directement l'écran de scan (les CMD s'y ajoutent).
  const returnPalette=purpose!=='standard';
  const scanBlock=returnPalette?'':`<div class="hub-palette-scan"><label class="field full" for="hp-scan"><span>Scanner le colis à envoyer</span><div class="hub-palette-scan-row"><input id="hp-scan" maxlength="80" autocomplete="off" spellcheck="false" placeholder="Scannez ou saisissez le tracking puis Entrée"><button class="btn primary" type="button" id="hp-scan-add" onclick="hubPaletteScanAdd()">${icon('scan')}Ajouter</button></div></label><p class="form-hint">Le serveur vérifie à l’instant que le colis est physiquement à ce Hub et qu’il est admissible.</p><div id="hp-scan-feedback" class="hub-palette-scan-feedback" role="status" aria-live="polite">Présentez le premier colis à envoyer.</div></div><div id="hp-candidates" class="hub-palette-candidates"><p class="sub">Aucun colis scanné pour le moment.</p></div>`;
  const cta=returnPalette?'Envoyer la palette':'Créer la palette';
  const hint=returnPalette?'<div class="full form-hint">Cliquez « Envoyer la palette » : l’écran de scan s’ouvre aussitôt et chaque CMD scannée s’y ajoute avec sa décision (part direct · rendez-vous · à valider).</div>':'';
  modal(title,`<div class="form-grid">${sourceControl}${destinationControl}<label class="field"><span>Transporteur (facultatif)</span><input id="hp-transport" maxlength="120"></label><label class="field"><span>Code de suivi (généré automatiquement)</span><input id="hp-track" maxlength="80" value="${o24AutoTrackingCode()}" title="Rempli automatiquement — remplacez-le seulement si le transporteur fournit son propre numéro"></label><label class="field"><span>Nombre de lots</span><input id="hp-lots" type="number" min="0" max="500" value="0"></label><label class="field full"><span>Note (facultatif)</span><textarea id="hp-note" maxlength="600"></textarea></label>${hint}</div>${scanBlock}<div class="form-actions"><button class="btn primary" id="hp-create" type="button" onclick="hubPaletteCreate()">${cta}</button></div>`);
  const scanInput=document.getElementById('hp-scan');
  if(scanInput){scanInput.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();hubPaletteScanAdd()}});if(innerWidth>760)scanInput.focus({preventScroll:true})}
 }catch(e){toast(e.message,true)}
}
function hubPaletteUpdateTargets(){
 const d=hubPaletteDialog;if(!d)return;if(d.fixedDestination){hubPaletteResetCandidates();return;}
 const src=Number(document.getElementById('hp-source')?.value||d.defaultSource),dest=document.getElementById('hp-destination');if(!dest)return;
 let list=d.targets.filter(h=>Number(h.id)!==src);
  if(d.purpose==='return_to_origin')list=list.filter(h=>Number(h.id)!==d.central);
  else if(d.purpose==='return_to_central'||src!==d.central)list=list.filter(h=>Number(h.id)===d.central);
  else list=list.filter(h=>Number(h.id)!==d.central);
 dest.innerHTML=list.map(h=>`<option value="${h.id}">${esc(h.name)}${h.city?' · '+esc(h.city):''}</option>`).join('');
 hubPaletteResetCandidates();
}
function hubPaletteScanFeedback(message,kind){
 const node=document.getElementById('hp-scan-feedback');if(!node)return;
 node.className='hub-palette-scan-feedback'+(kind?' '+kind:'');node.textContent=message;
}
function hubPaletteRoute(){
 const d=hubPaletteDialog;if(!d)return null;
 const source=Number(document.getElementById('hp-source')?.value||d.defaultSource),destination=Number(document.getElementById('hp-destination')?.value||d.fixedDestination);
 if(!source||!destination)return null;
 return {source,destination,key:source+':'+destination};
}
function hubPaletteScanPaint(){
 const d=hubPaletteDialog,host=document.getElementById('hp-candidates'),button=document.getElementById('hp-create');
 if(!d||!host)return;
 const scans=d.scans||[];
 host.innerHTML=scans.length?`<div class="full form-hint">${scans.length} colis scanné${scans.length===1?'':'s'} · ${scans.reduce((n,p)=>n+(p.parcels||1),0)} colis dans la palette</div><div class="hp-selection-tools"><button type="button" class="btn sm" onclick="hubPaletteScanClear()">Tout retirer</button><span class="sub" id="hp-selected-count">${scans.length} sélectionné${scans.length===1?'':'s'}</span></div>${scans.map(p=>`<div class="check-label hub-palette-candidate hub-palette-scanned"><span class="hp-scanned-main"><b>${esc(p.tracking)}</b> · ${esc(p.recipient||'—')}<small class="sub">${esc(p.city||'')} · ${esc(p.status||'')}${p.forced?' · <b class="hp-forced">dérogation</b>':p.confirmed?' · <b class="hp-forced">rendez-vous confirmé</b>':''}${p.origin_hub?' · origine vérifiée : '+esc(p.origin_hub):''}</small></span><button type="button" class="icon-btn" aria-label="Retirer ${esc(p.tracking)}" title="Retirer ce colis" onclick="hubPaletteScanRemove(${p.id})">×</button></div>`).join('')}`:'<p class="sub">Aucun colis scanné pour le moment.</p>';
 hubPaletteRefreshCreateButton();
}
async function hubPaletteScanAdd(){
 const d=hubPaletteDialog;if(!d)return;
 const input=document.getElementById('hp-scan'),button=document.getElementById('hp-scan-add');
 const tracking=String(input?.value||'').trim();if(!tracking){hubPaletteScanFeedback('Scannez ou saisissez un numéro de suivi.','error');return}
 const route=hubPaletteRoute();
 if(!route){hubPaletteScanFeedback('Choisissez le Hub de départ et la destination.','error');return}
 if(hubPaletteMaterializeChecked())hubPaletteScanPaint();
 if(d.scans.some(p=>String(p.tracking).toUpperCase()===tracking.toUpperCase())){hubPaletteScanFeedback(tracking+' · déjà dans la palette.','warn');if(input){input.value='';input.focus({preventScroll:true})}return}
 if(d.scans.length>=100){hubPaletteScanFeedback('100 colis maximum par palette. Créez cette palette puis recommencez.','error');return}
 if(input)input.disabled=true;if(button)button.disabled=true;
 try{
  const qs=new URLSearchParams({mode:d.purpose,source_hub_id:String(route.source),destination_hub_id:String(route.destination),tracking});
  const result=await api('/logistics/palette-scan?'+qs.toString());
  if(hubPaletteDialog!==d)return;
  const p=result.parcel,decision=result.decision||{code:'accept',message:''};
  const entry={id:p.id,tracking:p.tracking,recipient:p.recipient,city:p.city,status:p.status,origin_hub:p.origin_hub,
               decision:decision.code,decision_message:decision.message,details:decision.details||{}};
  if(decision.code==='accept'){d.scans.push(entry);d.loadedRoute=route.key;hubPaletteScanFeedback('✓ '+p.tracking+' · '+(decision.message||'ajouté au retour'),'ok');hubPaletteScanPaint();return}
  if(decision.code==='double'){d.scans.push(entry);d.loadedRoute=route.key;hubPaletteScanFeedback('⚠ '+p.tracking+' · '+(decision.message||'double scan accepté'),'warn');hubPaletteScanPaint();return}
  // « confirm » (rendez-vous futur) ou « blocked » (règle des 7 jours / passages livreur) :
  // alerte sonore + choix explicite Oui / Non.
  d.pending=entry;
  hubPaletteScanSignal();
  const title=decision.code==='confirm'?'Rendez-vous futur':'Colis non éligible au retour';
  const host=document.getElementById('hp-scan-feedback');
  const details=entry.details||{};
  const facts=[details.appointment?('Rendez-vous : <b>'+details.appointment+'</b>'):'',
               (details.days_at_hub!==undefined)?('Jours au Hub : <b>'+details.days_at_hub+'</b>'):'',
               (details.handovers!==undefined)?('Passages livreur : <b>'+details.handovers+'</b>'):''].filter(Boolean).join(' · ');
  if(host){
    host.className='hub-palette-scan-feedback warn hub-palette-decision';
    host.innerHTML=`<div class="hp-decision"><strong>${title} · ${esc(p.tracking)}</strong>
      <p>${esc(decision.message||'')}</p>${facts?`<p class="sub">${facts}</p>`:''}
      <div class="hp-decision-actions">
       <button type="button" class="btn primary sm" onclick="hubPaletteScanDecide(true)">Oui · entrer dans la palette de retour</button>
       <button type="button" class="btn sm" onclick="hubPaletteScanDecide(false)">Non · reste à l’agence</button>
      </div></div>`;
  }
 }catch(e){
  if(hubPaletteDialog!==d)return;
  hubPaletteScanFeedback((e.message||'Colis refusé.')+' Non ajouté.','error');
 }finally{
  if(hubPaletteDialog===d&&input){input.disabled=false;input.value='';if(innerWidth>760)input.focus({preventScroll:true})}
  if(hubPaletteDialog===d&&button)button.disabled=false;
 }
}
function hubPaletteScanSignal(){
 try{if(window.o24Sound&&typeof window.o24Sound.signal==='function'){window.o24Sound.signal('err');return}}catch(e){}
 try{if(navigator.vibrate)navigator.vibrate([90,60,90])}catch(e){}
}
function hubPaletteScanDecide(accept){
 const d=hubPaletteDialog;if(!d||!d.pending)return;
 const entry=d.pending;d.pending=null;
 const input=document.getElementById('hp-scan');
 if(accept){
  entry.forced=entry.decision==='blocked';
  entry.confirmed=entry.decision==='confirm';
  d.scans.push(entry);d.loadedRoute=hubPaletteRoute()?.key||d.loadedRoute;
  hubPaletteScanFeedback('✓ '+entry.tracking+' entré dans la palette de retour'+(entry.forced?' · dérogation tracée':''),'ok');
  hubPaletteScanPaint();
 }else{
  hubPaletteScanFeedback(entry.tracking+' laissé à l’agence — non envoyé.', 'warn');
 }
 if(input){input.value='';input.focus({preventScroll:true})}
}
function hubPaletteScanRemove(id){
 const d=hubPaletteDialog;if(!d)return;
 const item=(d.scans||[]).find(p=>p.id===id);
 d.scans=(d.scans||[]).filter(p=>p.id!==id);
 hubPaletteScanFeedback(item?item.tracking+' retiré de la palette.':'Colis retiré.','warn');
 hubPaletteScanPaint();
}
function hubPaletteScanClear(){
 const d=hubPaletteDialog;if(!d||!(d.scans||[]).length)return;
 d.scans=[];d.loadedRoute=null;
 hubPaletteScanFeedback('Palette vidée. Vous pouvez recommencer le scan.','warn');
 hubPaletteScanPaint();
 const input=document.getElementById('hp-scan');if(input)input.focus({preventScroll:true});
}
function hubPaletteResetCandidates(){
 if(hubPaletteDialog){
  hubPaletteDialog.loadSerial=(hubPaletteDialog.loadSerial||0)+1;hubPaletteDialog.loadedRoute=null;
  hubPaletteDialog.scans=[];
 }
 const host=document.getElementById('hp-candidates');if(host)host.innerHTML='<p class="sub">Aucun colis scanné pour le moment.</p>';
 const button=document.getElementById('hp-create');if(button)button.disabled=true;
 hubPaletteScanFeedback('Trajet mis à jour : scannez les colis à renvoyer.');
}
async function hubPaletteLoadCandidates(){
 const d=hubPaletteDialog,host=document.getElementById('hp-candidates');if(!d||!host)return;
 const source=Number(document.getElementById('hp-source')?.value||d.defaultSource),destination=Number(document.getElementById('hp-destination')?.value||d.fixedDestination);
 hubPaletteResetCandidates();const serial=d.loadSerial,route=source+':'+destination;
 if(!source||!destination){toast('Choisissez le Hub de départ et de destination.',true);return}
 host.innerHTML='<p class="sub">Chargement des colis du trajet sélectionné…</p>';
 try{
  const qs=new URLSearchParams({mode:d.purpose,source_hub_id:String(source),destination_hub_id:String(destination)}),result=await api('/logistics/palette-candidates?'+qs.toString());
  if(hubPaletteDialog!==d||serial!==d.loadSerial||!host.isConnected)return;
  const available=result.rows||[],rows=available.slice(0,100);d.loadedRoute=route;d.rows=rows;
  if((d.scans||[]).length){d.scans=[]}
 const badge=p=>p.decision==='accept'?`<span class="tag good">Part direct</span>`:p.decision==='double'?`<span class="tag warn">Déjà Livré</span>`:p.decision==='confirm'?`<span class="tag warn">Rendez-vous · OUI requis</span>`:p.decision==='blocked'?`<span class="tag bad">À valider</span>`:'';
 const facts=p=>[p.days_at_hub!==undefined&&p.days_at_hub!==null?p.days_at_hub+' j':'',p.handovers!==undefined&&p.handovers!==null?p.handovers+' passage(s) livreur':'',p.appointment?'RDV '+p.appointment:''].filter(Boolean).join(' · ');
 host.innerHTML=rows.length?`<div class="full form-hint">${rows.length} colis physiquement au Hub de départ.${available.length>100?' Une palette contient 100 colis maximum : préparez-en une autre pour le reste.':''} ${d.purpose==='standard'?'Scannez-les ou cochez-les : chaque colis coché entre dans la palette.':'Scannez-les ou cochez-les : la coche vaut validation (OUI).'}</div><div class="hp-selection-tools"><button type="button" class="btn" id="hp-select-all" onclick="hubPaletteSelectAll(true)">${icon('check')}Sélectionner tout</button><button type="button" class="btn" id="hp-clear-all" onclick="hubPaletteSelectAll(false)">${icon('close')}Tout désélectionner</button><span class="sub hp-selected-count" id="hp-selected-count">0 / ${rows.length} sélectionnés</span></div>${rows.map(p=>`<label class="check-label hub-palette-candidate"><input class="hp-pick" type="checkbox" value="${p.id}" data-decision="${esc(p.decision||'')}" onchange="hubPaletteSelectionChanged()"><span><b>${esc(p.tracking)}</b> · ${esc(p.recipient)} ${badge(p)}<small class="sub">${esc(p.city||'')} · ${esc(p.status)}${facts(p)?' · '+esc(facts(p)):''}${p.origin_hub?' · origine vérifiée : '+esc(p.origin_hub):''}</small></span></label>`).join('')}`:empty('Aucun colis au Hub de départ','Aucun colis physiquement enregistré dans ce Hub. Scannez d’abord les colis à leur réception, puis revenez ici.');
  hubPaletteSelectionChanged();
 }catch(e){if(hubPaletteDialog===d&&serial===d.loadSerial&&host.isConnected){host.textContent=e.message;toast(e.message,true)}}
}
/* Sélection d'une palette : le scan ET les cases cochées comptent.
   Avant, seuls les colis scannés partaient : cocher une case puis « Créer la palette »
   répondait « Scannez au moins un colis à envoyer ». */
function hubPalettePickedItems(scans,rows,checkedIds){
 const picked=new Map((scans||[]).map(p=>[Number(p.id),{...p}]));
 for(const raw of (checkedIds||[])){
  if(raw===null||raw===undefined||raw==='')continue;
  const id=Number(raw);if(!Number.isFinite(id)||id<=0||picked.has(id))continue;
  const row=(rows||[]).find(r=>Number(r.id)===id)||{};
  picked.set(id,{id,tracking:row.tracking||'',decision:row.decision||'accept',confirmed:false,forced:false});
 }
 return [...picked.values()].map(p=>({...p,confirmed:!!p.confirmed||p.decision==='confirm'}));
}
function hubPaletteSelectAll(checked){document.querySelectorAll('#hp-candidates .hp-pick').forEach(x=>x.checked=checked);hubPaletteSelectionChanged()}
function hubPaletteSelectionChanged(){
 const all=document.querySelectorAll('#hp-candidates .hp-pick'),n=document.querySelectorAll('#hp-candidates .hp-pick:checked').length,count=document.getElementById('hp-selected-count');
 if(count)count.textContent=n+' / '+all.length+' sélectionnés';
 hubPaletteRefreshCreateButton();
}
/* Le bouton « Créer la palette » s'active dès qu'un colis est scanné OU coché. */
function hubPaletteRefreshCreateButton(){
 const button=document.getElementById('hp-create');if(!button)return;
 const scanned=(hubPaletteDialog?.scans||[]).length;
 const checked=document.querySelectorAll('#hp-candidates .hp-pick:checked').length;
 button.disabled=!(scanned||checked);
}
/* Les cases cochées deviennent des lignes de palette avant tout nouveau scan :
   la sélection ne se perd plus quand la liste est repeinte. */
function hubPaletteMaterializeChecked(){
 const d=hubPaletteDialog;if(!d)return 0;
 const ids=[...document.querySelectorAll('#hp-candidates .hp-pick:checked')].map(x=>Number(x.value));
 if(!ids.length)return 0;
 d.scans=hubPalettePickedItems(d.scans,d.rows,ids);
 return ids.length;
}
async function hubPaletteCreate(){
 const d=hubPaletteDialog;if(!d)return;
 const returnPalette=d.purpose!=='standard';
 const sourceHub=Number(document.getElementById('hp-source')?.value||d.defaultSource);
 const destinationHub=Number(document.getElementById('hp-destination')?.value||d.fixedDestination);
 if(!sourceHub||!destinationHub){toast('Choisissez le Hub de départ et la destination.',true);return}
 if(!returnPalette){
  // Palette standard : le scan et les cases cochées désignent les colis à envoyer.
  const checkedIds=[...document.querySelectorAll('#hp-candidates .hp-pick:checked')].map(x=>Number(x.value));
  const picked=hubPalettePickedItems(d.scans,d.rows,checkedIds);
  if(!picked.length){toast('Scannez ou cochez au moins un colis à envoyer.',true);return}
  const selectedRoute=sourceHub+':'+destinationHub;
  if(d.loadedRoute!==selectedRoute){hubPaletteResetCandidates();toast('Le trajet a changé : rescannez ou recochez les colis.',true);return}
  const blocked=picked.filter(p=>p.decision==='blocked');
  if(blocked.length){toast('Retour non éligible pour '+blocked.map(p=>p.tracking||('colis '+p.id)).join(', ')+' : scannez ce colis pour la dérogation.',true);return}
  if(picked.length>100){toast('Une palette contient 100 colis maximum. Décochez le surplus.',true);return}
  const parcel_ids=picked.map(p=>p.id);
  const confirmed_ids=picked.filter(p=>p.confirmed).map(p=>p.id),overridden_ids=picked.filter(p=>p.forced).map(p=>p.id);
  const body={kind:'transfer',palette_purpose:d.purpose,source_hub_id:sourceHub,destination_hub_id:destinationHub,parcel_ids,confirmed_ids,overridden_ids,
   transport:document.getElementById('hp-transport')?.value||'',tracking_code:document.getElementById('hp-track')?.value||'',
   lots:Number(document.getElementById('hp-lots')?.value||0),note:document.getElementById('hp-note')?.value||''};
  try{const r=await api('/logistics/documents','POST',body);hubPaletteDialog=null;closeModal();hubPaletteTab='default';toast('Palette préparée · '+r.reference);await renderView();await openOpsDocument(r.id)}catch(e){toast(e.message,true)}
  return;
 }
 // Palette retour : créée vide, puis écran de scan immédiat (les CMD s'ajoutent au scan).
 const body={kind:'transfer',palette_purpose:d.purpose,source_hub_id:sourceHub,destination_hub_id:destinationHub,parcel_ids:[],
  transport:document.getElementById('hp-transport')?.value||'',tracking_code:document.getElementById('hp-track')?.value||'',
  lots:Number(document.getElementById('hp-lots')?.value||0),note:document.getElementById('hp-note')?.value||''};
 try{const r=await api('/logistics/documents','POST',body);hubPaletteDialog=null;closeModal();
  hubPaletteTab=d.purpose==='return_to_origin'?'a-recevoir':'retours';
  toast('Palette '+r.reference+' ouverte · scannez les CMD');
  await renderView();await openOpsDocument(r.id)}catch(e){toast(e.message,true)}
}
async function newOpsDocument(kind='pickup',fixedKind=false){
 try{await opsLoadConfig();if(!opsConfig.hubs.some(h=>h.active)){toast('Créez au moins un hub actif avant de préparer un document.',true);await navigate('ops-settings');return}
 if(kind==='transfer'&&(!opsConfig.central_hub||!opsConfig.central_hub.active)){toast('Désignez un Hub Central actif avant de préparer une palette inter-Hubs.',true);await navigate('ops-settings');return}
 const hubOptions=[['','Choisir'],...opsConfig.hubs.filter(h=>h.active).map(h=>[h.id,`${h.name}${Number(h.id)===Number(opsConfig.central_hub_id)?' · Central Hub':''}`])];
 const kindField=fixedKind?`<input type="hidden" name="kind" value="${esc(kind)}"><div class="full form-hint"><b>${esc(opsKinds[kind])}</b> · Pour un retour interne, inversez le hub de départ et le hub de destination.</div>`:`<div class="full">${select('kind','Type de document',Object.entries(opsKinds),kind)}</div>`;
 const note=kind==='transfer'?'Chaque palette doit relier le Hub Central actif à un autre Hub; aucun transfert direct entre deux Hubs secondaires. Pour un mouvement retour, inversez le trajet. Les colis restent bloqués contre les modifications jusqu’à réception complète ou annulation avant départ.':'Le bon fige les références et le trajet. Les colis seront bloqués contre les modifications jusqu’à réception complète ou annulation avant départ.';
 modal('Préparer · '+opsKinds[kind],form(`${kindField}${kind!=='transfer'?select('client_id','Client',[['','Choisir un client'],...clientOptions()]):''}${select('driver_id','Transporteur du document',[['','Non affecté'],...S.users.filter(u=>u.role==='livreur'&&u.active).map(u=>[u.id,u.name])],'',false)}${kind!=='pickup'?select('source_hub_id','Hub de départ',hubOptions):''}${kind!=='return'?select('destination_hub_id','Hub de destination',hubOptions):''}<div class="field full"><label for="ops-parcel-list">Colis à rattacher (100 maximum)</label><select id="ops-parcel-list" multiple size="8" required></select><small class="sub">Ctrl / Cmd pour plusieurs lignes. Seuls les statuts compatibles sont proposés ; les autres verrous sont vérifiés côté serveur.</small></div>${textarea('note','Note visible aux parties du document')}<div class="full form-hint">${note}</div>`,'Créer le document'),true);
 if(!fixedKind)$('#f-kind').onchange=e=>newOpsDocument(e.target.value);
 function options(){const cid=Number($('#f-client_id')?.value),sourceId=Number($('#f-source_hub_id')?.value);$('#ops-parcel-list').innerHTML=S.parcels.filter(p=>kind==='transfer'?(sourceId>0&&Number(p.current_hub_id)===sourceId&&['Ramassé','Au hub','Réceptionné'].includes(p.status)):kind==='pickup'?(p.client_id===cid&&['Créé','Ramassé'].includes(p.status)):kind==='return'?(p.client_id===cid&&['Refusé','Retourné'].includes(p.status)):false).map(p=>`<option value="${p.id}">${esc(p.tracking)} · ${esc(p.recipient)} · ${esc(p.city)} · ${esc(p.status)}</option>`).join('')}
 if($('#f-client_id'))$('#f-client_id').onchange=options;if($('#f-source_hub_id'))$('#f-source_hub_id').onchange=options;options();
 bindForm(async d=>{const parcel_ids=[...$('#ops-parcel-list').selectedOptions].map(o=>Number(o.value));const r=await api('/logistics/documents','POST',{...d,parcel_ids});await refresh();await renderView();await openOpsDocument(r.id);toast('Document créé, colis rattachés')});
 }catch(e){toast(e.message,true)}
}
async function openOpsDocument(id,detailOnly=false){
 try{
  opsDoc=await api('/logistics/documents/'+id);
  if(opsDoc.kind==='partner_palette')return openPartnerPalette(id);
  const d=opsDoc,admin=S.user.role==='admin',hubManager=S.user.role==='agent',myHubId=Number(S.user.agent_hub_id)||0;
  const canScanDeparture=admin||(hubManager&&d.kind==='transfer'&&Number(d.source_hub_id)===myHubId);
  const canScanArrival=admin||(hubManager&&d.kind==='transfer'&&Number(d.destination_hub_id)===myHubId);
  const departureProgress=d.departure_scan_required?`<div class="ops-receipt-count"><strong>${d.departure_scanned} / ${d.count}</strong><span>colis scannés pour le départ${d.departure_reconciled_count?` · ${d.departure_reconciled_count} retiré(s) du manifeste`:''}</span></div>`:'';
  const departureForm=canScanDeparture&&d.kind==='transfer'&&['Préparé','Départ partiel'].includes(d.status)?`<button class="btn primary" onclick="openDispatchCollection('transfer',${id})">Envoyer au scan · collecte</button>`:'';
  const canReceive=['En transit','Partiellement reçu','Départ partiel'].includes(d.status);
  if(canScanDeparture&&d.kind==='transfer'&&['Préparé','Départ partiel'].includes(d.status)&&!detailOnly)return openDispatchCollection('transfer',id);
  if(canScanArrival&&canReceive&&!detailOnly)return openReceptionCollection('transfer',id);
  const receiveForm=canScanArrival&&canReceive?`<button class="btn primary" onclick="openReceptionCollection('transfer',${id})">Réception au scan · collecte</button>`:'';
  const lines=simpleTable(['Colis','Destinataire / Ville','Statut à la préparation','Situation actuelle','Scan de sortie','Réception'],d.lines.map(l=>[esc(l.tracking),`${esc(l.recipient)}<span class="sub">${esc(l.city)}</span>`,tag(l.initial_status),tag(l.current_status||l.initial_status),d.departure_scan_required?(l.departure_reconciled_at?`<span class="tag warn">Resté au Hub · ${opsDate(l.departure_reconciled_at)}</span>${admin&&l.departure_reconciliation_reason?`<span class="sub ops-wrap">Motif : ${esc(l.departure_reconciliation_reason)}</span>`:''}`:l.departure_scanned_at?`<span class="green">Scanné · ${opsDate(l.departure_scanned_at)}</span>`:'À scanner'):'—',l.departure_reconciled_at?'<span class="sub">Retiré du transfert</span>':l.received_at?`<span class="green">${opsDate(l.received_at)}</span>`:'En attente']));
  const actions=(admin&&d.status==='Préparé'?`<button class="btn danger" onclick="opsDocAction('cancel')">Annuler le bon</button>${d.departure_scan_required?'':`<button class="btn primary" onclick="opsDocAction('dispatch')">${icon('truck')}Confirmer le départ</button>`}`:'')+(admin&&d.kind==='transfer'&&d.departure_scan_required&&d.status==='Départ partiel'&&d.lines.some(l=>l.active&&!l.departure_scanned_at&&!l.departure_reconciled_at)?`<button class="btn danger" onclick="opsReconcileDeparture(${id})">${icon('alert')}Réconcilier les colis restés au Hub</button>`:'');
  modal(d.reference,`<div class="ops-document-head"><div><span class="eyebrow orange">${opsKinds[d.kind]}</span><h3>${esc(d.source_name)} → ${esc(d.destination_name)}</h3><p>${esc(d.client_name||'Plusieurs clients')} · ${esc(d.driver_name||'Transporteur non affecté')}</p><p>Préparé le ${opsDate(d.created_at)} · Version ${d.revision}</p></div><div>${opsTag(d.status)}${d.qr?`<img class="ops-doc-qr" src="${d.qr}" alt="QR du document ${esc(d.reference)}">`:''}</div></div><div class="ops-receipt-count${d.status!=='Annulé'&&d.received<d.count&&['En transit','Partiellement reçu'].includes(d.status)?' ops-receipt-ecart':''}"><strong>${d.received} / ${d.count}</strong><span>colis reçus${d.status==='Annulé'?' · bon annulé':` · écart théorique/physique : ${d.count-d.received} restant(s)`}</span>${d.status!=='Annulé'&&d.received<d.count&&['En transit','Partiellement reçu'].includes(d.status)?`<strong class="ops-ecart-badge">${icon('alert')}Écart −${d.count-d.received}</strong>`:''}</div>${departureProgress}${opsEtaAt(d)?`<p class="form-hint ops-eta-line">${icon('clock')}Arrivée estimée : <b>${opsDate(opsEtaAt(d).toISOString())}</b> — hypothèse navette quotidienne (départ + 24 h)${opsEtaAt(d).getTime()<Date.now()?' · <b style="color:#b46300">en retard</b>':''}</p>`:''}${d.note?`<p class="form-hint" data-no-translate>${esc(d.note)}</p>`:''}${d.cancel_reason?`<p class="form-hint orange">Annulation : <span data-no-translate>${esc(d.cancel_reason)}</span></p>`:''}${departureForm}${receiveForm}${lines}<details class="ops-history"><summary>Historique du document (${d.audit.length})</summary><div class="timeline">${d.audit.map(a=>`<div class="timeline-item"><b>${esc(a.action)}</b><p data-no-translate>${esc(a.details.tracking||a.details.reason||'')}</p><small data-no-translate>${esc(a.actor)} · ${opsDate(a.created_at)}</small></div>`).join('')}</div></details><div class="form-actions">${actions}<button class="btn" onclick="printOpsDocument(${id})">${icon('print')}Imprimer / PDF</button></div>`,true);


 }catch(e){toast(e.message,true)}
}
function opsDocAction(action){const d=opsDoc;if(action==='dispatch'&&d.kind==='transfer')return openDispatchCollection('transfer',d.id);modal(action==='dispatch'?'Confirmer la remise physique ?':'Annuler le document ?',form(`${action==='cancel'?textarea('reason','Motif obligatoire','',true):`<div class="full form-hint">${esc(d.reference)} · ${d.count} colis. Après départ, une annulation simple n’est plus possible : chaque colis doit être reçu et contrôlé.</div>`}`,action==='cancel'?'Annuler le document':'Confirmer le départ'));bindForm(async data=>{await api409(f=>api('/logistics/documents/'+d.id+'/'+action,'POST',{...data,revision:f?f.revision:d.revision}),async()=>({revision:(await api('/logistics/documents/'+d.id)).revision}));await refresh();await renderView();await openOpsDocument(d.id);toast('Document mis à jour')})}
async function opsReconcileDeparture(id){
 const d=opsDoc,candidates=(d?.lines||[]).filter(l=>l.active&&!l.departure_scanned_at&&!l.departure_reconciled_at);
 if(!d||d.id!==id||!candidates.length){toast('Aucune ligne non partie à réconcilier.',true);return}
 modal('Réconcilier les colis restés au Hub',form(`<div class="full form-hint orange"><b>${esc(d.reference)}</b> · Cette action détache uniquement les lignes sélectionnées qui n’ont pas de scan de sortie. Les colis déjà sortis restent liés au manifeste et poursuivent leur trajet.</div><div class="field full"><label>Choisissez les colis qui sont réellement restés au Hub source</label><div style="display:grid;gap:6px;max-height:240px;overflow:auto;border:1px solid var(--line);border-radius:7px;padding:10px">${candidates.map(l=>`<label class="check-label" style="margin:0"><input class="ops-reconcile-line" type="checkbox" name="reconcile_line_${l.id}" value="${l.id}"><span>${esc(l.tracking)} · ${esc(l.recipient)} · ${esc(l.city)}</span></label>`).join('')}</div><small class="sub">Le serveur revérifie que chaque colis est toujours au Hub de départ et n’a pas été scanné.</small></div>${textarea('reason','Motif obligatoire de la réconciliation','',true)}<label class="full check-label"><input type="checkbox" name="confirmed" required> J’ai vérifié physiquement que les colis sélectionnés ne sont pas partis du Hub.</label>`,'Réconcilier les lignes'));
 bindForm(async data=>{
  const line_ids=[...document.querySelectorAll('.ops-reconcile-line:checked')].map(x=>Number(x.value));
  if(!line_ids.length)throw Error('Sélectionnez au moins un colis resté au Hub.');
  if(data.confirmed!==true)throw Error('Confirmez le contrôle physique des colis.');
  await api('/logistics/documents/'+id+'/reconcile-departure','POST',{line_ids,reason:data.reason,revision:d.revision,confirmed:true});
  await refresh();await renderView();await openOpsDocument(id);toast('Réconciliation enregistrée; les départs et réceptions ont été recalculés.')
 });
}
function findOpsDocument(kind=null){modal(kind==='transfer'?'Rechercher une palette inter-hubs':'Rechercher un document',form(input('reference','Référence du bon / QR','','text',true),'Ouvrir'));bindForm(async d=>{const docs=await api('/logistics/documents');const found=docs.find(x=>(!kind||x.kind===kind)&&x.reference.toUpperCase()===d.reference.trim().toUpperCase());if(!found)throw Error(kind==='transfer'?'Aucune palette inter-hubs accessible dans les 500 derniers documents.':'Aucun document accessible dans les 500 derniers.');await openOpsDocument(found.id)})}
async function printOpsDocument(id){
 const owner=S?.user?.id;
 try{
  const d=await api('/logistics/documents/'+id);if(S?.user?.id!==owner)return;
  if(['transfer','return','pickup'].includes(d.kind)){
   const src=d.source_hub||{},dest=d.destination_hub||{},contact=d.client_contact||{};
   const isTransfer=d.kind==='transfer',isPickup=d.kind==='pickup';
   const clientName=d.client_name||contact.company||contact.legal_name||contact.name||'Client';
   const party=isPickup?{
    label:'Hub de réception',name:dest.name||d.destination_name||'—',
    lines:[dest.address,dest.city?`Réception · ${dest.city}`:'',d.driver_name?`Livreur : ${d.driver_name}`:'']
   }:isTransfer?{
    label:'Hubs concernés',name:`${src.name||d.source_name||'Hub de départ'} → ${dest.name||d.destination_name||'Hub de réception'}`,
    lines:[src.address,src.city?`Départ · ${src.city}`:'',dest.address,dest.city?`Réception · ${dest.city}`:'']
   }:{
    label:'Client destinataire',name:clientName,
    lines:[contact.name&&contact.name!==clientName?'Contact : '+contact.name:'',contact.phone?'Tél. : '+contact.phone:'',contact.email,contact.address]
   };
   const departedOnly=isTransfer&&d.departure_scan_required&&['Départ partiel','En transit','Partiellement reçu','Reçu'].includes(d.status);
   const printLines=(d.lines||[]).filter(l=>!l.departure_reconciled_at&&(!departedOnly||l.departure_scanned_at));
   const printCount=departedOnly?d.departure_scanned:d.count;
   const isReturnPalette=isTransfer&&['return_to_central','return_to_origin'].includes(d.palette_purpose||'standard');
   const nature=d.kind==='pickup'?'RAMASSAGE':(d.kind==='return'||isReturnPalette)?'RETOUR':'RÉCEPTION';
   const natureNote=nature==='RAMASSAGE'?'Colis ramassés à réceptionner au Hub':nature==='RETOUR'?(isReturnPalette?(d.palette_purpose==='return_to_central'?'Retour vers le Hub Central':'Retour vers le Hub d’origine'):'Retour à remettre au vendeur'):'Transfert inter-Hub à réceptionner';
   const printData={
    title:nature==='RAMASSAGE'?'Bon de ramassage':nature==='RETOUR'?'Bon de retour':'Bon d’envoi · transfert inter-hubs',nature,nature_note:natureNote,
    reference:d.reference,date:opsDate(d.dispatched_at||d.created_at),status:d.status,
    route:isPickup?`${d.driver_name||'Livreur'} → ${dest.name||d.destination_name}`:isTransfer?`${src.name||d.source_name} → ${dest.name||d.destination_name}`:`${src.name||d.source_name||'Hub'} → ${clientName}`,
    party,count:printCount,received:d.received,remaining:Math.max(0,printCount-d.received),
    note:[d.note,departedOnly&&d.count>printCount?`${d.count-printCount} colis en attente de départ, non inclus dans ce bon.`:'',d.departure_reconciled_count?`${d.departure_reconciled_count} colis sont restés au Hub source et ont été retirés du manifeste.`:'',d.cancel_reason?`Annulation : ${d.cancel_reason}`:''].filter(Boolean).join(' · '),
    rows:printLines.map(l=>({tracking:l.tracking,city:l.city,recipient:l.recipient,phone:l.phone,amount:l.amount})),
    signatures:isPickup?['Livreur','Transporteur','Réception par le hub']:isTransfer?['Hub de départ','Transporteur','Réception par le hub destination']:['Responsable du hub','Transporteur','Réception par le client']
   };
   await doPrint(o24BonHtml(printData),root=>{if(S?.user?.id!==owner){root.innerHTML='';throw Error('Session modifiée. Rouvrez le document.')}});
   return;
  }
  await doPrint(`<style>@page{size:A4;margin:12mm}#print-root{padding:0}#print-root table{font-size:10px}#print-root th,#print-root td{padding:7px}#print-root thead{display:table-header-group}</style><img class="wordmark" src="/static/wordmark.png" alt="ORIENTAL24">${d.qr?`<img style="float:right;width:85px" src="${d.qr}" alt="QR">`:''}<h1>${opsKinds[d.kind]} · ${esc(d.reference)}</h1><p>${esc(d.source_name)} → ${esc(d.destination_name)}<br>Client : ${esc(d.client_name||'Multi-clients')}<br>Transporteur : ${esc(d.driver_name||'Non affecté')}<br>État : ${esc(d.status)} · ${d.received}/${d.count} colis reçus<br>Créé le ${opsDate(d.created_at)}</p><table><thead><tr><th>Référence</th><th>Destinataire</th><th>Ville</th><th>Statut initial</th><th>Reçu le</th></tr></thead><tbody>${d.lines.map(l=>`<tr><td>${esc(l.tracking)}</td><td>${esc(l.recipient)}</td><td>${esc(l.city)}</td><td>${esc(l.initial_status)}</td><td>${opsDate(l.received_at)}</td></tr>`).join('')}</tbody></table><p data-no-translate>${esc(d.note||'')}${d.cancel_reason?'<br>ANNULÉ : '+esc(d.cancel_reason):''}</p><p>Document interne de démonstration. État imprimé le ${opsDate(new Date().toISOString())}. Les réceptions sont des déclarations de l’administration, pas des signatures électroniques. Aucun règlement bancaire déclenché.</p>`,root=>{if(S?.user?.id!==owner){root.innerHTML='';throw Error('Session modifiée.')}})
 }catch(e){if(S?.user?.id===owner)toast(e.message,true)}
}
function opsSettingsView(config){
 opsConfig=config;
 const central=config.central_hub,activeHubs=config.hubs.filter(h=>h.active);
 const centralLabel=central&&central.active?`${esc(central.name)} · ${esc(central.city)}`:config.central_hub_id?`Hub inactif ou introuvable · ID ${config.central_hub_id}`:'Aucun Hub Central désigné';
 const centralStatus=central&&central.active?'Actif':config.central_hub_id?'À corriger':'À configurer';
 const hubs=config.hubs.map(h=>{
  const manager=h.manager,activeManager=manager&&manager.active;
  const managerCell=manager?`${esc(manager.name)}<span class="sub">${esc(manager.email)} · ${manager.active?'Actif':'Désactivé'}${h.active_manager_count>1?' · Conflit : plusieurs comptes actifs':''}</span>`:'<span class="tag warn">Aucun responsable</span>';
  const managerAction=activeManager?`<button class="btn sm" onclick="opsHubManagerReplaceForm(${h.id})">${icon('user')}Remplacer responsable</button>`:`<button class="btn sm" onclick="opsHubManagerForm(${h.id})">${icon('user')}Ajouter responsable</button>`;
  return [esc(h.name),`${esc(h.city)}<span class="sub">${esc(h.address)}</span>`,(h.coverage||[]).map(c=>esc(c.city)).join(' · ')||'<span class="sub">Aucune ville attribuée · fallback Central</span>',managerCell,opsTag(h.active?'Actif':'Inactif'),`${managerAction}<button class="btn sm" onclick="opsHubForm(${h.id})">Modifier</button>`];
 });
 return heading('Hubs & motifs','Chaque ville est attribuée à un seul Hub. Les villes non attribuées utilisent le Hub Central désigné comme solution de secours. L’attribution ne modifie pas l’ouverture livraison/ramassage.',`<button class="btn" onclick="opsReasonForm()">${icon('plus')}Ajouter un motif</button><button class="btn primary" onclick="opsHubForm()">${icon('plus')}Ajouter un hub</button>`)+
 `<section class="card"><div class="card-head"><div><h3>Hub Central</h3><p>Point de consolidation et de départ du réseau. Le fallback des villes sans Hub attribué est configuré ici; les trajets des manifestes inter-Hubs restent soumis aux règles de transfert.</p></div>${opsTag(centralStatus)}</div><div class="ops-action-row"><strong>${centralLabel}</strong><button class="btn primary" ${activeHubs.length?'':'disabled'} onclick="opsCentralHubForm()">${icon('edit')}${config.central_hub_id?'Changer le Hub Central':'Désigner le Hub Central'}</button></div><p class="sub">Un seul Hub actif peut être désigné. Le changement ne modifie pas les manifestes existants; choisissez d’abord un nouveau Hub Central avant de désactiver l’actuel.</p></section>`+
 `<section class="card ops-margin"><div class="card-head"><div><h3>Hubs configurés</h3><p>Chaque Hub a son responsable et des villes attribuées. Désactiver un Hub n’efface pas les documents existants.</p></div></div>${simpleTable(['Hub','Ville du Hub / adresse','Villes attribuées','Responsable de Hub','État','Actions'],hubs)}</section><section class="card ops-margin"><div class="card-head"><div><h3>Motifs de suivi et de tentative</h3><p>Les libellés des anciennes tentatives restent figés.</p></div></div>${simpleTable(['Code','Motif','État',''],config.reasons.map(r=>[esc(r.code),esc(r.label),opsTag(r.active?'Actif':'Inactif'),`<button class="btn sm" onclick='opsReasonForm(${JSON.stringify(r.code)})'>Modifier</button>`]))}</section>`
}
function opsCentralHubForm(){
 const active=(opsConfig?.hubs||[]).filter(h=>h.active);
 if(!active.length){toast('Créez un Hub actif avant de désigner le Hub Central.',true);return}
 const options=[['','Choisir un Hub actif'],...active.map(h=>[h.id,`${h.name} · ${h.city}`])];
 modal('Désigner le Hub Central',form(`${select('hub_id','Hub Central',options,opsConfig.central_hub_id||'')}<div class="full form-hint">Ce choix devient la valeur de secours des villes sans Hub attribué. Les règles existantes de transfert inter-Hubs restent inchangées; les manifestes historiques ne sont pas réécrits.</div>`,'Enregistrer le Hub Central'));
 bindForm(async d=>{const hub_id=Number(d.hub_id);if(!Number.isSafeInteger(hub_id)||hub_id<=0)throw Error('Choisissez un Hub actif.');const result=await api('/logistics/central-hub','PATCH',{hub_id});await saved(result.changed?'Hub Central modifié et historisé':'Hub Central inchangé')})
}
function opsHubForm(id){
 const h=opsConfig.hubs.find(h=>h.id===id)||{},cities=opsConfig.cities||S.cities||[],covered=new Set((h.covered_city_ids||[]).map(Number));
 const cityAssignments=`<div class="field full"><label>Villes attribuées à ce Hub</label><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px;max-height:230px;overflow:auto;border:1px solid var(--line);border-radius:7px;padding:10px">${cities.map(c=>{const currentId=Number(c.hub_id)||0,label=currentId===Number(id)?'Déjà attribuée à ce Hub':currentId?`Actuellement : ${esc(c.hub_name||'Hub #'+currentId)}`:'Non attribuée';return `<label class="check-label" style="margin:0"><input class="hub-assignment-city" type="checkbox" value="${c.id}" ${covered.has(Number(c.id))?'checked':''}><span>${esc(c.name)} · ${esc(c.region||'')}<small class="sub" style="display:block">${label}</small></span></label>`}).join('')}</div><small class="sub">Une ville ne peut être attribuée qu’à un Hub. Cocher une ville déjà attribuée la transfère ici. Cela ne change pas les interrupteurs livraison/ramassage.</small></div>`;
 const managerFields=!id?`<div class="full form-hint"><b>Responsable unique de ce Hub</b> · Le compte sera créé dans la même transaction que le Hub.</div>${input('manager_name','Nom du responsable')}${input('manager_email','E-mail de connexion','','email')}${input('manager_phone','Téléphone (facultatif)','','tel',false)}${input('manager_password','Mot de passe initial','','password',true,'minlength="10" autocomplete="new-password"')}<div class="full form-hint">Minimum 10 caractères. Le mot de passe n’est pas ajouté aux journaux d’audit. Transmettez-le au responsable par un canal sûr.</div>`:'';
 modal(id?'Modifier un Hub':'Nouveau Hub',form(`${input('name','Nom du Hub',h.name||'')}${select('city_id','Ville physique du Hub',cities.map(c=>[c.id,c.name]),h.city_id||'')}${textarea('address','Adresse',h.address||'',true)}${cityAssignments}${managerFields}${id?`<label class="check-label"><input type="checkbox" name="active" ${h.active?'checked':''}>Hub actif</label>`:''}`));
 bindForm(async d=>{d.city_ids=[...document.querySelectorAll('.hub-assignment-city:checked')].map(x=>Number(x.value));await api('/logistics/hubs'+(id?'/'+id:''),id?'PATCH':'POST',d);await saved(id?'Hub et villes attribuées enregistrés':'Hub, responsable et villes attribuées enregistrés')})
}
function opsHubManagerForm(hubId){
 const h=opsConfig.hubs.find(x=>Number(x.id)===Number(hubId));if(!h){toast('Hub introuvable.',true);return}
 if(h.active_manager_count>0){toast('Ce Hub possède déjà un responsable actif.',true);return}
 modal('Ajouter un responsable · '+esc(h.name),form(`${input('manager_name','Nom du responsable')}${input('manager_email','E-mail de connexion','','email')}${input('manager_phone','Téléphone (facultatif)','','tel',false)}${input('manager_password','Mot de passe initial','','password',true,'minlength="10" autocomplete="new-password"')}<div class="full form-hint">Minimum 10 caractères. Le compte sera rattaché uniquement à ce Hub. Le mot de passe n’est pas ajouté aux journaux d’audit.</div>`,'Créer le compte'));
 bindForm(async d=>{await api('/logistics/hubs/'+hubId+'/manager','POST',d);await saved('Compte du responsable créé et rattaché au Hub')})
}
function opsHubManagerReplaceForm(hubId){
 const h=opsConfig.hubs.find(x=>Number(x.id)===Number(hubId));if(!h){toast('Hub introuvable.',true);return}
 modal('Remplacer le responsable · '+esc(h.name),form(`<div class="full form-hint orange">Tous les responsables actifs${h.manager?`, dont ${esc(h.manager.name)}`:''} seront désactivés et leurs sessions révoquées dans la même transaction que la création du remplaçant. En cas d’erreur, le compte actuel reste actif.</div>${input('manager_name','Nom du nouveau responsable')}${input('manager_email','E-mail de connexion','','email')}${input('manager_phone','Téléphone (facultatif)','','tel',false)}${input('manager_password','Mot de passe initial','','password',true,'minlength="10" autocomplete="new-password"')}<div class="full form-hint">Minimum 10 caractères. Le mot de passe n’est pas ajouté aux journaux d’audit. Transmettez-le par un canal sûr.</div>`,'Remplacer le responsable'));
 bindForm(async d=>{await api('/logistics/hubs/'+hubId+'/manager/replace','POST',d);await saved('Responsable remplacé atomiquement')})
}
function opsReasonForm(code){const r=opsConfig.reasons.find(r=>r.code===code)||{};modal(code?'Modifier un motif':'Nouveau motif',form(`${input('code','Code technique',r.code||'','text',true,code?'readonly':'pattern="[a-z][a-z0-9_-]{1,39}"')}${input('label','Libellé visible',r.label||'')}<label class="check-label"><input type="checkbox" name="active" ${r.active!==0?'checked':''}>Motif actif</label>`));bindForm(async d=>{await api('/logistics/reasons','POST',d);await saved('Motif enregistré')})}
async function openOpsParcel(id){try{opsParcel=await api('/logistics/parcels/'+id);const {parcel:p,attempts,documents,tickets}=opsParcel;modal('Tentatives &amp; documents · '+p.tracking,`<div class="ops-document-head"><div><h3>${esc(p.recipient)}</h3><p>Version opérationnelle ${p.ops_revision}</p><p>Prochaine tentative : <b>${opsDate(p.next_attempt_at)}</b> (heure du Maroc)</p></div>${tag(p.status)}</div>${p.invoice_id||p.financial_locked?'<div class="form-hint orange">Colis figé dans un relevé financier. Les corrections de statut sont bloquées.</div>':''}<div class="ops-action-row">${S.user.role!=='client'&&!p.invoice_id&&!p.financial_locked&&!p.operations_locked&&(S.user.role==='livreur'?p.status!=='Livré':['En livraison','Programmé','Refusé'].includes(p.status))?`<button class="btn primary" onclick="opsAttemptForm(${id})">${icon('check')}Enregistrer une tentative</button>`:''}<button class="btn" onclick="opsLinkedTicket(${id})">${icon('ticket')}Réclamation sur ce colis</button></div><h3 class="ops-subtitle">Tentatives et déclarations de livraison</h3>${simpleTable(['Quand / Auteur','Résultat / Motif','Rendez-vous / Déclaration'],attempts.map(a=>[`${opsDate(a.created_at)}<span class="sub">${esc(a.actor)}</span>`,`${tag(a.outcome)}<span class="sub">${esc(a.reason_label||'')}</span>${a.note?`<span class="sub ops-wrap">${esc(a.note)}</span>`:''}`,a.outcome==='Livré'?`${esc(a.receiver)}<span class="sub">COD déclaré : ${centMoney(a.amount_cents)} MAD</span><span class="sub">Déclaration sans signature/photo</span>`:opsDate(a.next_attempt_at)]))}<h3 class="ops-subtitle">Documents liés</h3>${documents.map(d=>`<button class="btn sm" onclick="openOpsDocument(${d.id})">${esc(d.reference)} · ${esc(d.status)}</button>`).join(' ')||'<p class="sub">Aucun document accessible lié.</p>'}<h3 class="ops-subtitle">Réclamations accessibles</h3>${tickets.map(t=>`<button class="btn sm" onclick="ticketDetail(${t.id})">TKT-${t.id} · ${esc(t.status)} · ${esc(t.priority)}</button>`).join(' ')||'<p class="sub">Aucune réclamation liée dans votre périmètre.</p>'}`,true)}catch(e){toast(e.message,true)}}
async function opsAttemptForm(id){try{const cfg=S.user.role==='livreur'?await api('/logistics/followup-reasons'):await opsLoadConfig();const {parcel:p}=await api('/logistics/parcels/'+id),key=financeKey();const outcomes=(S.user.role==='livreur'?S.status_policy.attempt_outcomes.filter(v=>(S.status_policy.driver_transitions[p.status]||[]).includes(v)):(p.status==='Refusé'?['Retourné']:S.status_policy.attempt_outcomes)).filter(v=>S.user.role!=='livreur'||!['Réceptionné','Retourné'].includes(v));if(!outcomes.length)throw Error('Aucune tentative disponible pour ce colis. Contactez le Hub.');modal('Résultat de la tentative',form(`<div class="full form-hint">${esc(p.tracking)} · État actuel ${esc(p.status)}. Une tentative reste dans l’historique ; elle ne crée pas une deuxième commission.</div>${select('outcome','Résultat',outcomes.map(v=>[v,v]))}${select('reason_code','Motif si non livré',[['','Choisir un motif'],...cfg.reasons.filter(r=>r.active).map(r=>[r.code,r.label])],'',false)}${input('next_attempt_at','Rendez-vous futur (heure du Maroc)','','datetime-local',false)}${input('receiver','Réceptionnaire déclaré (si livré)','','text',false)}${input('collected_amount','COD déclaré si livré (MAD)',p.amount,'number',false,'min="0" step="0.01"')}${textarea('note','Commentaire visible au client')}<div class="full form-hint orange">Il s’agit d’une déclaration de livraison, pas d’une signature ou photo certifiée. Aucun transfert bancaire.</div>`,'Enregistrer la tentative'),true);bindForm(async d=>{await api409(f=>api('/logistics/parcels/'+id+'/attempts','POST',{...d,revision:f?f.ops_revision:p.ops_revision,request_key:key}),async()=>({ops_revision:(await api('/logistics/parcels/'+id)).parcel.ops_revision}));await refresh();await renderView();await openOpsParcel(id);toast('Tentative enregistrée')})}catch(e){toast(e.message,true)}}
function opsLinkedTicket(pid){modal('Réclamation liée au colis',form(`${input('subject','Objet')}${select('priority','Priorité',['Basse','Normale','Haute'].map(v=>[v,v]),'Normale')}${textarea('body','Votre message','',true)}`,'Créer la réclamation'));bindForm(async d=>{const r=await api('/logistics/parcels/'+pid+'/tickets','POST',d);await refresh();await renderView();await ticketDetail(r.id);toast('Réclamation liée au colis')})}
const opsOriginalChangeStatus=changeStatus;
changeStatus=async function(id){if(opsOffline){opsOriginalChangeStatus(id);const el=$('#modal-form .form-grid');if(el)el.insertAdjacentHTML('beforeend',`<div class="full">${select('reason_code','Motif si programmé',[['','Choisir'],...(OFFLINE_SEED.followup_reasons||[]).map(r=>[r.code,r.label])],'',false)}${input('next_attempt_at','Rendez-vous futur (simulation locale)','','datetime-local',false)}</div>`);return}const p=S.parcels.find(p=>p.id===id);if(S.user.role==='livreur')return openParcelState(id);try{await opsLoadConfig();opsOriginalChangeStatus(id);if(!$('#modal-form'))return;const formEl=$('#modal-form .form-grid');formEl.insertAdjacentHTML('beforeend',`<div class="full ops-schedule-extra">${select('reason_code','Motif (obligatoire si programmé)',[['','Non renseigné'],...opsConfig.reasons.filter(r=>r.active).map(r=>[r.code,r.label])],'',false)}${input('next_attempt_at','Prochain rendez-vous (heure du Maroc)','','datetime-local',false)}<p class="form-hint">La programmation exige un motif et une date future.</p></div>`)}catch(e){toast(e.message,true)}};
function opsNotificationsView(data){return heading('Notifications internes','Les notifications lues sont supprimées automatiquement après 2 heures. Les notifications non lues sont conservées.',`<button class="btn" onclick="markOpsNotices()">${icon('check')}Tout marquer comme lu</button>`)+`<section class="card"><div class="card-head"><h3>${data.unread} non lue(s)</h3><span class="sub">200 dernières notifications</span></div>${data.items.length?data.items.map(n=>`<article class="ops-notice ${n.read_at?'read':''}"><span class="stat-icon blue">${icon('bell')}</span><div><h3>${esc(n.title)}</h3><p>${esc(n.body)}</p><small>${opsDate(n.created_at)}</small></div>${!n.read_at?`<button class="btn sm" onclick="markOpsNotices(${n.id})">Marquer lue</button>`:'<span class="tag good">Lue</span>'}</article>`).join(''):empty('Aucune notification','Les prochains événements de vos colis apparaîtront ici.')}</section>`}
async function markOpsNotices(id){try{await api('/logistics/notifications','PATCH',id?{id}:{all:true});await renderView()}catch(e){toast(e.message,true)}}
function opsAnalyticsView(data){const attempts=data.drivers.reduce((n,d)=>n+d.attempts,0),del=data.drivers.reduce((n,d)=>n+d.delivered_attempts,0);return heading('Activité enregistrée','Des événements datés, pas une estimation de présence au travail.')+`<div class="demo-notice">Mesure démarrée le ${opsDate(data.started_at)}. Aucun historique antérieur n’est inventé. Les jours sont ceux des horodatages serveur ; le taux porte sur les tentatives déclarées, pas sur tous les colis livrés historiques.</div><section class="card"><div class="toolbar"><label>Du <input id="ops-period-from" type="date" value="${data.period_from}"></label><label>Au <input id="ops-period-to" type="date" value="${data.period_to}"></label><button class="btn primary" onclick="opsPeriod={from:$('#ops-period-from').value,to:$('#ops-period-to').value};renderView()">Filtrer</button>${[7,14,30].map(n=>`<button class="btn sm" onclick="opsDays(${n})">${n} jours</button>`).join('')}</div></section><section class="stats ops-margin">${stat('Affectations enregistrées',data.drivers.reduce((n,d)=>n+d.assignment_events,0),'','user','blue','Événements, pas colis uniques')}${stat('Tentatives déclarées',attempts,'','truck','','Dans la période sélectionnée')}${stat('Tentatives livrées',del,'','checkcircle','green','Historique des déclarations')}${stat('Succès des tentatives',attempts?Math.floor(del/attempts*1000)/10:'—',attempts?'%':'','chart','purple',del+' / '+attempts+' tentatives')}</section><section class="card"><div class="card-head"><h3>Analyse livreurs</h3></div>${simpleTable(['Livreur','Affectations','Tentatives','Livrées','Lecture'],data.drivers.map(d=>[esc(d.name),d.assignment_events,d.attempts,d.delivered_attempts,d.assignment_events||d.attempts?'Événements enregistrés':'Aucun événement dans cette période']))}</section><section class="card ops-margin"><div class="card-head"><h3>Activité quotidienne des tentatives</h3></div>${simpleTable(['Jour serveur','Livreur','Tentatives','Livrées'],data.daily.map(d=>[date(d.day),esc(d.driver||'Non affecté'),d.attempts,d.delivered]))}</section><section class="card ops-margin"><div class="card-head"><div><h3>Hubs · situation actuelle</h3><p>Dernier hub déclaré et colis attendus, indépendamment de la période ci-dessus. Pas une localisation GPS.</p></div></div>${simpleTable(['Hub','Dernier hub déclaré de','Colis en transit attendus'],data.hubs.map(h=>[esc(h.name),h.parcels_here+' colis',h.expected]))}</section>`}
function hubDailyChart(rows,series){
 let points=[...(rows||[])].sort((a,b)=>String(a.day).localeCompare(String(b.day)));
 let weekly=false;
 if(points.length>31){
  weekly=true;const grouped=new Map();
  for(const row of points){
   const dt=new Date(String(row.day)+'T00:00:00Z');
   const weekday=(dt.getUTCDay()+6)%7;dt.setUTCDate(dt.getUTCDate()-weekday);
   const key=dt.toISOString().slice(0,10);
   if(!grouped.has(key))grouped.set(key,{day:key});
   const item=grouped.get(key);for(const line of series)item[line.key]=(item[line.key]||0)+Number(row[line.key]||0);
  }
  points=[...grouped.values()];
 }
 if(!points.length)return empty('Aucune activité graphique','Les événements apparaîtront après leur enregistrement.');
 const W=760,H=230,L=42,R=12,T=16,B=34,base=H-B,plotH=base-T,n=points.length,max=Math.max(1,...points.flatMap(r=>series.map(s=>Number(r[s.key]||0)))),group=(W-L-R)/n,bw=Math.max(2,Math.min(18,group/(series.length+1.4)));
 const grid=[0,.5,1].map(fr=>{const y=base-plotH*fr;return `<line x1="${L}" y1="${y}" x2="${W-R}" y2="${y}" stroke="#e8edf3"/><text x="${L-7}" y="${y+4}" text-anchor="end" fill="#7b8794" font-size="10">${Math.round(max*fr)}</text>`}).join('');
 const bars=points.map((row,i)=>series.map((line,j)=>{const v=Number(row[line.key]||0),h=v?Math.max(1,v/max*plotH):0,x=L+i*group+(group-series.length*bw)/2+j*bw,y=base-h;return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(1,bw-2).toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${line.color}"><title>${esc(row.day)} · ${esc(line.label)} : ${v}</title></rect>`}).join('')).join('');
 const step=Math.max(1,Math.ceil(n/10));
 const labels=points.map((row,i)=>i%step===0||i===n-1?`<text x="${(L+i*group+group/2).toFixed(1)}" y="${H-9}" text-anchor="middle" fill="#778392" font-size="9">${esc(String(row.day).slice(5))}</text>`:'').join('');
 return `<div class="hub-chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(series.map(x=>x.label).join(', '))}" style="width:100%;height:auto;display:block">${grid}${bars}${labels}</svg><div class="chart-legend">${series.map(x=>`<span><i class="dot" style="background:${x.color}"></i>${esc(x.label)}</span>`).join('')}</div>${weekly?'<p class="sub">Période longue : regroupement hebdomadaire pour la lisibilité du graphique. Le tableau conserve les valeurs quotidiennes.</p>':''}</div>`;
}
function hubMinutes(value){if(value==null)return '—';const n=Number(value);return n<60?`${n} min`:`${(n/60).toFixed(1)} h`}
function hubDashboardView(data){
 const w7=data.windows?.['7']||{},w30=data.windows?.['30']||{},m=data.metrics||{};
 const firstRate=m.first_attempt_rate_pct==null?'—':`${m.first_attempt_rate_pct}%`;
 const returnRate=m.return_rate_pct==null?'—':`${m.return_rate_pct}%`;
 const firstHint=`${m.first_attempt_delivered||0} / ${m.first_attempts||0} premières tentatives enregistrées`;
 const returnHint=`${m.return_attempts||0} résultat(s) « Retourné » · ${m.attempt_parcels||0} colis avec tentative`;
 const processHint=`${m.processing_sample_size||0} échantillon(s) · réception physique → première affectation locale`;
 return heading('Activité de mon Hub',`${esc(data.hub.name)} · ${esc(data.hub.city)}. Indicateurs agrégés, limités à votre Hub.`)+
 `<div class="demo-notice">Les arrivées attendues sont issues des départs déclarés; aucun détail de colis en transit n’est affiché. Les KPIs reposent uniquement sur les tentatives horodatées avec leur Hub, les réceptions physiques enregistrées et les affectations locales. Les snapshots de tentatives et de traitement sont collectés depuis ${opsDate(data.metrics_started_at)}; aucune attribution historique incertaine n’est inventée. Les réceptions déjà datées dans les manifestes restent consultables. Les nombres et taux ci-dessous sont bruts : aucun score composite ni classement n’est calculé.</div><section class="card"><div class="toolbar"><label>Du <input id="ops-period-from" type="date" value="${data.period_from}"></label><label>Au <input id="ops-period-to" type="date" value="${data.period_to}"></label><button class="btn primary" onclick="opsPeriod={from:$('#ops-period-from').value,to:$('#ops-period-to').value};renderView()">Filtrer</button>${[7,30].map(n=>`<button class="btn sm" onclick="opsDays(${n})">${n} jours</button>`).join('')}</div></section>
 <section class="stats ops-margin">${stat('Colis actuellement au Hub',data.parcels_here,'','box','blue','Dernière localisation déclarée')}${stat('Colis attendus',data.expected_arrivals,'','truck','purple','Départ confirmé, réception en attente')}${stat('Manifestes entrants actifs',data.inbound_documents,'','file','','Sans détail des lignes en transit')}${stat('Sorties à terminer',data.outbound_documents,'','scan','purple',`${data.pending_departure_scans} colis à scanner en sortie`)}</section>
 <section class="stats ops-margin">${stat('Départs · 7 jours',w7.departures||0,'','truck','blue',`Depuis ${date(w7.from)}`)}${stat('Réceptions · 7 jours',w7.receipts||0,'','checkcircle','green',`Depuis ${date(w7.from)}`)}${stat('Départs · 30 jours',w30.departures||0,'','truck','purple',`Depuis ${date(w30.from)}`)}${stat('Réceptions · 30 jours',w30.receipts||0,'','checkcircle','green',`Depuis ${date(w30.from)}`)}</section>
 <section class="stats ops-margin">${stat('Réussite au premier essai',firstRate,'','chart','green',firstHint)}${stat('Colis retournés',m.returned_parcels||0,'','return','orange',`${returnHint} · ${returnRate}`)}${stat('Traitement médian',hubMinutes(m.processing_median_minutes),'','clock','purple',processHint)}${stat('Traitement moyen',hubMinutes(m.processing_average_minutes),'','clock','blue',processHint)}</section>
 <section class="stats ops-margin">${stat('Départs',data.departures,'','truck','','Dans la période choisie')}${stat('Réceptions',data.receipts,'','checkcircle','green','Transferts physiquement reçus')}${stat('Affectations locales',data.daily.reduce((n,x)=>n+(x.assignments||0),0),'','user','blue','Dans la période choisie')}${stat('Tentatives structurées',m.attempts||0,'','chart','','Dans la période choisie')}</section>
 <section class="two-col ops-margin"><article class="card"><div class="card-head"><div><h3>Réceptions et affectations</h3><p>Événements bruts par jour.</p></div></div>${hubDailyChart(data.daily,[{key:'arrivals',label:'Réceptions Hub',color:'#25a879'},{key:'assignments',label:'Affectations',color:'#3866dd'}])}</article><article class="card"><div class="card-head"><div><h3>Tentatives et résultats</h3><p>Seules les tentatives structurées et attribuées à ce Hub.</p></div></div>${hubDailyChart(data.daily,[{key:'attempts',label:'Tentatives',color:'#5371a5'},{key:'delivered_attempts',label:'Livrées',color:'#25a879'},{key:'returns',label:'Retours',color:'#ee8e44'}])}</article></section>
 <section class="card ops-margin"><div class="card-head"><div><h3>Activité quotidienne · valeurs brutes</h3><p>La durée de traitement est mesurée entre l’arrivée physique enregistrée et la première affectation ultérieure à un livreur du même Hub. Les anciennes affectations sans snapshot Hub ne sont pas attribuées rétroactivement.</p></div></div>${data.daily.length?simpleTable(['Jour','Départs','Réceptions','Arrivées tracées','Affectations','Tentatives','Livrées','Retours'],data.daily.map(d=>[date(d.day),d.departures||0,d.receipts||0,d.arrivals||0,d.assignments||0,d.attempts||0,d.delivered_attempts||0,d.returns||0])):empty('Aucune activité sur cette période','Les départs, réceptions, affectations et tentatives apparaîtront ici.')}</section>`;
}
function hubDriversView(data){
 hubDriverRows=data.drivers||[];
 const banner=`<section class="workspace-notices" aria-label="Application livreur"><article class="workspace-notice notice-banner"><span class="notice-symbol" aria-hidden="true">${icon('truck')}</span><div class="notice-copy"><strong dir="rtl">📱 تطبيق الليفرو</strong><span dir="rtl">حمّل تطبيق ORIENTAL24 Livreur على التليفون: الكوليات ديال اليوم، السكانير والتحصيل.</span><a href="/static/ORIENTAL24-Livreur.apk" download>تحميل تطبيق الليفرو ${icon('download')}</a></div><div class="notice-art" aria-hidden="true">${routeArt()}</div></article></section>`;
 return banner+driverWorkspaceView(hubDriverRows);
}
function hubDriverEdit(id){const driver=hubDriverRows.find(d=>d.id===id);if(driver)hubDriverForm(driver)}
function hubDriverAccess(id,action=null){
 const driver=hubDriverRows.find(d=>d.id===id);if(!driver||S?.user?.role!=='agent')return;
 const options=[[driver.driver_blocked?'unblock':'block',driver.driver_blocked?'Réactiver l’accès':'Bloquer l’accès'],[driver.driver_archived?'restore':'archive',driver.driver_archived?'Restaurer le compte':'Archiver le compte']];
 modal('Accès livreur · '+esc(driver.name),form(`${select('action','Action',options,action||options[0][0])}${textarea('reason','Motif obligatoire','',true)}<div class="full form-hint">L’action concerne uniquement un livreur rattaché à votre Hub. L’archivage est refusé tant qu’il reste des colis non livrés ou un document actif. Aucun règlement, COD ou relevé financier n’est modifié.</div><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme cette modification d’accès.</label>`,'Confirmer'));
 bindForm(async d=>{await api('/logistics/hub/drivers/'+driver.id+'/access','POST',{action:d.action,reason:d.reason,revision:driver.driver_revision,confirmed:d.confirmed===true});await saved('Accès livreur mis à jour')});
}
function hubDriverForm(existing=null){
 if(S?.user?.role!=='agent')return;
 const edit=!!existing,hubName=esc(S.hubs?.[0]?.name||'votre Hub');
 const fields=`${input('name','Nom complet',existing?.name||'','text',true,'maxlength="120"')}${input('email','Adresse e-mail',existing?.email||'','email',true,'maxlength="254" autocomplete="username"')}${input('phone','Téléphone (facultatif)',existing?.phone||'','tel',false,'maxlength="40"')}${edit?select('active','Accès au compte',[['true','Actif'],['false','Désactivé']],String(!!existing.active)):''}${input('password',edit?'Nouveau mot de passe (facultatif)':'Mot de passe initial','','password',!edit,'minlength="10" maxlength="128" autocomplete="new-password"')}<div class="full form-hint">${edit?`Le livreur reste lié à ${hubName}. Un mot de passe vide conserve l’actuel. Colis ouverts : <b>${existing.assigned_open_count||0}</b>.`:`Ce compte sera automatiquement rattaché à ${hubName}. Transmettez le mot de passe au livreur par un canal sûr.`}</div>`;
 modal(edit?'Gérer un livreur local':'Créer un livreur local',form(fields,edit?'Enregistrer':'Créer le compte'));
 bindForm(async d=>{if(edit){await api('/logistics/hub/drivers/'+existing.id,'PATCH',{name:d.name,email:d.email,phone:d.phone,active:d.active==='true',password:d.password||''});await saved('Compte livreur mis à jour')}else{await api('/logistics/hub/drivers','POST',{name:d.name,email:d.email,phone:d.phone,password:d.password});await saved('Compte livreur créé et rattaché à votre Hub')}});
}
function hubDriverStatementsView(data){
 const rows=data.rows||[],t=data.totals||{};
 return heading('Relevés des livreurs du Hub',`${esc(data.hub.name)} · relevés associés au Hub au moment de leur émission. Consultation et impression.`)+
 `<div class="demo-notice">Cette page affiche les relevés livreur déjà calculés par les règles financières existantes. Pour générer un relevé, utilisez le bouton Facture dans Livreurs de mon Hub. Les barèmes sont définis par l’administration. Les paiements et rapprochements restent manuels et Admin-only. Les anciens relevés sans snapshot Hub sont exclus, même si leur livreur est rattaché aujourd’hui à ce Hub.</div><section class="stats">${stat('Relevés affichés',data.count||0,'','file','blue','500 plus récents · lecture seule')}${stat('COD initial',centMoney(t.cod_cents||0),'MAD','wallet','purple','Somme des relevés non annulés')}${stat('COD restant',centMoney(t.cash_remaining_cents||0),'MAD','wallet','orange','À rapprocher manuellement par Admin')}${stat('Commission restante',centMoney(t.commission_remaining_cents||0),'MAD','chart','blue','Selon les relevés existants')}</section><section class="card"><div class="card-head"><div><h3>Relevés associés à ${esc(data.hub.name)}</h3><p>Aucune action de règlement n’est disponible dans le compte Manager.</p></div></div>${rows.length?simpleTable(['Relevé · livreur','Période · émis le','Colis','COD · commission MAD','COD restant','Commission restante','État'],rows.map(r=>[`<button class="btn sm" onclick="openDriverStatement(${r.id})">${esc(r.reference)}</button><span class="sub">${esc(r.driver_name)}</span>`,`${r.period_from||r.period_to?`${esc(r.period_from||'…')} → ${esc(r.period_to||'…')}`:'Toutes périodes'}<span class="sub">${opsDate(r.created_at)}</span>`,r.parcel_count,`${centMoney(r.cod_cents)} · ${centMoney(r.commission_cents)}`,`${centMoney(r.cash_remaining_cents)} MAD`,`${centMoney(r.commission_remaining_cents)} MAD`,opsTag(r.status)])):empty('Aucun relevé attribué à ce Hub','Générez un relevé depuis Livreurs de mon Hub. Les relevés émis par Admin et attribués à ce Hub apparaissent également ici.')}</section>`;
}
function hubInvoiceStatus(value){const cls=value==='Soldée'?'good':value==='Partielle'?'warn':value==='Annulée'?'bad':value==='Brouillon'?'blue':value==='Ajustée à zéro'?'purple':'info';return `<span class="tag ${cls}">${esc(value)}</span>`}
function hubInvoicesView(data){
 const rows=data.invoices||[],due=rows.reduce((n,x)=>n+(x.remaining_cents||0),0),paid=rows.reduce((n,x)=>n+(x.paid_cents||0),0),total=rows.reduce((n,x)=>n+(x.total_cents||0),0);
 return heading('Factures COD de mon Hub',`${esc(data.hub.name)} · relevés de COD brut émis par l’Admin; consultation uniquement.`)+`<div class="demo-notice">Le montant correspond au COD intégral des livraisons attribuées à ce Hub dans la période de la facture. Les commissions restent séparées selon les relevés livreurs existants. Aucun virement n’est déclenché; seuls les encaissements confirmés manuellement par l’Admin réduisent le solde.</div><section class="stats">${stat('Factures émises',rows.length,'','file','blue','Brouillons Admin non affichés')}${stat('COD facturé',centMoney(total),'MAD','wallet','purple','Montants bruts · commission exclue')}${stat('Reçu et relié',centMoney(paid),'MAD','checkcircle','green','Rapprochement manuel Admin')}${stat('Reste dû',centMoney(due),'MAD','clock','orange','Aucun transfert automatique')}</section><section class="card">${rows.length?simpleTable(['Facture Hub','Période','Livraisons','COD facturé','Reçu relié','Solde','État'],rows.map(x=>[`<strong>${esc(x.reference)}</strong><span class="sub">${opsDate(x.issued_at)}</span>`,`${esc(x.period_from)} → ${esc(x.period_to)}`,x.delivery_count,`${centMoney(x.total_cents)} MAD`,`${centMoney(x.paid_cents)} MAD`,`${centMoney(x.remaining_cents)} MAD`,hubInvoiceStatus(x.settlement_status)])):empty('Aucune facture émise','Les factures apparaîtront après génération et validation par l’Admin.')}</section>`;
}
let hubInvoiceAdminData=null,hubInvoiceCurrentDetail=null;
function hubInvoicesAdminView(data){
 hubInvoiceAdminData=data;const rows=data.invoices||[];
 return heading('Factures COD des Hubs','COD brut attribué à chaque Hub · brouillons générés et émis manuellement par l’Admin.',`<button class="btn primary" onclick="hubInvoiceCreateDraft()">${icon('plus')}Générer un brouillon</button>`)+`<div class="demo-notice">Le brouillon additionne le COD intégral des livraisons enregistrées pour le Hub et la période choisie. Il n’en déduit ni commission ni frais, et ne réécrit aucun relevé existant. L’Admin vérifie les lignes avant émission. Enregistrez chaque reçu physique une seule fois dans Caisse COD, puis reliez-le manuellement à une facture Hub; aucun transfert bancaire ni règlement automatique.</div>${data.unattributed_delivery_count?`<div class="form-hint orange">${data.unattributed_delivery_count} livraison(s), soit ${centMoney(data.unattributed_cod_cents)} MAD, n’ont pas de snapshot Hub fiable et restent exclues. Revue Admin requise; aucune attribution automatique.</div>`:''}<section class="stats">${stat('Brouillons à revoir',data.draft_count||0,'','file','blue','Aucune obligation avant émission')}${stat('COD restant sur factures émises',centMoney(data.total_due_cents||0),'MAD','clock','orange','Solde des factures non soldées')}${stat('COD reçu et relié',centMoney(data.total_received_cents||0),'MAD','checkcircle','green','Rapprochements manuels')}${stat('Reçu Admin non relié à une facture',centMoney(data.unlinked_receipt_cents||0),'MAD','wallet','purple',`${data.unlinked_receipt_count||0} reçu(s) · visible(s), jamais affecté(s) automatiquement`)}</section><section class="card">${rows.length?simpleTable(['Facture','Hub','Période','Livraisons','COD facturé','Reçu relié','Solde','État',''],rows.map(x=>[`<strong>${esc(x.reference)}</strong><span class="sub">${opsDate(x.created_at)}</span>`,esc(x.hub_name),`${esc(x.period_from)} → ${esc(x.period_to)}`,x.delivery_count,`${centMoney(x.total_cents)} MAD`,`${centMoney(x.paid_cents)} MAD`,`${centMoney(x.remaining_cents)} MAD`,hubInvoiceStatus(x.settlement_status),`<button class="btn sm" onclick="hubInvoiceDetail(${x.id})">Détails</button>`])):empty('Aucune facture Hub','Générez un brouillon pour une période contenant des livraisons COD non encore facturées.')}</section>`;
}
function hubInvoiceCreateDraft(){
 const hubs=hubInvoiceAdminData?.hubs||[];if(!hubs.length){toast('Aucun Hub configuré.',true);return}
 const today=financeDay(),monthStart=today.slice(0,7)+'-01',key=financeKey();
 modal('Générer un brouillon de facture Hub',form(`${select('hub_id','Hub',hubs.map(h=>[h.id,`${h.name} · ${h.city}${h.active?'':' · archivé'}`]))}${input('period_from','Du',monthStart,'date',true)}${input('period_to','Au',today,'date',true)}<div class="full form-hint">Le brouillon inclura uniquement les livraisons « Livré » avec snapshot COD de ce Hub, dans la période, non déjà incluses dans une facture active. Montant = COD intégral déclaré; la commission est traitée séparément.</div><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme le Hub et les dates; je vais vérifier les lignes avant émission.</label>`,'Créer le brouillon'));
 bindForm(async d=>{const r=await api('/logistics/hub-invoices/drafts','POST',{hub_id:Number(d.hub_id),period_from:d.period_from,period_to:d.period_to,request_key:key});await saved(`Brouillon ${r.reference} créé · ${centMoney(r.total_cents)} MAD`);await hubInvoiceDetail(r.id)});
}
async function hubInvoiceDetail(id){
 try{
  const d=await api('/logistics/hub-invoices/'+id),x=d.invoice,lines=d.lines||[],settlements=d.settlements||[],adjustments=d.adjustments||[],pendingHandoffs=d.pending_handoff_count||0;hubInvoiceCurrentDetail=d;
  const lineTable=simpleTable(['Date · tentative','Tracking','Ville','Statut actuel','COD facturé'],lines.map(l=>[opsDate(l.delivery_at),esc(l.tracking),esc(l.city),esc(l.current_status),`${centMoney(l.amount_cents)} MAD`]));
  const settlementTable=simpleTable(['Reçu Admin','Date · reçu','Montant relié','Motif'],settlements.map(l=>[`#${l.receipt_id}`,opsDate(l.receipt_created_at),`${centMoney(l.amount_cents)} MAD`,esc(l.reason||'—')]));
  const adjustmentTable=simpleTable(['Date · Admin','Variation','Avant → après','Motif'],adjustments.map(a=>[`${opsDate(a.created_at)}<span class="sub">${esc(a.actor_name)}</span>`,`${a.delta_cents>0?'+':''}${centMoney(a.delta_cents)} MAD`,`${centMoney(a.old_total_cents)} → ${centMoney(a.new_total_cents)} MAD`,esc(a.reason)]));
  const unlinked=(d.receipts||[]).filter(r=>r.invoice_unlinked_cents>0);
  const actions=x.status==='draft'?`<button class="btn primary" onclick="hubInvoiceIssue(${x.id})">${icon('check')}Émettre après revue</button><button class="btn danger" onclick="hubInvoiceCancel(${x.id})">Annuler le brouillon</button>`:x.status==='issued'?`<button class="btn" onclick="hubInvoiceAdjust(${x.id},${x.total_cents},${x.paid_cents})">${icon('edit')}Ajouter un ajustement</button>${x.remaining_cents>0?(unlinked.length?`<button class="btn primary" onclick="hubInvoiceLinkReceipt(${x.id},${x.remaining_cents})">${icon('link')}Relier un reçu Admin existant</button>`:pendingHandoffs?`<div class="form-hint orange">${pendingHandoffs} remise(s) chauffeur→Hub de cette facture n’ont pas encore de reçu Admin enregistré. Enregistrez-les d’abord dans Caisse COD; la saisie directe est bloquée pour éviter un doublon.</div><button class="btn" onclick="navigate('hub-cod')">${icon('layers')}Ouvrir Caisse COD</button>`:`<button class="btn primary" onclick="hubInvoiceRecordReceipt(${x.id},${x.remaining_cents})">${icon('wallet')}Enregistrer un nouveau reçu</button><button class="btn" onclick="navigate('hub-cod')">${icon('layers')}Caisse COD</button>`):''}`:'';
  const receiptTable=simpleTable(['Reçu Admin','Origine · émis le','Attendu / reçu','Relié facture Hub','Non relié facture','Motif'],(d.receipts||[]).map(r=>[`#${r.id}`,`${r.source_type==='hub_invoice'?'Saisie facture Hub':'Caisse COD'}<span class="sub">${opsDate(r.created_at)}</span>`,`${centMoney(r.expected_cents)} / ${centMoney(r.effective_received_cents)} MAD`,`${centMoney(r.invoice_allocated_cents)} MAD`,`${centMoney(r.invoice_unlinked_cents)} MAD`,esc(r.reason||'—')]));
  modal(`${esc(x.reference)} · ${esc(x.hub_name)}`,`<div class="detail-info"><div class="detail-line"><span>Période</span><strong>${esc(x.period_from)} → ${esc(x.period_to)}</strong></div><div class="detail-line"><span>Livraisons COD</span><strong>${x.delivery_count}</strong></div><div class="detail-line"><span>COD brut initial</span><strong>${centMoney(x.base_total_cents)} MAD</strong></div><div class="detail-line"><span>Ajustements nets</span><strong>${x.adjustments_cents>0?'+':''}${centMoney(x.adjustments_cents)} MAD</strong></div><div class="detail-line"><span>COD facturé après ajustements</span><strong>${centMoney(x.total_cents)} MAD</strong></div><div class="detail-line"><span>Reçu et relié</span><strong>${centMoney(x.paid_cents)} MAD</strong></div><div class="detail-line"><span>Solde</span><strong>${centMoney(x.remaining_cents)} MAD · ${hubInvoiceStatus(x.settlement_status)}</strong></div></div><div class="form-hint">La commission n’est pas déduite. Enregistrez chaque encaissement physique une seule fois dans Caisse COD, puis reliez ici le reçu Admin. Le même reçu peut ensuite être rapproché séparément au relevé livreur : deux obligations de la chaîne COD, sans second mouvement d’argent.</div><h3 class="ops-subtitle">Livraisons du brouillon / facture</h3>${lineTable}<h3 class="ops-subtitle">Reçus Admin de ce Hub</h3>${d.receipts?.length?receiptTable:empty('Aucun reçu Admin','Enregistrez le cash reçu une seule fois dans Caisse COD, puis revenez relier le reçu à cette facture.')}${settlements.length?`<h3 class="ops-subtitle">Rapprochements de cette facture</h3>${settlementTable}`:''}${adjustments.length?`<h3 class="ops-subtitle">Ajustements manuels · journal avant/après</h3>${adjustmentTable}`:''}<div class="form-actions">${actions}</div>`,true);
 }catch(e){toast(e.message,true)}
}
async function hubInvoiceIssue(id){
 modal('Émettre la facture Hub',form(`<div class="full form-hint orange">Vérifiez les lignes et le COD brut avant confirmation. L’émission crée une obligation financière immuable; aucun paiement ou transfert n’est déclenché.</div><label class="full check-label"><input type="checkbox" name="confirmed" required> J’ai vérifié la période, le Hub et le montant; j’émets cette facture.</label>`,'Émettre'));
 bindForm(async()=>{await api('/logistics/hub-invoices/'+id+'/issue','POST',{confirmed:true});await saved('Facture Hub émise');await hubInvoiceDetail(id)});
}
function hubInvoiceCancel(id){
 modal('Annuler le brouillon Hub',form(`${textarea('reason','Motif obligatoire de l’annulation','',true)}<div class="full form-hint">Seul un brouillon peut être annulé. Les lignes restent journalisées; aucun brouillon n’est effacé.</div><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme l’annulation de ce brouillon.</label>`,'Annuler'));
 bindForm(async d=>{await api('/logistics/hub-invoices/'+id+'/cancel','POST',{reason:d.reason,confirmed:true});await saved('Brouillon annulé et journalisé');await hubInvoiceDetail(id)});
}
function hubInvoiceAdjust(id,totalCents,paidCents){
 const key=financeKey();modal('Ajuster une facture Hub émise',form(`<div class="full form-hint">Total actuel : <b>${centMoney(totalCents)} MAD</b> · déjà rapproché : <b>${centMoney(paidCents)} MAD</b>. La correction sera ajoutée au journal avec montant avant/après. Elle ne peut pas descendre sous les reçus déjà rapprochés.</div>${input('delta_amount','Variation signée (MAD)','0.00','number',true,'step="0.01"')}${textarea('reason','Motif obligatoire de l’ajustement','',true)}<label class="full check-label"><input type="checkbox" name="confirmed" required> J’ai vérifié la correction et confirme son enregistrement manuel.</label><div class="full form-hint orange">Aucun reçu n’est annulé et aucun remboursement ou transfert n’est exécuté automatiquement.</div>`,'Ajouter l’ajustement'));
 bindForm(async d=>{const r=await api('/logistics/hub-invoices/'+id+'/adjustments','POST',{delta_amount:d.delta_amount,reason:d.reason,request_key:key,confirmed:true});await saved(`Ajustement ajouté · ${centMoney(r.old_total_cents)} → ${centMoney(r.new_total_cents)} MAD`);await hubInvoiceDetail(id)});
}
function hubInvoiceRecordReceipt(id,dueCents){
 const key=financeKey();modal('Enregistrer un nouveau reçu Hub',form(`${input('received_amount','Montant physiquement reçu (MAD)',(dueCents/100).toFixed(2),'number',true,'min="0.01" step="0.01"')}${input('applied_amount','Montant à relier à cette facture (MAD)',(dueCents/100).toFixed(2),'number',true,`min="0.01" max="${(dueCents/100).toFixed(2)}" step="0.01"`)}${textarea('reason','Motif si partiel ou excédentaire','',false)}<div class="full form-hint">Utilisez cette option uniquement si aucun reçu existant dans Caisse COD ne correspond à ce cash. L’affectation est plafonnée au solde de la facture; l’excédent reste visible et non relié.</div><label class="full check-label"><input type="checkbox" name="not_recorded_before" required> Ce montant a été reçu physiquement et n’a jamais été enregistré dans Caisse COD.</label><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme le reçu et son affectation manuelle.</label>`,'Enregistrer le reçu'));
 const rec=$('#f-received_amount'),app=$('#f-applied_amount'),reason=$('#f-reason'),label=document.querySelector('label[for="f-reason"]');
 const sync=()=>{if(!rec||!app||!reason)return;const got=Math.round(Number(rec.value||0)*100),used=Math.round(Number(app.value||0)*100),cap=Math.min(got,dueCents);if(used>cap)app.value=(cap/100).toFixed(2);const partial=got!==dueCents||Math.round(Number(app.value||0)*100)!==cap;reason.required=partial;if(label)label.textContent='Motif si partiel ou excédentaire'+(partial?' *':'')};
 rec?.addEventListener('input',sync);app?.addEventListener('input',sync);sync();
 bindForm(async d=>{const r=await api('/logistics/hub-invoices/'+id+'/receipts','POST',{received_amount:d.received_amount,applied_amount:d.applied_amount,reason:d.reason||'',not_recorded_before:d.not_recorded_before===true,request_key:key,confirmed:d.confirmed===true});await saved(`Reçu enregistré · ${centMoney(r.amount_applied_cents)} MAD reliés · ${centMoney(r.unlinked_cents)} MAD non reliés`);await hubInvoiceDetail(id)});
}
function hubInvoiceLinkReceipt(id,dueCents){
 const receipts=(hubInvoiceCurrentDetail?.receipts||[]).filter(r=>r.invoice_unlinked_cents>0);if(!receipts.length){toast('Aucun reçu Admin non relié n’est disponible.',true);return}
 const options=receipts.map(r=>[r.id,`#${r.id} · ${opsDate(r.created_at)} · reçu ${centMoney(r.effective_received_cents)} · restant ${centMoney(r.invoice_unlinked_cents)} MAD`]);
 const key=financeKey();modal('Relier un reçu Admin existant',form(`${select('receipt_id','Reçu du Hub',options)}${input('amount','Montant à relier (MAD)',(Math.min(dueCents,receipts[0].invoice_unlinked_cents)/100).toFixed(2),'number',true,'min="0.01" step="0.01"')}${textarea('reason','Motif si rapprochement partiel','',false)}<div class="full form-hint">Le reçu doit appartenir au même Hub. Le montant ne peut pas dépasser le reçu disponible ni le solde de la facture. L’excédent reste non relié.</div><label class="full check-label"><input type="checkbox" name="confirmed" required> Je confirme avoir revu le reçu et cette affectation manuelle.</label>`,'Relier le reçu'));
 const receiptField=$('#f-receipt_id'),amountField=$('#f-amount'),reasonField=$('#f-reason'),reasonLabel=document.querySelector('label[for="f-reason"]');
 const capFor=r=>Math.min(dueCents,Number(r?.invoice_unlinked_cents||0));
 const sync=()=>{const r=receipts.find(x=>Number(x.id)===Number(receiptField?.value)),cap=capFor(r);if(amountField){amountField.max=(cap/100).toFixed(2);if(Number(amountField.value)>cap/100)amountField.value=(cap/100).toFixed(2)}const partial=Math.round(Number(amountField?.value||0)*100)!==cap;if(reasonField)reasonField.required=partial;if(reasonLabel)reasonLabel.textContent='Motif si rapprochement partiel'+(partial?' *':'')};
 receiptField?.addEventListener('change',sync);amountField?.addEventListener('input',sync);sync();
 bindForm(async d=>{const r=await api('/logistics/hub-invoices/'+id+'/settlements','POST',{receipt_id:Number(d.receipt_id),amount:d.amount,reason:d.reason||'',request_key:key,confirmed:true});await saved(`Rapprochement enregistré · ${centMoney(r.amount_cents)} MAD · reste facture ${centMoney(r.invoice.remaining_cents)} MAD`);await hubInvoiceDetail(id)});
}
function hubAssignParcel(parcelId){hubAssignSelected([Number(parcelId)])}
function hubBulkAssign(){
 const ids=[...document.querySelectorAll('#parcel-table .parcel-select:checked')].map(x=>Number(x.value)).filter(Number.isInteger);
 if(!ids.length){toast('Sélectionnez au moins un colis physiquement présent au Hub.',true);return}
 hubAssignSelected(ids);
}
function hubAssignSelected(ids){
 if(S?.user?.role!=='agent')return;
 const hubId=Number(S.user.agent_hub_id),drivers=(S.users||[]).filter(d=>d.role==='livreur'&&d.active&&Number(d.driver_hub_id)===hubId);
 if(!drivers.length){toast('Créez ou activez un livreur local avant l’affectation.',true);navigate('hub-drivers');return}
 const key=financeKey();
 modal('Affecter au livreur local',form(`<div class="full form-hint"><b>${ids.length} colis sélectionné(s).</b> Le serveur vérifiera que chaque colis est physiquement présent dans votre Hub et qu’aucun verrou financier ou document actif ne le bloque. L’affectation ne confirme pas la remise physique au livreur et ne modifie pas le COD.</div>${select('driver_id','Livreur actif de votre Hub',drivers.map(d=>[d.id,`${d.name} · ${d.phone||'sans téléphone'}`]))}<div class="full form-hint">Après confirmation, les colis affectés deviennent visibles dans l’application du livreur. Les colis déjà affectés à ce livreur ne seront pas dupliqués.</div>`,'Confirmer l’affectation'));
 bindForm(async d=>{const r=await api('/logistics/hub/assignments','POST',{driver_id:Number(d.driver_id),parcel_ids:ids,request_key:key,confirmed:true});await saved(`${r.assigned} colis affecté(s) · ${r.already_assigned} déjà affecté(s)`)});
}
function hubCodView(data){
 if(S.user.role!=='admin'){
  return heading('Caisse COD · '+esc(data.hub.name),`${esc(data.hub.city)} · remises agrégées de vos livreurs.`)+`<div class="demo-notice">Cette vue n’affiche aucun tracking, destinataire ou détail de colis. Elle enregistre la garde physique du cash uniquement; elle ne règle pas une facture et ne déclenche aucun virement. Les écarts exigent un motif.</div><section class="stats">${stat('COD livré en attente',centMoney(data.expected_due_cents||0),'MAD','wallet','blue','Colis livrés non encore remis au Hub')}${stat('Cash reçu au Hub, à remettre à l’Admin',centMoney(data.unremitted_cents||0),'MAD','box','purple','Remises enregistrées, pas encore rapprochées par l’Admin')}${stat('Livreurs avec COD en attente',(data.drivers_due||[]).filter(d=>d.driver_id!==null).length,'','user','','Comptes agrégés, sans lignes de colis')}</section><section class="card ops-margin"><div class="card-head"><div><h3>COD à recevoir des livreurs</h3><p>Le serveur regroupe automatiquement les livraisons de ce Hub qui n’ont pas encore de reçu.</p></div></div>${data.drivers_due.length?simpleTable(['Livreur','Livraisons','Attendu MAD',''],data.drivers_due.map(d=>[esc(d.driver_name),d.delivery_count,centMoney(d.expected_cents),d.driver_id?`<button class="btn sm primary" onclick="hubCodHandoffForm(${d.driver_id},${d.delivery_count},${d.expected_cents})">${icon('wallet')}Enregistrer la remise</button>`:`<span class="sub">À vérifier par l’Admin</span>`])):empty('Aucun COD en attente','Les prochains montants déclarés livrés apparaîtront ici.')}</section><section class="card ops-margin"><div class="card-head"><div><h3>Remises reçues</h3><p>Historique de caisse limité à ce Hub. L’Admin rapprochera séparément le montant remis par le Hub.</p></div></div>${data.handoffs.length?simpleTable(['Date · livreur','Attendu MAD','Reçu MAD','Écart / motif','État'],data.handoffs.map(h=>[`${opsDate(h.created_at)}<span class="sub">${esc(h.driver_name)}</span>`,centMoney(h.expected_cents),centMoney(h.effective_received_cents),`${centMoney(h.variance_cents)}<span class="sub ops-wrap">${esc(h.reason||'—')}</span>`,h.remitted_to_admin?opsTag('Rapproché Admin'):opsTag('À remettre à l’Admin')])):empty('Aucune remise enregistrée','Les remises seront historisées sans détail de colis.')}</section>`;
 }
 return heading('Caisse COD des Hubs','Rapprochement manuel des remises physiques. Aucun mouvement bancaire n’est déclenché.')+`<div class="demo-notice">Ce registre trace chauffeur → Hub puis Hub → Administration. Il ne remplace pas les relevés livreur ni les factures clients, ne modifie pas leur solde et n’effectue aucun paiement. Toute correction est ajoutée au journal avec motif; aucun reçu n’est réécrit.</div>${data.unassigned_cod_count?`<div class="form-hint orange">${data.unassigned_cod_count} livraison(s) avec COD déclaré (${centMoney(data.unassigned_cod_cents)} MAD) n’ont pas de Hub snapshot. Les livraisons historiques ou sans Hub de secours ne sont pas affectées automatiquement; vérifiez-les manuellement.</div>`:``}<section class="stats">${stat('Hubs configurés',data.hubs.length,'','layers','blue','')}${stat('COD livré à remettre aux Hubs',centMoney(data.hubs.reduce((n,h)=>n+h.driver_cod_due_cents,0)),'MAD','wallet','purple','Nombres bruts, sans détails de colis')}${stat('Remises Hub en attente Admin',centMoney(data.hubs.reduce((n,h)=>n+h.unremitted_cents,0)),'MAD','box','orange','Espèces enregistrées chez les Hubs')}${stat('COD reçu non relié aux relevés',centMoney(data.settlement_unlinked_cents||0),'MAD','wallet','purple','Excédents visibles; aucun rapprochement forcé')}</section><section class="card"><div class="card-head"><div><h3>Situation par Hub</h3><p>COD livré non reçu par le Hub et espèces reçues mais non rapprochées à l’Administration.</p></div></div>${simpleTable(['Hub','COD livré non reçu','Sans livreur · à vérifier','À rapprocher à l’Admin','État'],data.hubs.map(h=>[`${esc(h.name)}<span class="sub">${esc(h.city)}</span>`,`${h.driver_cod_count} livraisons · ${centMoney(h.driver_cod_due_cents)} MAD`,`${h.unassigned_driver_cod_count} livraison(s) · ${centMoney(h.unassigned_driver_cod_cents)} MAD`,`${centMoney(h.unremitted_cents)} MAD`,opsTag(h.active?'Actif':'Inactif')]))}</section><section class="card ops-margin"><div class="card-head"><div><h3>Remises de Hub en attente</h3><p>Sélectionnez des remises d’un seul Hub pour enregistrer le cash réellement reçu.</p></div><button class="btn primary" onclick="hubCodAdminReceiptForm()">${icon('check')}Enregistrer la réception Admin</button></div>${data.pending_handoffs.length?`<div class="table-wrap"><table><thead><tr><th><input type="checkbox" aria-label="Tout sélectionner" onchange="document.querySelectorAll('.hub-cod-handoff-select').forEach(x=>x.checked=this.checked)"></th><th>Hub · livreur · date</th><th>Attendu MAD</th><th>Reçu au Hub MAD</th><th>Écart / motif</th><th></th></tr></thead><tbody>${data.pending_handoffs.map(h=>`<tr><td><input class="hub-cod-handoff-select" type="checkbox" value="${h.id}" data-hub-id="${h.hub_id}" data-amount="${h.effective_received_cents}"></td><td>${esc(h.hub_name)}<span class="sub">${esc(h.driver_name)} · ${opsDate(h.created_at)}</span></td><td>${centMoney(h.expected_cents)}</td><td>${centMoney(h.effective_received_cents)}</td><td>${centMoney(h.variance_cents)}<span class="sub ops-wrap">${esc(h.reason||'—')}</span></td><td><button class="btn sm" onclick="hubCodAdjustmentForm('driver_handoff',${h.id},${h.effective_received_cents})">Ajuster</button></td></tr>`).join('')}</tbody></table></div>`:empty('Aucune remise en attente','Les montants enregistrés par les Hubs apparaîtront ici.')}</section><section class="card ops-margin"><div class="card-head"><div><h3>Réceptions Admin enregistrées</h3><p>Les reçus restent append-only; une correction crée une écriture distincte.</p></div></div>${data.admin_receipts.length?simpleTable(['Hub · date','Attendu MAD','Reçu MAD','Écart / motif','Relié aux relevés','Non relié',''],data.admin_receipts.map(r=>[`${esc(r.hub_name)}<span class="sub">${opsDate(r.created_at)}</span>`,centMoney(r.expected_cents),centMoney(r.effective_received_cents),`${centMoney(r.variance_cents)}<span class="sub ops-wrap">${esc(r.reason||'—')}</span>`,centMoney(r.settlement_allocated_cents||0),centMoney(r.settlement_unlinked_cents||0),`<button class="btn sm" onclick="hubCodAdjustmentForm('admin_receipt',${r.id},${r.effective_received_cents})">Ajuster</button>`])):empty('Aucune réception Admin','Aucun rapprochement cash des Hubs n’a encore été enregistré.')}</section><section class="card ops-margin"><div class="card-head"><div><h3>COD reçu · rapprochement aux relevés livreurs</h3><p>Après revue Admin, reliez manuellement le cash reçu à un relevé du même livreur. Le montant ne peut pas dépasser le reçu restant, la remise du Hub ou le cash dû du relevé. L’excédent reste visible et non relié. Si un reçu regroupe plusieurs remises, son solde restant est partagé entre elles et revérifié à chaque confirmation.</p></div></div>${simpleTable(['Hub · reçu','Livreur · remise','Attendu / reçu MAD','Relié MAD','Reste de la remise MAD','Reste du reçu Admin MAD',''],(data.settlement_handoffs||[]).map(h=>[`${esc(h.hub_name)}<span class="sub">Reçu #${h.receipt_id} · ${opsDate(h.created_at)}</span>`,`${esc(h.driver_name)}<span class="sub">Remise #${h.id}</span>`,`${centMoney(h.expected_cents)} / ${centMoney(h.effective_received_cents)}`,centMoney(h.settlement_allocated_cents||0),centMoney(h.settlement_unlinked_cents||0),centMoney(h.receipt_unlinked_cents||0),h.settlement_unlinked_cents>0&&h.receipt_unlinked_cents>0?`<button class="btn sm primary" onclick="hubCodAdminSettlementForm(${h.id})">${icon('link')}Relier au relevé</button>`:h.settlement_unlinked_cents>0?'<span class="tag warn">Solde du reçu épuisé</span>':'<span class="tag good">Rapproché</span>']))}</section>`;
}
function hubCodHandoffForm(driverId,count,expectedCents){
 const key=financeKey();modal('Remise COD du livreur',form(`<div class="full form-hint">${count} livraisons non rapprochées dans ce Hub · montant attendu <b>${centMoney(expectedCents)} MAD</b>. Aucun détail de colis ne sera affiché.</div>${input('received_amount','Montant réellement reçu (MAD)',(expectedCents/100).toFixed(2),'number',true,'min="0" step="0.01"')}${textarea('reason','Motif si le montant diffère','',false)}<div class="full form-hint orange">Cette déclaration enregistre une remise physique au Hub seulement; l’Admin fera le rapprochement ultérieur.</div>`,'Confirmer la remise'));
 bindForm(async d=>{await api('/logistics/cod/hub/handoffs','POST',{driver_id:driverId,received_amount:d.received_amount,reason:d.reason||'',request_key:key});await saved('Remise COD du livreur enregistrée')})
}
function hubCodAdminReceiptForm(){
 const selected=[...document.querySelectorAll('.hub-cod-handoff-select:checked')],ids=selected.map(x=>Number(x.value));
 if(!ids.length){toast('Sélectionnez au moins une remise.',true);return}
 const hubs=[...new Set(selected.map(x=>Number(x.dataset.hubId)))];if(hubs.length!==1){toast('Regroupez les remises d’un seul Hub à la fois.',true);return}
 const expected=selected.reduce((n,x)=>n+Number(x.dataset.amount||0),0),key=financeKey();
 modal('Réception cash · Hub → Administration',form(`<div class="full form-hint">${ids.length} remise(s) sélectionnée(s) · montant attendu <b>${centMoney(expected)} MAD</b>. Enregistrez uniquement le cash réellement compté.</div>${input('received_amount','Montant réellement reçu (MAD)',(expected/100).toFixed(2),'number',true,'min="0" step="0.01"')}${textarea('reason','Motif si le montant diffère','',false)}<div class="full form-hint orange">Aucun virement n’est déclenché. Cette ligne confirme uniquement le rapprochement physique effectué par l’Admin.</div>`,'Enregistrer la réception'));
 bindForm(async d=>{await api('/logistics/cod/admin/receipts','POST',{hub_id:hubs[0],handoff_ids:ids,received_amount:d.received_amount,reason:d.reason||'',request_key:key});await saved('Réception Admin enregistrée')})
}
async function hubCodAdminSettlementForm(handoffId){
 try{
  const data=await api('/logistics/cod/admin/handoffs/'+handoffId+'/settlement-options');
  if(!data.statements?.length){toast('Aucun relevé actif de ce livreur ne contient les colis de cette remise avec un cash dû restant.',true);return}
  if(data.handoff_remaining_cents<=0||data.receipt_remaining_cents<=0){toast('Aucun cash reçu non rapproché ne reste pour cette remise.',true);return}
  const key=financeKey(),statements=data.statements;
  const maxFor=s=>Math.min(data.handoff_remaining_cents,data.receipt_remaining_cents,s.cash_remaining_cents);
  const firstMax=maxFor(statements[0]);
  if(firstMax<=0){toast('Aucun montant ne peut être rapproché sur le relevé sélectionné.',true);return}
  const options=statements.map(s=>[s.id,`${statementRef(s.id)} · ${financePeriod(s)} · cash dû ${centMoney(s.cash_remaining_cents)} MAD · ${s.matched_delivery_count} colis commun(s)`]);
  modal('Rapprocher le COD reçu à un relevé livreur',form(`<div class="full form-hint"><b>${esc(data.hub_name)}</b> · reçu Admin #${data.receipt_id} · remise #${data.handoff_id} de <b>${esc(data.driver_name)}</b>.<br>Cash physiquement reçu au Hub : <b>${centMoney(data.handoff_received_cents)} MAD</b> · restant non relié : <b>${centMoney(data.handoff_remaining_cents)} MAD</b>.<br>COD du reçu Admin encore non relié : <b>${centMoney(data.receipt_remaining_cents)} MAD</b>. ${data.handoff_expected_cents!==data.handoff_received_cents?`Écart à l’attendu : ${centMoney(data.handoff_received_cents-data.handoff_expected_cents)} MAD.`:''}</div>${select('statement_id','Relevé actif du même livreur',options,statements[0].id)}${input('amount','Montant déjà reçu à constater (MAD)',(firstMax/100).toFixed(2),'number',true,`min="0.01" max="${(firstMax/100).toFixed(2)}" step="0.01"`)}${input('paid_on','Date du rapprochement',financeDay(),'date',true,`max="${financeDay()}"`)}${textarea('reason','Motif si rapprochement partiel / réparti','',false)}<div class="full form-hint">Le rapprochement ajoute une transaction Espèces existante au relevé sélectionné, au plus égale au cash dû restant de ce relevé. Les commissions suivent les règles actuelles du relevé. Aucun virement ni modification de formule.</div><label class="full billing-consent"><input type="checkbox" name="confirmed" required> Je confirme que le reçu Admin a été revu et que ce montant est effectivement affecté à ce relevé.</label>`,'Confirmer le rapprochement'));
  const amountField=$('#f-amount'),statementField=$('#f-statement_id'),reasonField=$('#f-reason'),reasonLabel=document.querySelector('label[for="f-reason"]');
  const syncReason=()=>{if(!amountField||!reasonField)return;const partial=Math.round(Number(amountField.value||0)*100)!==data.handoff_remaining_cents;reasonField.required=partial;if(reasonLabel)reasonLabel.textContent='Motif si rapprochement partiel / réparti'+(partial?' *':'')};
  if(statementField&&amountField){statementField.onchange=()=>{const selected=statements.find(s=>Number(s.id)===Number(statementField.value));if(!selected)return;const cap=maxFor(selected);amountField.max=(cap/100).toFixed(2);if(Number(amountField.value)>cap/100)amountField.value=(cap/100).toFixed(2);syncReason()};amountField.oninput=syncReason;syncReason()}
  bindForm(async d=>{await api('/logistics/cod/admin/receipts/'+data.receipt_id+'/settlements','POST',{handoff_id:Number(handoffId),statement_id:Number(d.statement_id),amount:d.amount,reason:d.reason||'',paid_on:d.paid_on,request_key:key,confirmed:true});await saved('Rapprochement manuel COD ↔ relevé enregistré')})
 }catch(e){toast(e.message,true)}
}
function hubCodAdjustmentForm(recordType,recordId,currentCents){
 const key=financeKey();modal('Ajouter un ajustement COD',form(`<div class="full form-hint">Montant actuellement enregistré : <b>${centMoney(currentCents)} MAD</b>. L’ajustement est une écriture append-only; le reçu initial reste inchangé.</div>${input('delta_amount','Correction signée (MAD)', '0.00','number',true,'step="0.01"')}${textarea('reason','Motif obligatoire','',true)}<div class="full form-hint">Valeur positive : augmente le montant rapproché. Valeur négative : le diminue. Aucun ajustement ne déclenche un paiement.</div>`,'Ajouter l’ajustement'));
 bindForm(async d=>{await api('/logistics/cod/admin/adjustments','POST',{record_type:recordType,record_id:recordId,delta_amount:d.delta_amount,reason:d.reason,request_key:key});await saved('Ajustement COD ajouté au journal')})
}
function opsDays(n){const to=window.o24CasablancaDay?.(new Date())||new Date().toISOString().slice(0,10),start=new Date(to+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-n+1);opsPeriod={from:window.o24CasablancaDay?.(start)||start.toISOString().slice(0,10),to};renderView()}
async function opsBulkAssign(){const parcel_ids=[...document.querySelectorAll('.parcel-select:checked')].map(e=>Number(e.value));if(!parcel_ids.length){toast('Sélectionnez les colis de la page à affecter.',true);return}modal('Affectation groupée · '+parcel_ids.length+' colis',form(`${select('driver_id','Livreur',[['','Choisir un livreur'],...S.users.filter(u=>u.role==='livreur'&&u.active).map(u=>[u.id,u.name])])}<div class="full form-hint">Aperçu obligatoire. Un colis clôturé, verrouillé ou lié à un document actif bloque le lot entier.</div>`,'Vérifier le lot'));bindForm(async d=>{const r=await api('/logistics/assignments/preview','POST',{...d,parcel_ids});modal('Confirmer l’affectation',form(`<div class="full"><h3>${esc(r.driver.name)} · ${r.parcels.length} colis</h3>${simpleTable(['Colis','Statut'],r.parcels.map(p=>[esc(p.tracking),tag(p.status)]))}<p class="form-hint">Données revérifiées à la confirmation. Transaction tout ou rien. Aperçu valable 30 minutes.</p></div>`,'Confirmer'));bindForm(async()=>{await api('/logistics/assignments/'+r.token+'/confirm','POST',{});await saved('Affectation groupée enregistrée')})})}
const opsOriginalParcelsView=parcelsView;
parcelsView=function(){let html=opsOriginalParcelsView();if(!opsOffline&&S.user.role==='admin')html=html.replace('<div id="parcel-table">','<div class="ops-bulk"><button class="btn sm" onclick="opsBulkAssign()">'+icon('users')+'Affecter la sélection</button><span>Sélection = page affichée · 100 colis maximum par lot</span></div><div id="parcel-table">');return html};
const opsOldPalletsView=palletsView;
palletsView=function(rows){if(opsOffline)return opsOldPalletsView(rows);return heading('Anciennes palettes','Registre historique, distinct des flux de palettes opérationnels.',`<button class="btn primary" onclick="navigate('palette-hub')">${icon('layers')}Palettes internes</button><button class="btn" onclick="navigate('partner-palettes')">Palettes partenaires</button>`)+`<div class="demo-notice">Ancien registre déclaratif : ${rows.length} palettes historiques archivées. Leur compteur n’est pas un rattachement réel de colis. Utilisez Palettes pour les transferts et retours inter-hubs, et Palettes partenaires pour les arrivées des sociétés et les retours vendeurs.</div><section class="card">${simpleTable(['Ancienne référence','Origine','Destination','Quantité déclarée','État historique'],rows.map(r=>[esc(r.code),esc(r.source),esc(r.destination),r.count,tag(r.status)]))}</section>`};
function opsTicketOwner(tid,priority){modal('Responsable de la réclamation',form(`${select('assigned_to','Administrateur',S.users.filter(u=>u.role==='admin'&&u.active).map(u=>[u.id,u.name]))}${select('priority','Priorité',['Basse','Normale','Haute'].map(x=>[x,x]),priority)}`));bindForm(async d=>{await api('/logistics/tickets/'+tid,'PATCH',d);await ticketDetail(tid);toast('Responsable et priorité enregistrés')})}
let fulfillmentProducts=[],fulfillmentDetail=null;
function fulfillmentCanPrepare() {
  return S.user.role === 'admin' || (S.user.role === 'agent' && canAccessFulfillment());
}
function fulfillmentCanReserve() {
  return ['admin', 'client'].includes(S.user.role);
}
function fulfillmentView(rows) {
  const actions = fulfillmentCanReserve() ? `<button class="btn primary" onclick="newFulfillment()">${icon('plus')}Commande depuis le stock</button>` : '';
  return heading('Préparation des commandes', 'Contrôle physique et préparation des commandes au Hub Central.', actions)
    + `<div class="demo-notice">Les commandes ci-dessous sont réservées dans le stock. Le responsable du Hub Central contrôle les produits et les quantités, puis crée le colis. Le stock physique est déduit uniquement à cette validation.</div><section class="card">${simpleTable(['Préparation','Client / Destinataire','Produits','État','Colis',''],rows.map(o=>[
      `<button class="tracking" onclick="openFulfillment(${o.id})">PREP-${String(o.id).padStart(5,'0')}</button><span class="sub">${date(o.created_at)}</span>`,
      `${esc(o.company||o.client)}<span class="sub">${esc(o.shipping.recipient)}</span>`,
      o.lines.reduce((n,l)=>n+l.quantity,0)+' unités', opsTag(o.status),
      o.tracking ? `<button class="tracking" onclick="parcelDetail(${o.parcel_id})">${esc(o.tracking)}</button>` : 'Pas encore créé',
      `<button class="btn sm" onclick="openFulfillment(${o.id})">${o.status==='Réservé'&&fulfillmentCanPrepare()?'Préparer':'Ouvrir'}</button>`
    ]))}</section>`;
}
async function newFulfillment(){if(!fulfillmentCanReserve()){toast('La réservation est créée par le client ou Admin.',true);return}try{fulfillmentProducts=await api('/products');if(!fulfillmentProducts.length){toast('Créez d’abord un produit et enregistrez son stock physique.',true);return}const key=financeKey();modal('Commande depuis le stock',form(`${S.user.role==='admin'?select('client_id','Client',[['','Choisir'],...clientOptions()]):''}${clientTrackingSlot()}${input('recipient','Destinataire')}${input('phone','Téléphone','','tel')}${select('city_id','Ville ouverte',S.cities.filter(c=>c.delivery).map(c=>[c.id,c.name]))}<label class="field city-free"><span>Ou tapez la ville (faute ou arabe acceptés)</span><input name="city_name" id="city-free-input" type="text" autocomplete="off" placeholder="Ex. : Ojda, وجدة"><small class="sub" id="city-free-note">La ville est reconnue automatiquement.</small></label>${textarea('address','Adresse (facultatif · la ville par défaut)','')}${input('amount','COD total (MAD)','','number',true,'min="0" step="0.01"')}<div class="full"><div class="flex between"><h3 style="font-size:14px">Produits à réserver</h3><button type="button" class="btn sm" onclick="addFulfillmentLine()">${icon('plus')}Ajouter un produit</button></div><div id="fulfillment-lines"></div></div>${textarea('note','Note sur le colis')}<div class="full parcel-create-flags"><div class="parcel-create-flag"><div><strong>Ne pas autoriser à ouvrir le colis</strong><small>Le destinataire ne peut pas ouvrir le colis avant le paiement.</small></div><label class="switch"><input type="checkbox" name="not_allowed_to_open" aria-label="Ne pas autoriser à ouvrir le colis"></label></div><div class="parcel-create-flag"><div><strong>Commande avec échange</strong><small>Signaler qu’un échange est prévu avec le destinataire.</small></div><label class="switch"><input type="checkbox" name="is_exchange" aria-label="Commande avec échange"></label></div><div class="parcel-create-flag"><div><strong>Colis fragile</strong><small>Manipuler avec précaution ; le signalement suit le colis et ses réclamations.</small></div><label class="switch"><input type="checkbox" name="is_fragile" aria-label="Colis fragile"></label></div></div><div class="full form-hint">La validation réserve réellement ces quantités dans la base de démonstration. L’annulation avant préparation les libère.</div>`,'Réserver les produits'),true);if($('#f-client_id'))$('#f-client_id').onchange=()=>{$('#fulfillment-lines').innerHTML='';addFulfillmentLine()};bindClientTracking();if(typeof bindCityFreeInput==='function')bindCityFreeInput();addFulfillmentLine();bindForm(async d=>{const items=[...document.querySelectorAll('.fulfillment-line')].map(row=>({product_id:Number(row.querySelector('select').value),quantity:Number(row.querySelector('input').value)}));const r=await api('/fulfillment/orders','POST',{...d,items,request_key:key});await refresh();await renderView();await openFulfillment(r.id);toast('Stock réservé, en attente de contrôle physique')})}catch(e){toast(e.message,true)}}
function addFulfillmentLine(){const cid=S.user.role==='client'?S.user.id:Number($('#f-client_id').value);const products=fulfillmentProducts.filter(p=>p.client_id===cid);$('#fulfillment-lines').insertAdjacentHTML('beforeend',`<div class="fulfillment-line"><select required aria-label="Produit à réserver"><option value="">Choisir un produit</option>${products.map(p=>`<option value="${p.id}">${esc(p.reference)} · ${esc(p.name)} · ${p.available??p.quantity} dispo.</option>`).join('')}</select><input aria-label="Quantité à réserver" type="number" min="1" max="100000" step="1" value="1" required><button type="button" class="icon-btn" onclick="this.closest('.fulfillment-line').remove()" aria-label="Retirer le produit">${icon('close')}</button></div>`)}
async function openFulfillment(id) {
  try {
    const o = await api('/fulfillment/orders/'+id);
    fulfillmentDetail = o;
    const dispatchHub = (S.hubs||[]).find(h=>Number(h.id)===Number(o.dispatch_hub_id));
    const pending = o.status === 'Réservé';
    modal('PREP-'+String(id).padStart(5,'0'), `
      <div class="ops-document-head"><div><h3>${esc(o.shipping.recipient)}</h3><p>${esc(o.company||o.client)}<br>${esc(o.shipping.address)}${o.city?' · '+esc(o.city):''}<br>${esc(o.shipping.phone)} · COD ${money(o.shipping.amount)} MAD</p></div>${opsTag(o.status)}</div>
      ${parcelPolicyBadges(o.shipping)}
      ${simpleTable(['SKU','Produit','Quantité'],o.lines.map(l=>[esc(l.sku),esc(l.name),l.quantity]))}
      ${o.shipping.note?`<p class="form-hint"><strong>Note sur le colis :</strong> ${esc(o.shipping.note)}</p>`:''}
      ${!o.tracking&&o.shipping.tracking?`<p class="form-hint">Tracking réservé : <b>${esc(o.shipping.tracking)}</b></p>`:''}
      ${o.tracking?`<div class="ops-action-row"><button class="btn" onclick="parcelDetail(${o.parcel_id})">${icon('box')}${esc(o.tracking)}</button></div>`:''}
      ${o.status==='Préparé'?`<div class="stock-return-ticket"><strong>${o.stock_restocked_at?'RETOUR AU STOCK · RÉINTÉGRÉ À LA RÉCEPTION PALETTE':o.stock_deducted_at?'STOCK DÉDUIT À LA CRÉATION DU COLIS':'ANCIENNE COMMANDE · DÉDUCTION À VÉRIFIER'}</strong><span>Hub de stock enregistré : ${esc(dispatchHub?.name||'non renseigné · vérifier avant préparation')}. Le stock est déduit dès « Contrôler et créer le colis ». Le retour stock s’ajoute automatiquement au scan de réception d’une palette « Retour vers Hub Central » au Hub Central. Ne pas remettre ce colis au client.</span></div>`:''}
      ${o.reason?`<p class="form-hint">${esc(o.reason)}</p>`:''}
      <div class="form-actions">
        ${pending&&fulfillmentCanReserve()?`<button class="btn danger" onclick="fulfillmentAction('cancel')">Annuler la réservation</button>`:''}
        ${pending&&fulfillmentCanPrepare()?`<button class="btn primary" onclick="fulfillmentAction('ship')">Contrôler et créer le colis</button>`:''}
      </div>`, true);
  } catch(e) { toast(e.message,true); }
}
async function fulfillmentAction(action) {
  const o = fulfillmentDetail;
  try {
    if (!o || o.status !== 'Réservé') throw Error('Cette commande n’est plus en attente de préparation.');
    if (action === 'ship' ? !fulfillmentCanPrepare() : action !== 'cancel' || !fulfillmentCanReserve())
      throw Error('Action non autorisée pour ce compte.');
    let central = null;
    if (action === 'ship') {
      await opsLoadConfig();
      central = opsConfig.hubs.find(h=>h.active&&Number(h.id)===Number(opsConfig.central_hub_id));
      if (!central || (S.user.role==='agent'&&Number(S.user.agent_hub_id)!==Number(central.id)))
        throw Error('Configurez un Hub Central actif avant de préparer les commandes.');
    }
    modal(action==='ship'?'Valider la préparation':'Libérer le stock réservé', form(`
      ${action==='ship'?`<div class="full form-hint"><strong>Hub Central du stock : ${esc(central.name)}</strong><br>PREP-${String(o.id).padStart(5,'0')} · ${esc(o.shipping.recipient)}</div><div class="full">${simpleTable(['SKU','Produit','Quantité à contrôler'],o.lines.map(l=>[esc(l.sku),esc(l.name),l.quantity]))}</div><label class="full check-label"><input type="checkbox" name="checked" required> J’ai contrôlé toutes les références et quantités.</label>`:textarea('reason','Motif / constat physique','',true)}
      <div class="full form-hint">${action==='cancel'?'Aucun colis n’a encore été créé. La réservation sera libérée.':'La validation crée le colis au Hub Central et déduit les quantités réservées du stock physique. Les frais de livraison actuels de la ville sont conservés sur le colis.'}</div>`, action==='ship'?'Contrôler et créer le colis':'Confirmer'));
    bindForm(async d=>{
      await api('/fulfillment/orders/'+o.id+'/'+action,'POST',action==='ship'?{...d,hub_id:central.id}:d);
      await refresh();await renderView();await openFulfillment(o.id);
      toast(action==='ship'?'Colis créé au Hub Central · stock déduit':'Réservation annulée · stock libéré');
    });
  } catch(e) { toast(e.message,true); }
}
const legacyClientInvoicesView=invoicesView,legacyClientInvoiceDetail=invoiceDetail,legacyClientPayInvoice=payInvoice;
let clientFinanceDetail=null;
invoicesView=function(rows){if(opsOffline)return legacyClientInvoicesView(rows);invoiceRows=rows;return heading('Facturation clients','Relevés figés et règlements partiels déclarés. Aucun transfert bancaire automatique.',S.user.role==='admin'?`<button class="btn primary" onclick="newInvoice()">${icon('plus')}Générer une facture</button>`:'')+`<section class="stats">${stat('À reverser aux clients',centMoney(rows.filter(i=>i.total_cents>0).reduce((s,i)=>s+i.remaining_cents,0)),'MAD','wallet','blue','Soldes des nets positifs')}${stat('À encaisser des clients',centMoney(rows.filter(i=>i.total_cents<0).reduce((s,i)=>s+i.remaining_cents,0)),'MAD','return','','Soldes des nets négatifs')}${stat('Règlements enregistrés',centMoney(rows.reduce((s,i)=>s+i.paid_cents,0)),'MAD','checkcircle','green','Deux sens de flux · non annulés')}${stat('Partiellement réglées',rows.filter(i=>i.status==='Partiellement réglée').length,'','clock','purple','Relevés restant à solder')}</section><section class="card">${simpleTable(['Facture / Client','Net initial / Sens','Réglé','Restant','Statut',''],rows.map(i=>[`<button class="tracking" onclick="invoiceDetail(${i.id})">FAC-${String(i.id).padStart(4,'0')}</button><span class="sub">${esc(i.company||i.client)}</span>`,`${centMoney(Math.abs(i.total_cents))} MAD<span class="sub">${esc(i.direction)}</span>`,centMoney(i.paid_cents)+' MAD',centMoney(i.remaining_cents)+' MAD',tag(i.status),`<button class="icon-btn" onclick="invoiceDetail(${i.id})" title="Consulter la facture">${icon('file')}</button>`]))}</section>`};
invoiceDetail=async function(id){try{const d=await api('/invoices/'+id),i=d.invoice;clientFinanceDetail=d;modal('FAC-'+String(id).padStart(4,'0'),`<div class="flex between"><h3>${esc(i.company||i.client)}</h3>${tag(billingStatusLabel(i.status))}</div><div class="detail-info" style="margin:20px 0"><div class="detail-line"><span>Net initial · ${esc(i.direction)}</span><strong>${centMoney(Math.abs(i.total_cents))} MAD</strong></div><div class="detail-line"><span>Règlements non annulés</span><strong>${centMoney(i.paid_cents)} MAD</strong></div><div class="detail-line"><span>Solde restant</span><strong>${centMoney(i.remaining_cents)} MAD</strong></div></div>${simpleTable(['Colis','Statut','COD','Frais'],d.parcels.map(p=>[esc(p.tracking),tag(p.status),money(p.status==='Livré'?p.amount:0),money(p.status==='Livré'?p.fee:p.return_fee)]))}<h3 class="ops-subtitle">Règlements déclarés</h3>${simpleTable(['Montant / Date','Mode / Référence','Enregistré par',''],d.receipts.map(r=>[`${centMoney(r.amount_cents)} MAD<span class="sub">${esc(r.payment_date||'Date historique inconnue')}${r.voided_at?' · ANNULÉ':''}</span>`,`${esc(r.method)}<span class="sub ops-wrap">${esc(r.reference)}</span>${r.void_reason?`<span class="sub">Annulation : ${esc(r.void_reason)}</span>`:''}`,esc(r.actor||'Migration historique'),S.user.role==='admin'&&!r.voided_at?`<button class="btn sm danger" onclick="voidClientReceipt(${r.id},${id})">Annuler la déclaration</button>`:'']))}<details class="ops-history"><summary>Journal financier (${d.payment_audit.length})</summary>${d.payment_audit.map(a=>`<p class="sub">${opsDate(a.created_at)} · ${esc(a.action)} · ${esc(a.actor||'Migration')} ${esc(a.details.reason||a.details.note||'')}</p>`).join('')}</details><div class="form-hint">Ces déclarations ne prouvent pas un mouvement bancaire. Annuler une déclaration ne rembourse pas le paiement et ne déverrouille pas les colis facturés.</div><div class="form-actions"><button class="btn" onclick="billingDownload('client',${id},'pdf')">PDF</button><button class="btn" onclick="billingDownload('client',${id},'csv')">CSV</button><button class="btn" onclick="printInvoice(${id})">${icon('print')}Imprimer / PDF</button>${S.user.role==='admin'&&i.status!=='Réglée'?`<button class="btn primary" onclick="payInvoice(${id})">${icon('check')}Enregistrer le règlement</button>`:''}</div>`,true)}catch(e){toast(e.message,true)}};
payInvoice=async function(id){try{const {invoice:i}=await api('/invoices/'+id),key=financeKey();if(!i.total_cents){modal('Clôturer sans flux',form('<div class="full form-hint">Net nul : aucun paiement ni mouvement d’argent.</div>','Clôturer'));bindForm(async()=>{await api('/invoices/'+id,'PATCH',{});await saved('Relevé nul clôturé')});return}modal('Enregistrer un règlement partiel ou total',form(`<div class="full form-hint orange">${esc(i.direction)} · Solde ${centMoney(i.remaining_cents)} MAD. Enregistrez uniquement une opération déjà effectuée. Aucun virement automatique.</div>${input('amount','Montant effectué (MAD)',(i.remaining_cents/100).toFixed(2),'number',true,'min="0.01" step="0.01"')}${select('method','Mode de règlement',['Virement','Espèces','Chèque','Autre'].map(v=>[v,v]))}${input('payment_date','Date effective',new Intl.DateTimeFormat('en-CA',{timeZone:'Africa/Casablanca'}).format(new Date()),'date')}${input('reference','Référence / pièce de caisse')}`,'Confirmer le règlement'));bindForm(async d=>{await api('/client-finance/invoices/'+id+'/receipts','POST',{...d,request_key:key});await saved('Règlement déclaré, solde recalculé')})}catch(e){toast(e.message,true)}};
function voidClientReceipt(rid,iid){modal('Annuler une déclaration de règlement',form(`${textarea('reason','Motif obligatoire','',true)}<div class="full form-hint orange">Le solde sera réouvert. Aucun remboursement n’est exécuté : il s’agit d’une correction de saisie avec trace.</div>`,'Confirmer la correction'));bindForm(async d=>{await api('/client-finance/receipts/'+rid+'/void','POST',d);await refresh();await renderView();await invoiceDetail(iid);toast('Déclaration annulée et historisée')})}
let accountDetail=null;
function accountsView(rows){return heading('Dossiers administratifs','Documents privés du compte et contrôle manuel par l’administration.')+`<div class="demo-notice">Utilisez uniquement des documents fictifs. La validation administrative ne vérifie ni l’identité officielle ni le compte bancaire. Elle ne change pas l’activation du compte. Aucun contrôle antivirus des PDF n’est fourni dans cette démo.</div><section class="card">${simpleTable(['Compte','Nom de facturation','Documents','État',''],rows.map(d=>[`${esc(d.account.company||d.account.name)}<span class="sub">${esc(roleName(d.account.role))}</span>`,esc(d.legal_name||'À compléter'),d.documents.length,opsTag(d.status),`<button class="btn sm" onclick="openAccountDossier(${d.user_id})">Ouvrir le dossier</button>`]))}</section>`}
async function openAccountDossier(uid){try{const d=await api('/account-dossiers/'+uid);accountDetail=d;modal('Dossier · '+(d.account.company||d.account.name),`<div class="ops-document-head"><div><h3>${esc(d.legal_name||'À compléter')}</h3><p>${esc(d.billing_address||'Adresse à compléter')}<br>Identifiant entreprise : ${esc(d.legal_id||'Non renseigné')}</p></div>${opsTag(d.status)}</div>${d.review_note?`<p class="form-hint orange">Avis de l’administration : ${esc(d.review_note)}</p>`:''}<div class="ops-action-row"><button class="btn" onclick="editAccountDossier()">${icon('edit')}Informations de facturation</button><button class="btn" onclick="uploadAccountDocument()">${icon('plus')}Ajouter un document fictif</button></div>${simpleTable(['Document','Type / Date','Taille',''],d.documents.map(f=>[esc(f.name),`${esc(f.kind)}<span class="sub">${date(f.created_at)}</span>`,Math.ceil(f.size/1024)+' Ko',`<a class="btn sm" href="/api/account-documents/${f.id}" download>Télécharger</a> <button class="btn sm danger" onclick="removeAccountDocument(${f.id})">Retirer</button>`]))}<details class="ops-history"><summary>Historique (${d.audit.length})</summary>${d.audit.map(a=>`<p class="sub">${opsDate(a.created_at)} · ${esc(a.actor)} · ${esc(a.action)} ${esc(a.details.reason||a.details.status||'')}</p>`).join('')}</details><div class="form-hint">1 Mo par fichier, 8 fichiers maximum. JPG/PNG réencodés sans métadonnées. PDF téléchargés en pièce jointe, sans analyse antivirus. Toute modification remet le dossier en brouillon.</div><div class="form-actions">${['Brouillon','À compléter'].includes(d.status)?'<button class="btn primary" onclick="accountDecision(\'submit\')">Soumettre pour revue</button>':''}${S.user.role==='admin'&&d.status==='À vérifier'?'<button class="btn primary" onclick="accountDecision(\'review\')">Examiner le dossier</button>':''}</div>`,true)}catch(e){toast(e.message,true)}}
function editAccountDossier(){const d=accountDetail;modal('Informations de facturation',form(`${input('legal_name','Nom / raison sociale',d.legal_name)}${textarea('billing_address','Adresse de facturation',d.billing_address,true)}${input('legal_id','Identifiant entreprise (facultatif)',d.legal_id,'text',false)}`));bindForm(async v=>{await api409(f=>api('/account-dossiers/'+d.user_id,'PATCH',{...v,revision:f?f.revision:d.revision}),async()=>({revision:(await api('/account-dossiers/'+d.user_id)).revision}));await renderView();await openAccountDossier(d.user_id);toast('Informations enregistrées, dossier en brouillon')})}
function uploadAccountDocument(){const d=accountDetail;modal('Document fictif du compte',form(`${select('kind','Type',['Contrat','RIB','Document entreprise','Autre'].map(v=>[v,v]))}<div class="field full"><label for="account-file">PDF, JPG ou PNG · 1 Mo maximum</label><input id="account-file" type="file" accept=".pdf,.jpg,.jpeg,.png" required></div><div class="full form-hint orange">Ne déposez pas de vrai RIB ni de document personnel dans cette version de démonstration.</div>`,'Déposer le document'));bindForm(async v=>{const f=$('#account-file').files[0];if(!f||f.size>1048576)throw Error('Fichier manquant ou supérieur à 1 Mo');const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Lecture du fichier impossible'));reader.readAsDataURL(f)});await api('/account-dossiers/'+d.user_id+'/documents','POST',{...v,name:f.name,content});await renderView();await openAccountDossier(d.user_id);toast('Document privé enregistré')})}
function removeAccountDocument(fid){const uid=accountDetail.user_id;modal('Retirer le document',form(textarea('reason','Motif du retrait','',true),'Retirer le fichier'));bindForm(async d=>{await api('/account-documents/'+fid,'DELETE',d);await renderView();await openAccountDossier(uid);toast('Fichier retiré ; trace du retrait conservée')})}
function accountDecision(action){const d=accountDetail;modal(action==='submit'?'Soumettre le dossier':'Revue administrative',form(action==='review'?`${select('status','Décision',['Validé','À compléter'].map(v=>[v,v]))}${textarea('note','Commentaire (obligatoire si à compléter)')}<label class="full check-label"><input type="checkbox" name="checked">J’ai effectué un contrôle administratif manuel, sans certification d’identité.</label>`:'<div class="full form-hint">Le nom, l’adresse et au moins un document sont requis. La validation est une décision manuelle de l’administration.</div>','Confirmer'));bindForm(async v=>{await api409(f=>api('/account-dossiers/'+d.user_id+'/'+action,'POST',{...v,revision:f?f.revision:d.revision}),async()=>({revision:(await api('/account-dossiers/'+d.user_id)).revision}));await renderView();await openAccountDossier(d.user_id);toast('Dossier mis à jour')})}
let stockPeriod={from:'',to:''},stockAnalyticsData=null,opsAnalyticsData=null;
const opsBaseAnalyticsView=opsAnalyticsView;
opsAnalyticsView=function(d){opsAnalyticsData=d;return opsBaseAnalyticsView(d)+`<section class="card ops-margin"><div class="card-head"><div><h3>Hubs · mouvements historiques</h3><p>Colis départs / réceptions datés dans la période. Un même colis transféré plusieurs fois peut compter plusieurs fois.</p></div><button class="btn sm" onclick="exportOpsAnalytics()">${icon('download')}CSV activité</button></div>${simpleTable(['Hub','Départs déclarés','Réceptions confirmées'],d.hub_activity.map(h=>[esc(h.name),h.departed,h.received]))}</section><section class="card ops-margin"><div class="card-head"><div><h3>Affectations quotidiennes</h3><p>Nombre d’événements de prise en charge, pas présence au travail.</p></div></div>${simpleTable(['Jour serveur','Livreur','Événements'],d.daily_assignments.map(a=>[date(a.day),esc(a.driver),a.assignment_events]))}</section>`};
function opsCSV(name,rows){const csv='\ufeff'+rows.map(row=>row.map(v=>{let s=String(v??'');if(/^[\s]*[=+@-]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"'}).join(';')).join('\r\n');const a=document.createElement('a'),u=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
function exportOpsAnalytics(){const d=opsAnalyticsData;opsCSV('ORIENTAL24-activite.csv',[['Catégorie','Entité','Date début','Date fin','Affectations','Tentatives','Livrées','Départs hub','Réceptions hub'],...d.drivers.map(r=>['Livreur',r.name,d.period_from,d.period_to,r.assignment_events,r.attempts,r.delivered_attempts,'','']),...d.daily_assignments.map(r=>['Affectations quotidiennes',r.driver,r.day,r.day,r.assignment_events,'','','','']),...d.daily.map(r=>['Tentatives quotidiennes',r.driver,r.day,r.day,'',r.attempts,r.delivered,'','']),...d.hub_activity.map(r=>['Hub',r.name,d.period_from,d.period_to,'','','',r.departed,r.received])])}
function stockAnalyticsView(d){stockAnalyticsData=d;return heading('Analyse produits','Mouvements datés et disponibilité actuelle, sans chiffre d’affaires inventé.',`<button class="btn" onclick="exportStockAnalytics()">${icon('download')}CSV produits</button>`)+`<section class="card"><div class="toolbar"><label>Du <input id="stock-period-from" type="date" value="${d.period_from}"></label><label>Au <input id="stock-period-to" type="date" value="${d.period_to}"></label><button class="btn primary" onclick="stockPeriod={from:$('#stock-period-from').value,to:$('#stock-period-to').value};renderView()">Filtrer</button></div></section><div class="demo-notice">Les entrées et sorties incluent les mouvements manuels validés. Les sorties CMD stock sont déduites lors de « Contrôler et créer le colis » au Hub Central; les retours sont réintégrés lors du scan de réception de la palette « Retour vers Hub Central ». Physique, réservé et disponible décrivent maintenant, indépendamment de la période. Le stock CMD est physiquement tenu au Hub Central; aucune quantité par Hub secondaire n’est calculée.</div><section class="card">${simpleTable(['Produit / Client','Entrées','Sorties','Sorties CMD stock','Retours réintégrés','Physique actuel','Réservé actuel','Disponible actuel'],d.products.map(p=>[`${esc(p.name)}<span class="sub">${esc(p.reference)} · ${esc(p.company)}</span>`,p.incoming,p.outgoing,p.prepared,p.restocked,p.quantity,p.reserved,p.available]))}</section>`}
function exportStockAnalytics(){const d=stockAnalyticsData;opsCSV('ORIENTAL24-produits.csv',[['SKU','Produit','Client','Du','Au','Entrées','Sorties','Départs CMD stock','Retours réintégrés','Physique actuel','Réservé actuel','Disponible actuel'],...d.products.map(p=>[p.reference,p.name,p.company,d.period_from,d.period_to,p.incoming,p.outgoing,p.prepared,p.restocked,p.quantity,p.reserved,p.available])])}

/* ── Palette encore préparée : ajouter des CMD / la supprimer ───────────── */
function hubPaletteDelete(id,reference,revision){
 modal('Supprimer la palette '+reference,`<p>La palette <b>${esc(reference)}</b> n’est pas encore validée. Sa suppression retire le bon et libère ses colis : ils redeviennent disponibles pour une autre palette.</p><p class="sub">Cette action est définitive et tracée (audit).</p><div class="form-actions"><button class="btn danger" type="button" onclick="hubPaletteDeleteConfirm(${id},${revision})">Supprimer définitivement</button><button class="btn" type="button" onclick="closeModal()">Annuler</button></div>`);
}
async function hubPaletteDeleteConfirm(id,revision){
 try{
  const r=await api('/logistics/documents/'+id+'/delete','POST',{confirmed:true,revision});
  closeModal();toast('Palette '+(r.reference||'')+' supprimée · '+r.released+' colis libéré(s)');
  await renderView();
 }catch(e){toast(e.message,true)}
}

async function hubPaletteAddCmd(id,purpose){
 // Palette retour encore ouverte : « Ajouter des CMD » ouvre l'écran de scan,
 // chaque CMD scannée s'y ajoute. Palette standard : on ouvre la fiche du bon.
 if(!id)return;
 closeModal();
 if(purpose==='return_to_central'||purpose==='return_to_origin')return openDispatchCollection('transfer',id);
 return openOpsDocument(id,true);
}

