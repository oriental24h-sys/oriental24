/* Status uses existing transition/attempt workflows. Follow-up Note only changes the reason. */
function parcelStateEditable(p){return !['client','support','agent'].includes(S.user.role)&&!p.invoice_id&&!p.financial_locked&&!p.operations_locked&&!(S.user.role==='livreur'&&['Livré','Retourné'].includes(p.status))}
function clientInterestedEligible(p){return S?.user?.role==='client'&&p.status!=='Intéressé'&&!['Livré','Retourné','Refusé','Annulé'].includes(p.status)&&!p.invoice_id&&!p.financial_locked&&!p.operations_locked&&!['Réglée','Soldé','Paid'].includes(p.invoice_status)}
function hubParcelStatusEditable(p){return S?.user?.role==='agent'&&p.hub_status_editable===true&&p.status!=='Livré'&&!p.invoice_id&&!p.financial_locked&&!p.operations_locked}
function parcelStatusEditable(p){if(S?.user?.role==='livreur')return p.status!=='Livré'&&!p.invoice_id&&!p.financial_locked&&!p.operations_locked;return S?.user?.role==='agent'?hubParcelStatusEditable(p):S?.user?.role==='client'?clientInterestedEligible(p):parcelStateEditable(p)}
function parcelNoteControl(p){if(S.user.role==='livreur'&&parcelStateEditable(p))return `<button class="parcel-note-button" onclick="openDriverFollowup(${p.id})">Motif / note ${icon('edit')}</button>`;const label=p.reason_label||p.reason_code||'Aucun motif';return parcelStateEditable(p)?`<button class="parcel-note-button ${p.reason_code?'has-reason':''}" aria-label="Note de ${esc(p.tracking)}" aria-haspopup="dialog" aria-expanded="false" onclick="openParcelReason(${p.id},this)"><span>Note${p.reason_code?' · '+esc(label):''}</span>${icon('down')}</button>`:`<span class="parcel-note-readonly">${esc(label)}</span>`}
function parcelStatusControl(p){if(S?.user?.role==='client')return clientInterestedEligible(p)?`<button class="parcel-status-button client-interested-button" title="Marquer comme intéressé" aria-label="Marquer ${esc(p.tracking)} comme intéressé" aria-haspopup="dialog" aria-expanded="false" onclick="openParcelState(${p.id},this)">Marquer intéressé${icon('down')}</button>`:'';return parcelStatusEditable(p)?`<button class="parcel-status-button" aria-label="État de ${esc(p.tracking)}" aria-haspopup="dialog" aria-expanded="false" onclick="openParcelState(${p.id},this)">${esc(p.status)}${icon('down')}</button>`:''}
function parcelStateControls(p){return `<div class="parcel-state-controls">${tag(p.status)}${parcelStatusControl(p)}${parcelNoteControl(p)}</div>`}
let activeReasonMenu=null;
function closeParcelReason(focus=true){const a=activeReasonMenu;if(!a)return;activeReasonMenu=null;a.node.remove();a.anchor?.setAttribute('aria-expanded','false');if(focus&&a.anchor?.isConnected)a.anchor.focus()}
async function openParcelReason(id,anchor){
 if(activeReasonMenu?.id===id&&activeReasonMenu.kind!=='state'){closeParcelReason();return}closeParcelReason(false);
 const node=document.createElement('section');node.className='parcel-reason-menu';node.setAttribute('role','dialog');node.setAttribute('aria-label','Note de suivi');node.innerHTML='<p class="reason-loading">Chargement des motifs…</p>';document.body.append(node);anchor?.setAttribute('aria-expanded','true');
 const state={node,anchor,id,owner:S.user.id,busy:false};activeReasonMenu=state;
 const place=()=>{if(activeReasonMenu!==state)return;const w=Math.min(340,innerWidth-24),rect=anchor?.getBoundingClientRect();node.style.width=w+'px';node.style.left=Math.max(12,Math.min(rect?.left||12,innerWidth-w-12))+'px';const h=Math.min(420,innerHeight-24),below=(rect?.bottom||20)+8,above=(rect?.top||0)-h-8;node.style.top=Math.max(12,below+h<=innerHeight-12?below:above>=12?above:innerHeight-h-12)+'px';node.style.maxHeight=h+'px'};state.place=place;place();
 try{
  const [d,config]=await Promise.all([loadParcelCommand(id),api(S.user.role==='livreur'?'/logistics/followup-reasons':'/logistics/config')]);if(activeReasonMenu!==state||S.user.id!==state.owner)return;
  if(!parcelStateEditable(d.parcel))throw Error('Ce colis ne peut plus être modifié. Actualisez la liste.');state.parcel=d.parcel;
  node.innerHTML=`<header><div><strong>Note de suivi</strong><small>${esc(d.parcel.tracking)} · ${esc(d.parcel.status)}</small></div><button class="icon-btn" aria-label="Fermer les motifs">${icon('close')}</button></header><p class="reason-help">Le motif seul change. Aucun statut, rendez-vous ou retour physique n’est confirmé.</p><label class="reason-search">${icon('search')}<input aria-label="Rechercher un motif" placeholder="Rechercher un motif…"></label><div class="reason-options"></div><p class="reason-error" role="alert" hidden></p><footer>${opsOffline?'Simulation locale · aucune synchronisation':'Motifs configurables par Admin → Hubs & motifs'}</footer>`;
  node.querySelector('header button').onclick=()=>closeParcelReason();
  const priority=['return_agency','no_answer','postponed','voicemail','always_unavailable','long_trip','exchange_refund','changed_mind','wrong_city','out_of_area','cancelled_delay','no_money','bought_elsewhere','duplicate_order','wrong_number','travelling','not_interested'];const rank=r=>priority.includes(r.code)?priority.indexOf(r.code):99;const choices=[{code:null,label:'Aucun motif (retirer la note)'},...config.reasons.filter(r=>r.active).sort((a,b)=>rank(a)-rank(b)||a.label.localeCompare(b.label,'fr'))];
  const draw=()=>{const query=parcelText(node.querySelector('input').value),list=node.querySelector('.reason-options');list.replaceChildren();for(const r of choices.filter(r=>parcelText(r.label).includes(query))){const button=document.createElement('button');button.type='button';button.className='reason-option';button.textContent=r.label;button.setAttribute('aria-pressed',String((d.parcel.reason_code||null)===r.code));button.disabled=state.busy;button.onclick=()=>saveParcelReason(state,r.code);list.append(button)}if(!list.children.length)list.textContent='Aucun motif trouvé.'};
  node.querySelector('input').oninput=draw;draw();place();node.querySelector(innerWidth<=760?'header button':'input').focus();
 }catch(e){if(activeReasonMenu===state){node.innerHTML=`<p class="reason-error">${esc(e.message)}</p><button class="btn sm" onclick="closeParcelReason()">Fermer</button>`}}
}
async function saveParcelReason(state,code){
 if(state.busy||activeReasonMenu!==state)return;state.busy=true;state.node.querySelectorAll('.reason-option').forEach(b=>b.disabled=true);
 try{
  const inline=!!document.querySelector(`[data-parcel-expanded="${state.id}"]`),inModal=!!document.querySelector('.parcel-command-modal');
  await api409(f=>api('/parcels/'+state.id+'/reason','PATCH',{reason_code:code,revision:f?f.ops_revision:(state.parcel.ops_revision||0)}),async()=>({ops_revision:(await api('/parcels/'+state.id)).parcel.ops_revision}));
  if(S?.user?.id!==state.owner){closeParcelReason(false);return}
  closeParcelReason(false);await refresh();await renderView();
  if(inline){const button=document.querySelector(`.parcel-expand-button[onclick="toggleParcelRow(${state.id},this)"]`);if(button)await toggleParcelRow(state.id,button)}
  if(inModal)await parcelDetail(state.id);
  toast('Motif enregistré · statut inchangé');
 }catch(e){if(activeReasonMenu===state){const error=state.node.querySelector('.reason-error');error.hidden=false;error.textContent=e.message;state.busy=false;state.node.querySelectorAll('.reason-option').forEach(b=>b.disabled=false)}}
}
document.addEventListener('pointerdown',e=>{if(activeReasonMenu&&!activeReasonMenu.node.contains(e.target)&&!activeReasonMenu.anchor?.contains(e.target))closeParcelReason(false)});
document.addEventListener('keydown',e=>{if(!activeReasonMenu)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeParcelReason()}else if(e.key==='Tab'){const focusables=[...activeReasonMenu.node.querySelectorAll('input:not(:disabled),select:not(:disabled),textarea:not(:disabled),button:not(:disabled)')],first=focusables[0],last=focusables.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}},true);
window.addEventListener('resize',()=>activeReasonMenu?.place?.());

// The row's status itself is the dropdown trigger; no generic modal is opened.
function parcelStatusChoices(p){
 if(S.user.role==='client')return clientInterestedEligible(p)?['Intéressé']:[];
 if(['admin','agent'].includes(S.user.role))return S.user.role==='agent'&&!hubParcelStatusEditable(p)?[]:S.statuses.filter(s=>s!=='Vers Hub Central');
 const next=S.status_policy.driver_transitions;
 return [p.status,...(next[p.status]||[])].filter(s=>!['Réceptionné','Retourné'].includes(s));
}
function statusMenuError(state,error){if(activeReasonMenu!==state)return;state.busy=false;const el=state.node.querySelector('.reason-error');if(el){el.hidden=false;el.textContent=error.message}state.node.querySelectorAll('button[data-status],button[type=submit]').forEach(b=>b.disabled=b.dataset.status===state.parcel?.status)}
async function openParcelState(id,anchor){
 if(activeReasonMenu?.kind==='state'&&activeReasonMenu.id===id){closeParcelReason();return}closeParcelReason(false);
 anchor=anchor||document.querySelector(`.parcel-status-button[onclick="openParcelState(${id},this)"]`);
 const node=document.createElement('section');node.className='parcel-reason-menu parcel-status-menu';node.setAttribute('role','dialog');node.setAttribute('aria-label','Changer l’état de la commande');node.innerHTML='<p class="reason-loading">Chargement des états autorisés…</p>';document.body.append(node);anchor?.setAttribute('aria-expanded','true');
 const state={kind:'state',node,anchor,id,owner:S.user.id,busy:false};activeReasonMenu=state;
 state.place=()=>{if(activeReasonMenu!==state)return;const w=Math.min(320,innerWidth-24),r=anchor?.getBoundingClientRect(),h=Math.min(state.confirming?570:440,innerHeight-24),below=(r?.bottom||20)+8,above=(r?.top||0)-h-8;node.style.width=w+'px';node.style.left=Math.max(12,Math.min(r?.left||12,innerWidth-w-12))+'px';node.style.top=Math.max(12,below+h<=innerHeight-12?below:above>=12?above:innerHeight-h-12)+'px';node.style.maxHeight=h+'px'};state.place();
 try{const d=await loadParcelCommand(id);if(activeReasonMenu!==state||S?.user?.id!==state.owner)return;state.parcel=d.parcel;if(!parcelStatusEditable(d.parcel))throw Error('Colis verrouillé, clôturé ou déjà marqué « Intéressé ». Actualisez la liste.');renderStatusOptions(state)}
 catch(e){if(activeReasonMenu===state)node.innerHTML=`<p class="reason-error">${esc(e.message)}</p><button class="btn sm" onclick="closeParcelReason()">Fermer</button>`}
}
function statusMenuHeader(state,title){return `<header><div><strong>${esc(title)}</strong><small>${esc(state.parcel.tracking)} · ${esc(state.parcel.status)}</small></div><button class="icon-btn" aria-label="Fermer les états" onclick="closeParcelReason()">${icon('close')}</button></header>`}
function renderStatusOptions(state){
 if(activeReasonMenu!==state)return;state.confirming=false;const footer=S.user.role==='client'?'Vous pouvez uniquement marquer cette commande comme intéressée. Cela ne confirme ni livraison ni paiement.':'Choisissez un état. Les étapes sensibles demandent une confirmation. Le motif précédent est réinitialisé.';state.node.innerHTML=statusMenuHeader(state,'Changer l’état')+'<div class="reason-options status-options"></div><p class="reason-error" role="alert" hidden></p><footer>'+footer+'</footer>';
 const list=state.node.querySelector('.status-options');for(const label of parcelStatusChoices(state.parcel)){const b=document.createElement('button');b.type='button';b.className='reason-option';b.dataset.status=label;b.textContent=label+(label===state.parcel.status?' · actuel':'');b.title=S.status_policy.help[label]||'';b.disabled=label===state.parcel.status;b.setAttribute('aria-pressed',String(b.disabled));b.onclick=()=>selectParcelStatus(state,label);list.append(b)}
 list.onkeydown=e=>{const buttons=[...list.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(document.activeElement);if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();buttons[e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowDown'?1:buttons.length-1))%buttons.length]?.focus()}};
 state.place();list.querySelector('button:not(:disabled)')?.focus();
}
async function selectParcelStatus(state,status){
 if(state.busy||activeReasonMenu!==state||status===state.parcel.status)return;
 const p=state.parcel,terminal=['Livré','Retourné','Refusé'].includes(status),backward=S.user.role==='admin'&&((['Livré','Retourné'].includes(p.status))||(S.status_policy.rank[status]<S.status_policy.rank[p.status]));
 state.attempt=!opsOffline&&S.user.role==='livreur'&&p.status!=='Livré'&&S.status_policy.attempt_outcomes.includes(status);
 if(S.user.role!=='agent'&&status!=='Programmé'&&!terminal&&!backward&&!state.attempt&&!['Transit','Réceptionné','Reçu par le livreur'].includes(status))return submitParcelStatus(state,status,{});
 state.busy=true;
 try{
  const config=(status==='Programmé'||(state.attempt&&status!=='Livré'))?await api(S.user.role==='livreur'?'/logistics/followup-reasons':'/logistics/config'):null;if(activeReasonMenu!==state)return;
  state.busy=false;state.confirming=true;state.requestKey=financeKey();
  const reasonRequired=status==='Programmé'||(state.attempt&&status!=='Livré');
  state.node.innerHTML=statusMenuHeader(state,'Confirmer : '+status)+`<form class="status-confirm"><p class="reason-help">${status==='Livré'?`Confirmer la livraison et la collecte de ${money(p.amount)} MAD.`:status==='Programmé'?'Choisissez un motif et un rendez-vous futur, heure du Maroc.':backward?'Correction administrative : retour à un état antérieur.':esc(S.status_policy.help[status]||'Confirmez le changement d’état.')}</p>${reasonRequired?`<label>Motif<select name="reason_code" required aria-label="Motif du nouvel état"><option value="">Choisir un motif</option>${config.reasons.filter(r=>r.active).map(r=>`<option value="${esc(r.code)}">${esc(r.label)}</option>`).join('')}</select></label>`:''}${S.user.role==='agent'&&status==='Livré'?'<p class="form-hint orange">Après confirmation, cette commande ne pourra plus être modifiée par un responsable de Hub.</p>':''}${status==='Livré'&&p.otp_required?'<label>Code client<input name="otp" inputmode="numeric" pattern="[0-9]{4}" maxlength="4" required aria-label="Code client à 4 chiffres"></label>':''}${status==='Programmé'?'<label>Rendez-vous · heure du Maroc<input name="next_attempt_at" type="datetime-local" required aria-label="Rendez-vous du nouvel état"></label>':''}${state.attempt&&status==='Livré'&&S.user.role!=='livreur'?`<label>Réceptionnaire déclaré<input name="receiver" required maxlength="150" aria-label="Réceptionnaire déclaré"></label><label>COD déclaré (MAD)<input name="collected_amount" type="number" min="0" step="0.01" value="${Number(p.amount)}" required aria-label="COD déclaré"></label>`:''}${S.user.role==='livreur'&&status==='Livré'?'':`<label>Commentaire ${backward?'obligatoire':'(facultatif)'}<textarea name="note" maxlength="1000" ${backward?'required':''} aria-label="Commentaire du nouvel état"></textarea></label>`}<p class="reason-error" role="alert" hidden></p><div class="status-confirm-actions"><button type="button" class="btn sm status-back">Retour</button><button type="submit" class="btn primary sm">Confirmer ${esc(status)}</button></div><small>${opsOffline?'Simulation HTML locale, sans tentative structurée ni preuve de livraison.':state.attempt?'Tentative historisée. Déclaration sans signature/photo, aucun transfert bancaire.':'Changement historisé. Aucun règlement bancaire automatique.'}</small></form>`;
  state.node.querySelector('.status-back').onclick=()=>{if(!state.busy)renderStatusOptions(state)};
  state.node.querySelector('form').onsubmit=async e=>{e.preventDefault();const d=Object.fromEntries(new FormData(e.target));if(backward&&!d.note.trim()){statusMenuError(state,new Error('Expliquez la correction administrative.'));return}await submitParcelStatus(state,status,d)};
  state.place();state.node.querySelector('header button').focus();
 }catch(e){statusMenuError(state,e)}
}
async function submitParcelStatus(state,status,fields){
 if(state.busy||activeReasonMenu!==state)return;state.busy=true;state.node.querySelectorAll('button[data-status],button[type=submit]').forEach(b=>b.disabled=true);
 const inline=!!document.querySelector(`[data-parcel-expanded="${state.id}"]`),inModal=!!document.querySelector('.parcel-command-modal');
 try{
  if(state.attempt&&status==='Livré'&&S.user.role==='livreur')fields={...fields,simple_delivery:true};
  if(state.attempt)await api409(f=>api('/logistics/parcels/'+state.id+'/attempts','POST',{...fields,outcome:status,revision:f?f.ops_revision:(state.parcel.ops_revision||0),request_key:state.requestKey}),async()=>({ops_revision:(await api('/logistics/parcels/'+state.id)).parcel.ops_revision}));
  else await api409(f=>api('/parcels/'+state.id,'PATCH',{...fields,status,revision:f?f.ops_revision:(state.parcel.ops_revision||0)}),async()=>({ops_revision:(await api('/parcels/'+state.id)).parcel.ops_revision}));
  if(S?.user?.id!==state.owner)return;if(activeReasonMenu===state)closeParcelReason(false);
  await refresh();await renderView();
  if(inline){const b=document.querySelector(`.parcel-expand-button[onclick="toggleParcelRow(${state.id},this)"]`);if(b)await toggleParcelRow(state.id,b)}
  if(inModal)await parcelDetail(state.id);toast('État enregistré : '+status);
 }catch(e){statusMenuError(state,e)}
}

async function openDriverFollowup(id){
 if(S?.user?.role!=='livreur')return;
 const owner=S.user.id;
 modal('Motif / note du livreur','<p class="sub">Chargement…</p>');
 const node=document.querySelector('#modal-root .modal');
 const current=()=>node?.isConnected&&S?.user?.id===owner;
 try{
  const [data,cfg]=await Promise.all([loadParcelCommand(id),api(S.user.role==='livreur'?'/logistics/followup-reasons':'/logistics/config')]);
  if(!current())return;
  const p=data.parcel;
  if(p.driver_id!==owner||!parcelStateEditable(p))throw Error('Commande non modifiable ou non affectée à ce livreur.');
  node.querySelector('.modal-body').innerHTML=`<p class="form-hint">${esc(p.tracking)} · ${esc(p.status)}. Le statut reste inchangé. Votre note sera ajoutée à la Chronologie, sans remplacer les instructions de livraison.</p><form><label>Motif de suivi<select name="reason_code"><option value="">Aucun motif</option>${cfg.reasons.filter(r=>r.active).map(r=>`<option value="${esc(r.code)}" ${r.code===p.reason_code?'selected':''}>${esc(r.label)}</option>`).join('')}</select></label><label>Note libre (facultative)<textarea name="note" maxlength="1000" placeholder="Votre commentaire de suivi…"></textarea></label><p class="reason-error" role="alert" hidden></p><div class="form-actions"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button class="btn primary" type="submit">Enregistrer le suivi</button></div></form>`;
  const f=node.querySelector('form');let busy=false;
  f.onsubmit=async e=>{
   e.preventDefault();if(busy||!current())return;busy=true;const btn=f.querySelector('[type=submit]'),err=f.querySelector('.reason-error');btn.disabled=true;err.hidden=true;
   try{
    await api('/parcels/'+id+'/followup','PATCH',{reason_code:f.elements.reason_code.value||null,note:f.elements.note.value.trim(),revision:p.ops_revision||0});
    if(!current())return;closeModal();await refresh();await renderView();toast('Suivi enregistré · statut inchangé');
   }catch(e){if(current()){err.hidden=false;err.textContent=e.message;btn.disabled=false;busy=false}}
  };
 }catch(e){if(current())node.querySelector('.modal-body').innerHTML=`<p class="reason-error">${esc(e.message)}</p><button class="btn" onclick="closeModal()">Fermer</button>`}
}
