/* === ORIENTAL24 · return-scan (début) === */
/* v1.22.0 « Envoi de palette retour au scan » — même écran que la réception palette :
   on choisit le vendeur et le hub, on scanne les colis un par un (lecteur USB, clavier ou caméra
   du téléphone), le lot s'affiche en bas, puis UN SEUL bouton « Valider et envoyer le retour »
   crée la palette retour et l'expédie au vendeur.

   À chaque scan, un verdict et un son :
     • validé (aigu)  : colis du vendeur, resté plus d'une semaine chez nous (état ≠ « Livré ») → ajouté ;
     • refusé (grave) : colis d'un autre vendeur · code inconnu · colis déjà « Livré » · colis déjà
                        réservé dans une autre palette ;
     • à confirmer    : colis du vendeur mais la semaine n'est pas encore passée → son refusé puis
                        question « l'ajouter quand même ? OUI / NON » (OUI ajoute, NON n'ajoute pas) ;
     • doublon        : colis déjà scanné dans ce lot.

   100 % local (Web Audio / BarcodeDetector) : aucune ressource ni API payante. */
let rpSc=null;
function rpScKey(){try{return [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('')}catch(e){return 'k'+Date.now()+Math.random().toString(16).slice(2)}}
function rpScSound(kind){try{if(window.o24Sound)return o24Sound.signal(kind)}catch(e){}}
function rpScWeek(){return (rpSc&&rpSc.week_days)||7}
function rpScNorm(v){return String(v||'').trim()}
function rpScErr(e){rpMsg('err',esc(e&&e.message||'Erreur'))}

function rpMsg(kind,html){const el=document.getElementById('rp-sc-msg');if(!el)return;el.className='pp-rx-msg'+(kind?' '+kind:'');el.innerHTML=html}
function rpFlash(kind){const box=document.getElementById('rp-sc-box');if(!box)return;box.classList.remove('ok','err','dup');if(kind)box.classList.add(kind);setTimeout(()=>box.classList.remove('ok','err','dup'),1100)}

window.rpScanStart=async()=>{
 rpSc={step:1,client_id:0,hub_id:0,transport:'',lots:0,tracking_code:'',note:'',week_days:7,lot:[],seen:{},pending:null,cfg:null,loading:false};
 let cfg=null;
 try{cfg=await rpConfig()}catch(e){toast(e.message||'Configuration indisponible',true);return}
 rpSc.cfg=cfg;
 rpModal();
};

async function rpConfig(){
 if(typeof opsOffline!=='undefined'&&opsOffline)return o24RpScanOfflineConfig();
 return api('/return-palettes/config');
}

function rpModal(){
 const cfg=rpSc.cfg||{hubs:[],clients:[]};
 modal('Envoyer un retour au scan',`
  <div class="rp-sc" id="rp-sc-box">
   <div class="rp-sc-steps"><span class="on" id="rp-sc-s1">1 · Vendeur &amp; hub</span><span id="rp-sc-s2">2 · Scan des colis</span><span id="rp-sc-s3">3 · Valider et envoyer</span></div>
   <div class="rp-sc-setup" id="rp-sc-setup">
    <p class="form-hint">Choisissez le <b>vendeur</b> destinataire du retour et le <b>hub</b> d'où partent les colis.
    Un colis est retournable s'il n'est pas <b>Livré</b> et qu'il est resté <b>plus d'une semaine</b> chez nous
    (réglage « return_week_days », ${rpScWeek()} jours). Tout est vérifié à chaque scan, avec son et message.</p>
    ${select('rp-sc-client','Vendeur destinataire',[['','Choisir le vendeur'],...cfg.clients.map(c=>[c.id,(c.company||c.name)])])}
    ${select('rp-sc-hub','Hub de départ',[['','Choisir le hub'],...cfg.hubs.map(h=>[h.id,h.name+(h.city?' · '+h.city:'')])])}
    <div class="rp-sc-row">${input('rp-sc-transport','Transport (facultatif)','','text',false,'maxlength="120" placeholder="Camion, SAT, société…"')}${input('rp-sc-lots','Lots (facultatif)','0','number',false,'min="0" max="500"')}</div>
    <div class="rp-sc-row">${input('rp-sc-tcode','Code de suivi du bordereau (facultatif)','','text',false,'maxlength="80"')}${input('rp-sc-note','Note (facultatif)','','text',false,'maxlength="200"')}</div>
    <div class="flex" style="gap:8px;flex-wrap:wrap;margin-top:8px">
     <button class="btn primary" type="button" onclick="rpScanStep2()">Commencer le scan</button>
     <button class="btn" type="button" onclick="closeModal()">Annuler</button></div>
   </div>
   <div class="rp-sc-scan" id="rp-sc-scan" hidden>
    <div class="rp-sc-head"><b id="rp-sc-who"></b><span class="sub" id="rp-sc-count">0 colis scanné</span></div>
    <div class="rp-sc-tools">
     ${input('rp-sc-input','Scanner le colis (lecteur USB, clavier ou caméra)','','text',false,'maxlength="80" autocomplete="off" placeholder="Tracking ORIENTAL24 puis Entrée"')}
     <button class="btn primary" type="button" id="rp-sc-add">Ajouter ce colis</button>
     <button class="btn sm" type="button" id="rp-sc-cam">📷 Caméra du téléphone</button>
     <button class="btn sm" type="button" id="rp-sc-snd" data-o24-snd>${(window.o24Sound&&o24Sound.on())?'🔊 Son activé':'🔇 Son coupé'}</button>
     <button class="btn sm" type="button" id="rp-sc-reset">↺ Vider les scans</button>
    </div>
    <div class="rp-sc-cambox" id="rp-sc-cambox" hidden><video playsinline muted></video><span id="rp-sc-camstate" class="sub">Caméra arrêtée</span></div>
    <div class="pp-rx-msg" id="rp-sc-msg"></div>
    <div class="rp-sc-list" id="rp-sc-list"></div>
    <div class="rp-sc-foot">
     <button class="btn primary" type="button" id="rp-sc-validate" disabled>Valider et envoyer le retour</button>
     <button class="btn" type="button" onclick="closeModal()">Fermer</button>
     <span class="sub" id="rp-sc-hint">Le lot n'est pas encore envoyé : rien n'est enregistré avant la validation.</span>
    </div>
   </div>
  </div>`,true);
 rpBind();
}

function rpBind(){
 const inp=rpField('rp-sc-input');
 if(inp)inp.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();rpScanCode(inp.value,false)}});
 const add=document.getElementById('rp-sc-add');
 if(add)add.onclick=()=>{const i=rpField('rp-sc-input');rpScanCode(i?i.value:'',false)};
 const snd=document.getElementById('rp-sc-snd');
 if(snd)snd.onclick=()=>{try{o24Sound?(o24Sound.set(!o24Sound.on())):0}catch(e){}const on=window.o24Sound?o24Sound.on():false;snd.textContent=on?'🔊 Son activé':'🔇 Son coupé';if(on)rpScSound('ok')};
 const reset=document.getElementById('rp-sc-reset');
 if(reset)reset.onclick=()=>{rpSc.lot=[];rpSc.seen={};rpSc.pending=null;rpMsg('','Lot vidé — recommencez le scan.');rpPaint();rpFocus()};
 const cam=document.getElementById('rp-sc-cam');
 if(cam)cam.onclick=()=>{
  const box=document.getElementById('rp-sc-cambox'),state=document.getElementById('rp-sc-camstate');
  if(!window.o24Cam){toast('Caméra indisponible : utilisez le lecteur USB ou la saisie.',true);return}
  rpSc.cam=rpSc.cam||o24Cam(box,cam,state,code=>rpScanCode(code,true));
  if(rpSc.cam.active()){rpSc.cam.stop()}else{rpSc.cam.start()}
 };
 const v=document.getElementById('rp-sc-validate');
 if(v)v.onclick=rpScanSend;
}

function rpField(n){return document.getElementById('f-'+n)||document.getElementById(n)||document.querySelector('[name="'+n+'"]')}
function rpFocus(){const i=rpField('rp-sc-input');if(i)i.focus({preventScroll:true})}

window.rpScanStep2=function(){
 const cl=Number((rpField('rp-sc-client')||{}).value||0);
 const hub=Number((rpField('rp-sc-hub')||{}).value||0);
 if(!cl){toast('Choisissez le vendeur destinataire.',true);return}
 if(!hub){toast('Choisissez le hub de départ.',true);return}
 rpSc.client_id=cl;rpSc.hub_id=hub;
 rpSc.transport=rpScNorm((rpField('rp-sc-transport')||{}).value);
 rpSc.lots=Number((rpField('rp-sc-lots')||{}).value||0)||0;
 rpSc.tracking_code=rpScNorm((rpField('rp-sc-tcode')||{}).value);
 rpSc.note=rpScNorm((rpField('rp-sc-note')||{}).value);
 const c=(rpSc.cfg.clients||[]).find(x=>x.id===cl)||{},h=(rpSc.cfg.hubs||[]).find(x=>x.id===hub)||{};
 document.getElementById('rp-sc-setup').hidden=true;
 document.getElementById('rp-sc-scan').hidden=false;
 document.getElementById('rp-sc-s1').className='';
 document.getElementById('rp-sc-s2').className='on';
 const who=document.getElementById('rp-sc-who');
 if(who)who.textContent=(c.company||c.name||'Vendeur')+' ← '+(h.name||'Hub')+(h.city?' · '+h.city:'');
 rpMsg('','Présentez le premier colis. Son « validé » = ajouté ; son grave = refusé ou à confirmer.');
 rpPaint();rpFocus();
};

async function rpScanCode(raw,fromCam){
 const code=rpScNorm(raw);
 if(!code)return;
 const inp=rpField('rp-sc-input');
 if(inp)inp.value='';
 if(rpSc.seen[code.toUpperCase()]){
  rpScSound('dup');rpFlash('dup');
  rpMsg('dup','Déjà scanné : <b>'+esc(code)+'</b>');rpFocus();return;
 }
 if(rpSc.loading)return;
 rpSc.loading=true;
 let v;
 try{v=await rpLookup(code)}
 catch(e){rpSc.loading=false;rpScSound('err');rpMsg('err',esc(e.message||'Vérification impossible'));rpFocus();return}
 rpSc.loading=false;
 if(v&&v.week_days)rpSc.week_days=v.week_days;
 const p=v.parcel||{};
 if(v.verdict==='ok'){
  rpScSound('ok');rpFlash('ok');
  rpAdd({parcel_id:p.id,tracking:p.tracking,recipient:p.recipient,city:p.city,days:p.days,status:p.status,confirmed:false});
  rpMsg('ok','✓ Ajouté : <b>'+esc(p.tracking)+'</b> · '+esc(p.recipient||'')+' · '+(p.days||0)+' j · '+esc(p.status||''));
  rpFocus();return;
 }
 if(v.verdict==='too_recent'){
  rpScSound('err');rpFlash('err');
  rpSc.pending={parcel_id:p.id,tracking:p.tracking,recipient:p.recipient,city:p.city,days:p.days,status:p.status,confirmed:true};
  rpMsg('err','✗ '+v.message+'<div class="rp-sc-choice"><button class="btn sm primary" type="button" onclick="rpScanAcceptTooRecent()">OUI — ajouter au lot</button><button class="btn sm" type="button" onclick="rpScanRejectTooRecent()">NON — ne pas ajouter</button></div>');
  rpFocus();return;
 }
 rpScSound('err');rpFlash('err');
 rpMsg('err','✗ '+v.message);
 rpFocus();
}

window.rpScanAcceptTooRecent=function(){
 if(!rpSc.pending)return;
 rpAdd(rpSc.pending);
 rpScSound('ok');rpFlash('ok');
 rpMsg('ok','✓ Ajouté quand même : <b>'+esc(rpSc.pending.tracking)+'</b> · '+(rpSc.pending.days||0)+' j — ajout confirmé par l’opérateur.');
 rpSc.pending=null;rpFocus();
};
window.rpScanRejectTooRecent=function(){
 if(!rpSc.pending)return;
 rpMsg('dup','Non ajouté : <b>'+esc(rpSc.pending.tracking)+'</b> (la semaine n’est pas passée).');
 rpSc.pending=null;rpFocus();
};

function rpAdd(it){
 const k=String(it.tracking).toUpperCase();
 if(rpSc.seen[k])return;
 rpSc.seen[k]=1;
 rpSc.lot.push(it);
 rpPaint();
}
function rpDel(tracking){
 const k=String(tracking).toUpperCase();
 delete rpSc.seen[k];
 rpSc.lot=rpSc.lot.filter(x=>String(x.tracking).toUpperCase()!==k);
 rpMsg('dup','Retiré du lot : <b>'+esc(tracking)+'</b>');
 rpPaint();rpFocus();
}
function rpPaint(){
 const box=document.getElementById('rp-sc-list');
 const n=rpSc.lot.length;
 const cnt=document.getElementById('rp-sc-count');
 if(cnt)cnt.textContent=n+' colis scanné'+(n>1?'s':'')+' · semaine '+rpScWeek()+' jours';
 const v=document.getElementById('rp-sc-validate');
 if(v){v.disabled=!n;v.textContent=n?('Valider et envoyer le retour ('+n+' colis)'):'Valider et envoyer le retour'}
 const hint=document.getElementById('rp-sc-hint');
 if(hint)hint.textContent=n?('À la validation : la palette retour est créée et expédiée au vendeur — '+n+' colis.'):'Le lot n’est pas encore envoyé : rien n’est enregistré avant la validation.';
 if(!box)return;
 if(!n){box.innerHTML='<p class="sub">Aucun colis scanné pour l’instant.</p>';return}
 box.innerHTML='<table class="rp-sc-table"><thead><tr><th>Tracking</th><th>Destinataire / Ville</th><th>Ancienneté</th><th>État</th><th></th></tr></thead><tbody>'+
  rpSc.lot.map(x=>'<tr><td><b>'+esc(x.tracking)+'</b>'+(x.confirmed?'<span class="rp-sc-tag">confirmé</span>':'')+'</td>'+
   '<td>'+esc(x.recipient||'')+'<span class="sub"> '+esc(x.city||'')+'</span></td>'+
   '<td>'+(x.days||0)+' j</td><td>'+esc(x.status||'')+'</td>'+
   '<td><button class="btn sm" type="button" onclick="rpScanRemove(\''+esc(x.tracking)+'\')">✕</button></td></tr>').join('')+
  '</tbody></table>';
}
window.rpScanRemove=rpDel;

async function rpLookup(code){
 if(typeof opsOffline!=='undefined'&&opsOffline)return o24RpScanOfflineLookup(rpSc.client_id,rpSc.hub_id,code);
 return api('/return-palettes/scan-lookup?tracking='+encodeURIComponent(code)+'&client_id='+rpSc.client_id+'&hub_id='+rpSc.hub_id);
}

async function rpScanSend(){
 const n=rpSc.lot.length;
 if(!n){toast('Scannez au moins un colis.',true);return}
 const btn=document.getElementById('rp-sc-validate');
 if(btn){btn.disabled=true;btn.textContent='Envoi…'}
 const payload={client_id:rpSc.client_id,hub_id:rpSc.hub_id,transport:rpSc.transport,lots:rpSc.lots,
  tracking_code:rpSc.tracking_code,note:rpSc.note,parcel_ids:rpSc.lot.map(x=>x.parcel_id),
  confirmed:rpSc.lot.filter(x=>x.confirmed).map(x=>x.parcel_id),request_key:rpScKey()};
 try{
  const r=(typeof opsOffline!=='undefined'&&opsOffline)?o24RpScanOfflineSend(payload):await api('/return-palettes/scan-send','POST',payload);
  rpScSound('done');
  if(rpSc.cam)try{rpSc.cam.stop()}catch(e){}
  closeModal();
  toast('Retour '+r.reference+' envoyé au vendeur — '+r.count+' colis ✓');
  if(typeof renderView==='function')renderView();
 }catch(e){
  rpScSound('err');
  rpMsg('err','✗ Envoi refusé : '+esc(e.message||''));
  if(btn){btn.disabled=false;btn.textContent='Valider et envoyer le retour ('+n+' colis)'}
  toast(e.message||'Envoi refusé',true);
 }
}

/* --- miroir démo (HTML hors serveur) : mêmes règles, mêmes messages --- */
/* Démo : un colis arrivé il y a 2 jours, pour voir « la semaine n'est pas passée » + OUI/NON. */
function o24RpScanOfflineSeed(){
 try{
  opcInit();
  if(localDemo.parcels.some(p=>p.tracking==='O24-100049'))return;
  const base=localDemo.parcels.find(p=>p.tracking==='O24-100043')||localDemo.parcels.find(p=>p.client_id===2)||localDemo.parcels[0];
  if(!base)return;
  const c=JSON.parse(JSON.stringify(base));
  c.id=oid(localDemo.parcels);c.tracking='O24-100049';c.status='Au hub';c.driver_id=null;
  c.recipient='Salma Récente';c.phone='0610001049';
  c.note='Démo v1.22 : colis arrivé il y a 2 jours (semaine non passée)';
  c.created_at=new Date(Date.now()-2*86400000).toISOString().slice(0,19);c.updated_at=c.created_at;
  localDemo.parcels.push(c);
 }catch(e){}
}
function o24RpScanOfflineConfig(){
 o24RpScanOfflineSeed();opcInit();
 return {hubs:localDemo.ops_hubs.filter(h=>h.active).map(h=>({...h,city:(localDemo.cities.find(c=>c.id===h.city_id)||{}).name||''})),
  clients:localDemo.users.filter(x=>x.role==='client'&&x.active&&x.client_type!=='societe_livraison').map(x=>({id:x.id,name:x.name,company:x.company}))};
}
function o24RpScanOfflineLookup(cid,hid,code){
 o24RpScanOfflineSeed();opcInit();
 const week=7;
 const c=String(code||'').trim();
 const cl=localDemo.users.find(u=>u.id===Number(cid));
 if(!cl)throw Error('Vendeur actif requis.');
 const p=localDemo.parcels.find(x=>String(x.tracking).toLowerCase()===c.toLowerCase());
 if(!p)return {verdict:'not_found',message:'Code inconnu : aucun colis avec ce tracking.',parcel:{},week_days:week};
 const days=Math.max(0,Math.floor((Date.now()-new Date(p.created_at).getTime())/86400000));
 const info={id:p.id,tracking:p.tracking,recipient:p.recipient,days:days,status:p.status,
  city:(localDemo.cities.find(x=>x.id===p.city_id)||{}).name||''};
 if(p.client_id!==cl.id){
  const other=localDemo.users.find(u=>u.id===p.client_id)||{};
  info.client_name=other.company||other.name||'';
  return {verdict:'other_client',message:'Ce colis appartient à <b>'+esc(info.client_name||'un autre vendeur')+'</b> — pas au vendeur choisi.',parcel:info,week_days:week};
 }
 if(p.status==='Livré')return {verdict:'delivered',message:'Colis <b>'+esc(p.tracking)+'</b> déjà <b>Livré</b> : aucun retour possible.',parcel:info,week_days:week};
 const busy=[...localDemo.partner_palettes,...localDemo.return_palettes].find(d=>(d.lines||[]).some(l=>l.parcel_id===p.id&&l.active&&!l.received_at&&!l.missing_at));
 if(busy){info.reserved_in=busy.reference;return {verdict:'reserved',message:'Colis <b>'+esc(p.tracking)+'</b> déjà réservé dans <b>'+esc(busy.reference)+'</b>.',parcel:info,week_days:week}}
 if(days<week)return {verdict:'too_recent',message:'Colis <b>'+esc(p.tracking)+'</b> : seulement <b>'+days+' jour(s)</b> chez nous — la semaine n’est pas encore passée (état : '+esc(p.status)+').',parcel:info,week_days:week};
 return {verdict:'ok',message:'Colis <b>'+esc(p.tracking)+'</b> · '+days+' jours · état '+esc(p.status)+'.',parcel:info,week_days:week};
}
function o24RpScanOfflineSend(d){
 opcInit();
 const cl=localDemo.users.find(u=>u.id===Number(d.client_id)&&u.role==='client'&&u.active);
 if(!cl)throw Error('Vendeur actif requis.');
 const h=localDemo.ops_hubs.find(x=>x.id===Number(d.hub_id)&&x.active);
 if(!h)throw Error('Hub de départ actif requis.');
 if(localUser.role!=='admin'&&localUser.role!=='agent')throw Error('Préparation et envoi des retours réservés à Admin et aux agents de réception.');
 if(localUser.role==='agent'&&localUser.agent_hub_id!==h.id)throw Error('Vous ne pouvez expédier des retours que depuis votre hub.');
 const confirmed=d.confirmed||[],ps=[];
 for(const pid of d.parcel_ids){
  const p=localDemo.parcels.find(x=>x.id===pid&&x.client_id===cl.id);
  if(!p)throw Error('Colis inaccessible pour ce vendeur.');
  const v=o24RpScanOfflineLookup(cl.id,h.id,p.tracking);
  if(v.verdict==='too_recent'&&!confirmed.includes(pid))throw Error('Colis '+p.tracking+' : la semaine n’est pas encore passée — confirmez son ajout.');
  if(v.verdict!=='ok'&&v.verdict!=='too_recent')throw Error(String(v.message).replace(/<[^>]+>/g,''));
  ps.push(p);
 }
 const prior=(localDemo.rp_scan_keys||[]).find(x=>x.key===d.request_key&&x.actor===localUser.id);
 if(prior){const doc0=(localDemo.return_palettes||[]).find(x=>x.id===prior.id);
  if(doc0)return {ok:true,id:doc0.id,reference:doc0.reference,count:(doc0.lines||[]).length,status:doc0.status,vendor:doc0.client_name,hub:doc0.source_name,week_days:7,confirmed:(d.confirmed||[]).length,replayed:true}}
 const nid=Math.max(0,...localDemo.return_palettes.map(x=>x.id))+1,at=onow();
 const lots=(d.lots===0||d.lots==null||d.lots==='')?0:Number(d.lots);
 const doc={id:nid,kind:'return_palette',reference:'PR-'+String(nid).padStart(6,'0'),client_id:cl.id,client_name:cl.company||cl.name,
  source_name:h.name,destination_name:cl.company||cl.name,destination_hub_id:h.id,note:String(d.note||'').slice(0,600),
  transport:String(d.transport||'').slice(0,120),tracking_code:String(d.tracking_code||'').slice(0,80),lots:lots,
  status:'En transit',created_at:at,dispatched_at:at,completed_at:null,revision:1,reminded_at:null,audit:[],
  lines:ps.map((p,i)=>({id:i+1,parcel_id:p.id,tracking:p.tracking,recipient:p.recipient,city:(localDemo.cities.find(c=>c.id===p.city_id)||{}).name||'',initial_status:p.status,active:1,received_at:null,received_by:null,missing_at:null,missing_by:null}))};
 doc.audit.unshift({id:1,actor:localUser.name,actor_id:localUser.id,action:'Palette retour scannée puis expédiée',details:{count:ps.length,vendor:cl.id,hub:h.id,transport:doc.transport,tracking_code:doc.tracking_code,lots:lots,week_days:7,confirmed:confirmed},created_at:at});
 localDemo.return_palettes.push(doc);
 localDemo.rp_scan_keys=localDemo.rp_scan_keys||[];
 localDemo.rp_scan_keys.push({key:d.request_key,actor:localUser.id,id:nid});
 for(const p of ps)oevent(p,doc.reference+' · retour expédié au vendeur (scan à l’agence)');
 return {ok:true,id:nid,reference:doc.reference,count:ps.length,status:'En transit',vendor:cl.company||cl.name,hub:h.name,week_days:7,confirmed:confirmed.length};
}
/* --- Palette retour refusée : ses colis redeviennent disponibles (re-scan possible) --- */
function rpScCtx(title){
 const who=()=>((typeof rpIdentity==='function'?rpIdentity():null)||(typeof ppIdentity==='function'?ppIdentity():null));
 const owner=who();modal(title,'<p>Chargement…</p>',true);
 const node=document.querySelector('#modal-root .modal');
 return {node,owner,current:()=>node.isConnected&&who()===owner};
}
window.rpRefuseAsk=function(id,reference,revision){
 const ctx=rpScCtx('Refuser la palette retour'+(reference?' '+reference:''));
 ctx.node.querySelector('.modal-body').innerHTML=
  `<p>Refuser cette palette retour rend ses colis <b>de nouveau disponibles</b> : ils pourront repartir dans un autre envoi (nouveau scan). La palette passe en <b>Annulée</b>.</p>`
  +textarea('rp-refuse-why','Motif du refus (obligatoire)','')
  +`<p class="form-error" id="rp-refuse-err" style="display:none"></p>
    <div class="form-actions"><button class="btn danger" id="rp-refuse-go">Refuser et libérer les colis</button><button class="btn" onclick="closeModal()">Annuler</button></div>`;
 const go=ctx.node.querySelector('#rp-refuse-go'),err=ctx.node.querySelector('#rp-refuse-err');
 go.onclick=async()=>{
  const why=String(rpField('rp-refuse-why').value||'').trim();
  if(why.length<3||why.length>600){err.textContent='Motif du refus obligatoire (3 à 600 caractères).';err.style.display='block';return}
  go.disabled=true;
  try{
   const r=(typeof opsOffline!=='undefined'&&opsOffline)?o24RpScanOfflineRefuse(id,why,revision)
    :await api('/return-palettes/'+id+'/refuse','POST',{reason:why,revision:revision,request_key:rpScKey()});
   rpScSound('done');closeModal();
   toast('Retour refusé · '+(r.released||0)+' colis de nouveau disponibles');
   if(typeof renderView==='function')renderView();
  }catch(e){go.disabled=false;err.textContent=e.message||'Refus impossible.';err.style.display='block'}
 };
};
function o24RpScanOfflineRefuse(id,reason,revision){
 opcInit();
 const doc=o24RpOfflineDetail(id);
 if(!['Préparé','En transit','Partiellement remis'].includes(doc.status))throw Error('Cette palette est déjà clôturée : elle ne peut plus être refusée.');
 if(Number(revision)!==Number(doc.revision||1))throw Error('Palette modifiée. Actualisez avant de confirmer.');
 const pending=(doc.lines||[]).filter(l=>l.active&&!l.received_at&&!l.missing_at);
 pending.forEach(l=>{l.active=0});
 doc.status='Annulé';doc.cancel_reason=String(reason).slice(0,600);doc.revision=Number(doc.revision||1)+1;
 doc.audit=doc.audit||[];
 doc.audit.unshift({id:(doc.audit[0]?doc.audit[0].id:0)+1,actor:localUser.name,actor_id:localUser.id,
  action:'Palette retour refusée — colis libérés',details:{reason:doc.cancel_reason,released:pending.map(l=>l.tracking),role:localUser.role},created_at:onow()});
 for(const l of pending){const p=localDemo.parcels.find(x=>x.id===l.parcel_id);if(p)oevent(p,doc.reference+' · retour refusé — colis de nouveau disponible')}
 return {ok:true,id:doc.id,released:pending.length,status:'Annulé'};
}
/* Réception réelle de la palette retour dans le HTML autonome. Le statut ne bouge
   qu'après une confirmation explicite de la remise physique au vendeur. */
function o24RpOfflineDetail(id){
 opcInit();
 const doc=(localDemo.return_palettes||[]).find(x=>Number(x.id)===Number(id));
 if(!doc)throw Error('Palette retour introuvable.');
 if(localUser.role==='client'&&Number(doc.client_id)!==Number(localUser.id))throw Error('Palette retour introuvable.');
 if(localUser.role==='agent'&&Number(doc.destination_hub_id)!==Number(localUser.agent_hub_id))throw Error('Palette retour hors de votre hub.');
 if(!['admin','agent','client'].includes(localUser.role))throw Error('Accès réservé.');
 const lines=(doc.lines||[]).map(l=>{const p=localDemo.parcels.find(x=>Number(x.id)===Number(l.parcel_id))||{};return {...l,current_status:p.status||l.initial_status,phone:p.phone||''}});
 const received=lines.filter(l=>l.received_at).length,missing=lines.filter(l=>l.missing_at&&!l.received_at).length;
 return {...doc,lines,count:lines.length,received,missing,remaining:lines.length-received-missing,audit:(doc.audit||[]).map(a=>({...a,details:a.details||{}}))};
}
function o24RpOfflineReceive(id,action,d){
 const doc=o24RpOfflineDetail(id);
 if(!['receive','receive-all'].includes(action))throw Error('Action de réception invalide.');
 if(d.confirmed!==true)throw Error('Confirmez avoir physiquement remis/reçu ce colis.');
 if(!Number.isInteger(d.revision)||d.revision!==Number(doc.revision||1))throw Error('Palette modifiée. Actualisez avant de confirmer.');
 if(action==='receive'){
  const tracking=String(d.tracking||'').trim();if(!tracking||tracking.length>160)throw Error('Saisissez le tracking du colis remis.');
  const line=doc.lines.find(l=>l.tracking===tracking);if(!line)throw Error('Ce tracking ne figure pas dans cette palette.');
  if(line.received_at)return {ok:true,id:doc.id,reference:doc.reference,status:doc.status,revision:doc.revision,already_received:true,received:0};
 }
 if(!['En transit','Partiellement remis'].includes(doc.status))throw Error('Confirmez l’envoi avant de réceptionner la palette.');
 const pending=doc.lines.filter(l=>!l.received_at&&!l.missing_at);
 if(action==='receive-all'&&(!Number.isInteger(d.expected_remaining)||d.expected_remaining!==pending.length))throw Error('Le nombre de colis restants a changé.');
 const received=action==='receive'?[doc.lines.find(l=>l.tracking===String(d.tracking||'').trim())]:pending;
 for(const l of received){const p=localDemo.parcels.find(x=>Number(x.id)===Number(l.parcel_id));if(!p||!['Refusé','Retourné'].includes(p.status))throw Error('L’état du colis '+l.tracking+' a changé.');}
 const at=onow(),changes=[];
 for(const l of received){const p=localDemo.parcels.find(x=>Number(x.id)===Number(l.parcel_id)),old=p.status;Object.assign(l,{active:0,received_at:at,received_by:localUser.id});Object.assign(p,{status:'Retourné',current_hub_id:null,ops_revision:(p.ops_revision||0)+1,updated_at:at});oevent(p,doc.reference+' · retour physiquement remis au vendeur · statut '+old+' → Retourné','Retourné');changes.push({tracking:l.tracking,from:old,to:'Retourné'});}
 const complete=received.length===pending.length;doc.status=complete?'Remis':'Partiellement remis';doc.completed_at=complete?at:null;doc.revision=Number(doc.revision||1)+1;doc.audit=doc.audit||[];doc.audit.unshift({id:(doc.audit[0]?.id||0)+1,actor:localUser.name,actor_id:localUser.id,action:complete?'Retour remis au vendeur (complet)':'Colis retour remis au vendeur',details:{trackings:received.map(l=>l.tracking),count:received.length,status:'Retourné',status_changes:changes},created_at:at});
 return {ok:true,id:doc.id,reference:doc.reference,status:doc.status,revision:doc.revision,received:received.length,already_received:false};
}
function o24RpOfflineOpen(id){
 let d;try{d=o24RpOfflineDetail(id)}catch(e){toast(e.message,true);return}
 const remise=['En transit','Partiellement remis'].includes(d.status),cl=localUser.role==='client';
 modal('Palette retour · '+d.reference,`<div class="pp-document-head"><div><span class="eyebrow orange">RETOUR · HUB → VENDEUR</span><h3>${esc(d.client_name||'Vendeur')}</h3><p>Départ : ${esc(d.source_name||'Hub')} · ${esc(d.transport||'Transport non renseigné')}</p><p>${d.tracking_code?'Code suivi : '+esc(d.tracking_code)+' · ':''}${d.lots?d.lots+' lot(s) · ':''}${opsDate(d.created_at)}</p></div>${tag(d.status)}</div><div class="pp-progress"><strong>${d.received}<small> / ${d.count}</small></strong><div><b>colis physiquement remis au vendeur</b><span>${d.remaining?d.remaining+' restant(s) à remettre':'Aucun colis restant'}</span></div></div>${remise?`<form id="o24-rp-offline-receive" class="pp-scan"><div class="form-error" role="alert"></div>${input('tracking','Scanner le tracking du colis remis au vendeur','','text',true,'maxlength="160" autocomplete="off" placeholder="Tracking ORIENTAL24 · lecteur USB ou saisie"')}<label class="pp-consent"><input type="checkbox" name="confirmed" required> ${cl?'Je confirme avoir physiquement reçu ce colis en retour.':'Je confirme que ce colis a physiquement été remis au vendeur '+esc(d.client_name||'')+'.'}</label><button class="btn primary" type="submit">${icon('check')}Confirmer la remise de ce colis</button></form>`:`<p class="form-hint">À la remise confirmée, le statut passe à Retourné. Les colis non facturés seront éligibles à la prochaine facture ; aucun paiement n’est créé automatiquement.</p>`}${simpleTable(['Tracking','Destinataire','Remise','Statut actuel'],d.lines.map(l=>[`<b>${esc(l.tracking)}</b>`,`${esc(l.recipient)}<span class="sub">${esc(l.city||'')}</span>`,l.received_at?`<span class="tag good">Remis</span><span class="sub">${opsDate(l.received_at)}</span>`:'À remettre',tag(l.current_status)]))}<h3 class="ops-subtitle">Historique de la palette</h3><div class="timeline">${d.audit.map(a=>`<div class="timeline-item"><b>${esc(a.action)}</b><small>${esc(a.actor||'—')} · ${opsDate(a.created_at)}</small>${a.details.trackings?`<p>${a.details.trackings.map(esc).join(' · ')}</p>`:''}</div>`).join('')}</div><p class="sub">La remise physique fait passer chaque colis reçu à Retourné. COD et frais restent inchangés ; Paid exige un règlement réel enregistré.</p>`,true);
 const f=document.querySelector('#modal-root #o24-rp-offline-receive');if(!f)return;
 f.addEventListener('submit',async e=>{e.preventDefault();const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');if(b.disabled)return;b.disabled=true;err.style.display='none';try{const r=await api('/return-palettes/'+id+'/receive','POST',{tracking:String(f.elements.tracking.value||'').trim(),confirmed:!!f.elements.confirmed.checked,revision:d.revision,request_key:rpScKey()});await refresh();await renderView();if(r.already_received)toast('Ce colis est déjà marqué remis.');else toast('Remise confirmée · statut mis à jour : Retourné');o24RpOfflineOpen(id)}catch(e){err.textContent=e.message||'Réception impossible.';err.style.display='block'}finally{b.disabled=false}}, {once:true});
}
/* Vue « Palettes retour » hors serveur (démo) : expédition, suivi et confirmation vendeur. */
function rpOfflineView(){
 localDemo.return_palettes=localDemo.return_palettes||[];
 const rows=localDemo.return_palettes.filter(d=>localUser.role==='admin'||(localUser.role==='client'&&Number(d.client_id)===Number(localUser.id))||(localUser.role==='agent'&&Number(d.destination_hub_id)===Number(localUser.agent_hub_id))).slice().reverse();
 const creator=['admin','agent'].includes(localUser.role),cl=localUser.role==='client';
 const cta=creator?`<button class="btn primary" onclick="rpScanStart()">${icon('scan')}Envoyer retour au scan</button>`:'';
 const intro=cl?'Scannez chaque colis réellement reçu puis confirmez la remise. Le statut passe à Retourné au moment de cette confirmation.':'Expédiez les colis au vendeur ; le statut ne passe à Retourné qu’après confirmation de leur remise physique.';
 return heading('Palettes retour',intro,cta)
  +`<div class="demo-notice">Démo autonome : scan de préparation et confirmation de réception vendeur simulés localement. Les colis en transit restent réservés et hors de la prochaine facture jusqu’à leur réception.</div>`
  +`<section class="card">${rows.length?simpleTable(['Palette / Vendeur','Hub départ / Transport','Colis remis','État','Actions'],rows.map(d=>[
     `<button class="tracking" onclick="o24RpOfflineOpen(${d.id})">${esc(d.reference)}</button><span class="sub">${esc(d.client_name||'')}</span>`,
     `${esc(d.source_name||'')}<span class="sub">${esc(d.transport||'Transport non renseigné')}${d.lots?' · '+d.lots+' lot(s)':''}</span>`,
     `${(d.lines||[]).filter(l=>l.received_at).length} / ${(d.lines||[]).length}`,
     tag(d.status),
     `<button class="btn sm ${d.status==='Remis'?'':'primary'}" onclick="o24RpOfflineOpen(${d.id})">${['En transit','Partiellement remis'].includes(d.status)?(cl?'Confirmer la réception':'Ouvrir / remise'):'Consulter'} ${icon('arrow')}</button>${creator&&['Préparé','En transit','Partiellement remis'].includes(d.status)?` <button class="btn sm danger" onclick="rpRefuseAsk(${d.id},'${esc(d.reference)}',${d.revision||1})">Refuser</button>`:''}`])):empty('Aucune palette retour',creator?'Scannez des colis pour créer le premier retour.':'Aucun retour en attente.')}</section>`
  +`<p class="form-hint">À la réception physique confirmée, le colis passe à Retourné. Le COD et les frais restent inchangés ; aucun règlement Paid n’est créé automatiquement.</p>`;
}
window.o24RpScanRoute=function(url,method,d){
 const u=new URL(url,'https://local.test'),parts=u.pathname.split('/').filter(Boolean),g=u.searchParams;
 if(parts[1]==='scan-lookup'&&method==='GET')return o24RpScanOfflineLookup(g.get('client_id'),g.get('hub_id'),g.get('tracking'));
 if(parts[1]==='scan-send'&&method==='POST')return o24RpScanOfflineSend(d||{});
 if(parts.length===2&&/^\d+$/.test(parts[1])&&method==='GET')return o24RpOfflineDetail(parts[1]);
 if(['receive','receive-all'].includes(parts[2])&&method==='POST')return o24RpOfflineReceive(parts[1],parts[2],d||{});
 if(parts[2]==='refuse'&&method==='POST')return o24RpScanOfflineRefuse(parts[1],(d||{}).reason,(d||{}).revision);
 return null;
};
/* === ORIENTAL24 · return-scan (fin) === */
