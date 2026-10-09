/* Scoped parcel contacts: current driver comes from the parcel detail API, never an old snapshot. */
paths.headset='M3 14v-3a9 9 0 0 1 18 0v3 M3 12H2v7h4v-7H3 M21 12h1v7h-4v-7h3 M19 19c0 3-3 3-6 3';
if(!opsOffline){menu.push(['ASSISTANCE',[['support-team','phone','Contacts support',['admin']]]]);titles['support-team']='Contacts support'}
let supportContacts=[];
function parcelPhone(phone,label='Appeler',id,name){
 const raw=String(phone||'').trim(),dial=raw.replace(/[ ()-]/g,'');
 if(!raw)return '<span class="parcel-contact-missing">Numéro non renseigné</span>';
 if(S?.user?.role==='support')return `<span class="parcel-phone readonly">${esc(raw)}</span>`;
 return /^\+?[0-9]{9,15}$/.test(dial)?`<a class="parcel-phone" href="tel:${esc(dial)}" data-cl-id="${id||0}" data-cl-phone="${esc(raw)}" data-cl-name="${esc(name||'')}" onclick="return o24ClCall(this)" aria-label="${esc(label+' '+raw)}">${icon('phone')}<span>${esc(raw)}</span></a>`:`<span class="parcel-contact-missing">${esc(raw)} · numéro à vérifier</span>`;
}
function parcelClientContactActions(p,kind,name,phone){
 const raw=String(phone||'').trim(),compact=raw.replace(/[ ()-]/g,''),digits=raw.replace(/\D/g,'');
 if(!/^\+?\d{9,15}$/.test(compact))return `<span class="parcel-contact-missing">${esc(raw||'Numéro non renseigné')} · numéro à vérifier</span>`;
 const tel=compact,wa=raw.startsWith('+')?digits:(digits.startsWith('00')?digits.slice(2):(digits.startsWith('212')?digits:(digits.startsWith('0')?'212'+digits.slice(1):(digits.length===9?'212'+digits:digits))));
 const who=kind==='driver'?'Livreur':'Support',message=`Bonjour ${name}, je vous contacte au sujet de la commande ${p.tracking} (${p.recipient}, ${p.city}).`;
 return `<div class="parcel-contact-client-number"><span class="parcel-contact-value">${esc(raw)}</span><div class="parcel-contact-actions"><a class="btn sm" href="tel:${esc(tel)}" aria-label="Appeler ${esc(who)} ${esc(name)}">${icon('phone')}Appeler</a><a class="btn sm" target="_blank" rel="noopener" href="https://wa.me/${esc(wa)}?text=${encodeURIComponent(message)}" aria-label="Envoyer un message WhatsApp à ${esc(who)} ${esc(name)}">${icon('chat')}WhatsApp</a></div></div>`;
}
function parcelContactCard(p,kind){
 const driver=kind==='driver',name=driver?p.driver:(p.support_name||p.city_support_name),phone=driver?p.driver_phone:(p.support_phone||p.city_support_phone),active=driver?p.driver_active:(p.support_active??p.city_support_active);
 const contact=name?(S?.user?.role==='client'?parcelClientContactActions(p,kind,name,phone):parcelPhone(phone,driver?'Appeler le livreur':'Appeler le support')):'<span class="parcel-contact-missing">Aucun numéro attribué</span>';
 return `<div class="parcel-contact ${driver?'delivery':'support'}"><span class="parcel-contact-icon">${icon(driver?'truck':'headset')}</span><div class="parcel-contact-label"><span>${driver?'Livreur actuel':'Support'}</span><strong>${esc(name|| (driver?'Non affecté':'Support non affecté'))}</strong>${name&&active===0?'<small class="orange">Contact inactif · à réaffecter</small>':''}</div><div class="parcel-contact-number">${contact}</div></div>`;
}
function parcelCommandBody(d,inline=false){
 const p=d.parcel,id=p.id,locked=p.invoice_id||p.financial_locked||p.operations_locked,canPrice=S.user.role!=='support'&&!locked&&!['Livré','Retourné','Refusé'].includes(p.status),refreshAction=inline==='client'?`refreshClientParcelDetails(${id})`:inline?`reloadParcelRow(${id})`:`parcelDetail(${id})`,closeAction=inline==='client'?`closeClientParcelDetails(${id})`:`closeParcelRow(${id})`;
 const timeline=[...d.events].sort((a,b)=>String(a.created_at||'').localeCompare(String(b.created_at||''))||a.id-b.id);
 return `<div class="parcel-command-top"><span class="mono">${icon('box')}${esc(p.tracking)}</span><div><button class="btn sm" onclick="${refreshAction}">${icon('refresh')}Actualiser</button>${S.user.role==='admin'&&typeof openParcelOtp==='function'?`<button class="btn sm" onclick="openParcelOtp(${id})">${icon('shield')}Code client</button>`:''}${inline?`<button class="icon-btn" onclick="${closeAction}" aria-label="Fermer les détails">${icon('close')}</button>`:''}</div></div><div class="parcel-command-grid detail-grid"><section class="parcel-command-card"><div class="detail-info"><div class="flex between"><div class="parcel-copy-recipient">${parcelCopyButton(p)}<h3>${esc(p.recipient)}</h3></div>${tag(p.status)}</div><div class="parcel-recipient-phone">${parcelPhone(p.phone,'Appeler le destinataire',p.id,p.recipient)}${!['client','support'].includes(S.user.role)?parcelWaButton(p):''}</div>${riskPanel(p.phone)}<p class="parcel-product">Nature du produit : <strong>${p.product?`<span data-no-translate>${esc(p.product)}</span>`:'Non renseignée'}</strong></p>${parcelPolicyBadges(p)}<p class="parcel-address" data-no-translate>${icon('pin')}${esc(p.address)} · ${esc(p.city||'')}</p>${p.time_window?`<p class="parcel-rdv-line">${icon('clock')}Créneau RDV : <strong>${rdvLabel(p.time_window)}</strong></p>`:''}<div class="parcel-cod"><span>Montant à collecter</span><strong>${money(p.amount)} <small>MAD</small></strong><span>Frais de livraison : ${money(p.fee)} MAD</span></div>${canPrice?`<button class="btn primary parcel-price-request" onclick="requestPrice(${id})">${icon('wallet')}Demande de changement de prix</button>`:''}${locked?`<p class="form-hint">${icon('lock')}${p.operations_locked?'Colis rattaché à un document actif.':'Colis verrouillé dans un relevé financier.'} Les coordonnées restent consultables.</p>`:''}</div><div class="parcel-contacts">${parcelContactCard(p,'driver')}${parcelContactCard(p,'support')}<p class="parcel-contact-note">${p.driver_returned?'Colis récupéré à l’agence ; attribution financière historique conservée. ':''}Coordonnées actuelles à l’ouverture de la fiche. Actualisez après une réaffectation.</p></div>${S.user.role==='admin'&&!opsOffline?`<div class="parcel-support-actions"><button class="btn sm" onclick="assignParcelSupport(${id})">${icon('user')}${p.support_contact_id?'Modifier le support':'Affecter un support'}</button><button class="btn sm" onclick="closeModal();navigate('support-team')">Gérer les contacts support</button></div>`:''}<div class="parcel-command-note"><span>Motif de suivi</span><div class="command-reason">${parcelNoteControl(p)}</div><span>Note de livraison</span><p>${p.note?`<span data-no-translate>${esc(p.note)}</span>`:'Aucune note pour ce colis.'}</p></div>${S.user.role==='client'?`<div class="client-parcel-footer client-inline-recipient">${clientRecipientRequestControl(p)}<span class="client-parcel-history-hint">Les informations détaillées et la Chronologie s’affichent dans ce panneau.</span></div>`:''}${S.user.role==='support'?'':`<div class="parcel-command-actions">${parcelCityButton(p,true)}${parcelClaimButton(p,true)}<button class="btn sm" onclick="printLabels([${id}])">${icon('print')}Étiquette</button>${!locked&&S.user.role!=='client'?`<button class="btn primary sm" onclick="changeStatus(${id})">${icon('edit')}Changer le statut</button>`:''}${!locked&&S.user.role==='admin'?`<button class="btn sm" onclick="assignDriver(${id})">${icon('user')}Affecter un livreur</button>`:''}</div>`}${opsOffline?'<p class="parcel-contact-note">HTML : contacts livreurs fictifs. L’affectation du support nécessite le serveur.</p>':''}</section><section class="parcel-command-card parcel-chronology"><div class="parcel-chronology-heading"><h3>Chronologie d’activité</h3><span>${timeline.length} événement(s) · du plus ancien au plus récent · appels et WhatsApp du livreur inclus</span></div><div class="timeline">${timeline.map(e=>`<div class="timeline-item"><span class="parcel-event-mark">${icon(e.status==='Appel client'?'phone':(e.status==='WhatsApp client'?'chat':'plus'))}</span>${tag(e.status)}<p>${esc(e.note||'Statut mis à jour')}</p><strong class="parcel-event-actor">${esc(e.actor||'Acteur non renseigné')}</strong><small>${opsDate(e.created_at)}</small></div>`).join('')||'<p class="sub">Aucun événement enregistré.</p>'}</div></section></div>`;
}
async function loadParcelCommand(id){const owner=S.user.id,d=await api('/parcels/'+id);if(S?.user?.id!==owner)throw new Error('Session modifiée. Rouvrez la commande.');const old=S.parcels.find(p=>p.id===id);if(old)Object.assign(old,d.parcel);return d}
parcelDetail=async function(id){try{const d=await loadParcelCommand(id);modal(d.parcel.tracking,parcelCommandBody(d),true);$('.modal')?.classList.add('parcel-command-modal')}catch(e){toast(e.message,true)}};
function clientSupportAction(p,kind,supportName,supportPhone){
 const raw=String(supportPhone||'').trim(),compact=raw.replace(/[ ()-]/g,''),digits=raw.replace(/\D/g,'');
 const valid=/^\+?\d{9,15}$/.test(compact)&&digits.length>=9&&digits.length<=15;
 const title=kind==='whatsapp'?'WhatsApp du support':'Appeler le support';
 if(!valid)return `<button type="button" class="client-action-icon ${kind} disabled" disabled title="${title} : numéro non renseigné" aria-label="${title} indisponible">${icon(kind==='whatsapp'?'chat':'headset')}</button>`;
 if(kind==='whatsapp'){
  const wa=digits.startsWith('212')?digits:(digits.startsWith('0')?'212'+digits.slice(1):'212'+digits);
  const message=`Bonjour ${supportName||'ORIENTAL24'}, je vous contacte au sujet de la commande ${p.tracking} (${p.recipient}, ${p.city}).`;
  return `<a class="client-action-icon whatsapp" href="https://wa.me/${esc(wa)}?text=${encodeURIComponent(message)}" target="_blank" rel="noopener" title="${title}" aria-label="${title}">${icon('chat')}</a>`;
 }
 return `<a class="client-action-icon support-call" href="tel:${esc(compact)}" title="${title}" aria-label="${title}">${icon('headset')}</a>`;
}
function clientInvoiceTags(p){
 if(!p.invoice_id)return '';
 const label=p.invoice_status==='Réglée'?'Paid':p.invoice_status==='Partiellement réglée'?'Partiellement réglée':'À régler';
 return `<div class="client-invoice-tags"><span class="client-invoice-badge">${esc(p.invoice_reference||'Facturée')}</span><span class="client-invoice-payment ${p.invoice_status==='Réglée'?'paid':''}">${esc(label)}</span></div>`;
}
function clientRecipientRequestControl(p){
 const closed=['Livré','Retourné'].includes(p.status);
 if(p.recipient_change_status==='En attente')return `<div class="client-change-pending"><span>${icon('clock')}Demande en attente</span><div class="client-change-pending-info"><strong data-no-translate>${esc(p.recipient_change_name||'—')}</strong><small data-no-translate>☎ ${esc(p.recipient_change_phone||'—')} · ${esc(p.recipient_change_city||'—')}</small><small>${p.recipient_change_address?`<span data-no-translate>${esc(p.recipient_change_address)}</span>`:'Adresse non renseignée'}</small>${closed?`<small class="client-change-terminal-note">Statut ${esc(p.status)} : l’administration ne peut plus accepter ce changement.</small>`:''}</div></div>`;
 if(closed)return `<div class="client-recipient-disabled"><button type="button" class="btn sm client-recipient-change" disabled aria-disabled="true" title="Indisponible pour un colis ${esc(p.status)}">${icon('lock')}Demande indisponible</button><small class="client-change-terminal-note">Impossible de demander un changement pour un colis ${esc(p.status)}.</small></div>`;
 return `<button type="button" class="btn sm client-recipient-change" onclick="requestRecipientChange(${p.id})">${icon('edit')}Demande changement de destinataire</button>`;
}
function clientRatingAction(p){
 const score=Number(p.driver_rating||p.support_rating||0),rated=score>0;
 return `<button type="button" class="client-action-icon review ${rated?'rated':''}" onclick="clientReview(${p.id})" title="${rated?'Évaluation enregistrée · modifier':'Évaluer le service'}" aria-label="${rated?'Modifier l’évaluation':'Évaluer le service'}">${icon('star')}</button>`;
}
function closeClientParcelDetails(id){
 const card=document.querySelector(`[data-client-parcel="${id}"]`),extra=card?.querySelector('.client-parcel-extra'),button=card?.querySelector('.client-parcel-toggle');
 if(!card||!extra||!button)return;extra.hidden=true;card.classList.remove('is-expanded');button.setAttribute('aria-expanded','false');button.title='Afficher les détails supplémentaires';button.setAttribute('aria-label','Afficher les détails supplémentaires de '+(card.querySelector('.client-parcel-reference .tracking')?.textContent||'la commande'));
}
async function refreshClientParcelDetails(id){
 const card=document.querySelector(`[data-client-parcel="${id}"]`),extra=card?.querySelector('.client-parcel-extra');if(!card||!extra||extra.hidden)return;
 extra.innerHTML='<div class="parcel-inline-detail"><p class="sub">Chargement de la commande…</p></div>';
 try{const d=await loadParcelCommand(id);if(!card.isConnected||extra.hidden)return;extra.innerHTML=`<div class="parcel-inline-detail">${parcelCommandBody(d,'client')}</div>`}
 catch(e){if(card.isConnected&&!extra.hidden)extra.innerHTML=`<div class="parcel-inline-detail"><p class="form-hint" role="alert">${esc(e.message||'Impossible de charger la commande.')}</p></div>`}
}
async function toggleClientParcelDetails(id,button){
 const card=button.closest('.client-parcel-card'),extra=card?.querySelector('.client-parcel-extra');if(!card||!extra)return;
 if(button.getAttribute('aria-expanded')==='true'){closeClientParcelDetails(id);return}
 document.querySelectorAll('.client-parcel-card.is-expanded').forEach(other=>{if(other!==card)closeClientParcelDetails(other.dataset.clientParcel)});
 extra.hidden=false;card.classList.add('is-expanded');button.setAttribute('aria-expanded','true');button.title='Masquer les détails supplémentaires';button.setAttribute('aria-label','Masquer les détails supplémentaires de '+(card.querySelector('.client-parcel-reference .tracking')?.textContent||'la commande'));
 await refreshClientParcelDetails(id);
}
function clientParcelCards(rows,selectable=true){
 if(!rows.length)return empty('Aucun colis trouvé','Essayez d’autres filtres ou ajoutez un nouveau colis.');
 return `<div class="client-parcel-list">${rows.map(p=>{
  const supportName=p.support_name||p.city_support_name||'Support ORIENTAL24';
  const supportPhone=p.support_phone||p.city_support_phone||'';
  const phone=String(p.phone||'');
  const invoice=clientInvoiceTags(p);
  return `<article class="client-parcel-card ${selectable?'client-parcel-has-select':''}" data-client-parcel="${p.id}">
   <div class="client-parcel-primary">
    ${selectable?`<div class="client-parcel-select"><input class="parcel-select" value="${p.id}" type="checkbox" aria-label="Sélectionner ${esc(p.tracking)}"></div>`:'<span class="client-parcel-select-placeholder" aria-hidden="true"></span>'}
    <div class="client-parcel-cell client-parcel-reference"><span class="client-data-label">Référence</span><button class="tracking" onclick="parcelDetail(${p.id})">${esc(p.tracking)}</button><small>${date(p.created_at)}</small>${parcelPolicyBadges(p,true)}</div>
    <div class="client-parcel-cell"><span class="client-data-label">Destinataire</span><strong data-no-translate>${esc(p.recipient||'—')}</strong></div>
    <div class="client-parcel-cell"><span class="client-data-label">Ville</span><strong data-no-translate>${esc(p.city||'—')}</strong></div>
    <div class="client-parcel-cell client-parcel-amount"><span class="client-data-label">Prix COD</span><strong>${money(p.amount)} <small>MAD</small></strong></div>
    <div class="client-parcel-cell client-parcel-status"><span class="client-data-label">Statut</span>${tag(p.status)}${invoice}</div>
    <div class="client-parcel-actions" aria-label="Actions de la commande">${p.invoice_status==='Réglée'?'<span class="client-paid-pill">Paid</span>':''}${clientSupportAction(p,'whatsapp',supportName,supportPhone)}${clientSupportAction(p,'call',supportName,supportPhone)}<button type="button" class="client-action-icon info" onclick="parcelDetail(${p.id})" title="Informations et chronologie" aria-label="Informations et chronologie">${icon('info')}</button>${clientRatingAction(p)}<button type="button" class="client-action-icon client-parcel-toggle" onclick="toggleClientParcelDetails(${p.id},this)" title="Afficher les détails supplémentaires" aria-label="Afficher les détails supplémentaires de ${esc(p.tracking)}" aria-expanded="false" aria-controls="client-parcel-extra-${p.id}">${icon('chevron')}<span class="sr-only">Afficher les détails supplémentaires</span></button></div>
   </div>
   <div id="client-parcel-extra-${p.id}" class="client-parcel-extra" hidden>
   <div class="client-parcel-details">
    <span><b>Produit</b>${p.product?`<span data-no-translate>${esc(p.product)}</span>`:'Non renseigné'}</span>
    <span><b>Téléphone</b>${phone?`☎ ${esc(phone)}`:'Non renseigné'}</span>
    <span><b>Adresse</b>${p.address?`<span data-no-translate>${esc(p.address)}</span>`:'Non renseignée'}</span>
    <span><b>Frais de livraison</b>${money(p.fee)} MAD</span>
    <span><b>Livreur</b>${p.driver?`<span data-no-translate>${esc(p.driver)}</span>`:'Non affecté'}${p.driver_phone?` · <span data-no-translate>${esc(p.driver_phone)}</span>`:''}</span>
    <span><b>Support</b><span data-no-translate>${esc(supportName)}</span>${supportPhone?` · <span data-no-translate>${esc(supportPhone)}</span>`:''}</span>
    ${p.time_window?`<span><b>Créneau</b>${esc(rdvLabel(p.time_window))}</span>`:''}
    ${p.reason_label?`<span><b>Motif</b>${esc(p.reason_label)}</span>`:''}
    ${p.invoice_id?`<span><b>Facture</b>${esc(p.invoice_reference||'—')} · Frais retour : ${money(p.return_fee)} MAD</span>`:''}
    ${p.note?`<span class="client-parcel-note"><b>Note</b><span data-no-translate>${esc(p.note)}</span></span>`:''}
   </div>
   <div class="client-parcel-footer">${clientRecipientRequestControl(p)}<span class="client-parcel-history-hint">L’historique complet s’ouvre avec le bouton « i ».</span></div>
   </div>
  </article>`;
 }).join('')}</div>`;
}
function requestRecipientChange(id){
 const p=S?.parcels?.find(x=>Number(x.id)===Number(id));
 if(!p){toast('Commande introuvable. Actualisez la page.',true);return}
 if(['Livré','Retourné'].includes(p.status)){toast('Impossible de demander un changement pour un colis Livré ou Retourné.',true);return}
 if(p.recipient_change_status==='En attente'){toast('Une demande de changement est déjà en attente.',true);return}
 const cities=(S.cities||[]).filter(c=>c.delivery).map(c=>[c.id,c.name]);
 if(p.city_id&&!cities.some(([cityId])=>Number(cityId)===Number(p.city_id)))cities.unshift([p.city_id,(p.city||'Ville actuelle')+' · ville actuelle']);
 if(!cities.length){toast('Aucune ville de livraison disponible.',true);return}
 const current=`<section class="full client-recipient-current"><div class="client-recipient-current-heading"><h3>Informations actuelles</h3><span class="tag">Le suivi reste inchangé</span></div><div class="client-recipient-current-grid"><div><span>Numéro de suivi · non modifiable</span><strong class="mono" dir="ltr">${esc(p.tracking)}</strong></div><div><span>Destinataire</span><strong data-no-translate>${esc(p.recipient||'—')}</strong></div><div><span>Téléphone</span><strong dir="ltr" data-no-translate>${esc(p.phone||'Non renseigné')}</strong></div><div><span>Ville</span><strong data-no-translate>${esc(p.city||'—')}</strong></div><div class="address"><span>Adresse actuelle</span><strong data-no-translate>${esc(p.address||'Non renseignée')}</strong></div></div></section>`;
 const safety=`<div class="full client-recipient-lock-note">${icon('lock')}Le tracking ne peut pas être modifié. Le montant COD, les frais, le statut et la facture restent inchangés. Les nouvelles coordonnées ne seront appliquées qu’après accord de l’administration.</div>`;
 modal('Demande de changement de destinataire',form(
  `${current}${input('recipient','Nom du nouveau destinataire','','text',true,'maxlength="120" autocomplete="name"')}${input('phone','Téléphone du nouveau destinataire',p.phone||'','tel',true,'maxlength="18" autocomplete="tel" placeholder="06… ou +212…"')}${select('city_id','Nouvelle ville de livraison',[['','Choisir une ville'],...cities],p.city_id||'',true)}${textarea('address','Nouvelle adresse complète',p.address||'',true)}${textarea('reason','Motif (facultatif)','',false)}${safety}`,
  'Envoyer la demande'));
 $('.modal')?.classList.add('client-recipient-window');
 $('#f-address')?.setAttribute('maxlength','300');$('#f-address')?.setAttribute('rows','3');$('#f-reason')?.setAttribute('maxlength','500');
 bindForm(async d=>{
  await api('/parcels/'+id+'/recipient-change-requests','POST',{recipient:d.recipient,phone:d.phone,city_id:Number(d.city_id),address:d.address,reason:d.reason||''});
  await refresh();await renderView();closeModal();toast('Demande envoyée à l’administration ✓');
 });
}
let clientRatingDraft=null;
function clientRatingTarget(target){
 if(!clientRatingDraft||!['driver','support'].includes(target))return;
 clientRatingDraft.target=target;
 const existing=clientRatingDraft.ratings[target]||{};
 clientRatingDraft.stars=Number(existing.stars)||0;
 clientRatingDraft.comment=existing.comment||'';
 renderClientRatingModal();
}
function clientRatingSet(stars){if(!clientRatingDraft)return;clientRatingDraft.stars=Number(stars)||0;renderClientRatingModal()}
function renderClientRatingModal(){
 const root=document.querySelector('#modal-root .modal-body');if(!root||!clientRatingDraft)return;
 const d=clientRatingDraft,p=d.parcel,target=d.target,who=target==='driver'?'livreur':'support';
 const face=d.stars>=5?'🤩':d.stars===4?'🙂':d.stars===3?'😐':d.stars===2?'🙁':d.stars===1?'😟':'😐';
 root.innerHTML=`<div class="client-rating-modal">
  <div class="client-rating-targets"><button type="button" class="${target==='driver'?'active':''}" onclick="clientRatingTarget('driver')">${icon('truck')}Évaluer le livreur</button><button type="button" class="${target==='support'?'active':''}" onclick="clientRatingTarget('support')">${icon('headset')}Évaluer le support</button></div>
  <section class="client-rating-parcel"><h3>Informations du colis</h3><p><span>Numéro de suivi</span><strong>${esc(p.tracking)}</strong></p><p><span>Destinataire</span><strong>${esc(p.recipient||'—')}</strong></p><p><span>Service évalué</span><strong>${esc(target==='driver'?(p.driver||'Livreur ORIENTAL24'):(p.support_name||p.city_support_name||'Support ORIENTAL24'))}</strong></p></section>
  <section class="client-rating-global"><h3>Évaluation globale</h3><div class="client-rating-face" aria-live="polite">${face}</div><div class="client-rating-stars" role="group" aria-label="Choisir le nombre d’étoiles">${[1,2,3,4,5].map(n=>`<button type="button" class="${n<=d.stars?'selected':''}" onclick="clientRatingSet(${n})" aria-label="${n} étoile${n>1?'s':''}">★</button>`).join('')}</div><p>${d.stars?`${d.stars}/5 étoiles`:'Choisissez de 1 à 5 étoiles'}</p></section>
  <div class="client-rating-comment"><label for="client-rating-comment">Commentaire (facultatif)</label><textarea id="client-rating-comment" maxlength="600" oninput="if(clientRatingDraft)clientRatingDraft.comment=this.value">${esc(d.comment||'')}</textarea></div>
  <div class="client-rating-actions"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button type="button" class="btn primary" onclick="submitClientRating()" ${d.stars? '':'disabled'}>${icon('check')}Soumettre</button></div>
 </div>`;
}
async function clientReview(id){
 try{
  const [result]=await Promise.all([api('/parcels/'+id+'/ratings')]);
  const p=S?.parcels?.find(x=>Number(x.id)===Number(id));if(!p)throw new Error('Commande introuvable.');
  const ratings={};(result.ratings||[]).filter(r=>Number(r.client_id)===Number(S.user.id)).forEach(r=>ratings[r.target]=r);
  const target=ratings.driver?'driver':(ratings.support?'support':'driver');
  clientRatingDraft={id:Number(id),parcel:p,ratings,target,stars:Number(ratings[target]?.stars)||0,comment:ratings[target]?.comment||''};
  modal('Évaluer le service','',true);$('.modal')?.classList.add('client-rating-window');renderClientRatingModal();
 }catch(e){toast(e.message||'Évaluation impossible.',true)}
}
async function submitClientRating(){
 const d=clientRatingDraft;if(!d||!d.stars)return;
 try{
  await api('/parcels/'+d.id+'/ratings','POST',{target:d.target,stars:d.stars,comment:d.comment||''});
  const targetField=d.target==='driver'?'driver_rating':'support_rating';const row=S?.parcels?.find(p=>Number(p.id)===d.id);if(row)row[targetField]=d.stars;
  clientRatingDraft=null;await refresh();await renderView();closeModal();toast('Évaluation enregistrée ✓');
 }catch(e){toast(e.message||'Évaluation impossible.',true)}
}
const contactBaseParcelTable=parcelTable;
parcelTable=function(rows,selectable=true){
 if(S?.user?.role==='client'&&view!=='print'&&window.innerWidth<=760)return clientParcelCards(rows,selectable);
 let html=contactBaseParcelTable(rows,selectable);if(view==='print')return html;
 for(const p of rows){
  const old=`<button class="icon-btn" title="Ouvrir le colis" onclick="parcelDetail(${p.id})">${icon('chevron')}</button>`;
  const supportName=p.support_name||p.city_support_name||'Support ORIENTAL24',supportPhone=p.support_phone||p.city_support_phone||'';
  const clientActions=S?.user?.role==='client'?`${p.invoice_status==='Réglée'?'<span class="client-paid-pill">Paid</span>':''}${clientSupportAction(p,'whatsapp',supportName,supportPhone)}${clientSupportAction(p,'call',supportName,supportPhone)}<button type="button" class="client-action-icon info" onclick="parcelDetail(${p.id})" title="Informations et chronologie" aria-label="Informations et chronologie">${icon('info')}</button>${clientRatingAction(p)}`:'';
  html=html.replace(old,`${clientActions}<button class="icon-btn parcel-expand-button" aria-label="Déplier ${esc(p.tracking)}" title="Déplier la commande" aria-expanded="false" onclick="toggleParcelRow(${p.id},this)">${icon('down')}</button>`)
 }
 return html
};
function closeParcelRow(id){const row=document.querySelector(`[data-parcel-expanded="${id}"]`);if(!row)return;const button=row.previousElementSibling?.querySelector('.parcel-expand-button');if(button)button.setAttribute('aria-expanded','false');row.previousElementSibling?.classList.remove('parcel-row-open');row.remove()}
async function toggleParcelRow(id,button){if(button.getAttribute('aria-expanded')==='true'){closeParcelRow(id);return}document.querySelectorAll('[data-parcel-expanded]').forEach(r=>closeParcelRow(Number(r.dataset.parcelExpanded)));const parent=button.closest('tr'),row=document.createElement('tr');row.className='parcel-expanded';row.dataset.parcelExpanded=id;row.innerHTML=`<td colspan="${parent.children.length}"><div class="parcel-inline-detail"><p class="sub">Chargement de la commande…</p></div></td>`;parent.after(row);parent.classList.add('parcel-row-open');button.setAttribute('aria-expanded','true');await reloadParcelRow(id)}
async function reloadParcelRow(id){const row=document.querySelector(`[data-parcel-expanded="${id}"]`);if(!row)return;try{const d=await loadParcelCommand(id);if(row.isConnected)row.querySelector('.parcel-inline-detail').innerHTML=parcelCommandBody(d,true)}catch(e){if(row.isConnected)row.querySelector('.parcel-inline-detail').innerHTML=`<p class="form-hint">${esc(e.message)}</p><button class="btn sm" onclick="closeParcelRow(${id})">Fermer</button>`}}
function supportTeamView(rows){supportContacts=rows;return heading('Contacts support','Les personnes joignables affichées sur vos commandes.',`<button class="btn primary" onclick="supportContactForm()">${icon('plus')}Ajouter un contact support</button>`)+`<div class="demo-notice">Enregistrez uniquement les coordonnées professionnelles autorisées à être partagées avec les clients et livreurs concernés. Un contact n’est pas un compte de connexion et ne reçoit aucun accès supplémentaire. Aucune personne ni aucun numéro n’est prérempli.</div><section class="card">${simpleTable(['Contact','Téléphone','État',''],rows.map(c=>[esc(c.name),parcelPhone(c.phone,'Appeler le support'),tag(c.active?'Actif':'Inactif'),`<button class="btn sm" onclick="supportContactForm(${c.id})">Modifier</button>`]))}</section><p class="form-hint">Affectation : ouvrir une commande → Affecter un support. Modifier un numéro ici actualise les fiches concernées à leur prochaine ouverture/actualisation. Désactiver empêche les nouvelles affectations, sans effacer l’historique.</p>`}
function supportContactForm(id){const c=supportContacts.find(c=>c.id===id)||{};modal(id?'Modifier le contact support':'Ajouter un contact support',form(`${input('name','Nom du contact',c.name||'','text',true,'maxlength="120"')}${input('phone','Téléphone professionnel',c.phone||'','tel',true,'maxlength="40" placeholder="06… ou +212…"')}${id?`<label class="full check-label"><input name="active" type="checkbox" ${c.active?'checked':''}>Contact actif</label>`:''}<p class="full form-hint">Le nom et le numéro seront visibles sur les colis auxquels ce contact est affecté.</p>`));bindForm(async d=>{await (id?api409(f=>api('/support-contacts/'+id,'PATCH',{...d,revision:f?f.revision:c.revision}),async()=>({revision:(await api('/support-contacts')).find(x=>x.id===id)?.revision ?? c.revision})):api('/support-contacts','POST',d));await saved('Contact support enregistré')})}
async function assignParcelSupport(id){try{const [d,contacts]=await Promise.all([api('/parcels/'+id),api('/support-contacts')]);const p=d.parcel;modal('Support de la commande',form(`${select('contact_id','Contact support',[['','Sans support affecté'],...contacts.filter(c=>c.active).map(c=>[c.id,c.name+' · '+c.phone])],p.support_contact_id||'',false)}<div class="full form-hint">${esc(p.tracking)}. Cette affectation ne change ni le livreur, ni le statut, ni les montants.${!contacts.some(c=>c.active)?' Ajoutez d’abord un contact dans Contacts support.':''}</div>`));bindForm(async v=>{await api409(f=>api('/parcels/'+id+'/support','PATCH',{contact_id:v.contact_id?Number(v.contact_id):null,revision:f?f.support_revision:p.support_revision}),async()=>{const x=await api('/parcels/'+id);return {support_revision:x.parcel.support_revision}});await parcelDetail(id);await reloadParcelRow(id);toast('Support de la commande mis à jour')})}catch(e){toast(e.message,true)}}
