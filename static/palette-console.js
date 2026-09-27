/* v1.6.7 · Console « Palettes » du hub — miroir de l'ancien écran : tabs Default / Retours / A recevoir,
   Reception Palette (scan par cases à cocher), Envoyer Retour (scan des colis Refusé/Retourné), actions par ligne
   (Receptionner · Print Sticker · Colis CSV · Close · Attachement · Bon de réception) et chronologie « Activités ». */
const pcBin='<svg viewBox="0 0 24 24" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M9 3h6l1 2h4v2H4V5h4l1-2zM6 9h12l-1 11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 9zm3 2v8h1.5v-8H9zm3.25 0v8h1.5v-8h-1.5zM12 5.5A1.5 1.5 0 1 1 12 8.5 1.5 1.5 0 0 1 12 5.5z"/></svg>';
let pcState={tab:'default',status:'',exc:'',hub_id:'',date_from:'',date_to:'',q:'',page:1,size:30},pcOwner=null,pcSel=new Set(),pcHubs=null,pcRelanceDays=7;
let pcRDoc=null,pcRChecked=new Set(),pcRetCtx=null,pcRetSel=[],pcRetCands=[],pcRetSerial=0;
menu[1][1].splice(2,0,['palette-hub','layers','Palettes',['admin','agent']]);
titles['palette-hub']='Palettes';
function pcQuery(){const me=ppIdentity();if(pcOwner!==me){pcOwner=me;pcState={tab:'default',status:'',exc:'',hub_id:'',date_from:'',date_to:'',q:'',page:1,size:30};pcSel=new Set()}const p={};for(const k in pcState)if(pcState[k]!==''&&pcState[k]!==null&&pcState[k]!==undefined)p[k]=pcState[k];return new URLSearchParams(p).toString()}
const pcLabel=s=>({'Préparé':'Brouillon','En transit':'En transit','Partiellement reçu':'Réception partielle','Partiellement remis':'Remise partielle','Reçu':'Reçu','Remis':'Remis','Clôturé (écarts)':'Clôturé (écarts)','Annulé':'Annulée'}[s]||s);
const pcAttCache={};
const pcAttSrc=a=>{if(a.preview)pcAttCache[a.id]=a.preview;return a.preview||('/api/palette-console/attach/'+a.id)};
function pcAttOpen(id){window.open(pcAttCache[id]||('/api/palette-console/attach/'+id))}
function pcChip(r){const tone=r.bucket==='OPEN'?'open':r.bucket==='PARTIEL'?'partiel':'closed';return `<span class="pc-chip ${tone}" title="${esc(pcLabel(r.status))}">${r.bucket}</span>${r.sans_reponse?`<span class="pc-chip late" title="Relance envoyée automatiquement au vendeur">RELANCE ${r.days}J</span>`:r.retard_hub?`<span class="pc-chip late orange" title="En attente du scan du hub depuis ${r.days} jours">RETARD ${r.days}J</span>`:''}`}
function pcActs(r){
 const closable=(r.kind==='partner'&&['En transit','Partiellement reçu'].includes(r.status))||(r.kind==='return'&&['En transit','Partiellement remis'].includes(r.status));
 const btn=(t,fn,cls,title)=>`<button type="button" class="pc-ibtn ${cls||''}" title="${title}" onclick="${fn}">${t}</button>`;
 return btn(icon('down'),'pcRowRecv(\''+r.kind+'\','+r.id+')','teal','Receptionner')
  +btn(icon('layers'),'pcSticker(\''+r.kind+'\','+r.id+')','','Print Sticker')
  +btn(icon('file'),'pcColisCSV(\''+r.kind+'\','+r.id+')','','Colis CSV')
  +(closable?btn(icon('close'),'pcClose(\''+r.kind+'\','+r.id+','+r.remaining+')','danger',r.kind==='return'?'Close return pallet':'Clôturer : les non scannés seront déclarés non réceptionnés'):'')
  +btn(icon('link'),'pcAttachOpen(\''+r.kind+'\','+r.id+')','','Attachement')
  +btn(icon('print'),'pcBonPrint(\''+r.kind+'\','+r.id+')','','Bon de reception')
  +btn(icon('chevron'),`pcMore('${r.kind}',${r.id},this)`,'','Activités');
}
function paletteConsoleView(d){
 pcState.page=d.page;pcState.tab=d.tab||pcState.tab;pcRelanceDays=d.relance_days||7;
 const admin=S.user.role==='admin';
 if(admin&&!pcHubs)api('/partner-palettes/config').then(cfg=>{pcHubs=cfg.hubs}).catch(()=>{});
 const hubs=pcHubs||[],f=pcState;
 const tabBtn=(id,label)=>`<button type="button" class="pc-tab ${f.tab===id?'on':''}" onclick="pcTab('${id}')">${label}</button>`;
 const rows=d.rows.map(r=>{
  const fusel=r.kind==='partner'&&['En transit','Partiellement reçu'].includes(r.status)&&f.tab!=='retours';
  return `<tr><td>${fusel?`<input type="checkbox" class="pc-fus" value="${r.id}" ${pcSel.has(r.id)?'checked':''} onchange="pcCount()">`:''}</td>
  <td><b class="pc-src">${esc(r.source_name)}</b><span class="sub mono">${esc(r.reference)}</span>${r.kind==='partner'&&r.client_name&&r.client_name!==r.source_name?`<span class="sub">${esc(r.client_name)}</span>`:''}${fusel?`<span class="sub pc-fusok">éligible Fusionner</span>`:''}</td>
  <td>${esc(r.destination_name)}${r.note?`<span class="sub">${esc(r.note)}</span>`:''}</td>
  <td>${esc(r.transport||'—')}</td>
  <td>${pcChip(r)}</td>
  <td>${r.track_ref?`<span class="mono">${esc(r.track_ref)}</span>`:'<span class="sub">—</span>'}</td>
  <td><b>${r.count}</b>${r.received||r.missing?`<span class="sub">${r.received} reçu(s)${r.missing?' · '+r.missing+' manquant(s)':''}</span>`:''}</td>
  <td>${r.lots?r.lots:'<span class="sub">—</span>'}</td>
  <td><span class="sub">${esc(opsDate(r.created_at))}</span></td>
  <td class="pc-rowacts">${pcActs(r)}</td>
  <td class="pc-morecell"><span class="pc-caret" onclick="pcMore('${r.kind}',${r.id},this)">›</span></td></tr>
  <tr class="pc-more-row" id="pc-more-${r.kind}-${r.id}" hidden><td colspan="11"><div class="pc-morebox">Chargement des Activités…</div></td></tr>`;
 }).join('');
 return heading('Palettes',f.tab==='default'?'Réceptionnez les palettes envoyées par les sociétés : cases, scan, fusion, écarts déclarés à la clôture.':f.tab==='retours'?'Envoyez les colis Refusé/Retourné du hub vers leurs vendeurs, palette par palette.':'Ce qui attend encore une réponse : palettes en transit et retours sans confirmation depuis '+pcRelanceDays+' jours.',`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button>`)
 +`<section class="card pc-card"><form class="pc-toolbar" onsubmit="pcGo(event)">
   <input type="date" name="date_from" value="${f.date_from}" title="Du">
   <input type="date" name="date_to" value="${f.date_to}" title="Au">
   ${select('status','Status',[['','Status'],['OPEN','OPEN'],['PARTIEL','Partiel'],['CLOSED','CLOSED']],f.status,false)}
   ${select('exc','Exceptions',[['','Exceptions'],['ecarts','Avec écarts'],['retard','Retard ≥ '+pcRelanceDays+' j']],f.exc,false)}
   ${select('hub_id','Default',[['','Tous les hubs'],...hubs.map(h=>[h.id,h.name+' · '+h.city])],f.hub_id,false)}
   <button class="btn teal solid" type="button" onclick="pcFusion()" id="pc-fusion-btn">Fusionner</button>
   <span class="pc-sel-count" id="pc-sel-count">${pcSel.size?'Selected : '+pcSel.size:''}</span>
   <span class="pc-spacer"></span>
   <span class="pc-total">Total des colis : ${d.total_colis}</span>
   <button class="pc-iconbtn" type="button" title="Actualiser" onclick="renderView()">${icon('refresh')}</button>
   ${select('size','Taille',[['30','1 - 30'],['50','1 - 50'],['100','1 - 100']],f.size,false)}
   <input name="q" value="${esc(f.q)}" placeholder="Rechercher…" aria-label="Recherche">
   <button class="pc-iconbtn" type="submit" title="Filtrer">${icon('search')}</button>
  </form>
  <div class="pc-tabs">${tabBtn('default','Default')}${tabBtn('retours','Retours')}${tabBtn('a-recevoir','A recevoir')}</div>
  <div class="pc-actions-row">${f.tab==='default'?`<button type="button" class="btn teal solid" onclick="pcRecepBtn()">${icon('down')}Reception Palette</button>${S.user.role==='admin'?`<button type="button" class="btn green solid" onclick="ppCreate()">${icon('truck')}Envoyer Palette</button>`:''}`:''}${f.tab==='retours'?`<button type="button" class="btn red solid" onclick="pcSendReturn()">${icon('truck')}Envoyer Retour</button>`:''}${f.tab==='a-recevoir'?`<p class="sub">Chaque ligne en attente garde son bouton <b>Receptionner</b> ; la relance vendeur part automatiquement après ${pcRelanceDays} jours sans réponse.</p>`:''}</div>
  <div class="pc-tablewrap"><table class="pc-table"><thead><tr><th></th><th>SOURCE</th><th>DESTINATION</th><th>TRANSPORT</th><th>STATUS</th><th>TRACKING ID</th><th>NOMBRE DES COLIS</th><th>NOMBRE DE LOTS</th><th>Date</th><th></th><th></th></tr></thead><tbody>${rows}</tbody></table>
  ${!d.rows.length?empty(f.tab==='retours'?'Aucun retour dans cette sélection':'Aucune palette dans cette sélection',f.tab==='a-recevoir'?'Rien n’attend de réponse : tout est réceptionné ou remis.':'Les palettes envoyées par les sociétés apparaîtront ici.'):''}</div>
  <div class="table-footer"><span>${d.total} palette(s)${d.total_restants?' · '+d.total_restants+' colis en attente':''}</span><div class="pagination"><span class="sub" style="margin-right:8px">${d.total?((d.page-1)*d.size+1):0} - ${Math.min(d.page*d.size,d.total)} of ${d.total}</span><button onclick="pcPage(-1)" ${d.page<=1?'disabled':''}>‹</button><span>${d.page} / ${Math.max(1,Math.ceil(d.total/d.size))}</span><button onclick="pcPage(1)" ${d.page*d.size>=d.total?'disabled':''}>›</button></div></div>
  ${d.reminded?`<p class="pc-reminded">⏰ ${d.reminded} relance(s) envoyée(s) aux vendeurs sans réponse depuis ${pcRelanceDays} jours.</p>`:''}</section>`;
}
async function pcGo(e){e.preventDefault();const g=e.target.elements;pcState.date_from=g.date_from.value;pcState.date_to=g.date_to.value;pcState.status=g.status.value;pcState.exc=g.exc.value;pcState.hub_id=g.hub_id.value;pcState.q=g.q.value.trim();pcState.size=Number(g.size.value);pcState.page=1;pcSel=new Set();await renderView()}
async function pcTab(t){pcState.tab=t;pcState.page=1;pcSel=new Set();await renderView()}
async function pcPage(delta){pcState.page+=delta;await renderView()}
function pcCount(){pcSel=new Set([...document.querySelectorAll('.pc-fus:checked')].map(x=>Number(x.value)));const b=document.getElementById('pc-fusion-btn'),c=document.getElementById('pc-sel-count');if(b)b.textContent='Fusionner'+(pcSel.size?' ('+pcSel.size+')':'');if(c)c.textContent=pcSel.size?'Selected : '+pcSel.size:''}
function pcRecepBtn(){if(!pcSel.size)return toast('Cochez d’abord une palette à réceptionner.',true);if(pcSel.size>1)return toast('Pour plusieurs palettes, utilisez « Fusionner ».',true);pcRecep([...pcSel][0])}
async function pcFusion(){const ids=[...pcSel];if(ids.length<2)return toast('Cochez au moins 2 palettes à fusionner.',true)
 try{const d=await api('/partner-palettes/fusion','POST',{palette_ids:ids});pcSel=new Set();await renderView();await ppFusOpen(d.id)}catch(e){toast(e.message,true)}}
async function pcRowRecv(kind,id){
 if(kind==='return'){const r=await api('/palette-console/return/'+id).catch(()=>null);if(r&&r.status==='Préparé')return toast('Retour encore en brouillon : ouvrez la fiche Palettes retour pour l’envoyer.',true);if(typeof openReturnPalette==='undefined')return toast('Fiche retour du vendeur : nécessite la version serveur.',true);return openReturnPalette(id)}
 const d=await api('/palette-console/partner/'+id).catch(()=>null);if(d&&d.status==='Préparé')return openPartnerPalette(id);pcRecep(id)}
/* ---------------------------------------------------- Activités (chevron) */
async function pcMore(kind,id,el){const row=document.getElementById('pc-more-'+kind+'-'+id);if(!row)return;
 if(!row.hidden){row.hidden=true;if(el)el.textContent='›';return}
 if(el)el.textContent='⌄';row.hidden=false;
 try{const d=await api('/palette-console/'+kind+'/'+id);if(row.hidden)return;
  const acts=d.activities.map(a=>`<div class="pc-act"><span class="pc-act-dot ${/annul|refus|non/i.test(a.action)?'red':'green'}">${/created|préparée|sent|ajout/i.test(a.action)?'+':'✓'}</span><div><b class="pc-act-badge">${esc(a.action)}</b><p>${esc(a.actor)} <small>· ${esc(opsDate(a.created_at))}</small></p>${a.details&&a.details.trackings&&a.details.trackings.length?`<small class="sub">${a.details.trackings.map(esc).join(' · ')}</small>`:''}</div></div>`).join('')||'<p class="sub">Aucune activité.</p>';
  const atts=d.attachments.length?`<div class="pc-gallery">${d.attachments.map(a=>`<figure><img src="${pcAttSrc(a)}" alt="pièce jointe" title="Ouvrir en grand" onclick="pcAttOpen('${a.id}')"><figcaption>${esc(a.note||'Photo')} · ${esc(a.actor)} · ${esc(opsDate(a.created_at))}</figcaption></figure>`).join('')}</div>`:'';
  row.querySelector('.pc-morebox').innerHTML=`<h4>Activités</h4>${acts}${atts}`;
 }catch(e){if(!row.hidden)row.querySelector('.pc-morebox').textContent=e.message}}
/* ---------------------------------------------------- Reception Palette (scan) */
 async function pcRecep(id){
 const ctx=ppContext('Reception Palette');
 pcRChecked=new Set();
 const draw=()=>{if(!ctx.current()||!pcRDoc)return;const d=pcRDoc;window.__pcRDraw=draw;
  ctx.node.querySelector('.modal-body').innerHTML=`<h2 class="pc-scan-title" id="pc-scan-title">Scanner les ${d.received+d.missing+pcRChecked.size} / ${d.count} colis de la palette</h2>
  <p class="sub" style="text-align:center">${esc(d.reference)} · ${esc(d.client_name)} → ${esc(d.destination_name)} · ${esc(pcLabel(d.status))}</p>
  <div class="pc-lines">${d.lines.map(l=>`<div class="pc-line"><label>
   <input type="checkbox" ${l.received_at||l.missing_at?'disabled':''} ${pcRChecked.has(l.tracking)?'checked':''} data-trk="${esc(l.tracking)}" onchange="pcTick(this)">
   <span class="pc-line-main"><b>${esc(l.recipient)}</b><small>(${esc(l.tracking)}) ${esc(l.phone||'')} · ${esc(l.city)}</small></span></label>
   ${l.received_at?'<span class="pc-st ok">RECEIVED</span>':l.missing_at?'<span class="pc-st bad">NON REÇU</span>':'<span class="pc-st">À RECEVOIR</span>'}
   ${!l.received_at&&!l.missing_at?`<button type="button" class="pc-trash" title="Déclarer non réceptionné" onclick="pcMissOne(${d.id},this)" data-trk="${esc(l.tracking)}">${pcBin}</button>`:''}</div>`).join('')}</div>
  <div class="pc-scanbar"><input id="pc-scan-in" placeholder="Scanner un tracking puis Entrée…" autocomplete="off"><button class="btn teal solid" id="pc-validate" ${pcRChecked.size?'':'disabled'}>Valider la reception</button></div>
  <p class="pc-manual-link" onclick="const x=document.getElementById('pc-scan-in');x.focus()">Ou Saisir le code manuellement</p>`;
  const inp=ctx.node.querySelector('#pc-scan-in'),vb=ctx.node.querySelector('#pc-validate');
  inp.onkeydown=e=>{if(e.key!=='Enter')return;e.preventDefault();const v=inp.value.trim();if(!v)return;
   const l=pcRDoc.lines.find(x=>x.tracking===v&&!x.received_at&&!x.missing_at);
   if(!l)return toast('Ce tracking n’est pas en attente dans cette palette.',true);
   pcRChecked.add(l.tracking);inp.value='';draw();const i2=ctx.node.querySelector('#pc-scan-in');if(i2)i2.focus()};
  vb.onclick=()=>pcValidate(d.id);
 };
 try{pcRDoc=await api('/palette-console/partner/'+id);if(!ctx.current())return;draw()}catch(e){ppError(ctx,e)}
}
function pcTick(el){const t=el.dataset.trk;if(el.checked)pcRChecked.add(t);else pcRChecked.delete(t);const d=pcRDoc;const v=document.getElementById('pc-validate');if(v)v.disabled=!pcRChecked.size;const h=document.getElementById('pc-scan-title');if(h)h.textContent=`Scanner les ${d.received+d.missing+pcRChecked.size} / ${d.count} colis de la palette`}
async function pcValidate(id){if(!pcRChecked.size)return
 try{const r=await api('/palette-console/partner/'+id+'/receive-bulk','POST',{trackings:[...pcRChecked],confirmed:true,request_key:financeKey()});pcRChecked=new Set();toast(r.received+' colis réceptionné(s)'+(r.pending?' · '+r.pending+' restants':' · palette complète'))
  pcRDoc=await api('/palette-console/partner/'+id);
  if(window.__pcRDraw)window.__pcRDraw();
  await renderView()}catch(e){toast(e.message,true)}}
async function pcMissOne(id,btn){const trk=btn.dataset.trk
 try{await api('/palette-console/partner/'+id+'/miss','POST',{tracking:trk,confirmed:true,request_key:financeKey()});
  pcRChecked.delete(trk);pcRDoc=await api('/palette-console/partner/'+id);if(window.__pcRDraw)window.__pcRDraw();
  toast('Colis déclaré non réceptionné — la société sera notifiée à la clôture.');await renderView()}catch(e){toast(e.message,true)}
}
/* ---------------------------------------------------- Envoyer Retour (scan) */
async function pcSendReturn(){
 const ctx=ppContext('Colis à retourner');pcRetCtx=ctx;pcRetSel=[];pcRetCands=[];
 let cfg=null;try{cfg=await api('/return-palettes/config');if(!ctx.current())return;if(!cfg.hubs.length)throw Error('Aucun hub actif — créez-en un depuis Palettes partenaires.')}catch(e){return ppError(ctx,e)}
 pcRetCtx._cfg=cfg;
 const loadC=async()=>{const v=ctx.node.querySelector('#pc-r-vendor').value,h=ctx.node.querySelector('#pc-r-hub').value;const serialN=++pcRetSerial;pcRetCands=[];if(!v||!h)return;
  try{const d=await api('/return-palettes/candidates?client_id='+v+'&hub_id='+h);if(serialN!==pcRetSerial||!ctx.current())return;pcRetCands=d.rows}catch(e){if(ctx.current())toast(e.message,true)}};
 const draw=()=>{if(!ctx.current())return;const c=ctx;
  c.node.querySelector('.modal-body').innerHTML=`<div class="pc-ret-form">
   <label><span>Select a transport</span><input id="pc-r-transport" list="pc-r-transports" value="${esc(c._t||'')}"><datalist id="pc-r-transports"><option value="SAT"></option><option value="Ghazala"></option><option value="car"></option><option value="Taxi"></option></datalist></label>
   <label><span>Select a destination</span><select id="pc-r-vendor"><option value="">Destination</option>${cfg.clients.map(x=>`<option value="${x.id}" ${String(c._v||'')===String(x.id)?'selected':''}>${esc(x.company||x.name)}</option>`).join('')}</select></label>
   <label><span>Hub de départ</span><select id="pc-r-hub">${cfg.hubs.map(h=>`<option value="${h.id}" ${String(c._h||(cfg.hubs.length===1?cfg.hubs[0].id:''))===String(h.id)?'selected':''}>${esc(h.name)} · ${esc(h.city)}</option>`).join('')}</select></label>
   <label><span>Tracking Code</span><input id="pc-r-code" placeholder="(optionnel) numéro de bordereau transport" value="${esc(c._c||'')}"></label>
   <label><span>Nombre de lots</span><input id="pc-r-lots" type="number" min="0" max="500" value="${esc(c._l||'')}" placeholder="Enter number of lots"></label>
  </div>
  <div class="pc-scanzone"><p>Merci de scanner les colis à retourner</p>
   <svg viewBox="0 0 120 120" class="pc-qr"><rect x="8" y="8" width="40" height="40" fill="none" stroke="#0e7f77" stroke-width="8"/><rect x="72" y="8" width="40" height="40" fill="none" stroke="#0e7f77" stroke-width="8"/><rect x="8" y="72" width="40" height="40" fill="none" stroke="#0e7f77" stroke-width="8"/><rect x="22" y="22" width="12" height="12" fill="#123a63"/><rect x="86" y="22" width="12" height="12" fill="#123a63"/><rect x="22" y="86" width="12" height="12" fill="#123a63"/><path d="M72 72h16v16H72zM96 72h16v16H96zM72 96h16v16H72zM96 96h16v16H96z" fill="#123a63"/></svg>
   <p class="pc-manual-link" onclick="document.getElementById('pc-r-scan').focus()">Ou Saisir le code manuellement</p>
   <input id="pc-r-scan" placeholder="Tracking refusé/retourné + Entrée" autocomplete="off">
  </div>
  <div id="pc-r-list">${pcRetSel.length?pcRetSel.map((p,i)=>`<div class="pc-scanrow"><span><b>${esc(p.tracking)}</b> <small>${esc(p.recipient)} · ${esc(p.city)} · ${esc(p.status)}</small></span><button type="button" class="pc-trash" title="Retirer du scan" onclick="pcRmv(${i})">${pcBin}</button></div>`).join(''):'<p class="sub" style="text-align:center;padding:10px 0">Aucun colis scanné pour l’instant.</p>'}</div>
  <div class="form-actions"><button class="btn teal solid" id="pc-r-send" ${pcRetSel.length&&c._v?'':'disabled'} onclick="pcRsend()">Valider l'envoi</button><button class="btn" onclick="closeModal()">Fermer</button></div>
  <p class="form-hint">La palette naît « En transit » vers le vendeur ; la relance automatique à ${pcRelanceDays} jours suit les retours jamais confirmés. Aucun effet financier.</p>`;
  const vf=c.node.querySelector('#pc-r-vendor'),hf=c.node.querySelector('#pc-r-hub'),sc=c.node.querySelector('#pc-r-scan'),tr=c.node.querySelector('#pc-r-transport'),cd=c.node.querySelector('#pc-r-code'),lt=c.node.querySelector('#pc-r-lots');
  const stash=()=>{c._t=tr.value;c._c=cd.value;c._l=lt.value;c._v=vf.value;c._h=hf.value;const b=c.node.querySelector('#pc-r-send');if(b)b.disabled=!(pcRetSel.length&&c._v)};
  [tr,cd,lt].forEach(x=>x.oninput=stash);
  vf.onchange=async()=>{stash();pcRetSel=[];await loadC();draw()};
  hf.onchange=async()=>{stash();pcRetSel=[];await loadC();draw()};
  sc.onkeydown=async e=>{if(e.key!=='Enter')return;e.preventDefault();const v=sc.value.trim().toLowerCase();if(!v)return;stash();
   if(!pcRetCands.length)await loadC();
   const p=pcRetCands.find(x=>x.tracking.toLowerCase()===v);
   if(!p)return toast('Colis hors liste : seuls Refusé/Retourné présents au hub du vendeur choisi.',true);
   if(pcRetSel.some(x=>x.tracking===p.tracking))return toast('Déjà scanné dans cet envoi.',true);
   pcRetSel.push(p);c.node.querySelector('#pc-r-scan').value='';draw();const f2=c.node.querySelector('#pc-r-scan');if(f2)f2.focus()};
 };
 window.__pcRetDraw=draw;
 draw();
 if(ctx._v&&ctx._h)loadC().then(()=>{if(ctx.current())draw()});
}
function pcRmv(i){pcRetSel.splice(i,1);if(window.__pcRetDraw)window.__pcRetDraw()}
async function pcRsend(){const m=document.querySelector('#modal-root .modal');if(!m)return;const get=id=>m.querySelector(id);
 const body={client_id:get('#pc-r-vendor').value||null,hub_id:get('#pc-r-hub').value||null,transport:get('#pc-r-transport').value,tracking_code:get('#pc-r-code').value,lots:Number(get('#pc-r-lots').value||0),trackings:pcRetSel.map(x=>x.tracking),confirmed:true,request_key:financeKey()};
 try{const r=await api('/palette-console/return-send','POST',body);pcRetSel=[];closeModal();toast('Retour envoyé · '+r.reference+' · '+r.count+' colis');await renderView()}catch(e){toast(e.message,true)}
}
/* ---------------------------------------------------- Clôture, sticker, bon, CSV, attachement */
async function pcClose(kind,id,remaining){
 const ctx=ppContext(kind==='return'?'Close return pallet':'Clôturer la palette');
 ctx.node.querySelector('.modal-body').innerHTML=`<p>${remaining} colis restant(s) seront déclarés <b>non réceptionnés</b>${kind==='partner'?' et la société émettrice sera notifiée (trackings inclus).':' et le vendeur destinataire sera notifié.'}</p>
 <label class="pp-consent"><input type="checkbox" id="pc-close-ok"> Je confirme la clôture et le comptage actuel (${remaining} restants).</label>
 <div class="form-actions"><button class="btn danger" id="pc-close-go" disabled>Clôturer avec écarts</button><button class="btn" onclick="closeModal()">Annuler</button></div>`;
 const ok=ctx.node.querySelector('#pc-close-ok'),go=ctx.node.querySelector('#pc-close-go');
 ok.onchange=()=>go.disabled=!ok.checked;
 go.onclick=async()=>{go.disabled=true;try{const r=await api('/palette-console/'+kind+'/'+id+'/close','POST',{confirmed:true,expected_remaining:remaining,request_key:financeKey()});closeModal();toast(r.missing?r.missing+' colis déclarés non réceptionnés'+(r.notified?' · expéditeur notifié':''):'Palette clôturée');await renderView()}catch(e){toast(e.message,true);go.disabled=false}};
}
function pcStickerHtml(d,kind){const st=(typeof S!=='undefined'&&S.settings)||{};
 const place=kind==='partner'?d.destination_name:d.source_name;
 const date=pcBonDate(d.dispatched_at||d.created_at);
 const stk=(l,n)=>{const city=String(l.city||'').trim();
  return `<section class="pc-stk"><header><img src="/static/logo.png" alt=""><span class="co"><b>${esc((typeof S!=='undefined'&&S.settings&&S.settings.company)||'ORIENTAL24 .S.A.R.L')}</b>${st.public_phone?`<br>${esc(st.public_phone)}`:''}</span></header>
 <div class="mid"><span class="zone">${esc((city[0]||'?').toUpperCase())}</span><span class="qr">${o24qrSvg(l.tracking,3)}</span><span class="seq">Colis: ${n}</span></div>
 <div class="trk">${esc(l.tracking)}</div>
 <div class="city">${esc(city||'—')}</div><div class="hub">${esc(place||'')}</div><div class="dt">${esc(date)}</div></section>`};
 return d.lines.map((l,i)=>stk(l,i+1)).join('\n')}
async function pcSticker(kind,id){const owner=ppIdentity();try{const d=await api('/palette-console/'+kind+'/'+id);if(owner!==ppIdentity())return
 await doPrint('<style>@page{size:A5;margin:6mm}body{font:11px Arial;color:#111;margin:0}.pc-stk{padding:8px 10px 30mm;display:flex;flex-direction:column;gap:6px;box-sizing:border-box;break-after:page}.pc-stk:last-child{break-after:auto}.pc-stk header{display:flex;align-items:center;gap:8px;border-bottom:1.5px solid #111;padding-bottom:6px}.pc-stk header img{height:24px}.pc-stk .co b{font-size:12.5px}.pc-stk .mid{display:flex;align-items:center;gap:14px;margin:8px 0}.pc-stk .zone{font-size:40px;font-weight:800;line-height:1;min-width:34px;text-align:center}.pc-stk .qr svg{display:block}.pc-stk .seq{writing-mode:vertical-rl;font-size:10.5px;letter-spacing:.6px;margin-left:auto;font-weight:600}.pc-stk .trk{font-size:9px;color:#555;letter-spacing:.4px}.pc-stk .city{font-size:19px;font-weight:800;line-height:1.1}.pc-stk .hub{font-size:15px;font-weight:700;font-style:italic}.pc-stk .dt{font-size:12px;font-weight:700;font-style:italic}</style>'+pcStickerHtml(d,kind),root=>{if(owner!==ppIdentity()){root.innerHTML='';throw Error('Session modifiée.')}})}catch(e){if(owner===ppIdentity())toast(e.message,true)}}
function pcBonDate(v){const x=new Date(v);return isNaN(x)?String(v||''):x.getDate()+'/'+(x.getMonth()+1)+'/'+x.getFullYear()}
function pcBonAmt(a){const n=Number(a);return isFinite(n)?String(+n.toFixed(2)):(a==null?'':String(a))}
function pcBonHtml(d,kind){const st=(typeof S!=='undefined'&&S.settings)||{};
 const who=kind==='partner'?(d.source_name+' → '+d.destination_name):(d.source_name+' → '+d.client_name);
 const place=kind==='partner'?d.destination_name:d.source_name;
 const rows=d.lines.map(l=>`<tr><td>${esc(l.tracking)}</td><td>${esc(l.city||'')}</td><td>${esc(l.recipient||'')}</td><td>${esc(l.phone||'')}</td><td>${pcBonAmt(l.amount)}</td></tr>`).join('');
 return `<article class="bon"><header><div class="co"><b>${esc((typeof S!=='undefined'&&S.settings&&S.settings.company)||'ORIENTAL24 .S.A.R.L')}</b><br>${esc(st.public_address||'Oujda — Maroc')}${st.public_phone?`<br>${esc(st.public_phone)}`:''}${st.public_email?`<br>${esc(st.public_email)}`:''}</div></header>
 <h1>${kind==='partner'?'Bon de réception':'Bon de retour'}</h1>
 <div class="meta"><div><span>Date : <b>${pcBonDate(d.dispatched_at||d.created_at)}</b></span></div><div class="c2"><b>${esc(place||'')}</b>${d.hub_phone?`<span>Tel: ${esc(d.hub_phone)}</span>`:''}${d.hub_city?`<span>${esc(d.hub_city)}, Morocco</span>`:''}</div><div class="r"><b>${esc(d.reference)}</b><br>${esc(who||'')}</div></div>
 <p class="nb">Nombre de colis : <b>${d.count}</b>${d.received?' · reçus '+d.received:''}${d.missing?' · non réceptionnés '+d.missing:''}</p>
 <table><thead><tr><th>ID de suivi</th><th>Ville</th><th>Nom</th><th>Téléphone</th><th>COD</th></tr></thead><tbody>${rows}</tbody></table>
 <div class="sign"><div>Signature du ${kind==='partner'?'hub':'vendeur'}</div><div>Signature ${esc(kind==='partner'?(d.client_name||'société'):place)}</div></div>
 <p class="foot">Document interne ORIENTAL24 · ni facture ni preuve de règlement · ${esc(d.reference)}</p></article>`}
async function pcBonPrint(kind,id){const owner=ppIdentity();try{const d=await api('/palette-console/'+kind+'/'+id);if(owner!==ppIdentity())return
 await doPrint('<style>@page{size:A4;margin:14mm}.bon{font:12px Arial;color:#142b49}.bon header{display:flex;justify-content:flex-end;border-bottom:2px solid #142b49;padding-bottom:10px}.bon header .co{text-align:right}.bon h1{font-size:19px;margin:14px 0 6px;font-weight:700}.bon .meta{display:flex;justify-content:space-between;gap:24px;font-size:11px;border-top:1px solid #142b49;border-bottom:1px solid #142b49;padding:6px 0;margin:0 0 8px}.bon .meta .c2{text-align:center}.bon .meta .r{text-align:right}.bon .meta span{display:block}.bon .nb{text-align:right;font-size:12px;margin:10px 0 4px}.bon table{width:100%;border-collapse:collapse;font-size:11px;margin-top:6px}.bon th,.bon td{border:0;border-bottom:1px solid #d7dee8;padding:6px 8px;text-align:left;overflow-wrap:anywhere}.bon th{font-weight:700;border-bottom:1.5px solid #142b49}.bon thead{display:table-header-group}.bon tr{break-inside:avoid}.bon td:nth-child(4),.bon th:nth-child(4){text-align:left}.bon .sign{display:flex;gap:60px;margin-top:34px}.bon .sign div{flex:1;border-top:1px solid #142b49;padding-top:6px;font-size:10px}.bon .foot{font-size:9.5px;color:#54677f;margin-top:14px}@media print{.bon thead{display:table-header-group}}</style>'+pcBonHtml(d,kind),root=>{if(owner!==ppIdentity()){root.innerHTML='';throw Error('Session modifiée.')}})}catch(e){if(owner===ppIdentity())toast(e.message,true)}}
function pcCsvCell(v){let s=String(v==null?'':v);if(/^[\s]*[=+@-]/.test(s))s="'"+s;return s.replace(/[\r\n]+/g,' ')}
function pcCsvBuild(d){const rows=['sep=;','ID de suivi; destinataire; adresse; Ville;Nature de produit;Numero de telephone;COD;Status']
 for(const l of d.lines)rows.push([l.tracking,l.recipient,l.address||'',l.city||'',l.product||'',l.phone||'',pcBonAmt(l.amount),String(l.current_status||'').toUpperCase()].map(pcCsvCell).join(';')+';')
 return rows.join('\n')+'\n'}
function pcCsvDownload(body,name){const blob=body instanceof Blob?body:new Blob(['\ufeff'+body],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500)}
async function pcColisCSV(kind,id){try{
 if(typeof opsOffline!=='undefined'&&opsOffline){const d=await api('/palette-console/'+kind+'/'+id);pcCsvDownload(pcCsvBuild(d),'ORIENTAL24-colis-'+(d.reference||id)+'.csv');return}
 const r=await fetch('/api/palette-console/'+kind+'/'+id+'/colis-csv');if(!r.ok)throw Error('Export indisponible sur ce document.')
 pcCsvDownload(await r.blob(),'ORIENTAL24-colis-'+kind+'-'+id+'.csv')}catch(e){toast(e.message,true)}}
async function pcAttachOpen(kind,id){
 const ctx=ppContext('Attachement · palette '+kind+' #'+id);
 const draw=async()=>{const d=await api('/palette-console/'+kind+'/'+id);if(!ctx.current())return;
  ctx.node.querySelector('.modal-body').innerHTML=`<p class="sub">Photos de preuve (état des colis, bordereaux…) — 1,5 Mo max par image, JPEG/PNG/WebP.</p>
  ${d.attachments.length?`<div class="pc-gallery">${d.attachments.map(a=>`<figure><img src="${pcAttSrc(a)}" alt="pièce jointe" title="Ouvrir en grand" onclick="pcAttOpen('${a.id}')"><figcaption>${esc(a.note||'Photo')} · ${esc(a.actor)} · ${esc(opsDate(a.created_at))}</figcaption></figure>`).join('')}</div>`:'<p class="sub">Aucune pièce jointe.</p>'}
  <div class="pc-ret-form"><input type="file" id="pc-att-file" accept="image/jpeg,image/png,image/webp"><input id="pc-att-note" placeholder="Légende (facultatif)" maxlength="300"></div>
  <div class="form-actions"><button class="btn teal solid" id="pc-att-up" disabled>Joindre</button><button class="btn" onclick="closeModal()">Fermer</button></div>`;
  const fl=ctx.node.querySelector('#pc-att-file'),up=ctx.node.querySelector('#pc-att-up');
  fl.onchange=()=>up.disabled=!fl.files[0];
  up.onclick=async()=>{const file=fl.files[0];if(!file)return;
   if(file.size>1500000)return toast('Image trop lourde (1,5 Mo maximum).',true);
   up.disabled=true;const dataUrl=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(r.result);r.onerror=rej;r.readAsDataURL(file)});
   try{await api('/palette-console/'+kind+'/'+id+'/attach','POST',{data_url:dataUrl,note:ctx.node.querySelector('#pc-att-note').value.trim()});toast('Pièce jointe ajoutée');await draw()}catch(e){toast(e.message,true);up.disabled=false}};
 };
 try{await draw()}catch(e){ppError(ctx,e)}
}
