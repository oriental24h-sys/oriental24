/* No credentials in localStorage, bootstrap, account lists or logs. */
function adminPasswordControl(id){
 return id?`<div class="full form-hint"><button type="button" class="btn" onclick="adminResetPassword(${Number(id)})">Réinitialiser le mot de passe</button><p>Le mot de passe actuel n’est jamais affiché.</p></div>`:'<div class="full form-hint">Un mot de passe provisoire sécurisé sera généré après la création et affiché une seule fois, avec un bouton Copier.</div>';
}
function showTemporaryPassword(result){
 if(S?.user?.role!=='admin')return;
 let secret=result.temporary_password;result.temporary_password='';
 if(!secret)return;
 const owner=S.user.id;
 modal('Identifiants provisoires · affichage unique',`<p class="form-hint orange">Copiez ces identifiants maintenant et transmettez-les au titulaire par un canal sûr. Après fermeture, ils ne pourront plus être affichés. Demandez au titulaire de changer son mot de passe dans son profil.</p><div class="field"><label>E-mail</label><input id="temporary-email" readonly data-no-translate></div><div class="field"><label>Mot de passe provisoire</label><input id="temporary-password" readonly autocomplete="off" data-no-translate></div><p class="sub">Cet affichage se ferme après 5 minutes. Cela n’expire pas le mot de passe.</p><div class="form-actions"><button type="button" class="btn primary" id="temporary-copy">Copier le mot de passe</button><button type="button" class="btn" id="temporary-close">Fermer</button></div>`);
 const node=document.querySelector('#modal-root .modal'),field=node.querySelector('#temporary-password');
 node.querySelector('#temporary-email').value=result.email||'';field.value=secret;
 const clear=()=>{secret='';field.value='';node.querySelector('#temporary-email').value=''};
 const timer=setTimeout(()=>{if(node.isConnected&&S?.user?.id===owner)closeModal();else clear()},300000);
 modalCleanup=()=>{clearTimeout(timer);clear()};
 node.querySelector('#temporary-copy').onclick=async()=>{if(!node.isConnected||S?.user?.id!==owner)return;try{await navigator.clipboard.writeText(secret);if(node.isConnected)toast('Mot de passe copié.')}catch(e){field.focus();field.select();toast('Copiez le texte sélectionné avec Ctrl/Cmd+C.')}};
 node.querySelector('#temporary-close').onclick=()=>closeModal();
 refresh().then(()=>{if(S?.user?.id===owner)return renderView()}).catch(()=>{if(node.isConnected)toast('Compte enregistré. Actualisez la liste après avoir copié les identifiants.')});
}
function adminResetPassword(id){
 if(S?.user?.role!=='admin')return;
 const account=(S.users||[]).find(u=>Number(u.id)===Number(id));if(!account||account.role==='admin')return;
 const owner=S.user.id;
 modal('Réinitialiser le mot de passe',form(`<p class="full form-hint">Compte : <b>${esc(account.email)}</b>. Le mot de passe actuel sera remplacé et toutes les anciennes sessions seront fermées. Le compte ne sera pas activé automatiquement.</p>${input('current_password','Votre mot de passe Admin','','password',true,'autocomplete="current-password" maxlength="128"')}<label class="full pp-consent"><input type="checkbox" name="confirmed" required> Je confirme la réinitialisation.</label>`,'Générer un nouveau mot de passe'));
 const node=document.querySelector('#modal-root .modal');
 modalCleanup=()=>{const field=node.querySelector('[name=current_password]');if(field)field.value=''};
 bindForm(async d=>{const r=await api('/users/'+id+'/reset-password','POST',d);if(node.isConnected&&S?.user?.id===owner)showTemporaryPassword(r);else r.temporary_password=''});
}
