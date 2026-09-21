/* Row-level Facture shortcut: existing immutable driver settlement, never a second billing system. */
paths.dollar='M12 2v20 M17 6H9a4 4 0 0 0 0 8h6a3 3 0 0 1 0 6H6';
async function driverInvoice(id,anchor){
 if(S?.user?.role!=='admin'){toast('Génération réservée à Admin.',true);return}
 const owner=S.user.id;modal('Facture','<p class="sub">Vérification du livreur et des colis à facturer…</p>');const node=$('#modal-root .modal');node.classList.add('driver-invoice-modal');modalCleanup=()=>{if(anchor?.isConnected)anchor.focus({preventScroll:true})};const current=()=>node.isConnected&&S?.user?.id===owner&&S.user.role==='admin';
 try{
  const {driver:d}=await api('/drivers-workspace/'+id);if(!current())return;
  node.querySelector('.modal-body').innerHTML=`<p class="driver-invoice-question">Êtes-vous sûr de vouloir générer la facture de ce livreur ?</p><div class="driver-invoice-person"><strong>${esc(d.name)}</strong><span>${esc(d.email)}</span>${!d.active?'<small>Compte inactif · règlement de l’historique uniquement</small>':''}</div><div id="driver-invoice-preview"><p class="sub">Vérification des montants…</p></div><div class="form-error" id="driver-invoice-error" role="alert"></div><div class="driver-invoice-foot"><button class="btn" type="button" onclick="closeModal()">Annuler</button><button class="btn primary" type="button" id="driver-invoice-accept" disabled>Accepter</button></div>`;
  const accept=node.querySelector('#driver-invoice-accept'),err=node.querySelector('#driver-invoice-error'),box=node.querySelector('#driver-invoice-preview');
  let draft,issued=null,busy=false;
  try{draft=await api('/driver-finance/preview','POST',{driver_id:id});if(!current())return;box.innerHTML=`<p class="driver-invoice-period"><b>${draft.parcel_count} colis</b> clôturés non rapprochés · toutes périodes.<br>Livré, Refusé et Retourné selon le barème enregistré.</p><div class="driver-invoice-totals"><span>COD livré<b>${centMoney(draft.cod_cents)} MAD</b></span><span>Commissions<b>${centMoney(draft.commission_cents)} MAD</b></span><span>À remettre à ORIENTAL24<b>${centMoney(draft.cash_due_cents)} MAD</b></span><span>Commission à payer<b>${centMoney(draft.commission_due_cents)} MAD</b></span></div><p class="sub">${draft.mode==='net'?'Remise nette':'Remise intégrale'} · retenue ${centMoney(draft.retained_cents)} MAD · barème v${draft.revision}</p><details class="driver-invoice-lines"><summary>Voir les ${draft.parcel_count} colis concernés</summary>${financeLinesTable(draft.lines)}</details><p class="driver-invoice-note">« Facture » correspond au relevé interne du livreur, hors facture fiscale. Accepter fige les montants et verrouille ces colis ; aucun paiement n’est enregistré. Aperçu valable 30 minutes.${opsOffline?' Simulation locale uniquement.':''}</p>`;accept.disabled=false}
  catch(e){if(!current())return;box.innerHTML=`<p class="form-hint" role="alert">${esc(e.message)}</p>${/barème/i.test(e.message)?`<button type="button" class="btn sm" onclick="editDriverTerms(${id})">${icon('settings')}Configurer le barème</button>`:''}<p class="driver-invoice-note">Aucune facture créée. Fermez et réessayez après correction. Aucun tarif n’est ajouté automatiquement.</p>`;return}
  accept.onclick=async()=>{
   if(busy||!current())return;busy=true;accept.disabled=true;accept.textContent=issued?'Ouverture…':'Génération…';err.style.display='none';
   try{
    if(!issued){const result=await api('/driver-finance/preview/'+draft.token+'/confirm','POST',{});issued=result.statement_id}
    if(S?.user?.id!==owner)return;
    if(!current()){toast('Relevé créé. Retrouvez-le dans Caisse & commissions livreurs.');return}
    const detail=await api('/driver-finance/statements/'+issued);if(!current())return;
    closeModal();financeDetail=detail;financeDetailTab='parcels';financeTab='statements';renderDriverStatement();toast('Facture livreur générée · '+detail.statement.reference);
    try{await refresh();if(S?.user?.id===owner)await renderView()}catch{if(S?.user?.id===owner)toast('Relevé créé ; actualisez la liste des colis.',true)}
   }catch(e){if(current()){err.textContent=issued?'Relevé déjà créé. Réessayez pour l’ouvrir, sans nouvelle émission.':e.message;err.style.display='block';err.scrollIntoView({block:'nearest'})}}
   finally{busy=false;accept.disabled=false;accept.textContent=issued?'Ouvrir le relevé':'Accepter'}
  };
 }catch(e){if(current())node.querySelector('.modal-body').innerHTML=`<p class="form-hint" role="alert">${esc(e.message)}</p><button class="btn" onclick="closeModal()">Fermer</button>`}
}
