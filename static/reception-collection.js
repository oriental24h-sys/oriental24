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
  doc.lines=doc.lines.map(l=>({...l,parcel_id:l.id,active:!l.excluded}));
  const lines=doc.lines.filter(l=>l.active||l.received_at),pending=lines.filter(l=>l.active&&!l.received_at);
  const byCode=new Map(lines.map(l=>[norm(l.tracking),l]));
  ctx.node.querySelector('h2').textContent=(sending?'Envoi ':'Réception ')+doc.reference;
  ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-document-head"><div><span class="eyebrow orange">${sending?'ENVOI AU SCAN · COLLECTE':'RÉCEPTION AU SCAN · COLLECTE'}</span><h3>${esc(doc.reference)} · ${esc(doc.route||'')}</h3><p>${kind==='return'?(sending?'Retour au vendeur — préparation du départ':'Retour au vendeur — confirmation physique de la remise'):''}</p></div><span>${rbStatusTag(doc.status)}</span></div><div class="pp-progress"><strong id="rb-collect-count">0<small> / ${pending.length} scannés</small></strong><div><b>colis scannés</b><span id="rb-collect-remaining"></span></div></div>
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
   if(!line){ppReceptionSignal('err');message('err','✗ Hors bon : '+code+' — cette commande ne figure pas dans ce document.');return}
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
    await api(endpoint,'POST',frozen);
    if(!current())return;cam?.stop();ppReceptionSignal('done');closeModal();await refresh();await renderView();toast((sending?'Envoi validé : ':'Réception validée : ')+frozen.line_ids.length+' colis · '+doc.reference);
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
