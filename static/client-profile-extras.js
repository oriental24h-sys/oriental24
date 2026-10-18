/* Complement existing profile fields; never duplicate name, phone, company or RIB. */
let clientProfileExtraData=null;
function clientProfileExtrasView(d,g){
 clientProfileExtraData=d;
 const languages=[['fr','Français'],['en','English'],['ar','العربية']];
 const card=(title,body)=>`<section class="card profile-extra-card"><div class="card-head"><h3>${title}</h3></div><div class="profile-extra-body">${body}</div></section>`;
 const prefs=[['payment','Paiement enregistré'],...d.statuses.map(s=>['status:'+s,s])];
 const contactLabels={public_phone:'Téléphone',public_whatsapp:'WhatsApp',public_email:'E-mail',public_address:'Adresse',public_hours:'Horaires'};
 const contacts=Object.entries(d.contacts).filter(([k,v])=>v&&contactLabels[k]);
 return `<div class="client-profile-extras"><form id="client-profile-extras-form"><div class="form-error"></div>`+
 card('Paramètres de langue',`<p class="sub">La langue est enregistrée pour votre compte et réutilisée à la prochaine connexion.</p>${select('language','Langue de l’interface',languages,d.language||window.o24CurrentLanguage?.()||'fr')}`)+
 card('Identification & adresse',`<p class="sub">Le nom, le téléphone, l’entreprise et les coordonnées bancaires figurent déjà dans votre profil ci-dessus.</p><div class="form-grid">${input('legal_id','ICE / identifiant légal du dossier',d.legal_id,'text',false,'maxlength="100"')}${input('cin','CIN',d.cin,'text',false,'maxlength="30" autocomplete="off"')}${input('city','Ville',d.city,'text',false,'maxlength="120"')}${input('website','Site web',d.website,'url',false,'maxlength="300" placeholder="https://"')}${textarea('address','Adresse / adresse de facturation',d.address,false)}</div><p class="form-hint">L’adresse et l’identifiant légal réutilisent votre dossier administratif existant. Une modification remet ce dossier en brouillon pour une nouvelle vérification.</p>`)+
 card('Préférences de notification',`<p class="sub">Notifications internes ORIENTAL24 uniquement. Ces choix n’activent pas de SMS, WhatsApp ou e-mail et ne masquent pas les alertes de sécurité.</p><div class="profile-notification-grid">${prefs.map(([key,label],i)=>`<label class="profile-notification-option"><span>${esc(label)}</span><input type="checkbox" data-preference="${esc(key)}" ${d.preferences[key]?'checked':''} aria-label="Notification : ${esc(label)}"></label>`).join('')}</div>`)+
 `<div class="form-actions"><button type="submit" class="btn primary">${icon('check')}Enregistrer ces paramètres</button></div></form>`+
 card('Solde de facturation',`<p class="sub">Montants réels des factures du compte · tout l’historique. Les règlements partiels sont déduits du solde.</p>${simpleTable(['Libellé','Montant'],[['Total COD facturé',money(d.billing.cod)+' MAD'],['Frais facturés',money(d.billing.fees)+' MAD'],['Net facturé',money(d.billing.net)+' MAD'],['Règlements enregistrés vers vous',money(d.billing.paid)+' MAD'],['Reste à vous verser',money(d.billing.remaining)+' MAD'],['Reste dû par vous',money(d.billing.owed)+' MAD']])}<button type="button" class="btn primary" onclick="navigate('invoices')">Aller à la facturation</button>`)+
 card('Compte Google',`<p>${g.linked?'Compte associé : <b data-no-translate>'+esc(g.email)+'</b>':'Aucun compte Google associé.'}</p><p class="sub">Associez Google pour lire vos feuilles et vous connecter au compte ORIENTAL24 existant. Votre mot de passe reste utilisable. Aucun compte n’est créé automatiquement.</p>${!g.configured?'<p class="form-hint orange">Configuration Google requise sur le serveur. La connexion et l’import ne sont pas encore activés.</p>':''}<div class="pp-actions"><button type="button" class="btn" onclick="clientGoogleLink()" ${g.configured?'':'disabled'}>${g.linked?'Renouveler l’autorisation Google':'Associer mon compte Google'}</button>${g.linked?'<button type="button" class="btn danger" onclick="clientGoogleUnlink()">Dissocier Google</button>':''}</div>`)+
 card('Intégration Google Sheets',`<p class="sub">Saisissez l’ID ou l’URL de votre Google Sheet et le nom exact de l’onglet. La feuille doit être accessible en lecture au compte Google associé${g.linked?' : <b data-no-translate>'+esc(g.email)+'</b>':''}. N’ouvrez pas votre feuille au public.</p><p class="sub">500 commandes maximum · utilisez les en-têtes du modèle ORIENTAL24 et le format texte pour les téléphones et trackings. Une prévisualisation est obligatoire avant création des commandes.</p><a class="btn sm" href="/api/imports/template.xlsx">${icon('download')}Modèle Excel / en-têtes</a><form id="client-sheet-form"><div class="form-error"></div><div class="form-grid">${input('sheet_id','ID ou URL Google Sheet','','text',true,'maxlength="400"')}${input('sheet_name','Nom de la feuille','','text',true,'maxlength="100" placeholder="Feuille 1"')}</div><div class="form-actions"><button type="submit" class="btn primary" ${g.configured&&g.linked?'':'disabled'}>${icon('upload')}Prévisualiser depuis Google Sheets</button></div></form>`)+
 card('Nous contacter',contacts.length?simpleTable(['Contact','Coordonnées'],contacts.map(([k,v])=>[contactLabels[k],esc(v)])):'<p class="sub">Les coordonnées publiques n’ont pas encore été renseignées par l’administration.</p>')+'</div>';
}
function bindClientProfileExtras(){
 const d=clientProfileExtraData,owner=S.user.id;
 bindForm(async values=>{
  if(S?.user?.id!==owner)return;
  const preferences={};document.querySelectorAll('#client-profile-extras-form [data-preference]').forEach(x=>preferences[x.dataset.preference]=x.checked);
  const fields=Object.fromEntries(['city','cin','website','language','address','legal_id'].map(k=>[k,values[k]]));
  const r=await api('/client-profile','PATCH',{...fields,preferences,revision:d.revision,dossier_revision:d.dossier_revision});
  if(S?.user?.id!==owner)return;
  if(r.language)window.setO24Language(r.language);
  await refresh();await renderView();toast('Paramètres du profil enregistrés');
 },'client-profile-extras-form');
 bindForm(async values=>{
  const r=await api('/google/sheets/preview','POST',values);
  if(S?.user?.id!==owner)return;
  await openImportPreview(r.id);
 },'client-sheet-form');
}
function clientGoogleLink(){
 modal('Associer votre compte Google',form(`${input('current_password','Mot de passe ORIENTAL24 actuel','','password',true,'autocomplete="current-password" maxlength="128"')}<p class="form-hint full">Google demandera votre consentement. ORIENTAL24 lit les feuilles autorisées sans les modifier.</p>`,'Continuer vers Google'));
 bindForm(async d=>{const r=await api('/google/link','POST',d);location.assign(r.url)});
}
function clientGoogleUnlink(){
 modal('Dissocier Google',form('<p class="form-hint full">La connexion Google et les imports seront désactivés pour ce compte. Votre accès par mot de passe reste disponible. Vous pouvez également retirer l’autorisation ORIENTAL24 depuis les paramètres de sécurité de votre compte Google.</p>','Dissocier Google'));
 bindForm(async()=>{await api('/google/link','DELETE',{});closeModal();await renderView();toast('Compte Google dissocié')});
}
