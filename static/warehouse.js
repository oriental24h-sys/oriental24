/* v1.11.0 « Entrepôt intelligent & robotique » : WMS (emplacements, stock/picking/sortie),
   robots de tri (missions, batterie, charge), livraison par drone, contrôle qualité réception,
   synchronisation multi-agences (snapshot SHA-256). 100 % local. */
window.warehousePanel=async()=>{
  let k,w,bots,recs,log;
  try{[k,w,bots,recs,log]=await Promise.all([api('/warehouse/kpis'),api('/warehouses'),api('/bots'),api('/warehouse/receptions'),api('/sync/log')]);}
  catch(e){toast(e.message||'Module entrepôt indisponible',true);return}
  const wRows=(w.rows||[]).map(r=>`<tr><td><b>${esc(r.name)}</b></td><td>${esc(r.city||'—')}</td>
    <td>${r.slots_busy}/${r.slots_total} occupés</td>
    <td><span class="tag">${Math.round(100*(r.slots_busy||0)/Math.max(1,r.slots_total||1))} %</span></td></tr>`).join('');
  const bRows=(bots.rows||[]).map(r=>`<tr><td><b>${esc(r.name)}</b></td><td><span class="tag">${esc(r.kind)}</span></td>
    <td>${Math.round(r.battery_pct||0)} %</td><td><span class="tag">${esc(r.state)}</span></td><td>${r.missions_done||0}</td>
    <td style="white-space:nowrap">
     <button class="btn sm" type="button" onclick="whBotState(${r.id},'idle')">🟢</button>
     <button class="btn sm" type="button" onclick="whBotState(${r.id},'panne')">🛑</button>
     <button class="btn sm" type="button" onclick="whBotCharge(${r.id})">🔌 Charge</button></td></tr>`).join('');
  const mRows=(bots.missions||[]).map(m=>`<tr><td class="mono">#${m.id}</td><td class="mono">${esc(m.tracking)}</td>
    <td><span class="tag">${esc(m.kind)}</span></td><td>${esc(m.from_loc)} → ${esc(m.to_loc)}</td>
    <td><span class="tag">${esc(m.state)}</span></td>
    <td>${m.state!=='finie'?`<button class="btn sm primary" type="button" onclick="whMissionFinish(${m.id})">✓ Terminée</button>`:''}</td></tr>`).join('');
  const rRows=(recs.rows||[]).slice(0,8).map(r=>`<tr><td class="mono">${esc(r.tracking)}</td>
    <td><span class="tag">${esc(r.condition)}</span></td><td>${r.score}/100</td>
    <td class="muted" style="font-size:11px">${esc(r.note||'')}</td><td class="muted" style="font-size:11px">${esc(r.photo_ref||'')}</td></tr>`).join('');
  const lRows=(log.rows||[]).slice(0,6).map(r=>`<tr><td><span class="tag">${esc(r.direction)}</span></td>
    <td class="mono" style="font-size:10px">${esc(String(r.checksum).slice(0,16))}…</td><td>${r.items}</td><td>${r.merged}</td>
    <td class="muted" style="font-size:11px">${esc(String(r.created_at).slice(0,16))}</td></tr>`).join('');
  modal('Entrepôt intelligent & robotique',`
   <p class="form-hint" style="margin:0 0 10px">WMS (emplacements A-01-1…C-05-2) · robots de tri AGV/picking avec missions auto-affectées · <b>livraison par drone</b> (≤ 2 kg) · contrôle qualité à la réception · synchronisation multi-agences signée SHA-256 — aucun fournisseur externe.</p>
   <div class="stats" style="grid-template-columns:1fr 1fr 1fr 1fr">
    ${stat('Occupation',String(k.occupation_pct||0),'%','box','navy',(k.slots_busy||0)+'/'+(k.slots_total||0)+' empl.')}
    ${stat('En stock',String(k.stored||0),'','mapPin','navy',(k.ready||0)+' prêts · '+(k.out||0)+' sortis')}
    ${stat('Robots',(k.bots_idle||0)+'/'+(k.bots_total||0),'libres','truck',(k.bots_idle||0)>0?'green':'orange',(k.missions_queue||0)+' en file')}
    ${stat('Tri auto',String(k.automation_rate||0),'%','check',(k.automation_rate||0)>=80?'green':'navy',(k.missions_last_hour||0)+'/h')}</div>
   <h3 style="margin:16px 0 6px">🏬 Entrepôts &amp; emplacements</h3>
   ${wRows?`<table><thead><tr><th>Entrepôt</th><th>Ville</th><th>Occupation</th><th>Taux</th></tr></thead><tbody>${wRows}</tbody></table>`:'<p class="muted">Aucun entrepôt.</p>'}
   <div class="flex" style="gap:6px;margin-top:8px;flex-wrap:wrap">
    <input id="wh-name" placeholder="Nom de l’entrepôt" style="width:200px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="wh-city" placeholder="Ville" style="width:130px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" type="button" onclick="whAdd()">Créer (30 emplacements)</button></div>
   <h3 style="margin:16px 0 6px">🤖 Robots de tri (AGV / picking)</h3>
   ${bRows?`<table><thead><tr><th>Robot</th><th>Type</th><th>Batterie</th><th>État</th><th>Missions</th><th>Actions</th></tr></thead><tbody>${bRows}</tbody></table>`:'<p class="muted">Aucun robot — déclarez-en un ci-dessous.</p>'}
   <div class="flex" style="gap:6px;margin-top:8px;flex-wrap:wrap">
    <input id="wh-bot-name" placeholder="Nom du robot" style="width:150px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <select id="wh-bot-kind" style="padding:6px;border:1px solid #d7deea;border-radius:6px"><option value="tri">tri</option><option value="picking">picking</option><option value="AGV">AGV</option></select>
    <button class="btn sm primary" type="button" onclick="whBotAdd()">Ajouter le robot</button></div>
   <h3 style="margin:16px 0 6px">📡 File des missions</h3>
   ${mRows?`<table><thead><tr><th>#</th><th>Colis</th><th>Type</th><th>Trajet</th><th>État</th><th>Fin</th></tr></thead><tbody>${mRows}</tbody></table>`:'<p class="muted">File vide — les missions naissent des mises en stock et des pickings.</p>'}
   <h3 style="margin:16px 0 6px">👁️ Contrôle qualité réception (« vision »)</h3>
   ${rRows?`<table><thead><tr><th>Colis</th><th>État</th><th>Score</th><th>Note</th><th>Photo</th></tr></thead><tbody>${rRows}</tbody></table>`:'<p class="muted">Aucun contrôle — depuis la fiche colis : bouton « Réception ».</p>'}
   <p class="form-hint">Alertes réception : <b>${k.check_alerts||0}</b> anomalie(s) sur ${k.checks||0} contrôle(s).</p>
   <h3 style="margin:16px 0 6px">☁️ Synchronisation multi-agences (cloud-ready)</h3>
   <div class="flex" style="gap:6px;flex-wrap:wrap">
    <button class="btn sm" type="button" onclick="whSyncExport()">⬇️ Exporter le snapshot</button>
    <label class="btn sm" style="cursor:pointer">⬆️ Importer un snapshot<input type="file" accept="application/json" style="display:none" onchange="whSyncImport(this)"></label></div>
   ${lRows?`<table style="margin-top:8px"><thead><tr><th>Sens</th><th>Empreinte</th><th>Éléments</th><th>Fusionnés</th><th>Quand</th></tr></thead><tbody>${lRows}</tbody></table>`:''}`,true);
};
window.whAdd=async()=>{
  const g=id=>document.getElementById(id).value.trim();
  if(!g('wh-name')){toast('Nom obligatoire.',true);return}
  try{await api('/warehouses','POST',{name:g('wh-name'),city:g('wh-city')});toast('Entrepôt créé (30 emplacements) ✓');closeModal();warehousePanel();}
  catch(e){toast(e.message,true)}
};
window.whBotAdd=async()=>{
  const g=id=>document.getElementById(id).value.trim();
  if(!g('wh-bot-name')){toast('Nom obligatoire.',true);return}
  try{await api('/bots','POST',{name:g('wh-bot-name'),kind:g('wh-bot-kind')});toast('Robot ajouté ✓');closeModal();warehousePanel();}
  catch(e){toast(e.message,true)}
};
window.whBotState=async(id,st)=>{try{await api('/bots/'+id,'PATCH',{state:st});toast('État robot : '+st);closeModal();warehousePanel();}catch(e){toast(e.message,true)}};
window.whBotCharge=async(id)=>{try{await api('/bots/'+id+'/charge','POST',{});toast('Robot rechargé ✓');closeModal();warehousePanel();}catch(e){toast(e.message,true)}};
window.whMissionFinish=async(id)=>{try{await api('/warehouse/missions/'+id+'/finish','POST',{});toast('Mission terminée ✓');closeModal();warehousePanel();}catch(e){toast(e.message,true)}};
window.whSyncExport=async()=>{
  try{const j=await api('/sync/export');
    const b=new Blob([JSON.stringify(j,null,1)],{type:'application/json'});
    const a=document.createElement('a');a.href=URL.createObjectURL(b);
    a.download='oriental24-sync-'+String(j.generated_at||'').slice(0,10)+'.json';
    document.body.appendChild(a);a.click();a.remove();
    toast('Snapshot exporté (empreinte '+String(j.checksum).slice(0,8)+'…).');}
  catch(e){toast(e.message,true)}
};
window.whSyncImport=async(inp)=>{
  const file=inp.files&&inp.files[0];if(!file)return;
  try{const text=await file.text();const j=JSON.parse(text);
    const r=await api('/sync/import','POST',j);
    toast('Snapshot importé — '+r.merged+' colis fusionné(s) ✓');closeModal();warehousePanel();}
  catch(e){toast(e.message||'Snapshot invalide',true)}
  finally{inp.value=''}
};

/* ---- fiche colis : stock, drone, réception ---- */
window.whStorage=async(id)=>{
  let st;try{st=await api('/parcels/'+id+'/storage')}catch(e){toast(e.message,true);return}
  const head=st.stored?`<p style="margin:6px 0">Statut : <b>${esc(st.status)}</b> · emplacement <b class="mono">${esc(st.label||'—')}</b> · mode <b>${esc(st.mode)}</b> · ${esc(String(st.weight_kg||''))} kg</p>`
   :`<p class="muted" style="margin:6px 0">Colis non stocké — la mise en stock affecte un emplacement (allée-position-niveau) et lance une mission robot.</p>`;
  modal('Entrepôt — colis #'+id,head+`
   <div class="flex" style="gap:6px;flex-wrap:wrap">
    ${!st.stored?`<button class="btn sm primary" type="button" onclick="whStore(${id})">📦 Mettre en stock</button>`:''}
    ${st.stored&&st.status==='stock'?`<button class="btn sm primary" type="button" onclick="whPick(${id})">📋 Picking (préparer)</button>`:''}
    ${st.stored&&st.status!=='sorti'?`<button class="btn sm" type="button" onclick="whShipOut(${id})">🚚 Sortie d’entrepôt</button>`:''}</div>`,true);
};
window.whStore=async(id)=>{try{const r=await api('/parcels/'+id+'/store','POST',{});toast('Mis en stock — emplacement '+r.slot+' ✓');closeModal();whStorage(id);}catch(e){toast(e.message,true)}};
window.whPick=async(id)=>{try{await api('/parcels/'+id+'/pick','POST',{});toast('Picking lancé — colis prêt ✓');closeModal();whStorage(id);}catch(e){toast(e.message,true)}};
window.whShipOut=async(id)=>{try{await api('/parcels/'+id+'/ship-out','POST',{});toast('Sortie d’entrepôt ✓');closeModal();whStorage(id);}catch(e){toast(e.message,true)}};
window.whDrone=async(id)=>{
  modal('Mode de livraison — colis #'+id,`
   <p class="form-hint">Livraison par <b>drone</b> (véhicule aérien) : colis ≤ <b>2 kg</b> depuis un hub aérien (entrepôt de la ville) avec un drone actif en flotte. Modes : standard / drone express.</p>
   <div class="flex" style="gap:6px;flex-wrap:wrap;margin:8px 0">
    <input id="dm-weight" type="number" step="0.05" min="0.05" placeholder="Poids kg" style="width:100px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <select id="dm-mode" style="padding:6px;border:1px solid #d7deea;border-radius:6px">
     <option value="standard">standard</option><option value="drone">🚁 drone express</option></select>
    <button class="btn sm primary" type="button" onclick="whDroneSave(${id})">Appliquer</button></div>`,true);
};
window.whDroneSave=async(id)=>{
  const w=document.getElementById('dm-weight').value;
  const mode=document.getElementById('dm-mode').value;
  const d={mode};if(w!=='')d.weight_kg=Number(w);
  try{await api('/parcels/'+id+'/delivery-mode','POST',d);toast('Mode : '+mode+' ✓');closeModal();parcelDetail(id);}
  catch(e){toast(e.message,true)}
};
window.whReception=async(id)=>{
  modal('Contrôle qualité réception — colis #'+id,`
   <p class="form-hint">Contrôle « vision » à la réception : état du colis noté <b>intact / abîmé / manquant</b> (score 100/60/20) avec note et référence photo — toute anomalie génère une alerte sur la chaîne de preuve.</p>
   <div class="flex" style="gap:6px;flex-wrap:wrap;margin:8px 0">
    <select id="rc-cond" style="padding:6px;border:1px solid #d7deea;border-radius:6px">
     <option value="intact">intact (100)</option><option value="abime">abîmé (60)</option><option value="manquant">manquant (20)</option></select>
    <input id="rc-note" placeholder="Note (facultatif)" style="width:170px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="rc-photo" placeholder="Réf. photo (facultatif)" style="width:120px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" type="button" onclick="whReceptionSave(${id})">Enregistrer</button></div>`,true);
};
window.whReceptionSave=async(id)=>{
  try{const r=await api('/parcels/'+id+'/reception-check','POST',{
    condition:document.getElementById('rc-cond').value,
    note:document.getElementById('rc-note').value.trim(),
    photo_ref:document.getElementById('rc-photo').value.trim()});
    toast('Contrôle enregistré — score '+r.score+'/100 ✓');closeModal();parcelDetail(id);}
  catch(e){toast(e.message,true)}
};

/* injection fiche (après techInjectRow / smartInjectRow) */
function whInjectRow(id){
  const box=document.querySelector('.modal .parcel-command-actions')||document.querySelector('.modal .parcel-command-grid');
  if(!box||box.querySelector('.wh-row'))return;
  const role=(S&&S.user&&S.user.role)||'';
  const div=document.createElement('div');
  div.className='wh-row flex';
  div.style.cssText='gap:6px;flex-wrap:wrap;margin-top:6px;width:100%';
  div.innerHTML=`${['admin','agent'].includes(role)?`<button class="btn sm" type="button" onclick="whStorage(${id})">📦 Entrepôt</button>
   <button class="btn sm" type="button" onclick="whReception(${id})">👁️ Réception</button>`:''}
   ${role==='admin'?`<button class="btn sm" type="button" onclick="whDrone(${id})">🚁 Livraison drone</button>
   <button class="btn sm" type="button" onclick="warehousePanel()">🤖 Entrepôt &amp; robotique</button>`:''}`;
  if(div.innerHTML.trim())box.appendChild(div);
}
const whBaseInjectRow=techInjectRow;
techInjectRow=function(id){whBaseInjectRow(id);try{whInjectRow(id)}catch(e){}};
