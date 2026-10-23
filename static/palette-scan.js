/* === ORIENTAL24 · palette-scan (début) === */
/* v1.19.0 — « Réception palette » : le scan COLLECTE (aucune réception immédiate),
   puis réception groupée + validation en un seul clic → état « Réceptionnée » automatique.
   Caméra du téléphone : démarrage auto, lecture continue, torche, vibration + sons.
   100 % local (Web Audio / BarcodeDetector), aucune ressource externe. */
let ppSound=(()=>{try{return localStorage.getItem('o24-pp-sound')!=='0'}catch(e){return true}})();
let ppAc=null;
function ppTone(f,t0,dur,type,vol){const o=ppAc.createOscillator(),g=ppAc.createGain();o.type=type||'sine';o.frequency.setValueAtTime(f,t0);o.connect(g);g.connect(ppAc.destination);g.gain.setValueAtTime(0.0001,t0);g.gain.exponentialRampToValueAtTime(vol||0.22,t0+0.012);g.gain.exponentialRampToValueAtTime(0.0001,t0+dur);o.start(t0);o.stop(t0+dur+0.03)}
function ppUnlockSound(){
 if(!ppSound)return;
 try{const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;ppAc=ppAc||new AC();if(ppAc.state==='suspended')ppAc.resume().catch(()=>{})}catch(e){}
}
function ppBeep(kind){
 if(!ppSound)return;
 try{
  const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;
  ppAc=ppAc||new AC();if(ppAc.state==='suspended')ppAc.resume();
  const t=ppAc.currentTime+0.005;
  if(kind==='ok'){ppTone(880,t,0.12,'sine',0.22);ppTone(1320,t+0.09,0.15,'sine',0.22)}
  else if(kind==='done'){ppTone(660,t,0.11);ppTone(880,t+0.09,0.11);ppTone(1320,t+0.19,0.22)}
  else if(kind==='rx-duplicate'){ppTone(180,t,0.18,'triangle',0.25);ppTone(130,t+0.20,0.25,'triangle',0.25)}
  else if(kind==='rx-error'){ppTone(520,t,0.09,'square',0.16);ppTone(520,t+0.14,0.09,'square',0.16);ppTone(520,t+0.28,0.09,'square',0.16)}
  else if(kind==='dup'){ppTone(740,t,0.11,'triangle',0.2);ppTone(740,t+0.16,0.11,'triangle',0.2)}
  else{ppTone(200,t,0.15,'square',0.2);ppTone(150,t+0.14,0.26,'square',0.2)}
 }catch(e){}
}
function ppVib(kind){try{if(!navigator.vibrate)return;navigator.vibrate(kind==='ok'?70:kind==='done'?[60,50,130]:kind==='dup'?[50,60,50]:[95,60,95])}catch(e){}}
function ppSignal(kind){ppBeep(kind);ppVib(kind)}
// Reception-only feedback: no change to outbound transfers or return scans.
function ppReceptionSignal(kind){ppBeep(kind==='dup'?'rx-duplicate':kind==='err'?'rx-error':kind);ppVib(kind)}
function ppReceptionGuide(){return 'Présentez le premier colis. Son « validé » = ajouté ; son grave = DOUBLE — commande déjà scannée. Autre erreur : trois bips courts.'}
function ppReceptionControls(){return `<p class="form-hint">${ppReceptionGuide()}</p><button type="button" class="btn sm" data-o24-snd onclick="window.o24Sound.set(!window.o24Sound.on())">${ppSound?'🔊 Son activé':'🔇 Son coupé'}</button>`}
async function ppReceiveWithFeedback(send,isCurrent=()=>true){
 ppUnlockSound();
 try{const r=await send();if(isCurrent())ppReceptionSignal(r.already_received?'dup':'ok');return r}
 catch(e){if(isCurrent())ppReceptionSignal('err');throw e}
}
function ppSoundToggle(){ppSound=!ppSound;try{localStorage.setItem('o24-pp-sound',ppSound?'1':'0')}catch(e){}const b=document.getElementById('pp-rx-snd');if(b)b.textContent=ppSound?'🔊 Son activé':'🔇 Son coupé';if(ppSound)ppBeep('ok')}
function ppRxMsg(kind,html){const el=document.getElementById('pp-rx-msg');if(!el)return;el.className='pp-rx-msg'+(kind?' '+kind:'');el.innerHTML=html}
function ppRxFlash(kind){const box=document.getElementById('pp-rx-box');if(!box)return;box.classList.remove('ok','err','dup');if(kind)box.classList.add(kind);setTimeout(()=>box.classList.remove('ok','err','dup'),1100)}
async function ppRxFind(code){const d=await api('/partner-palettes?q='+encodeURIComponent(code)+'&size=20');const rows=(d&&d.rows)||[];const c=String(code).toLowerCase();
 return rows.find(x=>String(x.reference||'').toLowerCase()===c)||rows.find(x=>String(x.partner_reference||'').toLowerCase()===c)||rows[0]||null}
/* --- caméra : formats dispo + contrôleur réutilisable --- */
function ppRxCamFormats(){try{if(!window.BarcodeDetector)return[];return['code_128','code_39','code_93','qr_code','ean_13','ean_8','itf','codabar','upc_a','upc_e','data_matrix']}catch(e){return[]}}
async function ppRxCamSupported(){if(!window.BarcodeDetector||!navigator.mediaDevices?.getUserMedia)return false;try{const f=await BarcodeDetector.getSupportedFormats();return f.some(x=>ppRxCamFormats().includes(x))}catch(e){return false}}
function ppRxCam(box,btn,state,onCode,onStatus){
 let stream=null,det=null,raf=0,track=null,last='',lastAt=0,torchBtn=null,starting=false,generation=0;
  const setState=t=>{if(state)state.textContent=t};
  const hideVideo=()=>{try{const v=box&&box.querySelector('video');if(v){if(typeof v.pause==='function')v.pause();v.srcObject=null}}catch(e){}if(box)box.hidden=true};
  const loop=async()=>{
  if(!stream)return;
  try{
   const codes=await det.detect(box.querySelector('video'));
   const v=(codes[0]&&codes[0].rawValue||'').trim();
   const now=Date.now();
   if(v&&(v!==last||now-lastAt>2600)){last=v;lastAt=now;onCode(v)}
  }catch(e){}
  raf=requestAnimationFrame(loop);
 };
 return {
  active:()=>!!stream,
  async start(){
   if(stream)return true;
   if(starting)return false;
   starting=true;const token=++generation;let pending=null;
   try{
    if(!window.BarcodeDetector||!navigator.mediaDevices?.getUserMedia)throw Error('Caméra non prise en charge sur cet appareil.');
    const supported=await BarcodeDetector.getSupportedFormats();
    if(token!==generation)return false;
    const fmts=supported.filter(f=>ppRxCamFormats().includes(f));
    if(!fmts.length)throw Error('Formats de codes-barres non pris en charge.');
    det=new BarcodeDetector({formats:fmts});
    pending=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
    if(token!==generation){pending.getTracks().forEach(t=>t.stop());return false}
    stream=pending;
    const v=box.querySelector('video');v.srcObject=stream;box.hidden=false;await v.play();
    if(token!==generation){pending.getTracks().forEach(t=>t.stop());stream=null;hideVideo();return false}
    track=stream.getVideoTracks()[0];setState('Caméra active — présentez le code');
    if(btn)btn.textContent='⏹ Arrêter la caméra';
    try{const caps=track.getCapabilities?track.getCapabilities():{};if(caps&&caps.torch&&!torchBtn){torchBtn=document.createElement('button');torchBtn.type='button';torchBtn.className='btn sm';torchBtn.textContent='💡 Lampe';let on=false;torchBtn.onclick=async()=>{on=!on;try{await track.applyConstraints({advanced:[{torch:on}]});torchBtn.textContent=on?'💡 Lampe ON':'💡 Lampe'}catch(e){}};btn.parentNode.insertBefore(torchBtn,btn.nextSibling)}}catch(e){}
    loop();return true;
   }catch(e){
    pending?.getTracks().forEach(t=>t.stop());if(stream===pending)stream=null;
    det=null;hideVideo();
    if(token===generation)setState(e.message||'Caméra refusée ou indisponible — utilisez la saisie.');return false
   }finally{starting=false}
  },
  stop(){
   generation++;
   try{cancelAnimationFrame(raf)}catch(e){}
   if(stream){stream.getTracks().forEach(t=>t.stop());stream=null}
   det=null;hideVideo();if(btn)btn.textContent='📷 Caméra du téléphone';setState('Caméra arrêtée')
  }
 };
}
async function ppRxCamWidget(){
 const ok=await ppRxCamSupported();
 return `<button type="button" class="btn sm" id="pp-rx-cam-btn">📷 Caméra du téléphone</button>${ok?'':`<span class="sub pp-rx-camera-note">Caméra indisponible sur cet appareil : lecteur USB/Bluetooth ou saisie manuelle.</span>`}`;
}
/* --- étape 1 : code palette --- */
function ppReceiveStart(){
 if(!(S.user.role==='admin'||S.user.role==='agent'))return;
 const ctx=ppContext('Réception palette');
 ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-rxstart"><div class="pp-rxqr">${icon('scan')}</div><h3>Scanner le code de la palette pour démarrer la réception</h3>
  <div class="pp-rxbox" id="pp-rx-box"><input id="pp-rx-code" placeholder="PP-000123 · réf. société · tracking d’un colis" autocomplete="off" maxlength="120"></div>
  <div class="pp-rx-tools"><button class="btn primary" type="button" id="pp-rx-go">Démarrer la réception</button></div>
  <div class="pp-rx-msg" id="pp-rx-msg">Ou saisir le code manuellement puis valider.</div>
  <p class="sub">Le scan ne réceptionne rien : il prépare la liste. La réception est enregistrée à la fin, en un seul clic.</p></div>`;
 const inp=ctx.node.querySelector('#pp-rx-code');inp.focus();
 const go=async()=>{
  const code=inp.value.trim();
  if(!code){ppSignal('err');ppRxMsg('err','Scannez ou saisissez un code.');return}
  try{
   const r=await ppRxFind(code);
   if(!r){ppSignal('err');ppRxFlash('err');ppRxMsg('err','Aucune palette pour ce code : <b>'+esc(code)+'</b>.');return}
   if(r.status==='Préparé'){ppSignal('err');ppRxFlash('err');ppRxMsg('err','Palette <b>'+esc(r.reference)+'</b> encore en brouillon : la société doit d’abord confirmer l’envoi.');return}
   if(r.status==='Annulé'){ppSignal('err');ppRxFlash('err');ppRxMsg('err','Palette <b>'+esc(r.reference)+'</b> annulée : aucune réception possible.');return}
   if(r.status==='Clôturé (écarts)'||r.status==='Reçu'){ppSignal('dup');ppRxFlash('dup');ppRxMsg('dup','Palette <b>'+esc(r.reference)+'</b> déjà traitée : '+r.received+' / '+r.count+' reçus.');return}
   ppSignal('ok');inp.value='';if(S?.user?.role==='agent')await openPartnerPalette(r.id);else await ppReceiveScan(r.id);
  }catch(e){ppSignal('err');ppRxMsg('err',esc(e.message))}
 };
 ctx.node.querySelector('#pp-rx-go').onclick=go;
 inp.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.preventDefault();go()}});
}
/* --- étape 2 : collecte au scan, puis réception groupée --- */
async function ppReceiveScan(id){return openReceptionCollection('partner',id)}
async function ppReceiveLegacyScan(id){
 const ctx=ppContext('Réception palette');
 const st={lines:[],byCode:new Map(),scanned:new Map(),cam:null,busy:false};
 modalCleanup=()=>{try{st.cam&&st.cam.stop()}catch(e){}};
 const remain=()=>st.lines.filter(l=>!l.received_at&&!l.missing_at&&!st.scanned.has(String(l.tracking).toUpperCase())).length;
 const norm=t=>String(t||'').trim().toUpperCase();
 const lineRow=l=>{const c=norm(l.tracking),on=st.scanned.has(c);
  return `<div class="pp-rx-line ${l.received_at?'ok':l.missing_at?'miss':on?'scanned':''}"><span class="mono">${esc(l.tracking)}</span><span class="sub">${esc(l.recipient)} · ${esc(l.city)}</span>
   ${l.received_at?'<span class="tag good">Déjà réceptionné</span>':l.missing_at?'<span class="tag warn">Manquant</span>':on?`<span class="tag good">✓ Scanné</span><button type="button" class="btn sm pp-rx-x" data-und="${esc(l.tracking)}" title="Retirer du lot">✕</button>`:'<span class="tag blue">À scanner</span>'}</div>`};
 const askList=()=>st.lines.filter(l=>!l.received_at&&!l.missing_at);
 const scanBox=()=>`<div class="pp-rxbox" id="pp-rx-box">
   <label for="pp-rx-track">Scanner les colis (lecteur USB, clavier ou caméra)</label>
   <div class="pp-rx-entry">
    <input id="pp-rx-track" placeholder="Tracking ORIENTAL24 puis Entrée" autocomplete="off" maxlength="80">
    <button class="btn primary" type="button" id="pp-rx-one">Ajouter ce colis</button>
    <span id="pp-rx-cam-slot"></span>
    <button class="btn sm" type="button" id="pp-rx-snd" onclick="ppSoundToggle()">${ppSound?'🔊 Son activé':'🔇 Son coupé'}</button>
    <button class="btn sm" type="button" id="pp-rx-reset">↺ Vider les scans</button>
   </div>
   <div class="pp-rx-cam" id="pp-rx-cam" hidden><video playsinline muted></video></div>
   <span class="sub pp-rx-camera-state" id="pp-rx-cam-state" aria-live="polite"></span>
   <div class="pp-rx-msg" id="pp-rx-msg" role="status" aria-live="polite">${ppReceptionGuide()}</div></div>`;
 const validBox=()=>{const n=askList().length,left=remain();
  return `<div class="pp-validate" id="pp-rx-val"><b class="${left?'':'ready'}">${left?('Il reste '+left+' colis à scanner'):(n+' / '+n+' colis scannés ✓')}</b>
   <button class="btn primary" type="button" id="pp-rx-validate" ${left?'disabled':''}>Réceptionner les ${n} colis et valider</button>
   <p class="sub">${left?'Scannez les colis restants : la réception s’enregistre une seule fois à la fin.':'Cliquez : tous les colis scannés seront réceptionnés d’un coup et la palette passera à « Réceptionnée ».'}</p></div>`};
 const paint=()=>{
  const n=askList().length,got=st.scanned.size,left=remain();
  const cnt=ctx.node.querySelector('#pp-rx-count');if(cnt)cnt.innerHTML=`${got}<small> / ${n} scannés</small>`;
  const rem=ctx.node.querySelector('#pp-rx-remain');if(rem)rem.textContent=left?left+' restant(s) à scanner':'tous les colis scannés';
  const list=ctx.node.querySelector('#pp-rx-list');if(list)list.innerHTML=st.lines.map(lineRow).join('');
  const val=ctx.node.querySelector('#pp-rx-val');if(val)val.outerHTML=validBox();
  const vb=ctx.node.querySelector('#pp-rx-validate');
  if(vb)vb.onclick=()=>validate();
  const stt=ctx.node.querySelector('#pp-rx-status');
  if(stt)stt.innerHTML=ppBadge(left?'Partiellement reçu':(n?'Partiellement reçu':'En transit'));
 };
 const undo=t=>{const c=norm(t);if(st.scanned.delete(c)){ppBeep('dup');ppRxMsg('dup','Retiré du lot : <b>'+esc(t)+'</b>');paint()}};
 const add=async(code,fromCam)=>{
  if(st.busy)return;ppUnlockSound();st.busy=true;
  try{
   const c=norm(code);
   const l=st.byCode.get(c);
   if(!l){ppReceptionSignal('err');if(!fromCam){ppRxFlash('err');ppRxMsg('err','✗ Hors palette : <b>'+esc(code)+'</b> — ce colis n’est pas dans cette palette.')}else{ppRxMsg('err','✗ Hors palette : <b>'+esc(code)+'</b>')}return}
   if(l.missing_at){ppReceptionSignal('err');ppRxMsg('err','✗ <b>'+esc(l.tracking)+'</b> déclaré manquant : à traiter en incident.');return}
   if(l.received_at){ppReceptionSignal('dup');ppRxFlash('dup');ppRxMsg('dup','DOUBLE — commande déjà scannée / réceptionnée : <b>'+esc(l.tracking)+'</b>. Aucun ajout.') ;return}
   if(st.scanned.has(c)){ppReceptionSignal('dup');ppRxFlash('dup');ppRxMsg('dup','DOUBLE — commande déjà scannée : <b>'+esc(l.tracking)+'</b>. Aucun ajout.');return}
   st.scanned.set(c,l);
   ppReceptionSignal('ok');ppRxFlash('ok');
   ppRxMsg('ok','✓ Ajouté : <b>'+esc(l.tracking)+'</b> ('+st.scanned.size+'/'+askList().length+')');
   paint();
   if(remain()===0){ppSignal('done');ppRxMsg('ok','Tous les colis sont scannés ✓ — cliquez <b>« Réceptionner les '+askList().length+' colis et valider »</b>.');}
  }finally{st.busy=false}
 };
 const validate=async()=>{
  const btn=ctx.node.querySelector('#pp-rx-validate');if(btn)btn.disabled=true;
  try{
   const n=askList().length;ppSignal('done');
   let cur=await api('/partner-palettes/'+id);
   const key=financeKey();
   const post=rev=>api('/partner-palettes/'+id+'/receive-all','POST',{confirmed:true,request_key:key,revision:rev,expected_remaining:cur.remaining});
   let r;try{r=await post(cur.revision)}catch(e){if(!CONFLICT_RX.test(String(e.message||'')))throw e;cur=await api('/partner-palettes/'+id);r=await post(cur.revision)}
   closeModal();await renderView();
   toast('Réception validée : '+n+' colis · palette '+((r&&r.status)||'Reçu')+' ✓');
  }catch(e){if(btn)btn.disabled=false;ppReceptionSignal('err');toast(e.message,true)}
 };
 const bind=()=>{
  const one=ctx.node.querySelector('#pp-rx-one'),inp=ctx.node.querySelector('#pp-rx-track');
  if(inp){inp.focus();inp.addEventListener('keydown',ev=>{if(ev.key==='Enter'){ev.preventDefault();const t=inp.value.trim();if(!t){ppReceptionSignal('err');ppRxMsg('err','Scannez ou saisissez un tracking.');return}inp.value='';add(t,false)}})}
  if(one)one.onclick=()=>{const t=inp.value.trim();if(!t){ppReceptionSignal('err');ppRxMsg('err','Scannez ou saisissez un tracking.');return}inp.value='';add(t,false)};
  const rz=ctx.node.querySelector('#pp-rx-reset');if(rz)rz.onclick=()=>{if(!st.scanned.size)return;st.scanned.clear();ppBeep('dup');ppRxMsg('dup','Lot vidé — rescannez les colis.');paint()};
  const list=ctx.node.querySelector('#pp-rx-list');
  if(list)list.onclick=ev=>{const b=ev.target.closest('[data-und]');if(b)undo(b.getAttribute('data-und'))};
  const vb=ctx.node.querySelector('#pp-rx-validate');if(vb)vb.onclick=validate;
  /* Caméra du téléphone : même rangée de contrôles que le scan clavier/USB. */
  const slot=ctx.node.querySelector('#pp-rx-cam-slot');
  if(slot){
   ppRxCamWidget().then(html=>{if(!ctx.current())return;slot.innerHTML=html;const cbtn=slot.querySelector('#pp-rx-cam-btn');if(!cbtn)return;
    const box=ctx.node.querySelector('#pp-rx-cam'),cst=ctx.node.querySelector('#pp-rx-cam-state');
    st.cam=ppRxCam(box,cbtn,cst,(code)=>{add(code,true)},null);
    cbtn.onclick=async()=>{if(st.cam.active()){st.cam.stop()}else{const ok=await st.cam.start();if(ok)ppRxMsg('ok','Caméra active : scannez les colis.')}};
    if(ctx.node.querySelector('#pp-rx-track'))ctx.node.querySelector('#pp-rx-track').focus();
   }).catch(e=>{if(ctx.current())slot.innerHTML=`<span class="sub pp-rx-camera-note">${esc(e.message)}</span>`});
  }
 };
 const draw=async()=>{
  const d=await api('/partner-palettes/'+id);
  st.lines=d.lines||[];st.byCode=new Map(st.lines.map(l=>[norm(l.tracking),l]));
  const body=ctx.node.querySelector('.modal-body');
  if(!body.querySelector('#pp-rx-body')){
   ctx.node.querySelector('h2').textContent='Réception '+d.reference;
   body.innerHTML=`<div id="pp-rx-body"><div class="pp-document-head"><div><span class="eyebrow orange">RÉCEPTION AU SCAN · COLLECTE</span><h3>${esc(d.reference)} · ${esc(d.client_name)}</h3><p>${esc(d.destination_name)}${d.transport?' · '+esc(d.transport):''}</p></div><span id="pp-rx-status">${ppBadge(d.status)}</span></div>
   <div class="pp-progress"><strong id="pp-rx-count">0<small> / ${st.lines.filter(l=>!l.received_at&&!l.missing_at).length} scannés</small></strong><div><b>colis scannés</b><span id="pp-rx-remain">…</span></div></div>
   ${scanBox()}
   <div class="pp-rx-list" id="pp-rx-list"></div>
   <div id="pp-rx-val-slot">${validBox()}</div>
   <div class="pp-actions"><button class="btn" type="button" onclick="openPartnerPalette(${id})">${icon('layers')}Fiche complète / incident</button><button class="btn" type="button" onclick="closeModal();renderView()">Fermer</button></div></div>`;
   bind();
  }
  paint();
 };
 try{await draw()}catch(e){ppError(ctx,e)}
}
/* v1.22.0 — API partagée : sons, vibration et caméra réutilisables par les autres écrans de scan
   (envoi de palette retour au scan). Un seul moteur, donc exactement les mêmes sons. */
window.o24Sound={unlock:ppUnlockSound,beep:ppBeep,signal:ppSignal,vibrate:ppVib,on:()=>ppSound,set:v=>{ppSound=!!v;try{localStorage.setItem('o24-pp-sound',ppSound?'1':'0')}catch(e){}document.querySelectorAll('[data-o24-snd]').forEach(b=>{b.textContent=ppSound?'🔊 Son activé':'🔇 Son coupé'});if(ppSound)ppBeep('ok')}};
window.o24Cam=ppRxCam;window.o24CamFormats=ppRxCamFormats;window.o24CamSupported=ppRxCamSupported;
/* === ORIENTAL24 · palette-scan (fin) === */

/* Seller pickup receipt: collect individual scans, then commit one atomic batch. */
async function rbCollectReceive(id){
 if(!['admin','agent'].includes(S?.user?.role))return;
 const ctx=ppContext('Réception du ramassage');ppUnlockSound();
 let cam=null,busy=false,frozen=null,doc=null;const scanned=new Map(),norm=v=>String(v||'').trim().toUpperCase();
 modalCleanup=()=>{try{cam?.stop()}catch(e){}};
 const current=()=>ctx.current();
 const message=(kind,text)=>{if(!current())return;const box=ctx.node.querySelector('#rb-collect-feedback');box.className='pp-rx-msg '+kind;box.textContent=text};
 try{
  doc=await api('/ramassage-bons/'+id);if(!current())return;
  const lines=doc.lines.filter(l=>l.active||l.received_at),pending=lines.filter(l=>l.active&&!l.received_at);
  const byCode=new Map(lines.map(l=>[norm(l.tracking),l]));
  ctx.node.querySelector('h2').textContent='Réception '+doc.reference;
  ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-document-head"><div><span class="eyebrow orange">RÉCEPTION AU SCAN · COLLECTE</span><h3>${esc(doc.reference)} · ${esc(doc.client_company||doc.client_name)}</h3><p>${esc(doc.hub_name||'')}</p></div><span>${rbStatusTag(doc.status)}</span></div><div class="pp-progress"><strong id="rb-collect-count">0<small> / ${pending.length} scannés</small></strong><div><b>colis scannés</b><span id="rb-collect-remaining"></span></div></div>
  <div class="pp-rxbox"><label for="rb-collect-input">Scanner les colis (lecteur USB, clavier ou caméra)</label><form id="rb-collect-form" class="pp-rx-entry"><input id="rb-collect-input" autocomplete="off" maxlength="80" placeholder="Tracking ORIENTAL24 puis Entrée"><button type="submit" class="btn primary">Ajouter ce colis</button><span id="pp-rx-cam-slot"></span><button type="button" class="btn sm" data-o24-snd onclick="window.o24Sound.set(!window.o24Sound.on())">${ppSound?'🔊 Son activé':'🔇 Son coupé'}</button><button type="button" class="btn sm" id="rb-collect-reset">↺ Vider les scans</button></form><div class="pp-rx-cam" id="rb-collect-camera" hidden><video playsinline muted></video></div><span id="rb-collect-camera-state" class="sub" aria-live="polite"></span><div class="pp-rx-msg" id="rb-collect-feedback" role="status" aria-live="polite">${ppReceptionGuide()}</div></div>
  <div class="pp-rx-list" id="rb-collect-list"></div><div class="pp-validate"><b id="rb-collect-ready"></b><button type="button" class="btn primary" id="rb-collect-confirm" disabled>Réceptionner les ${pending.length} colis et valider</button><p class="sub">Scannez tous les colis restants. Aucune réception n’est enregistrée avant la validation finale.</p></div><div class="pp-actions"><button type="button" class="btn" id="rb-collect-close">Fermer</button></div>`;
  const input=ctx.node.querySelector('#rb-collect-input'),form=ctx.node.querySelector('#rb-collect-form'),confirm=ctx.node.querySelector('#rb-collect-confirm');
  const paint=()=>{
   ctx.node.querySelector('#rb-collect-count').innerHTML=`${scanned.size}<small> / ${pending.length} scannés</small>`;
   const left=pending.length-scanned.size;
   ctx.node.querySelector('#rb-collect-ready').className=left?'':'ready';
   ctx.node.querySelector('#rb-collect-remaining').textContent=left?left+' restant(s) à scanner':'Tous les colis restants sont scannés';
   ctx.node.querySelector('#rb-collect-ready').textContent=!pending.length?'Aucun colis restant à réceptionner':left?'Il reste '+left+' colis à scanner':scanned.size+' / '+pending.length+' colis scannés ✓';
   confirm.disabled=busy||left>0||!pending.length||!['Confirmé','En cours'].includes(doc.status);
   ctx.node.querySelector('#rb-collect-list').innerHTML=lines.map(l=>`<div class="pp-rx-line ${l.received_at?'ok':scanned.has(l.parcel_id)?'scanned':''}"><span class="mono">${esc(l.tracking)}</span><span class="sub">${esc(l.recipient||'')} · ${esc(l.city||'')}</span>${l.received_at?'<span class="tag good">Déjà réceptionné</span>':scanned.has(l.parcel_id)?`<span class="tag good">✓ Scanné</span><button type="button" class="btn sm pp-rx-x" data-rb-undo="${l.parcel_id}" ${busy||frozen?'disabled':''} title="Retirer du lot">✕</button>`:'<span class="tag blue">À scanner</span>'}</div>`).join('');
  };
  const add=code=>{
   if(!current()||busy||frozen)return;ppUnlockSound();const key=norm(code),line=byCode.get(key);
   if(!key)return;
   if(!line){ppReceptionSignal('err');message('err','✗ Hors bon : '+code+' — cette commande ne figure pas dans ce ramassage.');return}
   if(line.received_at||scanned.has(line.parcel_id)){ppReceptionSignal('dup');message('dup','DOUBLE — commande déjà scannée / réceptionnée : '+line.tracking+'. Aucun ajout.');return}
   if(!line.active||!['Confirmé','En cours'].includes(doc.status)){ppReceptionSignal('err');message('err','Ce bon n’est pas disponible pour réception.');return}
   scanned.set(line.parcel_id,line);ppReceptionSignal('ok');paint();
   message('ok','✓ Ajouté : '+line.tracking+' ('+scanned.size+'/'+pending.length+')'+(scanned.size===pending.length?' — tous les colis sont scannés. Validez la réception.':''));
  };
  form.onsubmit=e=>{e.preventDefault();const value=input.value;input.value='';add(value);input.focus()};
  ctx.node.querySelector('#rb-collect-reset').onclick=()=>{if(busy||frozen)return;scanned.clear();paint();message('','Lot vidé — scannez à nouveau les commandes.');input.focus()};
  ctx.node.querySelector('#rb-collect-list').onclick=e=>{const btn=e.target.closest('[data-rb-undo]');if(!btn||busy||frozen)return;scanned.delete(Number(btn.dataset.rbUndo));paint();message('','Commande retirée de la liste des scans.');input.focus()};
  ctx.node.querySelector('#rb-collect-close').onclick=()=>closeModal();
  confirm.onclick=async()=>{
   if(busy||!current()||scanned.size!==pending.length||!pending.length)return;
   frozen=frozen||{parcel_ids:[...scanned.keys()],snapshot:doc.snapshot,confirmed:true,request_key:financeKey()};
   busy=true;input.disabled=true;form.querySelector('button').disabled=true;ctx.node.querySelector('#rb-collect-reset').disabled=true;paint();
   try{
    await api('/ramassage-bons/'+id+'/receive-batch','POST',frozen);
    if(!current())return;cam?.stop();ppReceptionSignal('done');closeModal();await refresh();await renderView();toast('Réception validée : '+pending.length+' colis · '+doc.reference);
   }catch(e){if(current()){ppReceptionSignal('err');message('err',e.message+' Aucune nouvelle confirmation automatique. Réessayez la même validation, ou fermez et rouvrez le bon pour contrôler les scans.')}}
   finally{busy=false;if(current())paint()}
  };
  paint();input.focus();
  const slot=ctx.node.querySelector('#pp-rx-cam-slot');slot.innerHTML=await ppRxCamWidget();if(!current())return;
  const cameraButton=slot.querySelector('#pp-rx-cam-btn');
  if(cameraButton){cam=ppRxCam(ctx.node.querySelector('#rb-collect-camera'),cameraButton,ctx.node.querySelector('#rb-collect-camera-state'),add,null);cameraButton.onclick=()=>{ppUnlockSound();if(cam.active())cam.stop();else cam.start()}}
 }catch(e){ppError(ctx,e)}
}
