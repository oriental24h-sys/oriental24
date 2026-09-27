/* Claims use the existing ticket scope: Admin or the parcel's current owner/driver. */
paths.claim='M12 8v5 M12 16h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0';
const claimCategories=['Livraison','Ramassage','Facturation','Retour','Autre'];
function parcelClaimButton(p,label=false){return `<button type="button" class="${label?'btn sm':'icon-btn'} parcel-claim-button" title="Créer une réclamation" aria-label="Créer une réclamation pour ${esc(p.tracking)}" onclick="event.stopPropagation();openParcelClaim(${p.id},this)">${icon('claim')}${label?'Réclamation':''}</button>`}
function claimAttachmentsMarkup(files){return files.length?`<section class="claim-attached"><h3>Pièces jointes <span class="tag">${files.length}</span></h3>${files.map(f=>`<button class="btn sm" onclick="claimDownload(${f.id})">${icon('download')}<span>${esc(f.name)}</span><small>${Math.ceil(f.size/1024)} Ko</small></button>`).join('')}<p class="sub">Téléchargements privés · aucun contrôle antivirus garanti.</p></section>`:''}
async function claimDownload(id){
 const owner=S?.user?.id;try{let blob,name;
  if(opsOffline){const f=await api('/claim-attachments/'+id);blob=new Blob([Uint8Array.from(atob(f.content),c=>c.charCodeAt(0))],{type:f.mime});name=f.name}
  else{const r=await fetch('/api/claim-attachments/'+id,{credentials:'same-origin'});if(!r.ok)throw Error('Pièce jointe inaccessible. Vérifiez votre connexion et vos droits.');blob=await r.blob();const header=r.headers.get('Content-Disposition')||'';name=header.match(/filename="?([^";]+)"?/)?.[1]||'piece-jointe'}
  if(S?.user?.id!==owner)return;const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);
 }catch(e){if(S?.user?.id===owner)toast(e.message,true)}
}
function claimReadFile(file){return new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve({name:file.name,content:String(r.result).split(',')[1]});r.onerror=()=>reject(Error('Lecture du fichier impossible.'));r.readAsDataURL(file)})}
async function openParcelClaim(id,anchor){
 if(!S?.user)return;clearTimeout(window.toastTimer);$('#toast-root').innerHTML='';closeParcelReason(false);const owner=S.user.id;modal('Créer une réclamation','<p class="sub">Chargement de la commande…</p>');const node=$('#modal-root .modal');node.classList.add('parcel-claim-modal');node.parentElement.classList.add('claim-backdrop');modalCleanup=()=>{if(anchor?.isConnected)anchor.focus({preventScroll:true})};const current=()=>node.isConnected&&S?.user?.id===owner;
 try{
  const {parcel:p}=await loadParcelCommand(id);if(!current())return;
  node.querySelector('.modal-body').innerHTML=`<form id="parcel-claim-form"><div class="claim-form-content"><p class="claim-intro">Signalez un problème sur cette commande. Elle sera liée automatiquement à votre réclamation.</p>${input('subject','Sujet','','text',true,'maxlength="180"')}${select('category','Catégorie',claimCategories.map(v=>[v,v]),'Autre')}<div class="field"><label for="claim-package">Colis / Package</label><input id="claim-package" value="${esc(p.tracking)}" readonly><span class="sub">${esc(p.recipient)} · ${esc(p.city)}</span></div>${textarea('body','Description','',true)}<div class="claim-upload-heading">Pièces jointes <span class="sub">Facultatif</span></div><label class="claim-upload" for="claim-files">${icon('upload')}<strong>Ajouter des pièces jointes</strong><span>PDF, JPG ou PNG</span><input id="claim-files" type="file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png" multiple></label><p class="claim-limits">3 fichiers maximum · 1 Mo au total · images jusqu’à 8 mégapixels.<br>Accès réservé à l’auteur et à l’administration. Ne joignez pas de données sensibles inutiles.</p><div id="claim-file-list" aria-live="polite"></div>${opsOffline?'<p class="form-hint orange">Simulation locale : aucun envoi au support. Les fichiers restent dans ce navigateur si son stockage est disponible.</p>':''}<div class="form-error" role="alert"></div></div><div class="form-actions claim-form-footer"><button type="button" class="btn" onclick="closeModal()">Annuler</button><button type="submit" class="btn primary" id="claim-create">${icon('plus')}Créer la réclamation</button></div></form>`;
  const formEl=node.querySelector('form'),fileInput=node.querySelector('#claim-files'),list=node.querySelector('#claim-file-list'),error=node.querySelector('.form-error'),submit=node.querySelector('[type=submit]');formEl.querySelector('textarea').maxLength=3000;
  let files=[],busy=false,lastPayload='',key=financeKey();
  const showError=msg=>{error.textContent=msg;error.style.display='block';error.scrollIntoView({block:'nearest'})};
  const renderFiles=()=>{list.innerHTML=files.map((f,i)=>`<div class="claim-file"><span>${esc(f.name)} <small>${Math.ceil(f.size/1024)} Ko</small></span><button type="button" class="icon-btn" aria-label="Retirer ${esc(f.name)}" data-remove="${i}">${icon('close')}</button></div>`).join('');list.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{if(!busy){files.splice(Number(b.dataset.remove),1);renderFiles()}})};
  fileInput.onchange=()=>{if(busy)return;const next=[...files,...fileInput.files];fileInput.value='';error.style.display='none';if(next.length>3||next.reduce((a,f)=>a+f.size,0)>1048576){showError('Trois fichiers maximum et 1 Mo au total.');return}if(next.some(f=>!f.size||! /\.(pdf|jpe?g|png)$/i.test(f.name)||f.name.length>180)){showError('Choisissez des fichiers PDF, JPG ou PNG non vides (nom de 180 caractères maximum).');return}files=next;renderFiles()};
  formEl.onsubmit=async e=>{
   e.preventDefault();if(busy||!current())return;error.style.display='none';const subject=formEl.elements.subject.value.trim(),body=formEl.elements.body.value.trim(),category=formEl.elements.category.value;if(!subject||!body){showError('Sujet et description obligatoires.');return}
   busy=true;submit.disabled=true;fileInput.disabled=true;let created=false;
   try{
    const attachments=await Promise.all(files.map(claimReadFile));if(!current())return;const payload={subject,body,category,priority:'Normale',attachments};const serialized=JSON.stringify(payload);if(lastPayload&&lastPayload!==serialized)key=financeKey();lastPayload=serialized;
    const result=await api('/logistics/parcels/'+id+'/tickets','POST',{...payload,request_key:key});created=true;if(S?.user?.id!==owner)return;
    if(current()){closeModal();await ticketDetail(result.id)}
    if(S?.user?.id!==owner)return;toast(opsOffline?'Réclamation créée localement · aucun envoi au support':'Réclamation créée · TKT-'+result.id);
    if(opsOffline&&!localPersistence)toast('Réclamation en mémoire seulement : stockage local indisponible ou saturé.',true);
   }catch(e){if(current())showError(e.message);else if(S?.user?.id===owner)toast(created?'Réclamation enregistrée. Consultez Réclamations.':e.message,true)}
   finally{busy=false;submit.disabled=false;fileInput.disabled=false}
  };
  if(innerWidth>760)formEl.elements.subject.focus({preventScroll:true});
 }catch(e){if(current())node.querySelector('.modal-body').innerHTML=`<p class="form-hint" role="alert">${esc(e.message)}</p><button class="btn" onclick="closeModal()">Fermer</button>`}
}
