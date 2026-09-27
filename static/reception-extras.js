/* Réception renforcée : incidents, alertes, tarifs clients, API partenaires, agents. */
const rxIsReceiver=u=>u?.role==='admin'||u?.role==='agent';
const rxKindLabel=k=>({missing:'Colis manquant',extra:'Colis imprévu',damaged:'Colis endommagé'}[k]||k);
const rxKindTag=k=>`<span class="tag ${k==='damaged'?'bad':k==='missing'?'warn':'blue'}">${rxKindLabel(k)}</span>`;

menu[2][1].splice(0,0,['alerts','bell','Alertes',['admin','agent']]);
titles['alerts']='Alertes de retard';

function alertsView(d){
 const card=g=>{
  const rows=g.items.map(i=>i.tracking?`<article class="ops-notice"><span class="stat-icon warn">${icon('box')}</span><div><h3><button class="tracking" onclick="parcelDetail(${i.parcel_id})">${esc(i.tracking)}</button></h3><p>${esc(i.company)} · ${esc(i.hub||'hub non précisé')} · ${i.age_hours} h sans affectation</p></div></article>`
   :i.kind?`<article class="ops-notice"><span class="stat-icon warn">${icon('bell')}</span><div><h3><button class="tracking" onclick="openPartnerPalette(${i.document_id})">${esc(i.reference)}</button></h3><p>${rxKindLabel(i.kind)} · ${esc(i.company)}</p></div></article>`
   :`<article class="ops-notice"><span class="stat-icon">${icon('layers')}</span><div><h3><button class="tracking" onclick="openPartnerPalette(${i.document_id})">${esc(i.reference)}</button></h3><p>${esc(i.company)} → ${esc(i.hub)} · ${i.age_hours} h</p></div></article>`).join('');
  return `<section class="card"><div class="card-head"><h3>${esc(g.title)}</h3>${g.limit?`<span class="tag">seuil ${g.limit} h</span>`:''}</div>${rows||empty('Rien à signaler','Cette catégorie est à jour.')}</section>`};
 const total=d.groups.reduce((n,g)=>n+g.items.length,0);
 return heading('Alertes de retard','Calculées à la demande depuis les horodatages, sans envoi externe.',`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button>`)+`<div class="pp-explainer"><span class="stat-icon warn">${icon('bell')}</span><div><b>${total} point(s) à traiter.</b><p>Palettes annoncées non arrivées, réceptions partielles en attente, colis réceptionnés non affectés et incidents ouverts. Les seuils se règlent dans Paramètres → Général.</p></div></div>`+d.groups.map(card).join('');
}

/* ---------------- Incidents de réception ---------------- */

function rxIncidentsBlock(d){return `<div id="pp-incidents" class="pp-incidents"><p class="sub">Chargement des incidents…</p></div>`}
function rxHolds(holds){return holds?.length?`<p class="form-hint orange">${holds.length} colis endommagé(s) en attente de décision : affectation suspendue.</p>`:''}

async function ppRenderIncidents(ctx,id,d){
 const slot=ctx.node.querySelector('#pp-incidents');if(!slot||!ctx.current())return;
 try{const data=await api('/partner-palettes/'+id+'/incidents');if(!ctx.current())return;
 const canWork=rxIsReceiver(S.user)&&['En transit','Partiellement reçu'].includes(d.status);
 const isCompany=S.user.role==='client';
 const item=i=>{const own=i.kind!=='missing';
  return `<article class="pp-incident"><div class="pp-incident-head">${rxKindTag(i.kind)}<b>${esc(i.tracking)}</b><span class="tag ${i.status==='Traité'?'good':i.status==='Réponse société'?'blue':'warn'}">${esc(i.status)}</span></div>
  <p>${esc(i.note)}</p><small>Déclaré par ${esc(i.creator)} · ${esc(opsDate(i.created_at))}</small>
  ${i.has_photo?`<button class="btn sm" onclick="rxIncidentPhoto(${i.id})">${icon('download')}Photo</button>`:''}
  ${i.company_response?`<div class="pp-thread"><b>Réponse société</b><small>${esc(opsDate(i.responded_at))}</small><p>${esc(i.company_response)}</p></div>`:''}
  ${i.resolution?`<div class="pp-thread"><b>Décision : ${i.kind==='damaged'?(i.resolution==='release'?'colis débloqué pour livraison':'blocage conservé'):'dossier clôturé'}</b>${i.resolution_note?`<p>${esc(i.resolution_note)}</p>`:''}<small>${esc(opsDate(i.resolved_at))}</small></div>`:''}
  <div class="pp-incident-actions">
   ${isCompany&&i.status!=='Traité'?`<button class="btn sm navy" onclick="ppRespondForm(${id},${i.id},'${i.kind}')">Répondre</button>`:''}
   ${rxIsReceiver(S.user)&&(i.status!=='Traité'||(i.kind==='damaged'&&i.resolution==='hold'))?`<button class="btn sm" onclick="ppResolveForm(${id},${i.id},'${i.kind}','${i.resolution||''}')">${i.kind==='damaged'?'Décider':'Clôturer le dossier'}</button>`:''}
  </div></article>`};
 slot.innerHTML=`<h3 class="ops-subtitle">Incidents de réception (${data.rows.length})</h3>${rxHolds(data.damaged_holds)}${data.rows.map(item).join('')||`<p class="sub">Aucun écart déclaré. Un manque, un surplus ou un dégât se déclare depuis les actions ci-dessus.</p>`}`;
 }catch(e){if(ctx.current())slot.innerHTML=`<p class="form-hint orange">${esc(e.message)}</p>`}
}
async function rxIncidentPhoto(iid){try{if(opsOffline){toast('Photo simulée : voir l’historique du HTML local.');return}await billingFetchFile('/api/partner-palette-incidents/'+iid+'/photo','incident-'+iid+'.jpg')}catch(e){toast(e.message,true)}}

function rxExtrasButtons(id,d){
 return `<div class="pp-actions wrap"><span class="sub">Écart constaté physiquement :</span>
 <button class="btn sm warn" onclick="ppIncidentForm(${id},'missing')">${icon('bell')}Colis manquant</button>
 <button class="btn sm warn" onclick="ppIncidentForm(${id},'damaged')">${icon('bell')}Colis endommagé</button>
 <button class="btn sm" onclick="ppIncidentForm(${id},'extra')">${icon('plus')}Colis imprévu</button>
 ${d.remaining?`<button class="btn sm danger" onclick="ppCloseGapsForm(${id},${d.revision})">${icon('check')}Clôturer avec ${d.remaining} manquant(s)</button>`:''}</div>`;
}

async function fileToAttachment(input){
 const f=input.files[0];if(!f)return null;
 if(f.size>1048576)throw Error('Photo supérieure à 1 Mo.');
 const raw=await f.arrayBuffer();let bin='';const bytes=new Uint8Array(raw);
 for(let i=0;i<bytes.length;i+=0x8000)bin+=String.fromCharCode.apply(null,bytes.subarray(i,i+0x8000));
 return {name:f.name||'photo.jpg',content:btoa(bin)};
}

async function ppIncidentForm(id,kind){
 const ctx=ppContext(rxKindLabel(kind));
 try{const d=await api('/partner-palettes/'+id);if(!ctx.current())return;
 const pending=d.lines.filter(l=>!l.received_at&&!l.missing_at);
 if(kind==='missing'&&!pending.length)throw Error('Tous les colis sont déjà reçus ou déclarés.');
 const trackingField=kind==='missing'?select('line_id','Colis attendu mais absent',pending.map(l=>[l.id,l.tracking+' · '+l.recipient]))
  :input('tracking',kind==='damaged'?'Tracking du colis endommagé':'Tracking du colis imprévu','','text',true,'maxlength="80" autocomplete="off"');
 ctx.node.querySelector('.modal-body').innerHTML=`<form id="pp-incident-form"><div class="form-error"></div><div class="form-grid">
 <div class="full form-hint"><b>${esc(d.reference)} · ${esc(d.client_name)}</b> → ${esc(d.destination_name)}<br>${kind==='missing'?'Le colis cité est libéré du manifeste et signalé à la société : il n’est PAS marqué reçu.':kind==='damaged'?'Le colis est reçu physiquement à l’état endommagé : il passe Réceptionné, mais son affectation livreur est suspendue jusqu’à décision.':'Le colis imprévu est signalé sans modifier aucune commande ni aucun montant.'}</div>
 ${trackingField}${textarea('note','Constat détaillé','',true)}<div class="full"><label class="pp-consent file"><input type="file" name="photo" accept="image/jpeg,image/png" ${kind==='damaged'?'required':''}> ${kind==='damaged'?'Photo du dégât (obligatoire, < 1 Mo, JPG/PNG)':'Photo facultative (< 1 Mo)'}</label></div>
 <label class="full pp-consent"><input type="checkbox" name="confirmed" required> Je confirme ce constat physique au hub ${esc(d.destination_name)}.</label>
 <p class="full form-hint orange">La société est notifiée dans son espace et peut répondre ; le dossier reste dans l’historique, sans suppression.</p>
 <div class="form-actions full"><button class="btn" type="button" onclick="closeModal()">Fermer</button><button class="btn primary" type="submit">${icon('check')}Déclarer</button></div></div></form>`;
 const f=ctx.node.querySelector('#pp-incident-form');f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');if(b.disabled)return;b.disabled=true;err.style.display='none';
 try{const payload={kind,note:f.elements.note.value.trim(),confirmed:f.elements.confirmed.checked,request_key:financeKey()};
  if(kind==='missing')payload.line_id=Number(f.elements.line_id.value);else payload.tracking=f.elements.tracking.value.trim();
  const pic=await fileToAttachment(f.elements.photo);if(pic)payload.photo=pic;
  const r=await api('/partner-palettes/'+id+'/incidents','POST',payload);if(!ctx.current())return;await refresh();if(!ctx.current())return;await openPartnerPalette(id);toast(r.replayed?'Déclaration déjà enregistrée : aucun doublon.':'Incident déclaré et société notifiée')}catch(e2){if(ctx.current()){err.textContent=e2.message;err.style.display='block'}}finally{if(ctx.current())b.disabled=false}}
}catch(e){ppError(ctx,e)}
}

async function ppCloseGapsForm(id){
 const ctx=ppContext('Clôturer la palette avec écarts');
 try{const d=await api('/partner-palettes/'+id);if(!ctx.current())return;const pending=d.lines.filter(l=>!l.received_at&&!l.missing_at);
 if(!pending.length)throw Error('Aucun colis à déclarer manquant.');
 ctx.node.querySelector('.modal-body').innerHTML=`<form id="pp-gaps-form"><div class="form-error"></div><div class="form-grid">
 <div class="full form-hint"><b>${esc(d.reference)}</b> : les ${pending.length} colis ci-dessous seront déclarés MANQUANTS, un dossier par colis. Aucun n’est marqué reçu ; tous restent visibles et la société est notifiée.</div>
 <div class="full pp-confirm-list">${pending.map(l=>`<div>${esc(l.tracking)} · ${esc(l.recipient)}</div>`).join('')}</div>
 ${textarea('reason','Motif de clôture avec écarts','',true)}
 <label class="full pp-consent"><input type="checkbox" name="confirmed" required> Je confirme la clôture de cette palette avec ces manques physiquement constatés.</label>
 <p class="full form-hint orange">Cette décision ne supprime ni colis ni historique. Elle ne marque aucun colis comme réceptionné.</p>
 <div class="form-actions full"><button class="btn" type="button" onclick="closeModal()">Fermer</button><button class="btn danger" type="submit">Clôturer avec ${pending.length} manquant(s)</button></div></div></form>`;
 const f=ctx.node.querySelector('#pp-gaps-form');f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');if(b.disabled)return;b.disabled=true;
 try{const r=await api409(g=>api('/partner-palettes/'+id+'/close-gaps','POST',{reason:f.elements.reason.value.trim(),confirmed:f.elements.confirmed.checked,expected_remaining:g?g.remaining:pending.length,revision:g?g.revision:d.revision,request_key:financeKey()}),async()=>{const x=await api('/partner-palettes/'+id);return {revision:x.revision,remaining:x.remaining}});if(!ctx.current())return;await refresh();if(!ctx.current())return;await openPartnerPalette(id);toast(r.replayed?'Clôture déjà enregistrée : aucun doublon.':'Palette clôturée avec écarts')}catch(e2){if(ctx.current()){err.textContent=e2.message;err.style.display='block'}}finally{if(ctx.current())b.disabled=false}}
}catch(e){ppError(ctx,e)}
}

async function ppRespondForm(id,iid,kind){
 const ctx=ppContext('Répondre sur '+rxKindLabel(kind).toLowerCase());
 ctx.node.querySelector('.modal-body').innerHTML=`<form><div class="form-error"></div><div class="form-grid">${textarea('response','Votre réponse à ORIENTAL24','',true)}<p class="full form-hint">Votre réponse est jointe au dossier et notifiée à l’administration. Elle ne modifie ni colis ni montant.</p><div class="form-actions full"><button class="btn" type="button" onclick="closeModal()">Fermer</button><button class="btn primary" type="submit">Envoyer la réponse</button></div></div></form>`;
 const f=ctx.node.querySelector('form');f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');b.disabled=true;
 try{await api(`/partner-palettes/${id}/incidents/${iid}/respond`,'POST',{response:f.elements.response.value.trim()});if(!ctx.current())return;await refresh();if(!ctx.current())return;await openPartnerPalette(id);toast('Réponse transmise à l’administration')}catch(e2){if(ctx.current()){err.textContent=e2.message;err.style.display='block';b.disabled=false}}}
}
async function ppResolveForm(id,iid,kind,current){
 const ctx=ppContext(kind==='damaged'?'Décision sur le colis endommagé':'Clôturer l’écart');
 ctx.node.querySelector('.modal-body').innerHTML=`<form><div class="form-error"></div><div class="form-grid">
 ${kind==='damaged'?select('action','Décision',[['release','Débloquer le colis pour affectation livreur'],['hold','Conserver le blocage (pas de livraison)']],current==='hold'?'hold':'release'):''}
 ${textarea('note','Décision motivée','',true)}<p class="full form-hint">La société est notifiée. ${kind==='damaged'?'« Débloquer » lève la suspension d’affectation ; « Conserver » la maintient et peut être revue plus tard.':'La clôture archive le dossier sans rien supprimer.'}</p>
 <div class="form-actions full"><button class="btn" type="button" onclick="closeModal()">Fermer</button><button class="btn primary" type="submit">${icon('check')}Enregistrer la décision</button></div></div></form>`;
 const f=ctx.node.querySelector('form');f.onsubmit=async e=>{e.preventDefault();const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');b.disabled=true;
 try{const payload={note:f.elements.note.value.trim(),...(kind==='damaged'?{action:f.elements.action.value}:{action:'close'})};await api(`/partner-palettes/${id}/incidents/${iid}/resolve`,'POST',payload);if(!ctx.current())return;await refresh();if(!ctx.current())return;await openPartnerPalette(id);toast('Décision enregistrée et société notifiée')}catch(e2){if(ctx.current()){err.textContent=e2.message;err.style.display='block';b.disabled=false}}}
}

/* Caméra : remplit uniquement le champ tracking ; chaque réception reste confirmée à la main. */
function ppCameraSlot(target){return window.BarcodeDetector&&navigator.mediaDevices?.getUserMedia&&!opsOffline?`<button type="button" class="btn sm" id="${target}-camera">${icon('scan')}Caméra</button><p class="pp-camera-line" id="${target}-camera-box" hidden><video playsinline muted style="width:100%;max-height:220px;border-radius:12px;background:#0a1e3c"></video><span class="sub" id="${target}-camera-status">Présentez le code du colis.</span></p>`:''}
function ppCameraBind(target,input,stop){
 const btn=document.getElementById(target+'-camera');if(!btn)return;
 let stream=null,timer=null;
 btn.onclick=async()=>{
  if(stream){clearTimeout(timer);stream.getTracks().forEach(t=>t.stop());stream=null;marginTop(btn);btn.textContent='Caméra';box.hidden=true;return}
  const box=document.getElementById(target+'-camera-box'),st=document.getElementById(target+'-camera-status');
  function marginTop(el){el.classList.remove('active')}function reset(){stream=null;timer=null}
  btn.disabled=true;
  try{const formats=(await BarcodeDetector.getSupportedFormats()).filter(f=>['qr_code','code_128'].includes(f));
   if(!formats.length)throw Error('Formats non pris en charge');
   const detector=new BarcodeDetector({formats});
   stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'}},audio:false});
   const video=box.querySelector('video');video.srcObject=stream;box.hidden=false;await video.play();btn.textContent='Arrêter la caméra';
   let last='';const loop=async()=>{try{const codes=await detector.detect(video);const v=codes[0]?.rawValue?.trim();if(v&&v!==last){last=v;input.value=v;st.textContent='Code lu : vérifiez puis confirmez manuellement.'}}catch(e){st.textContent=e.message}if(stream)timer=setTimeout(loop,350)};loop();
  }catch(e){reset();box.hidden=true;toast('Caméra indisponible ou refusée : utilisez la saisie ou un lecteur USB.',false)}finally{btn.disabled=false}
 };
 if(stop)stop.addEventListener('pp-close',()=>{if(stream){clearTimeout(timer);stream.getTracks().forEach(t=>t.stop());stream=null}});
}

/* ---------------- Tarifs par client ---------------- */

async function tariffForm(cid){
 const ctx=ppContext('Tarifs du client');
 try{const d=await api('/clients/'+cid+'/tariffs');if(!ctx.current())return;
 ctx.node.querySelector('.modal-body').innerHTML=`<div class="full form-hint"><b>${esc(d.client.company||d.client.name)}</b> · ${d.client.client_type==='societe_livraison'?'Société de livraison':'Vendeur'}<br>Un tarif personnalisé s’applique uniquement aux <b>NOUVEAUX colis</b> de ce client dans cette ville. Les colis, relevés et factures existants gardent leurs montants.</div>
 <div class="table-wrap full"><table><thead><tr><th>Ville</th><th>Défaut</th><th>Livraison MAD</th><th>Retour MAD</th><th></th></tr></thead><tbody>${d.cities.map(ci=>`<tr><td><b>${esc(ci.city)}</b></td><td class="sub">${money(ci.default_fee)} / ${money(ci.default_return_fee)}</td><td><input class="pp-rate" id="rate-f-${ci.city_id}" type="number" min="0" max="10000" step="0.01" value="${ci.fee??''}" placeholder="${ci.default_fee}" aria-label="Livraison ${esc(ci.city)}"></td><td><input class="pp-rate" id="rate-r-${ci.city_id}" type="number" min="0" max="10000" step="0.01" value="${ci.return_fee??''}" placeholder="${ci.default_return_fee}" aria-label="Retour ${esc(ci.city)}"></td><td><button class="btn sm navy" onclick="rxSaveTariff(${cid},${ci.city_id})">Enregistrer</button>${ci.fee!==null?`<button class="btn sm" onclick="rxResetTariff(${cid},${ci.city_id})">Défaut</button>`:''}<span class="sub">${ci.updated_at?'Modifié '+esc(opsDate(ci.updated_at)):''}</span></td></tr>`).join('')}</tbody></table></div>
 <h3 class="ops-subtitle">Historique des tarifs</h3><div class="timeline">${d.audit.map(a=>`<div class="timeline-item"><b>${esc(a.city)} : ${a.new_fee===null?'retour au tarif par défaut':'livraison '+money(a.new_fee)+' MAD · retour '+money(a.new_return_fee)+' MAD'}</b><small>${esc(a.actor)} · ${esc(opsDate(a.created_at))} · avant : ${money(a.old_fee)}/${money(a.old_return_fee)}</small></div>`).join('')||'<p class="sub">Aucune personnalisation enregistrée.</p>'}</div>
 <div class="form-actions full"><button class="btn" onclick="closeModal()">Fermer</button></div>`;
 }catch(e){ppError(ctx,e)}
}
async function rxSaveTariff(cid,city){
 const fee=document.getElementById('rate-f-'+city).value.trim(),ret=document.getElementById('rate-r-'+city).value.trim();
 if(fee===''||ret===''){toast('Saisissez livraison ET retour, ou utilisez Défaut.',true);return}
 try{await api(`/clients/${cid}/tariffs/${city}`,'PUT',{fee:Number(fee),return_fee:Number(ret)});toast('Tarif enregistré : il vaut pour les prochains colis uniquement');await tariffForm(cid)}catch(e){toast(e.message,true)}
}
async function rxResetTariff(cid,city){try{await api(`/clients/${cid}/tariffs/${city}`,'DELETE');toast('Retour au tarif par défaut de la ville');await tariffForm(cid)}catch(e){toast(e.message,true)}}

/* ---------------- Clés API partenaires ---------------- */

async function apiKeysForm(cid,label){
 const ctx=ppContext('API partenaire — '+(label||''));
 try{const data=await api('/partner-api-keys');if(!ctx.current())return;
 const rows=data.rows.filter(k=>k.client_id===cid);
 ctx.node.querySelector('.modal-body').innerHTML=`<div class="full form-hint">Une seule clé active par société. Elle donne accès à <b>ses seules commandes</b> : création, suivi, liste des villes. Jamais aux autres clients, ni à la facturation. La clé complète s’affiche une seule fois ; conservez-la dans un coffre.</div>
 ${rows.map(k=>`<div class="pp-incident"><div class="pp-incident-head"><b>${esc(k.label)}</b><span class="tag ${k.revoked_at?'bad':'good'}">${k.revoked_at?'Révoquée':'Active'}</span></div><small>Créée par ${esc(k.creator)} le ${esc(opsDate(k.created_at))}${k.last_used_at?' · dernière utilisation '+esc(opsDate(k.last_used_at)):''}</small>${!k.revoked_at?`<div class="pp-incident-actions"><button class="btn sm danger" onclick="rxRevokeKey(${k.id},${cid},'${esc(label||'')}')">Révoquer</button><button class="btn sm" onclick="rxApiGuide()">Exemples d’appels</button></div>`:''}</div>`).join('')||'<p class="sub">Aucune clé pour cette société.</p>'}
 ${!rows.some(k=>!k.revoked_at)?`<form id="pp-key-form" class="form-grid"><div class="form-error full"></div>${input('label','Libellé de la clé (ex. ERP principal)','','text',true,'maxlength="80"')}<div class="form-actions full"><button class="btn primary" type="submit">${icon('plus')}Créer une clé</button></div></form>`:''}
 <div class="form-actions full"><button class="btn" onclick="rxApiGuide()">Guide d’intégration</button><button class="btn" onclick="closeModal()">Fermer</button></div>`;
 const f=ctx.node.querySelector('#pp-key-form');if(f)f.onsubmit=async e=>{e.preventDefault();const err=f.querySelector('.form-error');try{const r=await api('/partner-api-keys','POST',{client_id:cid,label:f.elements.label.value.trim()});if(!ctx.current())return;ctx.node.querySelector('.modal-body').innerHTML=`<div class="full form-hint"><b>Clé créée pour ${esc(r.company)}.</b> Copiez-la maintenant : elle ne sera plus jamais affichée.</div><div class="pp-key">${esc(r.key)}</div><div class="form-actions full"><button class="btn navy" onclick="rxCopyKey('${r.key}')">${icon('copy')}Copier la clé</button><button class="btn" onclick="rxApiGuide()">Voir les exemples d’appels</button><button class="btn" onclick="apiKeysForm(${cid},'${esc(r.company)}')">Terminer</button></div>`}catch(e2){err.textContent=e2.message;err.style.display='block'}}
 }catch(e){ppError(ctx,e)}
}
async function rxRevokeKey(kid,cid,label){if(!confirm('Révoquer cette clé ? Les appels existants seront refusés immédiatement. Les colis déjà créés sont conservés.'))return;try{await api(`/partner-api-keys/${kid}/revoke`,'POST',{});toast('Clé révoquée');await apiKeysForm(cid,label)}catch(e){toast(e.message,true)}}
async function rxCopyKey(key){try{await navigator.clipboard.writeText(key);toast('Clé copiée : transmettez-la par un canal sûr.')}catch{prompt('Copiez la clé :',key)}}
function rxApiGuide(){
 modal('Intégration API société',`<div class="pp-guide"><p>Base : <b>https://VOTRE-SERVEUR</b> · en-têtes <code>Authorization: Bearer O24K-…</code> et <code>Content-Type: application/json</code>.</p>
 <h4>1 · Villes et tarifs applicables</h4><pre>curl -H "Authorization: Bearer O24K-…" https://VOTRE-SERVEUR/api/partner/v1/cities</pre>
 <h4>2 · Créer une commande (trackings de la société)</h4><pre>curl -X POST https://VOTRE-SERVEUR/api/partner/v1/parcels \\
  -H "Authorization: Bearer O24K-…" -H "Content-Type: application/json" \\
  -H "Idempotency-Key: cmd-2026-09-20-000417" \\
  -d '{"tracking":"ABC-00417","recipient":"Client exemple","phone":"0600000000","city":"Oujda","address":"12, rue Exemple","amount":249,"product":"Coffret","note":"Appel API"}'</pre>
 <p>Relancer le même appel avec la <b>même Idempotency-Key</b> retourne la même création, sans doublon. Un même tracking est accepté chez une autre société, jamais deux fois chez vous.</p>
 <h4>3 · Suivi d’une commande</h4><pre>curl -H "Authorization: Bearer O24K-…" https://VOTRE-SERVEUR/api/partner/v1/parcels/ABC-00417</pre>
 <h4>4 · Mises à jour à synchroniser</h4><pre>curl -H "Authorization: Bearer O24K-…" "https://VOTRE-SERVEUR/api/partner/v1/parcels?updated_since=2026-09-20T08:00:00&size=100"</pre>
 <p class="sub">Limites : 120 requêtes/minute, vos seules commandes, aucune facturation ni autre client. La réception physique reste confirmée par ORIENTAL24 à l’arrivée.</p></div>`);
}

/* ---------------- Agents de réception ---------------- */

function rxAgentsBlock(){
 const agents=(S.users||[]).filter(u=>u.role==='agent'),hubs=S.hubs||[];
 const hubName=id=>hubs.find(h=>h.id===id)?.name||'Hub retiré';
 return `<section class="card"><div class="card-head"><h3>Agents de réception (${agents.length})</h3><button class="btn sm primary" onclick="agentForm(null)">${icon('plus')}Ajouter un agent</button></div>${agents.length?`<div class="table-wrap"><table><thead><tr><th>Agent</th><th>Hub de réception</th><th>Statut</th><th></th></tr></thead><tbody>${agents.map(u=>`<tr><td><div class="recipient"><span class="avatar navy">${initials(u.name)}</span><strong>${esc(u.name)}</strong><span class="sub">${esc(u.email)}</span></div></td><td>${esc(hubName(u.agent_hub_id))}</td><td><span class="tag ${u.active?'good':'bad'}">${u.active?'Actif':'Désactivé'}</span></td><td><button class="icon-btn" onclick="agentForm(${u.id})">${icon('edit')}</button></td></tr>`).join('')}</tbody></table></div>`:empty('Aucun agent','Créez un compte agent par hub : il réceptionne les palettes sans voir la facturation.')}</section>`;
}
function agentForm(id){
 const u=id?(S.users||[]).find(x=>x.id===id):{name:'',email:'',phone:'',active:1,agent_hub_id:null};
 const hubs=(S.hubs||[]).filter(h=>h.active||h.id===u.agent_hub_id);
 if(!hubs.length){toast('Créez d’abord un hub actif (Palettes partenaires → Ajouter un hub).',true);return}
 modal(id?'Modifier l’agent':'Nouvel agent de réception',form(
  `<div class="full form-hint">L’agent réceptionne <b>uniquement</b> les palettes arrivant à son hub : scan, écarts, clôture. Il ne voit ni facturation, ni liste des colis, ni autres hubs.</div>
  ${input('name','Nom complet',u.name)}${!id?input('email','Adresse e-mail','','email'):`<div class="form-hint">${esc(u.email)}</div>`}${input('phone','Téléphone',u.phone,'tel')}
  ${select('agent_hub_id','Hub de réception',hubs.map(h=>[h.id,h.name+' · '+h.city]),u.agent_hub_id)}
  ${input('password',id?'Nouveau mot de passe (facultatif)':'Mot de passe initial','','password',!id,'minlength="10" autocomplete="new-password"')}
  ${id?`<div class="switch"><input id="user-active" type="checkbox" name="active" ${u.active?'checked':''}><label for="user-active">Compte actif</label></div>`:''}
  <div class="full form-hint">Révoqué immédiatement en cas de désactivation : toutes ses sessions ferment.</div>`));
 bindForm(async d=>{await api('/users'+(id?'/'+id:''),id?'PATCH':'POST',{...d,role:'agent',agent_hub_id:Number(d.agent_hub_id)});await saved('Compte agent enregistré')});
}

const rxBaseUsersView=usersView;
usersView=function(){
 const html=rxBaseUsersView();
 if(view!=='clients')return html;
 return html+rxAgentsBlock();
};
