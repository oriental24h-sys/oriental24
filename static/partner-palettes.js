/* Partner intake: shared operational locks, independent of invoice/payment state. */
let ppFilters={q:'',state:'',page:1,size:20},ppOwner=null;
const ppLabel=s=>({'Préparé':'Brouillon','En transit':'Envoyée · à recevoir','Partiellement reçu':'Réception partielle','Reçu':'Réceptionnée','Clôturé (écarts)':'Clôturée avec écarts','Annulé':'Annulée'}[s]||s);
const ppBadge=s=>`<span class="tag ${s==='Reçu'?'good':s==='Annulé'?'bad':s==='Partiellement reçu'||s==='Clôturé (écarts)'?'warn':'blue'}">${esc(ppLabel(s))}</span>`;
const ppAccess=u=>u?.role==='admin'||u?.role==='agent'||u?.role==='client'&&u.client_type==='societe_livraison';
const ppIdentity=()=>S?`${S.user.id}:${S.user.role}`:null;
function ppQuery(){if(ppOwner!==ppIdentity()){ppOwner=ppIdentity();ppFilters={q:'',state:'',page:1,size:20}}return new URLSearchParams(ppFilters).toString()}
let ppWorkspaceTab='incoming',ppWorkspaceOwner=null;
function ppWorkspaceSelect(tab){ppWorkspaceTab=tab==='returns'?'returns':'incoming';renderView()}
function ppWorkspaceActions(){
 const refresh=`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button>`;
 if(ppWorkspaceTab==='returns')return refresh+`<button class="btn primary" onclick="rpScanStart()">${icon('scan')}Envoyer retour au scan</button><button class="btn" onclick="rpCreate()">${icon('plus')}Envoi manuel (liste)</button>`;
 return refresh+(S.user.role==='admin'?`<button class="btn" onclick="ppHubForm()">${icon('pin')}Ajouter un hub</button>`:'')+`<button class="btn primary" onclick="ppReceiveStart()">${icon('download')}Réception palette</button>`+(S.user.role==='agent'?'':`<button class="btn primary" onclick="ppCreate()">${icon('plus')}Préparer une palette</button>`);
}
async function partnerAdminWorkspace(){
 const owner=ppIdentity();if(ppWorkspaceOwner!==owner){ppWorkspaceOwner=owner;ppWorkspaceTab='incoming'}
 const incoming=ppWorkspaceTab!=='returns';
 const data=await api(incoming?'/partner-palettes?'+ppQuery():'/return-palettes?'+rpQuery());
 const sub=incoming?'Arrivées de palettes envoyées par les clients et partenaires vers ORIENTAL24.':'Retours vendeurs expédiés depuis un hub ORIENTAL24, suivis séparément des arrivées partenaires.';
 const tabs=`<section class="card"><div class="tabs" role="tablist"><button class="tab ${incoming?'active':''}" role="tab" aria-selected="${incoming}" onclick="ppWorkspaceSelect('incoming')">Arrivées partenaires</button><button class="tab ${!incoming?'active':''}" role="tab" aria-selected="${!incoming}" onclick="ppWorkspaceSelect('returns')">Retours vendeurs</button></div></section>`;
 return heading('Palettes partenaires',sub,ppWorkspaceActions())+tabs+(incoming?partnerPalettesView(data,true):returnPalettesView(data,true));
}
menu[1][1].splice(2,0,['partner-palettes','layers','Palettes partenaires',['admin','client','agent']]);
menu[1][1].find(x=>x[0]==='pallets')[2]='Anciennes palettes';
titles['pallets']='Anciennes palettes';
titles['partner-palettes']='Palettes partenaires';
opsKinds.partner_palette='Palette société → ORIENTAL24';
function partnerPalettesView(d, embedded=false){
 ppFilters.page=d.page;
 const actions=`<button class="btn" onclick="renderView()">${icon('refresh')}Actualiser</button>${S.user.role==='admin'?`<button class="btn" onclick="ppHubForm()">${icon('pin')}Ajouter un hub</button>`:''}${(S.user.role==='admin'||S.user.role==='agent')?`<button class="btn primary" onclick="ppReceiveStart()">${icon('download')}Réception palette</button>`:''}${S.user.role==='agent'?'':`<button class="btn primary" onclick="ppCreate()">${icon('plus')}Préparer une palette</button>`}`;
 const pageHeading=heading('Palettes partenaires',S.user.role==='admin'?'Contrôlez les arrivées des sociétés, sans modifier leurs trackings.':S.user.role==='agent'?'Réceptionnez les palettes arrivant à votre hub.':'Préparez vos palettes, déclarez leur envoi et suivez leur réception.',actions);
 return (embedded?'':pageHeading)+`<div class="pp-explainer"><span class="stat-icon">${icon('layers')}</span><div><b>Votre code reste votre code.</b><p>La société expédie un manifeste de colis. Seule la réception physique confirmée par Admin passe les colis à <b>Réceptionné</b>. Les absents restent à recevoir. Aucun paiement automatique.${opsOffline?' Simulation locale uniquement.':''}</p></div></div><section class="card"><form class="pp-filters" onsubmit="ppFilter(event)">${input('pp-search','Tracking commande, référence palette ou société',ppFilters.q,'search',false,'maxlength="120" placeholder="Ex. O24-100123, PP-000009 ou nom de société"')}${select('pp-state','État',[['','Tous les états'],...['Préparé','En transit','Partiellement reçu','Reçu','Clôturé (écarts)','Annulé'].map(s=>[s,ppLabel(s)])],ppFilters.state)}<button class="btn navy" type="submit">Filtrer</button>${(S.user.role==='admin'||S.user.role==='agent')?'<button type="button" class="btn" onclick="ppFusionStart()" id="pp-fusion-btn" disabled>Fusionner (0)</button>':''}</form>${simpleTable(['Palette / Société','Destination / Transport','Réception','État',''],d.rows.map(r=>[`${(S.user.role==="admin"||S.user.role==="agent")&&["En transit","Partiellement reçu"].includes(r.status)?`<label class="pp-fuscheck"><input type="checkbox" class="pp-fus" value="${r.id}" onchange="ppFusionCount()"></label>`:`<span class="pp-fuscheck"></span>`}<button class="tracking" onclick="openPartnerPalette(${r.id})">${esc(r.reference)}</button><span class="sub">${esc(r.client_name)}</span>${r.tracking_matches?.length?`<span class="sub pp-search-match">Commande trouvée : ${r.tracking_matches.slice(0,3).map(x=>esc(x.tracking)).join(' · ')}${r.tracking_match_count>3?' · +'+(r.tracking_match_count-3):''}</span>`:''}${r.partner_reference?`<span class="sub">Réf. société : ${esc(r.partner_reference)}</span>`:''}`,`${esc(r.destination_name)}<span class="sub">${esc(r.transport||'Transport non renseigné')}</span>`,`<b>${r.received} / ${r.count}</b><span class="sub">${r.status==='Annulé'?'Manifeste annulé':r.remaining+' restant(s)'}</span>`,ppBadge(r.status),`<button class="btn sm" onclick="${S.user.role==='agent'?'openPartnerPalette('+r.id+')':S.user.role==='admin'&&['En transit','Partiellement reçu'].includes(r.status)?'ppReceiveScan('+r.id+')':'openPartnerPalette('+r.id+')'}">${(S.user.role==='admin'||S.user.role==='agent')&&['En transit','Partiellement reçu'].includes(r.status)?'Réceptionner':'Ouvrir'} ${icon('arrow')}</button>`]))}${!d.rows.length?empty('Aucune palette dans cette sélection','Les palettes préparées par les sociétés apparaîtront ici.'):''}<div class="table-footer"><span>${d.total} palette(s)</span><div class="pagination"><button onclick="ppPage(-1)" ${d.page<=1?'disabled':''}>‹</button><span>${d.page} / ${Math.max(1,Math.ceil(d.total/d.size))}</span><button onclick="ppPage(1)" ${d.page*d.size>=d.total?'disabled':''}>›</button></div></div></section>`;
}
async function ppFilter(e){e.preventDefault();ppFilters.q=e.target.elements['pp-search'].value;ppFilters.state=e.target.elements['pp-state'].value;ppFilters.page=1;await renderView()}
async function ppPage(delta){ppFilters.page+=delta;await renderView()}
function ppContext(title){const owner=ppIdentity();modal(title,'<p>Chargement…</p>',true);const node=$('#modal-root .modal');return {node,owner,current:()=>node.isConnected&&ppIdentity()===owner}}
function ppError(ctx,e){if(ctx.current())ctx.node.querySelector('.modal-body').innerHTML=`<p class="form-hint orange">${esc(e.message)}</p><div class="form-actions"><button class="btn" onclick="closeModal()">Fermer</button></div>`}
function ppSubmit(ctx,f,send){let frozen=null,done=null;f.onsubmit=async e=>{e.preventDefault();if(!ctx.current())return;const b=f.querySelector('[type=submit]'),err=f.querySelector('.form-error');if(b.disabled)return;b.disabled=true;err.style.display='none';try{if(!done){if(!frozen){frozen={...Object.fromEntries(new FormData(f)),confirmed:!!f.elements.confirmed?.checked,request_key:financeKey()};for(const x of f.querySelectorAll('input,select,textarea,button[type=button]'))x.disabled=true}done=await send(frozen)}if(!ctx.current())return;await refresh();if(!ctx.current())return;await renderView();if(!ctx.current())return;if(done.id)await openPartnerPalette(done.id);else closeModal();if(ppIdentity()===ctx.owner)toast(done.already_received?'Colis déjà reçu : aucune double réception.':'Opération enregistrée')}catch(e){if(ctx.current()){err.textContent=e.message+' Réessayez avec la même confirmation, ou fermez et actualisez.';err.style.display='block'}}finally{b.disabled=false}}}
async function ppCreate(){
 if(!ppAccess(S?.user))return;const ctx=ppContext('Préparer une palette');
 try{const cfg=await api('/partner-palettes/config');if(!ctx.current())return;if(!cfg.hubs.length)throw Error('Aucun hub de réception actif. Demandez à Admin de créer le hub via « Ajouter un hub » avant de préparer la palette.');
 const admin=S.user.role==='admin';ctx.node.querySelector('.modal-body').innerHTML=form(`${admin?select('client_id','Société / vendeur',[['','Choisir une société ou un vendeur'],...cfg.companies.map(c=>[c.id,(c.company||c.name)+(c.client_type&&c.client_type!=='societe_livraison'?' · '+clientTypeLabel(c):'')])]):`<div class="full form-hint">Société : <b>${esc(S.user.company||S.user.name)}</b></div>`}${select('destination_hub_id','Hub ORIENTAL24 de réception',cfg.hubs.map(h=>[h.id,h.name+' · '+h.city]))}${input('partner_reference','Référence palette de la société (facultative)','','text',false,'maxlength="80"')}${input('transport','Transport / véhicule (facultatif)','','text',false,'maxlength="120"')}<div class="full pp-picker"><label for="pp-lookup">Rechercher un tracking à inclure</label><input id="pp-lookup" type="search" placeholder="Tracking original de la société" autocomplete="off"><div class="pp-actions"><button type="button" class="btn sm" id="pp-select-visible">Tout sélectionner (résultats)</button><button type="button" class="btn sm" id="pp-clear-selection">Vider la sélection</button><span class="pp-selection-count" id="pp-selection-count">0 colis sélectionné</span></div><div id="pp-candidates">${admin?'Choisissez une société.':'Chargement des colis…'}</div></div>${textarea('note','Note sur la palette')}<p class="full form-hint">1 à 500 colis Créé, non affectés, non reçus et sans document actif. Le brouillon réserve les colis mais ne confirme ni départ ni réception. Pour modifier un brouillon enregistré, annulez-le et préparez-en un nouveau.</p>`,'Enregistrer le brouillon');
 const f=ctx.node.querySelector('form');f.onsubmit=e=>e.preventDefault();let rows=[],selected=new Set(),load=0,chosen=null;
 const draw=()=>{const q=f.querySelector('#pp-lookup').value.toLowerCase();f.querySelector('#pp-selection-count').textContent=selected.size+' colis sélectionné(s)';f.querySelector('#pp-candidates').innerHTML=rows.filter(p=>!q||p.tracking.toLowerCase().includes(q)||p.recipient.toLowerCase().includes(q)).map(p=>`<label class="pp-candidate"><input type="checkbox" value="${p.id}" ${selected.has(p.id)?'checked':''}><span><b>${esc(p.tracking)}</b><small>${esc(p.recipient)} · ${esc(p.city)}</small></span></label>`).join('')||'<p class="sub">Aucun colis disponible pour cette sélection.</p>';f.querySelectorAll('.pp-candidate input').forEach(x=>x.onchange=()=>{if(x.checked)selected.add(Number(x.value));else selected.delete(Number(x.value));f.querySelector('#pp-selection-count').textContent=selected.size+' colis sélectionné(s)'})};
 const fetchRows=async()=>{const serial=++load,cid=admin?f.elements.client_id.value:S.user.id;chosen=null;selected.clear();rows=[];draw();if(!cid)return;try{const d=await api('/partner-palettes/candidates?client_id='+encodeURIComponent(cid));if(!ctx.current()||serial!==load)return;rows=d.rows;chosen=d.client_id;draw()}catch(e){if(ctx.current()&&serial===load)f.querySelector('#pp-candidates').textContent=e.message}};
 f.querySelector('#pp-select-visible').onclick=()=>{const q=f.querySelector('#pp-lookup').value.toLowerCase(),next=new Set([...selected,...rows.filter(p=>!q||p.tracking.toLowerCase().includes(q)||p.recipient.toLowerCase().includes(q)).map(p=>p.id)]);if(next.size>500){toast('Maximum 500 colis par palette. Réduisez la recherche.',true);return}selected=next;draw()};f.querySelector('#pp-clear-selection').onclick=()=>{selected.clear();draw()};f.addEventListener('submit',e=>{if(!chosen||!selected.size||selected.size>500){e.preventDefault();e.stopImmediatePropagation();const err=f.querySelector('.form-error');err.textContent='Sélectionnez 1 à 500 colis disponibles avant de continuer.';err.style.display='block'}},true);f.elements.client_id?.addEventListener('change',fetchRows);f.querySelector('#pp-lookup').oninput=draw;await fetchRows();if(!ctx.current())return;
 // Freeze the selected IDs before sending; retries use the identical payload.
 let parcelIDs=null,clientID=null;ppSubmit(ctx,f,async d=>{if(!parcelIDs){if(!chosen||!selected.size||selected.size>500)throw Error('Sélectionnez 1 à 500 colis ; fermez puis recommencez si nécessaire.');parcelIDs=[...selected];clientID=chosen}return api('/partner-palettes','POST',{...d,client_id:clientID,destination_hub_id:Number(d.destination_hub_id),parcel_ids:parcelIDs})});
 }catch(e){ppError(ctx,e)}
}
async function openPartnerPalette(id){
 if(!ppAccess(S?.user))return;const ctx=ppContext('Palette partenaire');
 try{const d=await api('/partner-palettes/'+id);if(!ctx.current())return;const canReceive=S.user.role==='admin'||S.user.role==='agent',receiving=canReceive&&['En transit','Partiellement reçu'].includes(d.status);
 ctx.node.querySelector('h2').textContent=d.reference;ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-document-head"><div><span class="eyebrow orange">SOCIÉTÉ → ORIENTAL24</span><h3>${esc(d.client_name)}</h3><p>${esc(d.destination_name)} · ${esc(d.transport||'Transport non renseigné')}</p><p>${d.partner_reference?'Réf. société : '+esc(d.partner_reference)+' · ':''}${date(d.created_at)}</p></div>${ppBadge(d.status)}</div><div class="pp-progress"><strong>${d.received}<small> / ${d.count}</small></strong><div><b>colis physiquement reçus</b><span>${d.status==='Annulé'?'Brouillon annulé ; aucun colis attendu.':(d.remaining?d.remaining+' restant(s) à recevoir':'Aucun colis attendu')+(d.missing?' · '+d.missing+' déclaré(s) manquant(s)':'')}</span></div></div>${d.note?`<p class="form-hint" data-no-translate>${esc(d.note)}</p>`:''}${d.cancel_reason?`<p class="form-hint orange">Annulation : <span data-no-translate>${esc(d.cancel_reason)}</span></p>`:''}<div class="pp-actions">${S.user.role==='admin'&&d.status==='Préparé'?`<button class="btn primary" onclick="ppAction(${id},'dispatch')">${icon('truck')}Confirmer l’envoi</button><button class="btn danger" onclick="ppAction(${id},'cancel')">Annuler le brouillon</button>`:''}${receiving&&S.user.role==='admin'?`<button class="btn" onclick="ppAction(${id},'receive-all')">${icon('checkcircle')}Recevoir tous les ${d.remaining} restants</button>`:''}<button class="btn" onclick="ppPrint(${id})">${icon('print')}Bon de réception / PDF</button><button class="btn" onclick="ppCSV(${id})">${icon('download')}CSV</button><button class="btn" onclick="openPartnerPalette(${id})">${icon('refresh')}Actualiser</button></div>${receiving?`<div class="pp-scan"><div id="pp-individual-receive-scan"></div></div>${rxExtrasButtons(id,d)}`:d.status==='Préparé'?'<p class="form-hint">Le brouillon ne vaut pas envoi. Confirmez uniquement lorsque la palette a réellement quitté la société.</p>':d.missing&&!d.remaining?`<p class="form-hint">Palette clôturée avec écarts : ${d.missing} colis déclaré(s) manquant(s), dossiers visibles ci-dessous.</p>`:d.remaining&&d.status!=='Annulé'?`<p class="form-hint">Réception à effectuer par Admin ou l’agent du hub ${esc(d.destination_name)}. Les colis absents restent attendus ; ils ne sont pas considérés comme reçus.</p>`:''}${d.status==='Clôturé (écarts)'||d.missing||receiving?rxIncidentsBlock(d):''}${simpleTable(['Tracking original','Destinataire / Ville','Réception','État actuel'],d.lines.map(l=>[`<button class="tracking" onclick="parcelDetail(${l.parcel_id})">${esc(l.tracking)}</button>`,`${esc(l.recipient)}<span class="sub">${esc(l.city)}</span>`,l.received_at?`<span class="tag good">Reçu</span><span class="sub">${esc(opsDate(l.received_at))}</span>`:l.missing_at?`<span class="tag warn">Manquant déclaré</span><span class="sub">${esc(opsDate(l.missing_at))}</span>`:`<span class="tag ${d.status==='Annulé'?'bad':'warn'}">${d.status==='Annulé'?'Annulé':'À recevoir'}</span>`,tag(l.current_status)]))}<h3 class="ops-subtitle">Historique de la palette</h3><div class="timeline">${d.audit.map(a=>`<div class="timeline-item"><b>${esc(a.action)}</b><small>${esc(a.actor)} · ${esc(opsDate(a.created_at))}</small>${a.details.trackings?`<p>${a.details.trackings.map(esc).join(' · ')}</p>`:''}</div>`).join('')}</div><p class="sub">Les trackings, COD, frais et factures sont conservés. Les colis reçus peuvent être affectés au livreur même si d’autres colis de cette palette restent attendus.</p>`;
 if(receiving)ppBindIndividualReceive(ctx,id,d)
 if(d.status==='Clôturé (écarts)'||d.missing||receiving)await ppRenderIncidents(ctx,id,d);
 }catch(e){ppError(ctx,e)}
}
function ppBindIndividualReceive(ctx,id,d){
 const root=ctx.node.querySelector('#pp-individual-receive-scan');if(!root||typeof o24ScanCollector!=='function')return;
 const admin=S?.user?.role==='admin',known=new Map((d.lines||[]).map(l=>[String(l.tracking||'').trim().toUpperCase(),l])),processed=new Set();
 const collector=o24ScanCollector(root,{
  id:'pp-individual-receive',label:'Scanner les colis reçus (lecteur USB, clavier ou caméra)',
  placeholder:'Tracking société puis Entrée',inputMax:80,max:Math.max(1,Math.min(500,Number(d.remaining)||500)),
  commitLabel:'Valider les réceptions',
  hint:'Les scans restent en attente jusqu’à la validation. Chaque colis est ensuite réceptionné individuellement.',
  confirmText:'Je confirme avoir physiquement reçu les colis au hub '+(d.destination_name||'de réception')+'.',
  confirmRequiredMessage:'Confirmez avoir physiquement reçu ces colis au hub.',
  renderItem:item=>`<b>${esc(item.tracking)}</b>${item.recipient?`<span class="sub">${esc(item.recipient)} · ${esc(item.city||'')}</span>`:''}`,
  resolve:async code=>{
   const tracking=String(code||'').trim(),key=tracking.toUpperCase(),line=known.get(key);
   if(processed.has(key))throw Error('Ce colis a déjà été réceptionné dans cette session.');
   if(admin&&!line)throw Error('Ce tracking ne figure pas dans cette palette.');
   if(line?.missing_at)throw Error('Ce colis est déclaré manquant et ne peut pas être réceptionné.');
   if(line?.received_at)throw Error('Ce colis est déjà réceptionné.');
   return {tracking:line?.tracking||tracking,recipient:line?.recipient||'',city:line?.city||''};
  },
  onCommit:async(items,control)=>{
   let received=0,already=0;
   for(const item of items){
    if(!ctx.current())return;
    try{
     const fresh=await api('/partner-palettes/'+id);
     const current=(fresh.lines||[]).find(l=>String(l.tracking||'').toUpperCase()===item.tracking.toUpperCase());
     if(current?.received_at){processed.add(item.tracking.toUpperCase());control.remove(item);already++;continue}
     if(current?.missing_at)throw Error('Ce colis est déclaré manquant et ne peut pas être réceptionné.');
     const request_key=financeKey();
     const result=await api409(revision=>api('/partner-palettes/'+id+'/receive','POST',{
      tracking:item.tracking,confirmed:true,request_key,revision:revision?revision.revision:fresh.revision
     }),async()=>({revision:(await api('/partner-palettes/'+id)).revision}));
     processed.add(item.tracking.toUpperCase());control.remove(item);if(result.already_received)already++;else received++;
    }catch(error){
     if(ctx.current()){
      const done=received+already;
      control.setMessage('err',(done?`Réception partielle : ${done} colis déjà traités. `:'')+(error.message||'Réception impossible.'));
      toast((done?`Réception partielle (${done} colis) · `:'')+(error.message||'Réception impossible.'),true);
     }
     return;
    }
   }
   if(!ctx.current())return;
   await refresh();if(!ctx.current())return;
   await renderView();if(!ctx.current())return;
   await openPartnerPalette(id);
   toast(`Réception enregistrée : ${received} colis${already?' · '+already+' déjà reçus':''} ✓`);
  }
 });
 modalCleanup=()=>collector?.destroy();
}

async function ppAction(id,action){
 const ctx=ppContext(action==='dispatch'?'Confirmer l’envoi':action==='cancel'?'Annuler le brouillon':'Confirmer la réception complète');
 try{const d=await api('/partner-palettes/'+id);if(!ctx.current())return;const all=action==='receive-all';if(all&&S.user.role!=='admin'&&S.user.role!=='agent')throw Error('Réception réservée à Admin et aux agents de réception.');
 ctx.node.querySelector('.modal-body').innerHTML=form(`<div class="full form-hint"><b>${esc(d.reference)} · ${esc(d.client_name)}</b><br>Destination : ${esc(d.destination_name)}<br>${all?d.remaining+' colis restants seront marqués Réceptionné.':action==='dispatch'?d.count+' colis seront déclarés envoyés, mais pas encore reçus.':'Les colis seront libérés sans supprimer le manifeste ni les commandes.'}</div>${all?`<div class="full pp-confirm-list">${d.lines.filter(l=>!l.received_at).map(l=>`<div>${esc(l.tracking)} · ${esc(l.recipient)}</div>`).join('')}</div>`:''}${action==='cancel'?textarea('reason','Motif d’annulation','',true):''}<label class="full pp-consent"><input type="checkbox" name="confirmed" required> ${all?'Je confirme avoir contrôlé et physiquement reçu TOUS les colis restants ci-dessus.':action==='dispatch'?'Je confirme que cette palette a réellement été envoyée vers ORIENTAL24.':'Je confirme l’annulation de ce brouillon non envoyé.'}</label><p class="full form-hint orange">${all?'Si un seul colis manque, fermez cette fenêtre et utilisez le scan unitaire.':action==='dispatch'?'Après envoi, les colis manquants restent attendus ; le manifeste ne peut plus être annulé.':'Aucun colis ni historique n’est supprimé.'}</p>`,all?'Confirmer la réception des '+d.remaining+' colis':action==='dispatch'?'Confirmer l’envoi':'Annuler le brouillon');ppSubmit(ctx,ctx.node.querySelector('form'),async payload=>{
  // receive-all: la liste confirmée physiquement peut changer entre-temps ; on rouvre le dialogue avec la liste à jour plutôt que rejouer à l’aveugle.
  if(all){try{return await api('/partner-palettes/'+id+'/receive-all','POST',{...payload,revision:d.revision,expected_remaining:d.remaining})}catch(e){if(CONFLICT_RX.test(String(e.message||''))){toast('La liste des colis restants a changé : fiche actualisée, contrôlez puis recommencez.');await openPartnerPalette(id)}throw e}}
  return api409(g=>api('/partner-palettes/'+id+'/'+action,'POST',{...payload,revision:g?g.revision:d.revision}),async()=>({revision:(await api('/partner-palettes/'+id)).revision}))
 });
 }catch(e){ppError(ctx,e)}
}
async function ppHubForm(){if(S?.user?.role!=='admin')return;const ctx=ppContext('Ajouter un hub ORIENTAL24');ctx.node.querySelector('.modal-body').innerHTML=form(`${input('name','Nom du hub','','text',true,'maxlength="100"')}${select('city_id','Ville',S.cities.map(c=>[c.id,c.name]))}${textarea('address','Adresse physique','',true)}<p class="full form-hint">Ce hub est partagé avec les autres outils logistiques. Il apparaîtra dans les destinations de réception des sociétés.</p>`,'Ajouter le hub');ppSubmit(ctx,ctx.node.querySelector('form'),async d=>{await api('/logistics/hubs','POST',{name:d.name,city_id:Number(d.city_id),address:d.address});return {ok:true}})}
async function ppCSV(id){try{if(!opsOffline){await billingFetchFile('/api/partner-palettes/'+id+'/csv','ORIENTAL24-palette-'+id+'.csv');return}const owner=ppIdentity(),d=await api('/partner-palettes/'+id);if(owner!==ppIdentity())return;const rows=[['Palette','Société','Tracking original','Destinataire','Ville','Réception','Reçu le'],...d.lines.map(l=>[d.reference,d.client_name,l.tracking,l.recipient,l.city,l.received_at?'Reçu':d.status==='Annulé'?'Annulé':'À recevoir',l.received_at||''])];billingSaveFile(new Blob([billingCSV(rows)],{type:'text/csv;charset=utf-8'}),'ORIENTAL24-'+d.reference+'.csv')}catch(e){toast(e.message,true)}}
async function ppPrint(id){
 const owner=ppIdentity();
 try{
  const d=await api('/partner-palettes/'+id);if(owner!==ppIdentity())return;
  const printData={
   title:'Bon de réception',reference:d.reference,
   date:opsDate(d.dispatched_at||d.created_at),status:ppLabel(d.status),
   route:`${d.client_name||'Société'} → ${d.hub_name||d.destination_name||'Hub'}`,
   party:{label:'Hub de réception',name:d.hub_name||d.destination_name,lines:[d.hub_address,d.hub_city]},
   count:d.count,received:d.received,remaining:d.remaining,missing:d.missing,note:d.note,
   rows:(d.lines||[]).map(l=>({tracking:l.tracking,city:l.city,recipient:l.recipient,phone:l.phone,amount:l.amount})),
   signatures:['Société expéditrice','Transporteur','Réception par le hub']
  };
  await doPrint(o24BonHtml(printData),root=>{if(owner!==ppIdentity()){root.innerHTML='';throw Error('Session modifiée. Rouvrez le bon de réception.')}})
 }catch(e){if(owner===ppIdentity())toast(e.message,true)}
}
let ppFusSel=new Set();
function ppFusionCount(){ppFusSel=new Set([...document.querySelectorAll('.pp-fus:checked')].map(x=>Number(x.value)));const b=document.getElementById('pp-fusion-btn');if(b){b.textContent='Fusionner ('+ppFusSel.size+')';b.disabled=ppFusSel.size<2}}
async function ppFusionStart(){
 if(S?.user?.role!=='admin'&&S?.user?.role!=='agent')return;
 ppFusionCount();if(ppFusSel.size<2){toast('Cochez au moins 2 palettes en attente de réception (même hub).',true);return}
 const ctx=ppContext('Fusionner les palettes');
 try{const d=await api('/partner-palettes/fusion','POST',{palette_ids:[...ppFusSel]});if(!ctx.current())return;ppFusSel=new Set();await renderView();await ppFusOpen(d.id)}catch(e){ppError(ctx,e)}
}
async function ppFusOpen(bid,initialItems=[],initialBusy=false){
 const ctx=ppContext('Réception du pack fusionné');
 const draw=(d,staged=[],busy=false)=>{
  ctx.node.querySelector('h2').textContent=d.reference;
  ctx.node.querySelector('.modal-body').innerHTML=`<div class="pp-document-head"><div><span class="eyebrow orange">FUSION · RÉCEPTION GROUPÉE</span><h3>${d.palettes.length} palettes → ${d.palettes.map(p=>esc(p.reference)).join(' · ')}</h3><p>${d.palettes.map(p=>esc(p.client_name)).join(', ')}</p></div><span class="tag ${d.closed?'good':'blue'}">${d.closed?'Pack clôturé':'Scan en cours'}</span></div><div class="pp-progress"><strong>${d.received}<small> / ${d.count}</small></strong><div><b>colis scannés reçus</b><span>${d.remaining?d.remaining+' restant(s) à scanner':'tous les colis contrôlés'}${d.missing?' · '+d.missing+' déclaré(s) non réceptionné(s)':''}</span></div></div>${!d.closed?'<div id="pp-fus-collector"></div>':'<p class="form-hint">Réception terminée : les colis non scannés ont été déclarés non réceptionnés et les sociétés ont été notifiées.</p>'}<div class="pp-actions">${!d.closed&&d.remaining?`<button class="btn danger" id="pp-fus-close">${icon('close')}Clôturer sans les ${d.remaining} restants (déclarer non réceptionnés + notifier)</button>`:''}<button class="btn" onclick="closeModal();renderView()">${icon('refresh')}Fermer et actualiser</button></div>${simpleTable(['Palette / Société','Tracking','Destinataire / Ville','Réception'],d.lines.map(l=>[`<b>${esc(l.reference)}</b><span class="sub">${esc(l.client_name)}</span>`,`<button class="tracking" onclick="parcelDetail(${l.parcel_id})">${esc(l.tracking)}</button>`,`${esc(l.recipient)}<span class="sub">${esc(l.city)}</span>`,l.received_at?`<span class="tag good">Reçu</span>`:l.missing_at?`<span class="tag warn">Non réceptionné</span>`:`<span class="tag blue">À scanner</span>`]))}`;
  if(!d.closed){
   const closeBtn=ctx.node.querySelector('#pp-fus-close');
   let collector=null;
   const root=ctx.node.querySelector('#pp-fus-collector');
   if(root&&typeof o24ScanCollector==='function'){
    const admin=S?.user?.role==='admin',known=new Map((d.lines||[]).map(l=>[String(l.tracking||'').trim().toUpperCase(),l]));
    collector=o24ScanCollector(root,{
     id:'pp-fusion-receive',label:'Scanner les colis du pack (lecteur USB, clavier ou caméra)',
     placeholder:'Tracking du colis puis Entrée',inputMax:160,max:Math.max(1,Math.min(500,Number(d.remaining)||500)),
     commitLabel:'Valider la réception du pack',
     hint:'Le lot reste local jusqu’à validation. Le serveur enregistre chaque réception dans sa palette d’origine.',
     initialMessage:'Présentez un colis du pack. Aucun colis n’est réceptionné avant la validation finale.',
     initialItems:staged,initialBusy:busy,
     renderItem:item=>`<b>${esc(item.tracking)}</b>${item.recipient?`<span class="sub">${esc(item.reference)} · ${esc(item.recipient)} · ${esc(item.city||'')}</span>`:''}`,
     resolve:async code=>{
      const tracking=String(code||'').trim(),line=known.get(tracking.toUpperCase());
      if(admin&&!line)throw Error('Ce tracking ne figure dans aucune palette du pack.');
      if(line?.missing_at)throw Error('Ce colis est déjà déclaré non réceptionné.');
      if(line?.received_at)throw Error('Ce colis est déjà réceptionné.');
      return {tracking:line?.tracking||tracking,reference:line?.reference||'',recipient:line?.recipient||'',city:line?.city||''};
     },
     onChange:(items,state)=>{if(closeBtn)closeBtn.disabled=items.length>0||state.busy},
     onCommit:async(items,control)=>{
      let latest=d,done=0;
      for(const item of items){
       if(!ctx.current())return;
       try{latest=await api('/partner-palettes/fusion/'+bid+'/scan','POST',{tracking:item.tracking})}
       catch(error){
        let fresh=null;try{fresh=await api('/partner-palettes/fusion/'+bid)}catch(e){}
        const current=(fresh?.lines||[]).find(l=>String(l.tracking||'').toUpperCase()===item.tracking.toUpperCase());
        if(current?.received_at){latest=fresh;control.remove(item);done++;continue}
        const pending=control.items;
        if(fresh&&ctx.current())draw(fresh,pending,false);
        else control.setMessage('err',(done?`Réception partielle : ${done} colis déjà traités. `:'')+(error.message||'Réception impossible.'));
        if(ctx.current())toast((done?`Réception partielle (${done} colis) · `:'')+(error.message||'Réception impossible.'),true);
        return;
       }
       control.remove(item);done++;
      }
      if(ctx.current()){
       draw(latest,[]);
       toast(`Fusion réceptionnée : ${done} colis confirmé${done===1?'':'s'} ✓`);
      }
     }
    });
    modalCleanup=()=>collector?.destroy();
   }
   if(closeBtn)closeBtn.onclick=async()=>{
    try{const r=await api('/partner-palettes/fusion/'+bid+'/close','POST',{expected_remaining:d.remaining});if(!ctx.current())return;collector?.destroy();draw(r);toast('Pack clôturé : '+r.missing+' non réceptionné(s), '+r.notified+' société(s) notifiée(s)')}catch(e){toast(e.message,true)}
   };
  }
 };
 try{const d=await api('/partner-palettes/fusion/'+bid);if(!ctx.current())return;draw(d,initialItems,initialBusy)}catch(e){ppError(ctx,e)}
}
