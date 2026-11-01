/* Unified physical reception: all scans local until one final server transaction. */
async function openReceptionCollection(kind,id,mode='receive'){
 const sending=mode==='dispatch';
 const endpoint=(sending?'/dispatch-collection/':'/reception-collection/')+kind+'/'+id;
 if(!['admin','agent','client'].includes(S?.user?.role))return;
 const ctx=ppContext(sending?'Envoi · collecte':'Réception · collecte');ppUnlockSound();
 let cam=null,busy=false,frozen=null,doc=null;const scanned=new Map(),norm=v=>String(v||'').trim().toUpperCase();
 modalCleanup=()=>{try{cam?.stop()}catch(e){}};
 const current=()=>ctx.current();
 const message=(kind,text)=>{if(!current())return;const box=ctx.node.querySelector('#rb-collect-feedback');box.className='pp-rx-msg '+kind;box.textContent=text};
 try{
  doc=await api(endpoint);if(!current())return;
  const partialSend=sending&&doc.allow_partial_dispatch;
  // Palette retour créée vide : chaque CMD scannée est ajoutée au manifeste au moment du scan.
  const returnScan=sending&&kind==='transfer'&&['return_to_central','return_to_origin'].includes(doc.palette_purpose);
  doc.lines=doc.lines.map(l=>({...l,parcel_id:l.id,active:!l.excluded}));
  const lines=doc.lines.filter(l=>l.active||l.received_at),pending=lines.filter(l=>l.active&&!l.received_at);
  const byCode=new Map(lines.map(l=>[norm(l.tracking),l]));
  ctx.node.querySelector('h2').textContent=(sending?'Envoi ':'Réception ')+doc.reference;
  ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-document-head"><div><span class="eyebrow orange">${sending?'ENVOI AU SCAN · COLLECTE':'RÉCEPTION AU SCAN · COLLECTE'}</span><h3>${esc(doc.reference)} · ${esc(doc.route||'')}</h3><p>${kind==='return'?(sending?'Retour au vendeur — préparation du départ':'Retour au vendeur — confirmation physique de la remise'):kind==='transfer'&&['return_to_central','return_to_origin'].includes(doc.palette_purpose)?(sending?'Palette retour — scannez chaque CMD : elle s’ajoute ici avec sa décision (part direct · rendez-vous · à valider).':'Palette retour — le scan de réception réintègre automatiquement les CMD liées au stock.'):''}</p></div><span>${rbStatusTag(doc.status)}</span></div><div class="pp-progress"><strong id="rb-collect-count">0<small> / ${pending.length} scannés</small></strong><div><b>colis scannés</b><span id="rb-collect-remaining"></span></div></div>
  <div class="pp-rxbox"><label for="rb-collect-input">Scanner les colis (lecteur USB, clavier ou caméra)</label><form id="rb-collect-form" class="pp-rx-entry"><input id="rb-collect-input" autocomplete="off" maxlength="160" placeholder="Tracking ORIENTAL24 puis Entrée"><button type="submit" class="btn primary">Ajouter ce colis</button><span id="pp-rx-cam-slot"></span><button type="button" class="btn sm" data-o24-snd onclick="window.o24Sound.set(!window.o24Sound.on())">${ppSound?'🔊 Son activé':'🔇 Son coupé'}</button><button type="button" class="btn sm" id="rb-collect-reset">↺ Vider les scans</button></form><div class="pp-rx-cam" id="rb-collect-camera" hidden><video playsinline muted></video></div><span id="rb-collect-camera-state" class="sub" aria-live="polite"></span><div class="pp-rx-msg" id="rb-collect-feedback" role="status" aria-live="polite">${ppReceptionGuide()}</div></div>
  <div class="pp-rx-list" id="rb-collect-list"></div><div class="pp-validate"><b id="rb-collect-ready"></b><button type="button" class="btn primary" id="rb-collect-confirm" disabled>${sending?'Envoyer':'Réceptionner'} les ${pending.length} colis et valider</button><p class="sub">${esc(doc.confirmation)} ${sending?'Aucun envoi':'Aucune réception'} n’est enregistré avant la validation finale.</p></div><div class="pp-actions"><button type="button" class="btn" id="rc-detail">Fiche complète / incident</button><button type="button" class="btn" id="rb-collect-close">Fermer</button></div>`;
  const input=ctx.node.querySelector('#rb-collect-input'),form=ctx.node.querySelector('#rb-collect-form'),confirm=ctx.node.querySelector('#rb-collect-confirm');
  const linePlaceholder=l=>l.blocked?`<span class="tag warn">${sending?'À vérifier':'Départ non scanné'}</span>`:'<span class="tag blue">À scanner</span>';
  const paint=()=>{
   ctx.node.querySelector('#rb-collect-count').innerHTML=`${scanned.size}<small> / ${pending.length} scannés</small>`;
   const left=pending.length-scanned.size;
   ctx.node.querySelector('#rb-collect-ready').className=(sending&&!partialSend?left===0:scanned.size>0)?'ready':'';
   ctx.node.querySelector('#rb-collect-remaining').textContent=left?left+' restant(s) à scanner':'Tous les colis restants sont scannés';
   ctx.node.querySelector('#rb-collect-ready').textContent=!pending.length?(sending?'Aucun colis restant à envoyer':'Aucun colis restant à réceptionner'):left?'Il reste '+left+' colis à scanner':scanned.size+' / '+pending.length+' colis scannés ✓';
   if(!sending||partialSend){
    confirm.textContent=(sending?'Envoyer':'Réceptionner')+' les '+scanned.size+' colis scannés et valider';
    ctx.node.querySelector('#rb-collect-ready').textContent=scanned.size?scanned.size+' colis à valider · '+left+(sending?' non scanné(s) : disponibles pour une autre palette':' restant(s) pour plus tard'):'Scannez au moins un colis pour valider';
   }
   confirm.disabled=busy||!scanned.size||!doc.available||(sending&&!partialSend&&(left>0||pending.some(l=>l.blocked)))||[...scanned.values()].some(l=>l.blocked);
   ctx.node.querySelector('#rb-collect-list').innerHTML=lines.map(l=>`<div class="pp-rx-line ${l.received_at?'ok':scanned.has(l.parcel_id)?'scanned':''}"><span class="mono">${esc(l.tracking)}</span><span class="sub">${l.recipient||l.city?esc([l.recipient,l.city].filter(Boolean).join(' · ')):(sending?'Détails masqués hors de votre Hub':'Détails disponibles après réception')}</span>${l.received_at?`<span class="tag good">${sending?'Déjà envoyé':'Déjà réceptionné'}</span>`:scanned.has(l.parcel_id)?`<span class="tag good">✓ Scanné</span><button type="button" class="btn sm pp-rx-x" data-rb-undo="${l.parcel_id}" ${busy||frozen?'disabled':''} title="Retirer du lot">✕</button>`:linePlaceholder(l)}</div>`).join('');
  };
  const add=async code=>{
   if(!current()||busy||frozen)return;ppUnlockSound();const key=norm(code),line=byCode.get(key);
   if(!key)return;
   if(!line){
    if(returnScan)return addByScan(key);
    ppReceptionSignal('err');message('err','✗ Hors bon : '+code+' — cette commande ne figure pas dans ce document.');return
   }
   if(line.received_at||scanned.has(line.parcel_id)){ppReceptionSignal('dup');message('dup','DOUBLE — commande déjà scannée / '+(sending?'envoyée':'réceptionnée')+' : '+line.tracking+'. Aucun ajout.');return}
   if(line.blocked){ppReceptionSignal('err');message('err',sending?(line.blocked_reason||'Commande non admissible pour ce départ.'):'Scan de sortie manquant : '+line.tracking+'. Actualisez après le départ.');return}
   if(!line.active||!doc.available){ppReceptionSignal('err');message('err',sending?'Ce bon n’est pas disponible pour envoi.':'Ce bon n’est pas disponible pour réception.');return}
   if(sending){
    busy=true;paint();
    try{const r=await api(endpoint+'/check?'+new URLSearchParams({tracking:line.tracking,snapshot:doc.snapshot}));if(!current())return;if(r.already_scanned){ppReceptionSignal('dup');message('dup','DOUBLE — commande déjà envoyée.');return}}
    catch(e){if(current()){ppReceptionSignal('err');message('err',e.message)}return}
    finally{busy=false;if(current())paint()}
   }
   scanned.set(line.parcel_id,line);ppReceptionSignal('ok');paint();
   message('ok','✓ Ajouté : '+line.tracking+' ('+scanned.size+'/'+pending.length+')'+(scanned.size===pending.length?' — tous les colis sont scannés. Validez la réception.':''));
  };
  const addByScan=async(code,extra={})=>{
   if(!current()||busy||frozen)return;
   busy=true;paint();
   try{
    const r=await api('/logistics/documents/'+id+'/scan-add','POST',{tracking:code,...extra});
    if(!current())return;
    if(r.needs_confirmation){askDecision(r,code);return}
    if(r.snapshot)doc.snapshot=r.snapshot;
    let line=byCode.get(norm(code));
    if(!line){
     line={id:r.line_id,parcel_id:r.line_id,tracking:r.tracking,recipient:r.recipient,city:r.city,received_at:null,excluded:false,blocked:false};
     doc.lines.push(line);lines.push(line);byCode.set(norm(r.tracking),line);pending.push(line);
    }
    if(line.received_at||scanned.has(line.parcel_id)){ppReceptionSignal('dup');message('dup','DOUBLE — commande déjà scannée : '+line.tracking+'.');return}
    scanned.set(line.parcel_id,line);ppReceptionSignal('ok');
    message('ok','✓ '+r.tracking+' ajouté à la palette · '+scanned.size+' CMD scannée(s)');
    paint();
   }catch(e){if(current()){ppReceptionSignal('err');message('err',e.message)}}
   finally{busy=false;if(current())paint()}
  };
  const askDecision=(r,code)=>{
   const box=ctx.node.querySelector('#rb-collect-feedback');if(!box)return;
   ppReceptionSignal('err');
   box.className='pp-rx-msg warn';
   box.innerHTML=`<div class="hp-decision"><strong>${esc(r.tracking)}</strong><p>${esc(r.message||'')}</p>
    <div class="hp-decision-actions"><button type="button" class="btn primary sm" data-rb-yes>Oui · envoyer en retour</button>
    <button type="button" class="btn sm" data-rb-no>Non · reste à l’agence</button></div></div>`;
   box.querySelector('[data-rb-yes]').onclick=()=>{if(!current())return;addByScan(code,{confirmed:r.decision==='confirm',overridden:r.decision==='blocked'})};
   box.querySelector('[data-rb-no]').onclick=()=>{if(!current())return;message('warn',code+' laissé à l’agence — non envoyé.');if(input){input.value='';input.focus({preventScroll:true})}};
  };
  form.onsubmit=async e=>{e.preventDefault();const value=input.value;input.value='';await add(value);if(current())input.focus()};
  ctx.node.querySelector('#rb-collect-reset').onclick=()=>{if(busy||frozen)return;scanned.clear();paint();message('','Lot vidé — scannez à nouveau les commandes.');input.focus()};
  ctx.node.querySelector('#rb-collect-list').onclick=e=>{const btn=e.target.closest('[data-rb-undo]');if(!btn||busy||frozen)return;scanned.delete(Number(btn.dataset.rbUndo));paint();message('','Commande retirée de la liste des scans.');input.focus()};
  ctx.node.querySelector('#rb-collect-close').onclick=()=>closeModal();
  ctx.node.querySelector('#rc-detail').onclick=()=>{if(kind==='partner')openPartnerPalette(id,true);else if(kind==='return')openReturnPalette(id,true);else if(kind==='transfer')openOpsDocument(id,true);else closeModal()};
  confirm.onclick=async()=>{
   if(busy||!current()||!scanned.size||!doc.available||(sending&&!partialSend&&scanned.size!==pending.length))return;
   frozen=frozen||{line_ids:[...scanned.keys()],snapshot:doc.snapshot,confirmed:true,request_key:financeKey()};
   busy=true;input.disabled=true;form.querySelector('button').disabled=true;ctx.node.querySelector('#rb-collect-reset').disabled=true;paint();
   try{
    const result=await api(endpoint,'POST',frozen);
    if(!current())return;cam?.stop();ppReceptionSignal('done');closeModal();await refresh();await renderView();
    const stockNotice=!sending&&result.stock_restocked?.length?` · ${result.stock_restocked.length} CMD stock réintégrée(s) automatiquement au Hub Central`:'';
    toast((sending?'Envoi validé : ':'Réception validée : ')+frozen.line_ids.length+' colis · '+doc.reference+stockNotice);
   }catch(e){if(current()){ppReceptionSignal('err');message('err',e.message+' Aucune nouvelle confirmation automatique. Réessayez la même validation, ou fermez et rouvrez le bon pour contrôler les scans.')}}
   finally{busy=false;if(current())paint()}
  };
  paint();input.focus();
  const slot=ctx.node.querySelector('#pp-rx-cam-slot');slot.innerHTML=await ppRxCamWidget();if(!current())return;
  const cameraButton=slot.querySelector('#pp-rx-cam-btn');
  if(cameraButton){cam=ppRxCam(ctx.node.querySelector('#rb-collect-camera'),cameraButton,ctx.node.querySelector('#rb-collect-camera-state'),add,null);cameraButton.onclick=()=>{ppUnlockSound();if(cam.active())cam.stop();else cam.start()}}
 }catch(e){ppError(ctx,e)}
}

function openDispatchCollection(kind,id){return openReceptionCollection(kind,id,'dispatch')}

/* ── Réception groupée : plusieurs palettes cochées → UNE seule validation ──────
   Le serveur réceptionne chaque palette entière dans sa propre sauvegarde : une
   palette en erreur n'annule pas les autres et son motif est renvoyé à l'écran. */
/* Réception de PLUSIEURS palettes, mais AU SCAN.
   « Réceptionner la sélection » n'enregistre plus tout automatiquement : l'écran
   liste toutes les CMD des palettes cochées, on scanne physiquement les colis
   présents, et seuls les colis scannés sont réceptionnés. Les autres restent
   « restant(s) » sur leur palette. */
async function openBulkReceptionScan(items){
 if(!['admin','agent','client'].includes(S?.user?.role))return;
 const sel=(items||[]).filter(x=>x&&Number(x.id)>0);
 if(!sel.length){toast('Cochez au moins une palette à réceptionner.',true);return}
 if(sel.length>30){toast('Maximum 30 palettes par réception groupée.',true);return}
 const ctx=ppContext('Réceptionner la sélection');ppUnlockSound();
 const norm=v=>String(v||'').trim().toUpperCase();
 let byCode=new Map(),docs=[],scanned=new Map(),busy=false,frozen=false;
 const current=()=>ctx.current();
 const message=(kind,text)=>{if(!current())return;const box=ctx.node.querySelector('#bulk-rx-msg');if(!box)return;box.className='pp-rx-msg '+kind;box.textContent=text};
 ctx.node.querySelector('.modal-body').innerHTML='<p class="sub">Chargement des palettes sélectionnées…</p>';
 try{
  for(const it of sel){
   const kind=it.kind||'transfer';
   const doc=await api('/reception-collection/'+kind+'/'+Number(it.id));
   docs.push(doc);
   for(const l of (doc.lines||[])){
    const excluded=!!l.excluded;
    byCode.set(norm(l.tracking),{kind,did:doc.id,ref:doc.reference,snapshot:doc.snapshot,lineId:l.id,
      tracking:l.tracking,received_at:l.received_at,blocked:l.blocked,excluded});
   }
  }
 }catch(e){if(current())ctx.node.querySelector('.modal-body').innerHTML=`<p class="form-hint orange">${esc(e.message)}</p><div class="form-actions"><button class="btn" onclick="closeModal()">Fermer</button></div>`;return}
 if(!current())return;
 const pending=[...byCode.values()].filter(l=>!l.received_at&&!l.excluded&&!l.blocked);
 if(!pending.length){
  ctx.node.querySelector('.modal-body').innerHTML=`<p class="form-hint orange">Aucun colis restant à réceptionner dans les palettes cochées.</p><div class="form-actions"><button class="btn" onclick="closeModal()">Fermer</button></div>`;
  return;
 }
 const docOf=did=>docs.find(d=>d.id===did);
 let cam=null;
 modalCleanup=()=>{try{cam&&cam.stop()}catch(e){}};
 ctx.node.querySelector('.modal-body').innerHTML=`
  <p class="form-hint">Scannez uniquement les colis <b>physiquement présents</b>. À la validation, seuls les colis scannés sont réceptionnés ; les autres restent « restant(s) » sur leur palette.</p>
  <div class="pp-rxbox"><label for="bulk-rx-input">Scanner les colis (lecteur USB, clavier ou caméra)</label>
    <form id="bulk-rx-form" class="pp-rx-entry">
      <input id="bulk-rx-input" autocomplete="off" maxlength="80" spellcheck="false" placeholder="Tracking ORIENTAL24 puis Entrée" aria-label="Tracking du colis reçu">
      <button type="submit" class="btn primary">${icon('scan')}Ajouter ce colis</button>
      <span id="pp-rx-cam-slot"></span>
      <button type="button" class="btn sm" data-o24-snd onclick="window.o24Sound.set(!window.o24Sound.on())">${ppSound?'🔊 Son activé':'🔇 Son coupé'}</button>
      <button type="button" class="btn sm" id="bulk-rx-reset">↺ Vider les scans</button>
    </form>
    <div class="pp-rx-cam" id="bulk-rx-camera" hidden><video playsinline muted></video></div>
    <span id="bulk-rx-cam-state" class="sub" aria-live="polite"></span>
    <small class="sub" id="bulk-rx-count">0 / ${pending.length} colis attendus</small>
  </div>
  <p class="pp-rx-msg" id="bulk-rx-msg" role="status" aria-live="polite"></p>
  <p class="form-hint">${ppReceptionGuide()}</p>
  <div class="pp-rx-list" id="bulk-rx-list"></div>
  <div class="pp-validate"><b id="bulk-rx-ready"></b><button type="button" class="btn primary" id="bulk-rx-go" disabled>Réceptionner les colis scannés</button></div>`;
 const input=ctx.node.querySelector('#bulk-rx-input'),form=ctx.node.querySelector('#bulk-rx-form'),go=ctx.node.querySelector('#bulk-rx-go');
 const paint=()=>{
  if(!current())return;
  ctx.node.querySelector('#bulk-rx-count').textContent=`${scanned.size} / ${pending.length} colis attendus`;
  ctx.node.querySelector('#bulk-rx-ready').textContent=scanned.size?`${scanned.size} colis scanné(s) · ${pending.length-scanned.size} pas encore scanné(s)`:'Scannez au moins un colis reçu.';
  go.disabled=busy||frozen||!scanned.size;
  ctx.node.querySelector('#bulk-rx-list').innerHTML=docs.map(d=>{
   const lines=[...byCode.values()].filter(l=>l.did===d.id);
   const done=lines.filter(l=>l.received_at).length,hit=lines.filter(l=>scanned.has(l.lineId)).length;
   const rest=lines.length-done-hit;
   return `<div class="pp-rx-line ${rest===0?'ok':''}"><span><b>${esc(d.reference)}</b><small class="sub">${lines.length} colis · ${done} déjà reçu(s) · ${hit} scanné(s) ici</small></span><span class="tag ${rest===0?'good':'warn'}">${rest===0?'Complet':rest+' restant(s)'}</span></div>`;
  }).join('');
 };
 const add=code=>{
  const key=norm(code);if(!key)return;
  const line=byCode.get(key);
  if(!line){ppReceptionSignal('err');message('err','✗ Hors sélection : '+code+' n’appartient à aucune palette cochée.');return}
  if(scanned.has(line.lineId)){ppReceptionSignal('dup');message('dup','DOUBLE — déjà scanné : '+line.tracking);return}
  if(line.received_at){ppReceptionSignal('dup');message('dup','Déjà réceptionné : '+line.tracking);return}
  if(line.excluded){ppReceptionSignal('err');message('err','Colis exclu du manifeste : '+line.tracking);return}
  if(line.blocked){ppReceptionSignal('err');message('err','Départ non scanné : '+line.tracking+' — terminez le départ de cette palette.');return}
  scanned.set(line.lineId,line);ppReceptionSignal('ok');paint();
  message('ok','✓ Ajouté : '+line.tracking+' · '+line.ref+' ('+scanned.size+'/'+pending.length+')');
 };
 form.onsubmit=e=>{e.preventDefault();if(!current()||busy||frozen)return;const v=input.value;input.value='';add(v);input.focus({preventScroll:true})};
 if(innerWidth>760)input.focus({preventScroll:true});
 paint();
 /* Même scan que les autres écrans : caméra du téléphone, son, « Vider les scans ». */
 const resetBtn=ctx.node.querySelector('#bulk-rx-reset');
 if(resetBtn)resetBtn.onclick=()=>{if(!current()||busy||frozen)return;scanned.clear();paint();message('','Lot vidé — scannez à nouveau les colis reçus.');try{input.focus({preventScroll:true})}catch(e){}};
 const camSlot=ctx.node.querySelector('#pp-rx-cam-slot');
 if(camSlot){
  try{
   camSlot.innerHTML=await ppRxCamWidget();
  }catch(e){camSlot.innerHTML=`<span class="sub pp-rx-camera-note">${esc(e.message)}</span>`}
  if(!current())return;
  const cbtn=camSlot.querySelector('#pp-rx-cam-btn');
  if(cbtn){
   cam=ppRxCam(ctx.node.querySelector('#bulk-rx-camera'),cbtn,ctx.node.querySelector('#bulk-rx-cam-state'),code=>add(code),null);
   cbtn.onclick=()=>{ppUnlockSound();if(cam.active())cam.stop();else cam.start()};
  }
 }
 go.onclick=async()=>{
  if(!current()||!scanned.size||busy||frozen)return;
  busy=true;frozen=true;paint();
  const label=go.textContent;go.textContent='Réception en cours…';
  const key=financeKey();
  const groups=new Map();
  for(const l of scanned.values()){
   if(!groups.has(l.did))groups.set(l.did,[l]);
   else groups.get(l.did).push(l);
  }
  const results=[];
  try{
   for(const [did,lines] of groups){
    const doc=docOf(did);
    try{
     const r=await api('/reception-collection/'+lines[0].kind+'/'+did,'POST',
       {confirmed:true,request_key:(key+'-'+did).slice(0,80),line_ids:lines.map(l=>l.lineId),snapshot:doc.snapshot});
     results.push({ok:true,ref:doc.reference,received:Number(r.received||lines.length)});
    }catch(e){results.push({ok:false,ref:doc.reference,error:e.message})}
   }
   if(!current())return;
   try{cam&&cam.stop()}catch(e){}
   const good=results.filter(r=>r.ok),bad=results.filter(r=>!r.ok);
   const total=good.reduce((n,r)=>n+r.received,0);
   ctx.node.querySelector('.modal-body').innerHTML=`
    <p class="form-hint">${good.length?`<b>${total} colis réceptionné(s)</b> sur ${good.length} palette(s).`:''}${bad.length?` ${bad.length} palette(s) en erreur.`:''}</p>
    ${bad.length?`<div class="pp-rx-list">${bad.map(r=>`<div class="pp-rx-line"><span><b>${esc(r.ref)}</b><small class="sub">${esc(r.error)}</small></span><span class="tag bad">Non réceptionnée</span></div>`).join('')}</div>`:''}
    <p class="form-hint">Les colis non scannés restent « restant(s) » sur leur palette : rouvrez-la avec « Ouvrir / recevoir » pour compléter.</p>
    <div class="form-actions"><button class="btn primary" onclick="closeModal()">Terminer</button></div>`;
   ppReceptionSignal(bad.length?'err':'ok');
   if(typeof renderView==='function')await renderView();
  }finally{if(current()){frozen=false;busy=false;go.textContent=label}}
 };
}
