/* Company-only edits: final eligibility is always enforced by the server. */
function companyOrderButtons(p){
 if(S?.user?.role!=='client'||S.user.client_type!=='societe_livraison')return '';
 const locked=p.company_order_editable!==true,why=esc(p.company_order_lock_reason||'Commande non modifiable.');
 const trash='<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7"/></svg>';
 return `<button class="icon-btn company-order-edit" ${locked?'disabled':''} title="${locked?why:'Modifier la commande'}" aria-label="Modifier la commande" onclick="editCompanyOrder(${p.id})">${icon('edit')}</button><button class="icon-btn company-order-delete" ${locked?'disabled':''} title="${locked?why:'Supprimer la commande'}" aria-label="Supprimer la commande" onclick="deleteCompanyOrder(${p.id})">${trash}</button>`;
}
async function editCompanyOrder(id){
 const owner=S?.user?.id;
 try{
  const r=await api('/parcels/'+id);if(S?.user?.id!==owner)return;const p=r.parcel;
  if(!p.company_order_editable)throw Error(p.company_order_lock_reason||'Commande non modifiable.');
  const cities=S.cities.filter(c=>c.delivery||c.id===p.city_id);
  modal('Modifier la commande '+p.tracking,form(`${input('tracking','Tracking société',p.tracking,'text',true,'maxlength="80"')}${input('recipient','Nom du destinataire',p.recipient)}${input('phone','Téléphone',p.phone,'tel')}${select('city_id','Ville de livraison',cities.map(c=>[c.id,c.name]),p.city_id)}${input('amount','Montant à collecter (MAD)',p.amount,'number',true,'min="0" max="1000000" step="0.01"')}${input('product','Nature du produit',p.product,'text',false)}${textarea('address','Adresse complète',p.address,true)}${textarea('note','Note de livraison',p.note)}<label class="full pp-consent"><input type="checkbox" name="not_allowed_to_open" ${p.open_allowed===0?'checked':''}> Ne pas autoriser à ouvrir le colis</label><label class="full pp-consent"><input type="checkbox" name="is_exchange" ${p.is_exchange?'checked':''}> Commande avec échange</label><p class="full form-hint">La palette brouillon sera mise à jour. Un changement de ville recalcule les frais selon votre tarif. Après validation de l’envoi, aucune modification n’est autorisée.</p>`,'Enregistrer les modifications'),true);
  bindForm(async d=>{if(S?.user?.id!==owner)return;await api('/parcels/'+id+'/company-edit','PATCH',{...d,city_id:Number(d.city_id),revision:p.ops_revision});await saved('Commande et brouillon mis à jour')});
 }catch(e){toast(e.message,true)}
}
async function deleteCompanyOrder(id){
 const owner=S?.user?.id;
 try{
  const r=await api('/parcels/'+id);if(S?.user?.id!==owner)return;const p=r.parcel;
  if(!p.company_order_editable)throw Error(p.company_order_lock_reason||'Suppression interdite.');
  modal('Supprimer la commande',form(`<p class="full form-hint"><b>${esc(p.tracking)} · ${esc(p.recipient)}</b><br>La commande sera retirée de votre liste et de la palette brouillon. Si c’est la dernière commande, le brouillon vide sera également supprimé. Une trace technique est conservée.</p><label class="full pp-consent"><input type="checkbox" name="confirmed" required> Je confirme la suppression de cette commande non envoyée.</label>`,'Supprimer la commande'));
  bindForm(async d=>{if(S?.user?.id!==owner)return;await api('/parcels/'+id+'/company-edit','DELETE',{revision:p.ops_revision,confirmed:d.confirmed});await saved('Commande supprimée avant envoi')});
 }catch(e){toast(e.message,true)}
}
