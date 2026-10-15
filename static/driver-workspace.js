/* Driver information, reversible access controls and physical dispatch/recovery. Admin only. */
let driverRows=[],driverFilter='current',driverSearch='',driverScanContext=null;
function driverHubLabel(id){const h=(S?.hubs||[]).find(x=>Number(x.id)===Number(id));return h?`${esc(h.name)}<span class="sub">${esc(h.city)}${h.active?'':' · Inactif'}</span>`:'<span class="tag warn">À examiner · aucun Hub</span>'}
function driverWorkspaceView(rows){driverRows=rows;return heading('Livreurs','Le matin : remettre les colis. Le soir : récupérer les non-livrés.',`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button><button class="btn primary" onclick="userForm(null,'livreur')">${icon('plus')}Ajouter un livreur</button>`)+`<section class="card"><div class="driver-toolbar"><div class="tabs">${[['current','Équipe'],['blocked','Blacklist'],['archived','Archives']].map(([v,t])=>`<button class="${driverFilter===v?'active':''}" onclick="driverFilter='${v}';renderView()">${t}</button>`).join('')}</div><input id="driver-search" type="search" aria-label="Rechercher un livreur" placeholder="Nom, e-mail, téléphone…" value="${esc(driverSearch)}" oninput="driverSearch=this.value;drawDriverWorkspace()"></div><div id="driver-workspace-table"></div></section><p class="sub" style="margin-top:15px">En tournée = colis non livrés pas encore récupérés. Livrés = historique toutes périodes. Les colis récupérés ne restent pas dans la tournée ; les liens financiers historiques sont conservés.</p>`}
function drawDriverWorkspace(){const q=driverSearch.toLocaleLowerCase(),rows=driverRows.filter(d=>(driverFilter==='archived'?d.driver_archived:driverFilter==='blocked'?!d.driver_archived&&!d.active:!d.driver_archived)&&[d.name,d.email,d.phone].join(' ').toLocaleLowerCase().includes(q));const cell=$('#driver-workspace-table');if(!cell)return;cell.innerHTML=simpleTable(['Livreur','Hub local','E-mail / Téléphone','Créé le','Statut','En tournée / Livrés',''],rows.map(d=>[`<strong>${esc(d.name)}</strong>`,driverHubLabel(d.driver_hub_id),`${esc(d.email)}<span class="sub">${esc(d.phone)}</span>`,date(d.created_at),`<span class="tag ${d.active?'good':'bad'}">${d.driver_archived?'Archivé':d.active?'Actif':'Bloqué'}</span>`,`<b>${d.outstanding||0}</b> / ${d.delivered||0}`,`<div class="driver-actions"><button class="icon-btn" title="Informations du livreur" aria-label="Informations de ${esc(d.name)}" onclick="driverInfo(${d.id})">${icon('edit')}</button><button class="icon-btn driver-invoice-button" title="Facture livreur" aria-label="Générer la facture de ${esc(d.name)}" onclick="driverInvoice(${d.id},this)">${icon('dollar')}</button><button class="icon-btn danger" title="${d.active?'Blacklist · Bloquer':'Débloquer'}" aria-label="${d.active?'Bloquer':'Débloquer'} ${esc(d.name)}" onclick="driverAccess(${d.id},'${d.active?'block':'unblock'}')" ${d.driver_archived?'disabled':''}>${icon('lock')}</button><button class="icon-btn green" title="Assigner des colis · matin" aria-label="Assigner des colis à ${esc(d.name)}" onclick="openDriverScan(${d.id},'assign',this)" ${!d.active?'disabled':''}>${icon('truck')}</button><button class="icon-btn orange" title="Recevoir des colis · retour du soir" aria-label="Recevoir des colis de ${esc(d.name)}" onclick="openDriverScan(${d.id},'receive',this)">${icon('return')}</button><button class="icon-btn danger" title="${d.driver_archived?'Désarchiver':'Archiver'}" aria-label="${d.driver_archived?'Désarchiver':'Archiver'} ${esc(d.name)}" onclick="driverAccess(${d.id},'${d.driver_archived?'restore':'archive'}')">${icon('box')}</button><button class="icon-btn" title="Historique du livreur" aria-label="Historique de ${esc(d.name)}" onclick="driverSummary(${d.id})">${icon('chevron')}</button></div>`]))}
async function driverInfo(id){const owner=S?.user?.id;if(S?.user?.role!=='admin')return;modal('Informations du livreur','<p class="sub">Chargement…</p>');const node=$('.modal');node.classList.add('driver-info-drawer');node.parentElement.classList.add('driver-info-backdrop');try{const {driver:d}=await api('/drivers-workspace/'+id);const driverHubChoices=[['','À examiner · aucun Hub associé'],...(S.hubs||[]).filter(h=>h.active).map(h=>[h.id,`${h.name} · ${h.city}`])];const currentDriverHub=(S.hubs||[]).find(h=>Number(h.id)===Number(d.driver_hub_id));if(currentDriverHub&&!currentDriverHub.active)driverHubChoices.push([currentDriverHub.id,`${currentDriverHub.name} · inactif`]);if(!node.isConnected||S?.user?.id!==owner)return;node.querySelector('.modal-body').innerHTML=`<form id="driver-info-form"><div class="driver-info-content"><div class="field"><label>Identifiant</label><input value="LIV-${String(d.id).padStart(4,'0')}" readonly></div>${input('name','Nom complet',d.name,'text',true,'maxlength="120"')}${input('password','Nouveau mot de passe (facultatif)','','password',false,'minlength="10" maxlength="128" autocomplete="new-password"')}<p class="sub">Vide = inchangé. Une réinitialisation ferme les sessions du livreur.</p><div class="field"><label>E-mail</label><input value="${esc(d.email)}" readonly></div>${select('driver_hub_id','Hub local du livreur',driverHubChoices,d.driver_hub_id||'',false)}<p class="sub">L’affectation au Hub détermine les colis que ce livreur peut recevoir. Les colis actifs ambigus doivent être résolus avant le rattachement.</p>${select('city_id','Ville',[['','Non précisée'],...S.cities.map(c=>[c.id,c.name])],d.driver_city_id||'',false)}${input('phone','Téléphone',d.phone,'tel',true,'maxlength="40"')}${textarea('address','Adresse',d.driver_address||'')}<div class="form-error" role="alert"></div></div><div class="form-actions"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button class="btn primary" type="submit">Modifier</button></div></form>`;const f=node.querySelector('form');f.querySelector('textarea').maxLength=500;f.onsubmit=async e=>{e.preventDefault();const btn=f.querySelector('[type=submit]');if(btn.disabled)return;btn.disabled=true;try{await api409(g=>api('/drivers-workspace/'+id,'PATCH',{name:f.elements.name.value,phone:f.elements.phone.value,city_id:f.elements.city_id.value?Number(f.elements.city_id.value):null,driver_hub_id:f.elements.driver_hub_id.value?Number(f.elements.driver_hub_id.value):null,address:f.elements.address.value,password:f.elements.password.value,revision:g?g.driver_revision:d.driver_revision}),async()=>({driver_revision:(await api('/drivers-workspace/'+id)).driver.driver_revision}));if(S?.user?.id!==owner)return;if(node.isConnected)closeModal();await refresh();await renderView();toast('Informations du livreur enregistrées')}catch(e){if(node.isConnected){const err=f.querySelector('.form-error');err.textContent=e.message;err.style.display='block'}}finally{btn.disabled=false}}}catch(e){if(node.isConnected)node.querySelector('.modal-body').innerHTML=`<p class="form-hint">${esc(e.message)}</p>`}}
async function driverAccess(id,action){if(S?.user?.role!=='admin')return;const owner=S.user.id;try{const {driver:d}=await api('/drivers-workspace/'+id);if(S?.user?.id!==owner)return;const titles={block:'Bloquer',unblock:'Débloquer',archive:'Archiver',restore:'Désarchiver'};modal(titles[action]+' le livreur',form(`<div class="full"><h3>${esc(d.name)}</h3><p class="driver-confirm-copy">${action==='block'?'Confirmez le blocage de ce compte. Ses sessions seront fermées et aucun nouveau colis ne pourra lui être assigné. La récupération physique reste possible.':action==='archive'?'Confirmez l’archivage. Les colis non livrés doivent être récupérés et les documents actifs terminés. Le compte sera désactivé, sans supprimer l’historique ni les soldes.':action==='restore'?'Remettre ce compte dans l’équipe ? Un compte encore blacklisté restera bloqué.':'Autoriser à nouveau la connexion et les affectations ? Les anciennes sessions restent révoquées.'}</p></div>${textarea('reason','Motif de cette action','',true)}`,titles[action]));bindForm(async v=>{await api409(g=>api('/drivers-workspace/'+id+'/access','POST',{action,reason:v.reason,revision:g?g.driver_revision:d.driver_revision}),async()=>({driver_revision:(await api('/drivers-workspace/'+id)).driver.driver_revision}));if(S?.user?.id!==owner)return;await saved('Action enregistrée')})}catch(e){toast(e.message,true)}}
async function driverSummary(id){const owner=S?.user?.id;try{const d=await api('/drivers-workspace/'+id);if(S?.user?.id!==owner)return;modal(d.driver.name+' · suivi',`<div class="form-hint">La tournée affiche les non-livrés encore à récupérer. Les Livrés restent associés au livreur. Les récupérations figurent ci-dessous, sans effacement de l’historique financier.</div><h3 class="ops-subtitle">Colis encore associés · ${d.parcels.length}</h3>${simpleTable(['Référence','État','Destinataire'],d.parcels.map(p=>[esc(p.tracking),tag(p.status),esc(p.recipient)]))}<h3 class="ops-subtitle">Dernières opérations</h3>${simpleTable(['Date','Action','Colis','Acteur'],d.audit.map(a=>[opsDate(a.created_at),esc({assign:'Remise au livreur',receive:'Récupération agence',block:'Blocage',unblock:'Déblocage',archive:'Archivage',restore:'Désarchivage'}[a.action]||a.action),a.parcel_id||'—',esc(a.actor)]))}`,true)}catch(e){toast(e.message,true)}}
function driverScanSignal(kind){
 try{if(window.o24Sound&&typeof window.o24Sound.signal==='function')window.o24Sound.signal(kind)}catch(e){}
}
function driverScanToggleSound(){
 const sound=window.o24Sound,button=$('#driver-scan-sound');
 if(!sound||typeof sound.set!=='function'||typeof sound.on!=='function')return;
 sound.set(!sound.on());
 if(button){button.textContent=sound.on()?'🔊 Son activé':'🔇 Son coupé';button.setAttribute('aria-pressed',String(sound.on()))}
}
async function openDriverScan(id,mode,anchor){
 if(S?.user?.role!=='admin')return;
 const owner=S.user.id,isReceive=mode==='receive';
 modal(isReceive?'Récupération des colis':'Assigner des colis','<p class="sub">Chargement…</p>',true);
 const node=$('.modal');node.classList.add('driver-scan-modal');
 const ctx={id,mode,owner,node,stream:null,timer:null,active:true,busy:false,scans:[],pendingPayload:null};
 ctx.current=()=>ctx.active&&node.isConnected&&S?.user?.id===owner;
 driverScanContext=ctx;
 ctx.stopCamera=()=>{clearTimeout(ctx.timer);ctx.timer=null;if(ctx.stream){ctx.stream.getTracks().forEach(t=>t.stop());ctx.stream=null}const video=node.querySelector('#driver-video');if(video){video.pause?.();video.srcObject=null;video.hidden=true}const btn=node.querySelector('#driver-camera-start');if(btn)btn.innerHTML=`${icon('scan')}Caméra du téléphone`};
 modalCleanup=()=>{ctx.active=false;ctx.stopCamera();if(driverScanContext===ctx)driverScanContext=null;if(anchor?.isConnected)anchor.focus({preventScroll:true})};
 try{
  const [d,cfg]=await Promise.all([api('/drivers-workspace/'+id),api('/logistics/config')]);
  if(!ctx.current())return;
  const hubs=(cfg.hubs||[]).filter(h=>h.active);
  node.querySelector('.modal-body').innerHTML=`
   <div class="driver-scan-hero"><div class="driver-scan-icon">${icon('scan')}</div>
    <h2>${isReceive?'Scanner les colis reçus du livreur':'Scanner les colis à remettre au livreur'}</h2>
    <p><strong>${esc(d.driver.name)}</strong> · ${esc(d.driver.email)}</p>
   </div>
   <div class="driver-scan-box" id="driver-scan-box">
    <label for="driver-code">Scanner les colis (lecteur USB, clavier ou caméra)</label>
    <form id="driver-scan-form" autocomplete="off">
     <div class="driver-scan-controls">
      <input id="driver-code" name="tracking" required maxlength="80" placeholder="Tracking ORIENTAL24 puis Entrée" autocomplete="off" spellcheck="false">
      <button class="btn primary" type="submit" id="driver-scan-add">Ajouter ce colis</button>
      <button class="btn sm" type="button" id="driver-camera-start">${icon('scan')}Caméra du téléphone</button>
      <button class="btn sm" type="button" id="driver-scan-sound" data-o24-snd aria-pressed="${window.o24Sound?.on?.()!==false}" onclick="driverScanToggleSound()">${window.o24Sound?.on?.()===false?'🔇 Son coupé':'🔊 Son activé'}</button>
      <button class="btn sm" type="button" id="driver-scan-clear">↺ Vider les scans</button>
     </div>
     <div class="form-error" role="alert"></div>
    </form>
    ${isReceive?`<div class="driver-scan-hub">${select('hub_id','Agence de réception',[['','Agence · hub non précisé'],...hubs.map(h=>[h.id,h.name])],'',false)}<span class="sub">L’agence choisie s’applique à tous les colis de ce lot.</span></div>`:''}
    <div class="driver-camera"><video id="driver-video" playsinline muted hidden></video><span class="sub" id="driver-camera-status">Lecteur USB/Bluetooth, saisie manuelle ou caméra disponibles.</span></div>
    <div id="driver-scan-result" class="driver-scan-result" role="status" aria-live="polite">Présentez le premier colis. Son validé = ajouté à la liste ; le lot est appliqué seulement après confirmation.</div>
   </div>
   <div class="driver-scan-progress"><b id="driver-scan-count">0 colis scanné</b><span>${isReceive?'Les colis Livré sont refusés et restent associés au livreur pour le suivi financier.':'Aucun colis n’est affecté avant la validation du lot.'}</span></div>
   <div id="driver-scan-list" class="driver-scan-list"></div>
   <div class="driver-scan-confirm"><div><strong id="driver-scan-confirm-label">${isReceive?'Récupérer':'Affecter'} 0 colis</strong><span>${isReceive?'Les colis valides seront retirés de la tournée du livreur.':'Les colis valides apparaîtront dans l’application du livreur.'}</span></div><button type="button" class="btn primary" id="driver-scan-commit" disabled>${isReceive?'Confirmer la réception':'Confirmer l’affectation'}</button></div>
   <p class="form-hint driver-scan-hint">${isReceive?'Les commandes non livrées validées quittent la tournée du livreur. Les états Refusé/Retourné et les attributions financières historiques sont conservés.':'Après validation, l’état passe à « Reçu par le livreur ». Aucun COD n’est encaissé automatiquement.'}</p>`;
  const formNode=node.querySelector('#driver-scan-form'),code=node.querySelector('#driver-code'),err=formNode.querySelector('.form-error');
  const feedback=node.querySelector('#driver-scan-result'),list=node.querySelector('#driver-scan-list'),count=node.querySelector('#driver-scan-count'),confirmLabel=node.querySelector('#driver-scan-confirm-label'),commit=node.querySelector('#driver-scan-commit'),hub=node.querySelector('#f-hub_id');
  const show=(kind,message)=>{if(!ctx.current())return;feedback.className='driver-scan-result'+(kind?' '+kind:'');feedback.setAttribute('role',kind==='error'?'alert':'status');feedback.textContent=message};
  const paint=()=>{
   if(!ctx.current())return;
   const n=ctx.scans.length;
   count.textContent=`${n} colis scanné${n===1?'':'s'}`;
   confirmLabel.textContent=`${isReceive?'Récupérer':'Affecter'} ${n} colis`;
   commit.disabled=ctx.busy||n===0;
   list.innerHTML=n?ctx.scans.map(p=>`<div class="driver-scan-row"><span class="driver-scan-row-code">${esc(p.tracking)}</span><span class="driver-scan-row-main"><strong>${esc(p.recipient||'Destinataire')}</strong><small>${esc(p.city||'')} · ${esc(p.status||'')}</small></span><button type="button" class="icon-btn" data-driver-scan-remove="${p.parcel_id}" aria-label="Retirer ${esc(p.tracking)} du lot" title="Retirer du lot">×</button></div>`).join(''):'<p class="sub driver-scan-empty">Aucun colis scanné pour le moment.</p>';
  };
  const queued=id=>ctx.scans.some(p=>p.parcel_id===id);
  ctx.addScan=async raw=>{
   const tracking=String(raw||'').trim();
   if(!ctx.current()||ctx.busy)return;
   if(ctx.pendingPayload){driverScanSignal('dup');show('duplicate','Le lot attend une confirmation identique. Videz-le et rescanez si vous devez le modifier.');return}
   if(!tracking){driverScanSignal('err');show('error','Scannez ou saisissez un numéro de suivi.');return}
   const normalized=tracking.toUpperCase();
   if(ctx.scans.some(p=>String(p.tracking).toUpperCase()===normalized)){
    driverScanSignal('dup');show('duplicate',`${tracking} · déjà présent dans ce lot, pas de doublon.`);code.value='';code.focus({preventScroll:true});return;
   }
   if(ctx.scans.length>=200){driverScanSignal('err');show('error','Limite de 200 colis par lot atteinte. Confirmez ce lot avant d’en commencer un autre.');code.value='';return}
   ctx.busy=true;code.disabled=true;formNode.querySelector('#driver-scan-add').disabled=true;err.textContent='';err.style.display='none';
   try{
    const result=await api('/drivers-workspace/'+id+'/scan-preview','POST',{tracking,mode});
    if(!ctx.current())return;
    const p=result.parcel;
    if(result.already||queued(p.id)){
     driverScanSignal('dup');show('duplicate',`${p.tracking} · déjà ${isReceive?'récupéré':'remis à ce livreur'} ; non ajouté au lot.`);return;
    }
    ctx.scans.push({parcel_id:p.id,revision:p.ops_revision,tracking:p.tracking,recipient:p.recipient,city:p.city,status:p.status,amount:p.amount});
    driverScanSignal('ok');show('ok',`✓ Ajouté : ${p.tracking} · ${p.recipient} (${ctx.scans.length} dans le lot).`);
   }catch(e){
    if(!ctx.current())return;
    driverScanSignal('err');show('error',`${tracking} · ${e.message||'Colis refusé.'} Non ajouté au lot.`);
   }finally{
    if(ctx.current()){ctx.busy=false;code.disabled=false;formNode.querySelector('#driver-scan-add').disabled=false;code.value='';paint();code.focus({preventScroll:true})}
   }
  };
  formNode.onsubmit=e=>{e.preventDefault();ctx.addScan(code.value)};
  list.onclick=e=>{if(ctx.busy)return;if(ctx.pendingPayload){show('duplicate','Le lot attend une confirmation identique. Videz-le et rescanez si vous devez le modifier.');return}const button=e.target.closest('[data-driver-scan-remove]');if(!button)return;const pid=Number(button.getAttribute('data-driver-scan-remove'));const item=ctx.scans.find(p=>p.parcel_id===pid);ctx.scans=ctx.scans.filter(p=>p.parcel_id!==pid);ctx.pendingPayload=null;driverScanSignal('dup');show('duplicate',item?`${item.tracking} retiré du lot.`:'Colis retiré du lot.');paint();code.focus({preventScroll:true})};
  node.querySelector('#driver-scan-clear').onclick=()=>{if(ctx.busy||!ctx.scans.length)return;ctx.scans=[];ctx.pendingPayload=null;if(hub)hub.disabled=false;driverScanSignal('dup');show('duplicate','Lot vidé. Vous pouvez recommencer le scan.');paint();code.focus({preventScroll:true})};
  node.querySelector('#driver-camera-start').onclick=()=>driverScanCamera(ctx);
  commit.onclick=async()=>{
   if(ctx.busy||!ctx.scans.length||!ctx.current())return;
   ctx.busy=true;ctx.stopCamera();code.disabled=true;commit.disabled=true;if(hub)hub.disabled=true;show('','Validation du lot en cours…');
   const payload=ctx.pendingPayload||(ctx.pendingPayload={mode,scans:ctx.scans.map(p=>({parcel_id:p.parcel_id,revision:p.revision})),hub_id:hub?.value?Number(hub.value):null,confirmed:true,request_key:financeKey()});
   try{
    const result=await api('/drivers-workspace/'+id+'/scan-batch','POST',payload);
    if(!ctx.current())return;
    ctx.pendingPayload=null;driverScanSignal(result.count?'done':'dup');
    const plural=result.count===1?'':'s';
    const message=isReceive?`Réception validée : ${result.count} colis récupéré${plural} et retiré${plural} de la tournée.`:`Affectation confirmée : ${result.count} colis remis au livreur.`;
    const alreadyPlural=result.already===1?'':'s';
    const extra=result.already?` ${result.already} colis déjà traité${alreadyPlural}, ignoré${alreadyPlural}.`:'';
    closeModal();try{await refresh();await renderView()}catch(e){}toast(message+extra);
   }catch(e){
    if(ctx.current()){driverScanSignal('err');show('error',`Confirmation non reçue : ${e.message||'Erreur de validation.'} Le lot est atomique. Réessayez à l’identique ; si une version a changé, videz le lot puis rescanez.`);ctx.busy=false;code.disabled=false;commit.disabled=ctx.scans.length===0;if(hub)hub.disabled=!!ctx.pendingPayload;code.focus({preventScroll:true})}
   }
  };
  paint();if(innerWidth>760)code.focus({preventScroll:true});
 }catch(e){if(ctx.current())node.querySelector('.modal-body').innerHTML=`<p class="form-hint">${esc(e.message)}</p>`}
}
async function driverScanCamera(ctx){
 const node=ctx.node,button=node.querySelector('#driver-camera-start'),status=node.querySelector('#driver-camera-status');
 if(!ctx.current()||ctx.busy)return;
 if(ctx.stream){ctx.stopCamera();status.textContent='Caméra arrêtée. Lecteur USB/Bluetooth ou saisie manuelle disponibles.';return}
 if(opsOffline||!window.BarcodeDetector||!navigator.mediaDevices?.getUserMedia){status.textContent='Caméra indisponible ici. Utilisez un lecteur USB/Bluetooth ou la saisie manuelle.';driverScanSignal('err');return}
 button.disabled=true;
 try{
  const supported=await BarcodeDetector.getSupportedFormats();
  const allowed=typeof window.o24CamFormats==='function'?window.o24CamFormats():['qr_code','code_128'];
  const formats=supported.filter(f=>allowed.includes(f));
  if(!formats.length)throw Error('Aucun format de code compatible avec cette caméra.');
  if(!ctx.current()||ctx.busy)return;
  const detector=new BarcodeDetector({formats});
  const stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
  if(!ctx.current()||ctx.busy){stream.getTracks().forEach(t=>t.stop());return}
  ctx.stream=stream;
  const video=node.querySelector('#driver-video');video.srcObject=stream;video.hidden=false;await video.play();
  button.innerHTML=`${icon('close')}Arrêter la caméra`;status.textContent='Caméra active : présentez un code à la fois.';
  let last='';
  const loop=async()=>{
   if(!ctx.current()||!ctx.stream)return;
   try{
    if(!ctx.busy){
     const detected=await detector.detect(video);
     if(!ctx.current())return;
     const value=detected[0]?.rawValue?.trim()||'';
     if(!value)last='';
     else if(value!==last){last=value;codeToScan(value)}
    }
   }catch(e){if(ctx.current())status.textContent='Lecture caméra interrompue : '+(e.message||'réessayez ou utilisez le lecteur USB.')}
   if(ctx.current()&&ctx.stream)ctx.timer=setTimeout(loop,350);
  };
  const codeToScan=value=>{const input=node.querySelector('#driver-code');input.value=value;ctx.addScan(value)};
  loop();
 }catch(e){
  if(ctx.stream)ctx.stopCamera();
  if(ctx.current()){status.textContent='Caméra indisponible ou refusée. Utilisez le lecteur USB/Bluetooth ou la saisie manuelle.';showDriverScanCameraError(ctx,e)}
 }finally{if(ctx.current())button.disabled=false}
}
function showDriverScanCameraError(ctx,error){driverScanSignal('err');const message=error&&error.message?error.message:'Caméra indisponible.';const el=ctx.node.querySelector('#driver-scan-result');if(el){el.className='driver-scan-result error';el.setAttribute('role','alert');el.textContent=message}}
