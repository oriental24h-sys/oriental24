/* v1.12.0 « Traçabilité RFID & exécution terrain » : captation dimensionnelle (poids
   volumétrique ÷5000, classes S/M/L/XL), RFID temps réel (tags EPC, portail multi-lectures,
   inventaire tournant), picking guidé pick-by-voice, plan de chargement LIFO, voix livreur.
   100 % local — aucun middleware RFID payant, aucun service vocal cloud. */
window.coCurrentId=null;
window.coSay=t=>{try{const u=new SpeechSynthesisUtterance(String(t||''));u.lang='fr-FR';speechSynthesis.speak(u)}catch(e){}};
window.coOut=(id,obj)=>{const el=document.getElementById(id);if(el)el.innerHTML='<pre style="white-space:pre-wrap;font-size:11px;background:#f4f7fb;border:1px solid #d7deea;border-radius:8px;padding:8px;margin:6px 0">'+esc(JSON.stringify(obj,null,1))+'</pre>'};
window.coPid=()=>Number((document.getElementById('co-parcel')||{}).value||window.coCurrentId||0);
window.coDimsSave=async()=>{
  const id=coPid();if(!id){toast('Choisissez un colis.',true);return}
  const g=k=>Number((document.getElementById(k)||{}).value||0);
  try{const r=await api('/parcels/'+id+'/dimensions','POST',{dim_l:g('co-l')||1,dim_w:g('co-w')||1,dim_h:g('co-h')||1,weight_kg:g('co-kg')||0.5});
    coOut('co-dim-result',r);toast('Dimensions captées ✓')}
  catch(e){coOut('co-dim-result',{error:e.message||String(e)});toast(e.message,true)}};
window.coRfidAssign=async()=>{
  const id=coPid();if(!id){toast('Choisissez un colis.',true);return}
  try{const r=await api('/parcels/'+id+'/dimensions','POST',{rfid_tag:((document.getElementById('co-rfid-tag')||{}).value||'').trim()});
    coOut('co-rfid-result',r);toast('Tag RFID attaché ✓')}
  catch(e){coOut('co-rfid-result',{error:e.message||String(e)});toast(e.message,true)}};
window.coRfidScan=async()=>{
  const raw=((document.getElementById('co-rfid-tags')||{}).value||'').trim();
  const portal=((document.getElementById('co-rfid-portal')||{}).value||'Portail quai 1').trim();
  const tags=raw.split(/[\s,;]+/).map(t=>t.trim().toUpperCase()).filter(Boolean);
  try{const r=await api('/rfid/scan','POST',tags.length?{tags,portal}:{count:5,portal});
    coOut('co-rfid-result',r);toast((r.matched||[]).length+' tag(s) reconnu(s) · '+(r.unmatched||[]).length+' inconnu(s)');coInventory()}
  catch(e){coOut('co-rfid-result',{error:e.message||String(e)});toast(e.message,true)}};
window.coInventory=async()=>{try{coOut('co-rfid-inventory',await api('/rfid/inventory'))}catch(e){toast(e.message,true)}};
window.coStoredRows=async()=>{try{const r=await api('/warehouse/storage');return (r&&r.storage)||[]}catch(e){return[]}};
window.coPickBuild=async()=>{
  const box=document.getElementById('co-pick-parcels');if(!box)return;
  try{
    const r=await api('/parcels?per_page=100');
    const rows=Array.isArray(r)?r:(r.parcels||r.rows||r.items||[]);
    const st=await coStoredRows();
    const byPid={};st.forEach(x=>{if(x.status==='stock')byPid[x.parcel_id]=x.label||x.slot||x.slot_label||''});
    box.innerHTML=rows.slice(0,30).map(p=>`<label style="display:inline-flex;gap:4px;align-items:center;margin:2px 8px 2px 0;font-size:12px"><input type="checkbox" class="co-pick-one" value="${p.id}"> ${esc(p.tracking)}${byPid[p.id]?' · <span class="tag">'+esc(byPid[p.id])+'</span>':' <span class="tag">hors stock</span>'}</label>`).join('')||'<p class="muted">Aucun colis.</p>';
  }catch(e){toast(e.message,true)}};
window.coPickStart=async()=>{
  const ids=Array.from(document.querySelectorAll('.co-pick-one:checked')).map(c=>Number(c.value));
  if(!ids.length){toast('Cochez au moins un colis en stock.',true);return}
  try{
    const r=await api('/pick-sessions','POST',{parcel_ids:ids});
    window.coPickSid=r.id;
    const d=await api('/pick-sessions/'+r.id);
    window.coPickSteps=d.steps||[];
    window.coPickIdx=(d.steps||[]).findIndex(s=>s.state==='en_attente');if(window.coPickIdx<0)window.coPickIdx=0;
    coRenderPick(d,r.order||[]);
  }catch(e){coOut('co-pick-result',{error:e.message||String(e)});toast(e.message,true)}};
window.coRenderPick=(d,order)=>{
  const steps=d.steps||window.coPickSteps||[];
  const path=(order&&order.length)?order:steps.map(s=>s.slot_label);
  let h=`<p style="margin:6px 0"><b>Tournée #${esc(d.id)}</b> — chemin d'allées : <span class="mono">${esc(path.join(' → '))}</span> · ${esc(d.done)}/${steps.length}</p>`;
  steps.forEach((s,i)=>{
    h+=`<div style="border:1px solid #d7deea;border-radius:8px;padding:6px 8px;margin:4px 0;${i===window.coPickIdx?'outline:2px solid #22c55e':''}">
     <b class="mono">${esc(s.slot_label)}</b> · ${esc(s.tracking)} — ${esc(s.voice||'')}
     <button class="btn sm" type="button" onclick="coSay(${JSON.stringify(String(s.voice||s.slot_label)).replace(/"/g,'&quot;')})">▶️ Écouter</button>
     ${s.state==='finie'?'<span class="tag">✅ fait</span>':`<button class="btn sm primary" type="button" onclick="coPickConfirm(${s.id})">✓ Confirmer</button>`}</div>`;});
  coOut('co-pick-result',{});const el=document.getElementById('co-pick-result');if(el)el.innerHTML=h;};
window.coPickConfirm=async(stepId)=>{
  try{
    await api('/pick-sessions/'+window.coPickSid+'/steps/'+stepId+'/confirm','POST',{});
    toast('Prise confirmée ✓');
    const d=await api('/pick-sessions/'+window.coPickSid);
    window.coPickSteps=d.steps||[];
    window.coPickIdx=(d.steps||[]).findIndex(x=>x.state==='en_attente');if(window.coPickIdx<0)window.coPickIdx=0;
    coRenderPick(d,[]);
    const cur=window.coPickSteps[window.coPickIdx];if(cur)coSay(cur.voice);
  }catch(e){toast(e.message,true)}};
window.coLoadPlan=async()=>{
  const did=Number(((document.getElementById('co-load-driver')||{}).value)||0);
  try{
    const url=did?('/load-plan?driver_id='+did):'/load-plan';
    const j=await api(url);
    const rows=(j.plan||[]).map(p=>`<tr><td>#${esc(p.load_seq)}</td><td>${esc(p.zone)}</td><td class="mono">${esc(p.tracking)}</td><td>${esc(p.city||'—')}</td><td>${esc(p.weight_kg)} kg</td><td>#${esc(p.unload_seq)}</td></tr>`).join('');
    const el=document.getElementById('co-load-result');
    if(el)el.innerHTML=`<p style="margin:6px 0"><b>Plan véhicule</b> — ${esc(j.method)} · ${esc(j.stops)} arrêts · ${j.overload?'<span class="tag">⚠️ surcharge</span>':'<span class="tag">charge '+esc(j.total_kg)+'/'+esc(j.max_kg)+' kg</span>'}</p>
     <table><thead><tr><th>Chargé</th><th>Zone</th><th>Colis</th><th>Ville</th><th>Poids</th><th>Déchargé</th></tr></thead><tbody>${rows}</tbody></table>`;
  }catch(e){coOut('co-load-result',{error:e.message||String(e)});toast(e.message,true)}};
window.coVoiceList=async()=>{try{coOut('co-voice-list',await api('/voice-commands'))}catch(e){toast(e.message,true)}};
window.coVoiceRun=async(text,id)=>{
  const t=String(text||'').toLowerCase();const fb=document.getElementById('co-voice-feedback');
  try{
    const d=await api('/voice-commands');
    let m=null;(d.commands||[]).forEach(c=>{if(!m&&(t.indexOf(c.key)!==-1||t.indexOf(c.say)!==-1))m=c.key});
    const pid=id||window.coCurrentId||coPid();
    if(m==='suivant'){const r=await api('/parcels?per_page=100');const rows=Array.isArray(r)?r:(r.parcels||r.rows||r.items||[]);
      const i=rows.findIndex(p=>p.id===pid);const nx=rows[(i+1)%Math.max(1,rows.length)];
      if(nx&&typeof parcelDetail==='function'){window.coCurrentId=nx.id;parcelDetail(nx.id)}}
    else if(m==='pris'){await api('/parcels/'+pid+'/pickup','POST',{});toast('Colis ramassé ✓');if(typeof parcelDetail==='function')parcelDetail(pid)}
    else if(m==='livre'){await api('/parcels/'+pid+'/deliver','POST',{});toast('Colis livré ✓');if(typeof parcelDetail==='function')parcelDetail(pid)}
    else if(m==='appeler'){const ph=((document.querySelector('.parcel-recipient-phone')||{}).textContent||'').replace(/\s/g,'').replace(/^\+/,'');if(ph)window.open('https://wa.me/212'+ph.replace(/^0/,''),'_blank');else toast('Numéro client introuvable.',true)}
    else if(m==='confirmer'){const cur=(window.coPickSteps||[])[window.coPickIdx||0];if(cur&&window.coPickSid)await coPickConfirm(cur.id);else toast('Aucune étape de picking en cours.',true)}
    if(fb)fb.textContent=m?('Commande reconnue : '+m+' ← « '+text+' »'):('Commande inconnue : « '+text+' »');
  }catch(e){toast(e.message,true)}};
window.coVoiceDictate=(id)=>{
  if(id)window.coCurrentId=id;
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  if(!SR){api('/voice-commands').then(d=>{const l=(d.commands||[]).map(c=>c.say);coSay(l.length?('Dites : '+l.join(', ou ')):'Dictée indisponible sur ce navigateur.')}).catch(()=>{});return}
  const rec=new SR();rec.lang='fr-FR';rec.maxAlternatives=1;
  rec.onresult=ev=>{const said=(ev.results[0][0].transcript||'');coVoiceRun(said,window.coCurrentId)};
  rec.onerror=()=>toast('Micro indisponible.',true);
  try{rec.start();coSay('Je vous écoute.')}catch(e){}};
window.coPanel=async(preId)=>{
  if(preId)window.coCurrentId=preId;
  let voc={commands:[]};try{voc=await api('/voice-commands')}catch(e){}
  const cmds=(voc.commands||[]).map(c=>`<li><b>${esc(c.key)}</b> — dites « ${esc(c.say)} » (${esc(c.label)})</li>`).join('');
  modal('Traçabilité & chargement',`
   <p class="form-hint" style="margin:0 0 10px">RFID temps réel · picking guidé pick-by-voice · captation dimensionnelle (poids volumétrique ÷5000) · plan de chargement LIFO · voix livreur — aucun fournisseur externe (ni middleware RFID, ni service vocal cloud).</p>
   <h3 style="margin:14px 0 6px">📐 Captation dimensionnelle</h3>
   <p class="form-hint" style="margin:0 0 6px">Colis : <select id="co-parcel" style="padding:6px;border:1px solid #d7deea;border-radius:6px"></select></p>
   <div class="flex" style="gap:6px;flex-wrap:wrap;align-items:center">
    <input id="co-l" placeholder="L cm" style="width:70px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="co-w" placeholder="l cm" style="width:70px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="co-h" placeholder="h cm" style="width:70px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="co-kg" placeholder="poids kg" style="width:80px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" id="co-dim-save" type="button" onclick="coDimsSave()">Enregistrer (÷5000)</button></div>
   <div id="co-dim-result"></div>
   <h3 style="margin:14px 0 6px">📡 RFID temps réel</h3>
   <div class="flex" style="gap:6px;flex-wrap:wrap;align-items:center">
    <input id="co-rfid-tag" placeholder="EPC-XXXXX (vide = auto)" style="width:170px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm" id="co-rfid-assign" type="button" onclick="coRfidAssign()">Attacher le tag</button>
    <input id="co-rfid-portal" value="Portail quai 1" style="width:150px;padding:6px;border:1px solid #d7deea;border-radius:6px"></div>
   <div class="flex" style="gap:6px;flex-wrap:wrap;align-items:center;margin-top:6px">
    <input id="co-rfid-tags" placeholder="EPC-AAAAA, EPC-BBBBB (vide = démo auto)" style="width:300px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" id="co-rfid-scan" type="button" onclick="coRfidScan()">Scanner le portail</button>
    <button class="btn sm" id="co-rfid-inv" type="button" onclick="coInventory()">Inventaire tournant</button></div>
   <div id="co-rfid-result"></div><div id="co-rfid-inventory"></div>
   <h3 style="margin:14px 0 6px">📦 Picking guidé (pick-by-voice)</h3>
   <div id="co-pick-parcels" style="max-height:130px;overflow:auto;border:1px solid #d7deea;border-radius:8px;padding:6px"></div>
   <button class="btn sm primary" id="co-pick-start" type="button" onclick="coPickStart()" style="margin-top:6px">Lancer le picking (chemin d'allées optimisé)</button>
   <div id="co-pick-result"></div>
   <h3 style="margin:14px 0 6px">🚚 Plan de chargement véhicule (LIFO de la route)</h3>
   <div class="flex" style="gap:6px;flex-wrap:wrap;align-items:center">
    <input id="co-load-driver" placeholder="id livreur (vide = moi)" style="width:150px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" id="co-load-btn" type="button" onclick="coLoadPlan()">Générer le plan</button></div>
   <div id="co-load-result"></div>
   <h3 style="margin:14px 0 6px">🎙️ Voix livreur (mains libres)</h3>
   <p class="form-hint" style="margin:0 0 6px">Commandes : <button class="btn sm" id="co-voice-list-btn" type="button" onclick="coVoiceList()">Afficher</button>
    <button class="btn sm primary" id="co-voice-test" type="button" onclick="coVoiceDictate(window.coCurrentId)">🎙️ Dicter une commande</button></p>
   <ul style="margin:4px 0 4px 18px;font-size:12px">${cmds||'<li class="muted">Indisponible.</li>'}</ul>
   <div id="co-voice-list"></div>
   <p id="co-voice-feedback" class="form-hint"></p>`,true);
  await coFillParcels(preId);await coPickBuild();};
window.coFillParcels=async(preId)=>{
  const sel=document.getElementById('co-parcel');if(!sel)return;
  try{
    const r=await api('/parcels?per_page=100');
    const rows=Array.isArray(r)?r:(r.parcels||r.rows||r.items||[]);
    sel.innerHTML=rows.map(p=>`<option value="${p.id}">${esc(p.tracking)} · ${esc(p.recipient||p.id)}</option>`).join('')||'<option value="">— aucun colis —</option>';
    if(preId)sel.value=String(preId);
  }catch(e){toast(e.message,true)}};
/* injection fiche (après techInjectRow / smartInjectRow / whInjectRow) */
function coInjectRow(id){
  const box=document.querySelector('.modal .parcel-command-actions')||document.querySelector('.modal .parcel-command-grid');
  if(!box||box.querySelector('.co-row'))return;
  window.coCurrentId=id;
  const role=(S&&S.user&&S.user.role)||'';
  const div=document.createElement('div');
  div.className='co-row flex';
  div.style.cssText='gap:6px;flex-wrap:wrap;margin-top:6px;width:100%';
  div.innerHTML=`${['admin','agent','livreur'].includes(role)?`<button class="btn sm" type="button" onclick="coPanel(${id})">📡 Traçabilité &amp; chargement</button>
   <button class="btn sm" type="button" onclick="coVoiceDictate(${id})">🎙️ Voix livreur</button>`:''}`;
  if(div.innerHTML.trim())box.appendChild(div);
}
const coBaseInjectRow=techInjectRow;
techInjectRow=function(id){coBaseInjectRow(id);try{coInjectRow(id)}catch(e){}};
