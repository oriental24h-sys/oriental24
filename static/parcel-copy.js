/* Explicit clipboard write only. Always read the authorized current parcel; never copy the user directory. */
paths.copy='M9 8h12v13H9z M5 16H3V3h12v2';
const parcelCopyPending=new Set();
function parcelCopyButton(p){return `<button type="button" class="icon-btn parcel-copy-button" title="Copier les informations de la commande" aria-label="Copier les informations de ${esc(p.tracking)}" onclick="event.stopPropagation();copyParcelInformation(${p.id},this)">${icon('copy')}</button>`}
function parcelInformationText(p){
 const value=v=>String(v??'').trim()||'Non renseigné';
 return ['ORIENTAL24 — Commande',`Référence : ${value(p.tracking)}`,`Destinataire : ${value(p.recipient)}`,`Téléphone : ${value(p.phone)}`,`Adresse : ${value(p.address)}`,`Ville : ${value(p.city)}`,`Produit : ${value(p.product)}`,`Montant COD : ${money(p.amount)} MAD`,`État : ${value(p.status)}`].join('\n');
}
async function copyParcelInformation(id,button){
 if(parcelCopyPending.has(id)||!S?.user)return;const owner=S.user.id;parcelCopyPending.add(id);if(button){button.disabled=true;button.setAttribute('aria-busy','true')}
 try{
  const d=await loadParcelCommand(id);if(S?.user?.id!==owner)return;const text=parcelInformationText(d.parcel);
  try{if(!navigator.clipboard?.writeText)throw Error('Clipboard unavailable');await navigator.clipboard.writeText(text);if(S?.user?.id===owner)toast('Informations de la commande copiées')}
  catch{if(S?.user?.id===owner)showParcelCopyFallback(d.parcel,text,owner)}
 }catch(e){if(S?.user?.id===owner)toast(e.message,true)}
 finally{parcelCopyPending.delete(id);if(button){button.disabled=false;button.removeAttribute('aria-busy')}}
}
function showParcelCopyFallback(p,text,owner){
 // Set the value, not HTML: names/products containing markup must remain plain text.
 modal('Copier la commande',`<p class="form-hint">${esc(p.tracking)} · Le navigateur n’a pas autorisé la copie automatique. Le texte est prêt : utilisez le bouton ci-dessous, Ctrl+C / ⌘C, ou la sélection de texte sur téléphone.</p><label class="parcel-copy-label" for="parcel-copy-text">Informations à copier</label><textarea id="parcel-copy-text" class="parcel-copy-text" readonly spellcheck="false"></textarea><p id="parcel-copy-feedback" class="form-hint" role="status" aria-live="polite">Aucune copie confirmée pour le moment.</p><div class="form-actions"><button type="button" class="btn" id="parcel-copy-select">Tout sélectionner</button><button type="button" class="btn primary" id="parcel-copy-retry">${icon('copy')}Copier le texte</button></div>`);
 const field=document.getElementById('parcel-copy-text'),feedback=document.getElementById('parcel-copy-feedback'),retry=document.getElementById('parcel-copy-retry');field.value=text;
 const selectText=()=>{field.focus({preventScroll:true});field.select();field.setSelectionRange(0,field.value.length)};
 document.getElementById('parcel-copy-select').onclick=selectText;
 retry.onclick=async()=>{
  if(S?.user?.id!==owner){feedback.textContent='Session modifiée. Rouvrez la commande dans votre espace.';return}
  retry.disabled=true;let copied=false;
  try{
   // Legacy copy is attempted in this explicit click, preserving browser user activation.
   selectText();try{copied=!!document.execCommand?.('copy')}catch{}
   if(!copied&&navigator.clipboard?.writeText){await navigator.clipboard.writeText(field.value);copied=true}
  }catch{}finally{retry.disabled=false}
  if(S?.user?.id!==owner)return;
  if(copied){feedback.textContent='Texte copié.';toast('Informations de la commande copiées')}
  else{selectText();feedback.textContent='Copie automatique bloquée. Utilisez Ctrl+C / ⌘C ou le menu Copier de votre téléphone.'}
 };
 selectText();
}
