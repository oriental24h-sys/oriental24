/* Delivery-city correction: Admin only. The API enforces the same rule, scope and locks. */
function parcelCityLocked(p){return !!(p.invoice_id||p.financial_locked||p.operations_locked||['Livré','Retourné','Refusé'].includes(p.status))}
function parcelCityButton(p,label=false){
 if(S?.user?.role!=='admin')return '';
 const locked=parcelCityLocked(p);
 return `<button type="button" class="${label?'btn sm':'icon-btn'} parcel-city-button" aria-label="Modifier la ville de ${esc(p.tracking)}" title="${locked?'Ville non modifiable : colis clôturé ou verrouillé':'Modifier la ville'}" ${locked?'disabled':''} onclick="event.stopPropagation();openParcelCity(${p.id},this)">${icon('edit')}${label?'Modifier la ville':''}</button>`;
}
async function openParcelCity(id,anchor){
 if(S?.user?.role!=='admin'){toast('Modification de la ville réservée à Admin.',true);return}
 closeParcelReason(false);
 const owner=S.user.id,originalView=view,expanded=!!document.querySelector(`[data-parcel-expanded="${id}"]`);
 modal('Modifier la ville','<p class="sub city-drawer-loading">Chargement de la commande…</p>');
 const node=document.querySelector('#modal-root .modal');node.classList.add('city-drawer');node.parentElement.classList.add('city-drawer-backdrop');
 modalCleanup=()=>{if(anchor?.isConnected)anchor.focus({preventScroll:true})};
 const current=()=>node.isConnected&&S?.user?.id===owner&&S.user.role==='admin';
 try{
  const [d,coverage]=await Promise.all([loadParcelCommand(id),api('/public')]);if(!current())return;
  const p=d.parcel,locked=parcelCityLocked(p),cities=coverage.cities.filter(c=>c.delivery),missing=!cities.some(c=>c.id===p.city_id),options=[...(missing?[[p.city_id,(p.city||'Ville actuelle')+' · livraison fermée']]:[]),...cities.map(c=>[c.id,c.name])];
  let tariffRows=[];try{tariffRows=(await api('/clients/'+p.client_id+'/tariffs')).cities||[]}catch{}
  if(!current())return;
  const feeForCity=cityId=>{const row=tariffRows.find(x=>Number(x.city_id)===Number(cityId)),base=coverage.cities.find(x=>Number(x.id)===Number(cityId));return{fee:row?.fee??row?.default_fee??base?.fee??p.fee,return_fee:row?.return_fee??row?.default_return_fee??base?.return_fee??p.return_fee}};
  const initialFees=feeForCity(p.city_id);
  node.querySelector('.modal-body').innerHTML=`<form id="city-edit-form"><div class="city-drawer-content"><div class="city-drawer-reference"><span>${icon('box')}<strong>${esc(p.tracking)}</strong></span><button type="button" class="btn sm" id="city-edit-reload">${icon('refresh')}Actualiser</button></div><p class="city-drawer-recipient">${esc(p.recipient)}</p><div class="city-drawer-address">${icon('pin')}<span>${esc(p.address)}<br><strong>${esc(p.city)}</strong></span></div>${select('city_id','Ville',options,p.city_id)}<div class="form-error" role="alert"></div>${locked?'<p class="form-hint orange">Cette commande est clôturée, facturée, rapprochée ou liée à un document actif. Sa ville ne peut pas être modifiée.</p>':!cities.length?'<p class="form-hint orange">Aucune ville ouverte à la livraison. Configurez les villes dans Paramètres.</p>':''}<p class="city-edit-help">La ville change et les frais de livraison et de retour sont recalculés selon le barème actif du client pour cette destination. L’adresse, le livreur, le statut et le montant COD restent inchangés. Vérifiez que l’adresse correspond à la ville choisie.</p><div class="city-preserved-fees"><span>Montant COD · conservé <b>${money(p.amount)} MAD</b></span><span>Frais de livraison · barème sélectionné <b id="city-fee-preview">${money(initialFees.fee)} MAD</b></span><span>Frais de retour · barème sélectionné <b id="city-return-fee-preview">${money(initialFees.return_fee)} MAD</b></span></div><p class="city-edit-help">${opsOffline?'Simulation locale · aucune synchronisation avec le serveur.':'Après confirmation, la fiche affichera les deux frais recalculés et le changement sera ajouté à la chronologie.'}</p></div><div class="form-actions city-drawer-footer"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button type="submit" class="btn primary" id="city-edit-save">${icon('check')}Enregistrer</button></div></form>`;
  const formEl=node.querySelector('form'),choice=formEl.querySelector('select'),save=formEl.querySelector('[type=submit]'),reload=node.querySelector('#city-edit-reload'),error=formEl.querySelector('.form-error');let busy=false;
  if(missing)choice.querySelector('option').disabled=true;
  choice.disabled=locked||!cities.length;
  const sync=()=>{save.disabled=busy||locked||!cities.length||!choice.value||Number(choice.value)===p.city_id};
  const previewFees=()=>{const fees=feeForCity(choice.value);node.querySelector('#city-fee-preview').textContent=money(fees.fee)+' MAD';node.querySelector('#city-return-fee-preview').textContent=money(fees.return_fee)+' MAD'};
  choice.onchange=()=>{sync();previewFees()};sync();previewFees();
  reload.onclick=()=>{if(!busy)openParcelCity(id,anchor)};
  formEl.onsubmit=async e=>{
   e.preventDefault();if(busy||save.disabled||!current())return;busy=true;sync();choice.disabled=true;reload.disabled=true;error.style.display='none';let committed=false;
   try{
    const result=await api409(f=>api('/parcels/'+id+'/city','PATCH',{city_id:Number(choice.value),revision:f?f.ops_revision:(p.ops_revision||0)}),async()=>({ops_revision:(await api('/parcels/'+id)).parcel.ops_revision}));
    committed=true;if(S?.user?.id!==owner)return;if(node.isConnected)closeModal();await refresh();if(S?.user?.id!==owner)return;await renderView();
    if(expanded&&view===originalView){const trigger=document.querySelector(`.parcel-expand-button[onclick="toggleParcelRow(${id},this)"]`);if(trigger)await toggleParcelRow(id,trigger)}
    toast(result.changed?`Ville mise à jour · livraison ${money(result.fee)} MAD · retour ${money(result.return_fee)} MAD`:'Ville inchangée');
   }catch(err){if(committed&&S?.user?.id===owner){toast('Ville enregistrée, mais la liste n’a pas pu être actualisée. Rechargez la page.',true)}else if(current()){error.textContent=err.message;error.style.display='block'}}
   finally{busy=false;choice.disabled=locked||!cities.length;reload.disabled=false;sync()}
  };
  (choice.disabled?node.querySelector('.modal-header button'):choice).focus({preventScroll:true});
 }catch(e){if(current())node.querySelector('.modal-body').innerHTML=`<div class="city-drawer-content"><p class="form-hint" role="alert">${esc(e.message)}</p><button class="btn" onclick="closeModal()">Fermer</button></div>`}
}
