/* Separate Hub commission ledger; never expose client billing/vendor payments to a manager. */
let hubBillTab='mine',hubBillOwner=null,hubBillData=null;
async function hubBillSelect(tab){hubBillTab=tab;await renderView()}
async function hubBillingWorkspace(embedded=false){
 const identity=S.user.id+':'+S.user.role,admin=S.user.role==='admin';
 if(hubBillOwner!==identity){hubBillOwner=identity;hubBillTab='mine'}
 const tabs=admin?[['mine',embedded?'Factures émises':'Factures des Hubs'],['terms','Barèmes des Hubs'],['schedule','Génération automatique'],['legacy','Ancien registre COD']]:[['mine','Mes factures'],['drivers','Factures livreurs']];
 if(!tabs.some(t=>t[0]===hubBillTab))hubBillTab='mine';
 const navigation=`<section class="card"><div class="billing-tabs">${tabs.map(([k,v])=>`<button class="${hubBillTab===k?'active':''}" onclick="hubBillSelect('${k}')">${esc(v)}</button>`).join('')}<span class="spacer"></span><button class="btn sm" onclick="renderView()">${icon('refresh')}Actualiser</button></div></section>`;
 const head=embedded?'':heading(admin?'Factures des Hubs':'Factures',admin?'Barèmes par Hub et émission quotidienne configurable. Aucun paiement automatique.':'Mes factures émises par Admin et factures des livreurs de mon Hub.');
 if(hubBillTab==='drivers'){
  if(billingOwner!==S.user.id||!billingFilters||billingFilters.kind!=='livreur')billingReset('livreur');
  const d=await api('/billing?'+billingQuery());
  return head+navigation+`<p class="form-hint">Factures des livreurs de votre Hub : documents PDF / CSV, impression et règlements réels avec confirmation. Création et barèmes : Livreurs de mon Hub → Facture.</p>`+billingView(d);
 }
 if(hubBillTab==='legacy')return head+navigation+hubInvoicesAdminView(await api('/logistics/hub-invoices'));
 const data=await api('/hub-billing');hubBillData=data;
 if(hubBillTab==='terms')return head+navigation+`<p class="form-hint">Un barème par Hub : Livré / Retourné / Refusé. Les factures déjà émises ne sont jamais recalculées. Net = retenue de la commission sur le COD; Intégral = COD et commission séparés. Aucun tarif implicite.</p><section class="card">`+simpleTable(['Hub','Méthode','Livré MAD','Retourné MAD','Refusé MAD','Version',''],data.hubs.map(h=>[esc(h.name)+(h.active?'':' · Inactif'),h.mode==='net'?'Net':h.mode==='gross'?'Intégral':'Non configuré',h.revision?centMoney(h.delivered_cents):'—',h.revision?centMoney(h.returned_cents):'—',h.revision?centMoney(h.refused_cents):'—',h.revision||'—',h.active?`<button class="btn sm" onclick="hubBillEditTerms(${h.id})">Configurer le barème</button>`:'']))+`</section>`;
 if(hubBillTab==='schedule'){
  const c=data.schedule,last=data.last_automatic_result;
  return head+navigation+`<section class="card" style="padding:24px"><h3>Émission automatique · heure du Maroc</h3><p class="form-hint">Chaque jour à l’heure choisie : une facture par Hub ayant un barème et des commandes clôturées non encore facturées. Les commandes déjà facturées sont exclues. Sans barème ou attribution Hub attestée : aucune facture inventée.</p>${!data.scheduler_running?'<p class="form-hint orange">Le moteur automatique n’est pas actif dans ce processus. En production il démarre par défaut. En démo : ORIENTAL24_HUB_BILLING_SCHEDULER=1, puis redémarrer.</p>':''}<form onsubmit="hubBillSaveSchedule(event)"><div class="form-grid"><label>Activation<select name="enabled"><option value="false" ${!c.enabled?'selected':''}>Désactivée</option><option value="true" ${c.enabled?'selected':''}>Activée</option></select></label><label>Heure · Africa/Casablanca<input type="time" name="time" value="${esc(c.time)}" required></label></div><p class="sub">Prochaine exécution : ${c.next_run?esc(new Date(c.next_run).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca'})):'—'}<br>Dernière exécution : ${c.last_run?esc(new Date(c.last_run).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca'})):'—'}</p>${last?`<p class="form-hint">Dernier passage : ${last.count} facture(s). Sans barème : ${last.missing_terms.map(h=>esc(h.name)).join(', ')||'aucun'}. Sans Hub actif attesté : ${last.unassigned_count} commande(s). Les commandes ignorées restent disponibles pour une prochaine émission.</p>`:''}${c.last_error?`<p role="alert">${esc(c.last_error)}</p>`:''}<div class="form-actions"><button class="btn primary" type="submit">Enregistrer le planning</button></div><p class="form-error" role="alert"></p></form></section>`;
 }
 const rows=data.rows||[],cod=rows.reduce((n,r)=>n+r.cod_cents,0),comm=rows.reduce((n,r)=>n+r.commission_cents,0);
 return head+navigation+`<section class="stats">${stat('Factures émises',rows.length,'','file','blue','500 plus récentes')}${stat('COD des factures',centMoney(cod),'MAD','wallet','purple','Snapshot · pas un paiement')}${stat('Commissions des Hubs',centMoney(comm),'MAD','chart','green','Selon les barèmes figés')}</section><p class="form-hint">Factures internes par barème Hub, distinctes du registre COD historique et des factures clients. Montants figés; aucune déclaration de paiement ni virement automatique.</p>${admin?'<div class="form-actions"><button class="btn primary" onclick="hubBillGeneratePreview()">Prévisualiser / générer maintenant</button></div>':''}<section class="card">${rows.length?simpleTable(['Facture','Hub','Émission','Colis','COD MAD','Commission MAD','Net à remettre MAD','Commission à verser MAD','Documents'],rows.map(r=>[`<button class="tracking" onclick="hubBillOpen(${r.id})">${esc(r.reference)}</button>`,esc(r.hub_name),date(r.created_at),r.parcel_count,centMoney(r.cod_cents),centMoney(r.commission_cents),centMoney(r.cash_due_cents),centMoney(r.commission_due_cents),`<button class="btn sm" onclick="hubBillOpen(${r.id})">Détail / PDF</button> <button class="btn sm" onclick="hubBillCSV(${r.id})">CSV</button>`])):empty('Aucune facture émise',admin?'Configurez les barèmes et l’heure de génération automatique.':'Les factures émises par Admin pour votre Hub apparaîtront ici.')}</section>${!admin?'<button class="btn sm" onclick="hubBillLegacyMine()">Consulter les anciennes factures COD</button>':''}`;
}
async function hubBillEditTerms(id){
 if(S.user.role!=='admin')return;
 const h=hubBillData.hubs.find(h=>h.id===id);if(!h)return;
 modal('Barème Hub · '+h.name,form(`${select('mode','Méthode',[['','Choisir'],['net','Net de commission'],['gross','COD intégral / commission séparée']],h.mode||'')}${input('delivered','Colis Livré · MAD',h.revision?centInput(h.delivered_cents):'','number',true,'min="0" max="10000" step="0.01"')}${input('returned','Colis Retourné · MAD',h.revision?centInput(h.returned_cents):'','number',true,'min="0" max="10000" step="0.01"')}${input('refused','Colis Refusé · MAD',h.revision?centInput(h.refused_cents):'','number',true,'min="0" max="10000" step="0.01"')}<p class="form-hint full">Saisissez 0 explicitement si un état n’est pas rémunéré. Prochaines factures uniquement.</p>`,'Enregistrer le barème'));
 bindForm(async d=>{await api('/hub-billing/terms/'+id,'PUT',{...d,revision:h.revision||0});await saved('Barème du Hub enregistré')});
}
async function hubBillSaveSchedule(e){
 e.preventDefault();if(S.user.role!=='admin')return;
 const f=e.target,b=f.querySelector('button'),err=f.querySelector('.form-error');if(b.disabled)return;b.disabled=true;
 try{await api('/hub-billing/schedule','PUT',{enabled:f.elements.enabled.value==='true',time:f.elements.time.value,revision:hubBillData.schedule.revision});await renderView();toast('Planning enregistré · heure du Maroc')}
 catch(e){err.textContent=e.message;err.style.display='block';b.disabled=false}
}
async function hubBillGeneratePreview(){
 if(S.user.role!=='admin')return;const owner=S.user.id;
 try{
  const d=await api('/hub-billing/preview');if(S?.user?.id!==owner)return;
  modal('Génération des factures des Hubs',`<p class="form-hint">Commandes clôturées non encore facturées jusqu’à ${esc(new Date(d.cutoff).toLocaleString('fr-FR',{timeZone:'Africa/Casablanca'}))}. Aucun paiement enregistré.</p>${simpleTable(['Hub','Colis','COD MAD','Commission MAD'],d.hubs.map(h=>[esc(h.hub_name),h.parcel_count,centMoney(h.cod_cents),centMoney(h.commission_cents)]))}${d.missing_terms.length?`<p class="form-hint orange">Sans barème, ignorés : ${d.missing_terms.map(h=>esc(h.name)).join(', ')}</p>`:''}${d.unassigned_count?`<p class="form-hint orange">${d.unassigned_count} commande(s) sans Hub actif attesté : revue Admin requise.</p>`:''}<form id="hub-bill-generate"><div class="form-error" role="alert"></div><label><input type="checkbox" name="confirmed" required> Je confirme l’émission de ces factures internes.</label><div class="form-actions"><button type="submit" class="btn primary" ${d.hubs.length?'':'disabled'}>Émettre ${d.hubs.length} facture(s)</button></div></form>`);
  const key=financeKey();bindForm(async()=>{await api('/hub-billing/generate','POST',{cutoff:d.cutoff,snapshot:d.snapshot,request_key:key,confirmed:true});await saved('Factures des Hubs émises')});
 }catch(e){toast(e.message,true)}
}
function hubBillInvoiceHTML(d){
 const x=d.invoice;
 return `<h2>${esc(x.reference)} · ${esc(x.hub_name)}</h2><p>Émise le ${esc(date(x.created_at))} · Barème v${x.terms_revision} · ${x.mode==='net'?'Net de commission':'COD intégral'}</p>${simpleTable(['Tracking','Ville','État facturé','COD MAD','Commission MAD'],d.lines.map(l=>[esc(l.tracking),esc(l.city),esc(l.status),centMoney(l.cod_cents),centMoney(l.commission_cents)]))}<p><b>COD : ${centMoney(x.cod_cents)} MAD · Commission Hub : ${centMoney(x.commission_cents)} MAD</b></p><p>Retenue : ${centMoney(x.retained_cents)} MAD<br>À remettre par le Hub : ${centMoney(x.cash_due_cents)} MAD<br>Commission à verser : ${centMoney(x.commission_due_cents)} MAD</p><p class="sub">Relevé interne, hors facture fiscale. Aucun règlement n’est attesté par ce document. COD et commissions livreurs ne sont pas recalculés ici.</p>`;
}
async function hubBillOpen(id){
 const owner=S.user.id;try{const d=await api('/hub-billing/'+id);if(S?.user?.id!==owner)return;modal(d.invoice.reference,hubBillInvoiceHTML(d)+`<div class="form-actions"><button class="btn" onclick="hubBillPrint(${id})">Imprimer / PDF</button><button class="btn" onclick="billingHubPDF(${id})">Télécharger PDF</button><button class="btn" onclick="hubBillCSV(${id})">CSV</button></div>`,true)}catch(e){toast(e.message,true)}
}
async function hubBillPrint(id){
 return billingPrintPDF('hub',id);

}

async function hubBillCSV(id){
 const owner=S.user.id;try{const r=await fetch('/api/hub-billing/'+id+'/csv',{credentials:'same-origin'});if(!r.ok)throw Error('CSV inaccessible.');const b=await r.blob();if(S?.user?.id!==owner)return;const url=URL.createObjectURL(b),a=document.createElement('a');a.href=url;a.download='HUB-'+String(id).padStart(6,'0')+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(e){toast(e.message,true)}
}
async function hubBillLegacyMine(){try{const d=await api('/logistics/hub/invoices');modal('Anciennes factures COD',hubInvoicesView(d),true)}catch(e){toast(e.message,true)}}
