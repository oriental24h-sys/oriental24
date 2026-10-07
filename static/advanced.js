/* v1.9.0 « Technologies avancées » : panneau Admin (boîte d'envoi WhatsApp/SMS, IA/ETA prédictive,
   prévisions, risque, CO₂, zones de tri), preuve de livraison scellée (blockchain), capteurs IoT,
   assistant public (règles FR/darija). Aucune API externe : les liens wa.me/sms s'ouvrent
   sur l'appareil de l'utilisateur. */
window.techPanel=async()=>{
  let ob,ins,zn;
  try{[ob,ins,zn]=await Promise.all([api('/outbox'),api('/insights'),api('/sort-zones')]);}
  catch(e){toast(e.message||'Technologies indisponibles',true);return}
  const m=ins.model||{},fc=(ins.forecasts&&ins.forecasts.rows)||[],risk=ins.risk||[],co2=ins.co2||{},cnt=ins.counters||{};
  const obRows=(ob.rows||[]).slice(0,8).map(r=>`<tr><td class="mono">${esc(r.tracking)}</td><td><span class="tag">${esc(r.channel)}</span></td>
    <td style="font-size:11px;max-width:220px">${esc(r.text)}</td><td style="white-space:nowrap">
    ${r.links&&r.links.whatsapp?`<a class="btn sm" target="_blank" rel="noopener" href="${r.links.whatsapp}">WhatsApp</a> <a class="btn sm" target="_blank" rel="noopener" href="${r.links.sms}">SMS</a>`:''}
    ${r.status==='pending'?`<button class="btn sm" type="button" onclick="techOutboxSent(${r.id})">✓ Envoyé</button>`:'<span class="tag">envoyé</span>'}</td></tr>`).join('');
  const fcBars=fc.map(r=>`<div style="display:flex;align-items:center;gap:8px;font-size:12px;margin:2px 0"><span class="muted" style="width:90px">${esc(r.date)}</span>
    <span style="background:#12b8a6;height:12px;border-radius:6px;display:inline-block;width:${Math.max(4,r.expected*8)}px"></span><b>${r.expected}</b></div>`).join('');
  const riskRows=risk.map(r=>`<tr><td class="mono">${esc(r.tracking)}</td><td>${esc(r.city||'—')}</td><td><span class="tag">${esc(r.status)}</span></td>
    <td style="color:${r.score>=50?'#f87171':'#f59e0b'}"><b>${r.score}</b></td><td class="muted" style="font-size:11px">${esc((r.reasons||[]).join(', '))}</td></tr>`).join('');
  const zoneRows=(zn.rows||[]).map(z=>`<tr><td class="mono">${esc(z.code)}</td><td>${esc(z.label)}</td>
    <td><input id="tz-${esc(z.code)}" value="${esc(z.pattern)}" style="width:100%;padding:5px;border:1px solid #d7deea;border-radius:6px;font-size:11px"></td>
    <td><button class="btn sm" type="button" onclick="techZoneSave('${esc(z.code)}','${esc(z.label)}',document.getElementById('tz-${esc(z.code)}').value,${z.active?false:true})">${z.active?'Désactiver':'Activer'}</button></td></tr>`).join('');
  modal('Technologies avancées',`
   <p class="form-hint" style="margin:0 0 10px">WhatsApp/SMS automatiques · IA (ETA apprise sur l'historique) · Blockchain (preuve scellée) · Géofencing · CO₂ — tout calculé localement, aucune API payante.</p>
   <div class="stats" style="grid-template-columns:1fr 1fr 1fr 1fr">
    ${stat('WhatsApp/SMS en file',(ob.rows||[]).filter(r=>r.status==='pending').length,'','chat','orange')}
    ${stat('ETA prédictive',m.learned?'apprise':'repli','','clock',m.learned?'green':'navy',(m.n||0)+' tournées')}
    ${stat('CO₂ du jour',String(co2.today_kg!=null?co2.today_kg:0),'kg','box','navy')}
    ${stat('Preuves scellées',cnt.seals||0,'','shield','green')}</div>
   <h3 style="margin:16px 0 6px">📨 Boîte d'envoi WhatsApp/SMS</h3>
   ${obRows?`<table><thead><tr><th>Suivi</th><th>Canal</th><th>Gabarit</th><th>Envoi</th></tr></thead><tbody>${obRows}</tbody></table>`:'<p class="muted">File vide — les notifications se remplissent automatiquement aux changements de statut, OTP et messages guidés.</p>'}
   <h3 style="margin:16px 0 6px">🧠 IA · prévisions 7 jours</h3>
   <p class="form-hint">Modèle ${m.learned?"<b>appris sur l'historique</b>":'de <b>repli</b>'} : ${esc(String(m.a))} min/arrêt + ${esc(String(m.b))} min/km · méthode ${esc((ins.forecasts&&ins.forecasts.method)||'')} · tendance ×${esc(String((ins.forecasts&&ins.forecasts.trend)||1))}</p>
   ${fcBars||"<p class=\"muted\">Pas encore d'historique livré.</p>"}
   <h3 style="margin:16px 0 6px">⚠️ Score de risque retard</h3>
   ${riskRows?`<table><thead><tr><th>Suivi</th><th>Ville</th><th>Statut</th><th>Score</th><th>Causes</th></tr></thead><tbody>${riskRows}</tbody></table>`:'<p class="muted">Aucun colis à risque. ✓</p>'}
   <h3 style="margin:16px 0 6px">♻️ Empreinte CO₂ (0,12 kg/km)</h3>
   <p class="form-hint">Jour : <b>${esc(String(co2.today_kg!=null?co2.today_kg:0))} kg</b> · 7 derniers jours : <b>${esc(String(co2.week_kg!=null?co2.week_kg:0))} kg</b> — estimation par tournée optimisée (2-opt).</p>`,true);
};
window.techOutboxSent=async(id)=>{await api('/outbox/'+id+'/sent','POST',{});toast('Notification marquée envoyée.');closeModal();techPanel();};
window.techZoneSave=async(code,label,pattern,active)=>{await api('/sort-zones','POST',{code,label,pattern,active});toast('Zone '+code+' enregistrée.');closeModal();techPanel();};
window.techZoneNew=()=>{const g=id=>{const el=document.getElementById(id);return el?el.value.trim():''};
  if(!g('tz-new-code')||!g('tz-new-label')||!g('tz-new-pattern')){toast('Code, libellé et motif obligatoires.',true);return}
  techZoneSave(g('tz-new-code').toUpperCase(),g('tz-new-label'),g('tz-new-pattern'),true);};

/* ---- fiche colis : preuve scellée, capteur IoT, zone de tri ---- */
window.techProof=async(id)=>{
  let d;try{d=await api('/parcels/'+id+'/proof')}catch(e){toast(e.message,true);return}
  const rows=(d.chain||[]).map(r=>`<tr><td>${r.n}</td><td><span class="tag">${esc(r.status)}</span></td><td class="muted" style="font-size:11px">${esc(String(r.date).slice(0,16))}</td><td class="mono" style="font-size:10px">${esc(r.hash)}…</td></tr>`).join('');
  const badge=d.verified===null?'<span class="tag">non scellé</span>':(d.verified?'<span class="tag" style="color:#0a7a5c">✓ chaîne vérifiée</span>':'<span class="tag" style="color:#f87171">✗ chaîne modifiée depuis le scell</span>');
  modal('Preuve de livraison scellée — colis #'+id,`
   <p class="form-hint">Blockchain légère : chaque événement est lié par une empreinte SHA-256 au précédent. Le scell atteste l'état de la chaîne à la livraison — toute falsification postérieure est détectée.</p>
   <p style="margin:8px 0">${badge} <span class="mono" style="font-size:10px">tête : ${esc(String(d.head||'').slice(0,24))}…</span></p>
   ${rows?`<table><thead><tr><th>#</th><th>Statut</th><th>Date</th><th>Empreinte</th></tr></thead><tbody>${rows}</tbody></table>`:'<p class="muted">Aucun événement.</p>'}
   ${S.user.role==='admin'?`<div style="margin-top:10px"><button class="btn primary sm" type="button" onclick="techProofSeal(${id})">${icon('shield')}Sceller la preuve maintenant</button></div>`:''}`,true);
};
window.techProofSeal=async(id)=>{await api('/parcels/'+id+'/proof/seal','POST',{});toast('Preuve scellée ✓');closeModal();techProof(id);};
window.techSensor=async(id)=>{
  let d={rows:[],alerts:0};try{d=await api('/parcels/'+id+'/telemetry')}catch(e){toast(e.message,true);return}
  const rows=(d.rows||[]).map(r=>`<tr><td class="muted" style="font-size:11px">${esc(String(r.created_at).slice(11,16))}</td>
    <td>${r.temp_c!=null?r.temp_c+' °C':'—'}</td><td>${r.shock_g!=null?r.shock_g+' g':'—'}</td>
    <td>${r.humidity!=null?r.humidity+' %':'—'}</td><td>${r.battery!=null?r.battery+' %':'—'}</td></tr>`).join('');
  modal('Capteurs IoT — colis #'+id,`
   <p class="form-hint">Télémétrie colis (chaîne du froid, chocs, humidité, batterie de capteur). Les mesures hors normes déclenchent une alerte <b>Alerte IoT</b> dans la chronologie. ${d.alerts?`<b style="color:#f87171">${d.alerts} alerte(s) enregistrée(s).</b>`:''}</p>
   <div class="flex" style="gap:6px;flex-wrap:wrap;margin:8px 0">
    <input id="ts-temp" type="number" step="0.1" placeholder="°C" style="width:80px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="ts-shock" type="number" step="0.1" placeholder="choc g" style="width:80px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="ts-hum" type="number" step="1" placeholder="humidité %" style="width:90px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="ts-bat" type="number" step="1" placeholder="batterie %" style="width:90px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" type="button" onclick="techSensorSend(${id})">Envoyer la mesure</button>
    <button class="btn sm" type="button" onclick="techSensorSim(${id})">🎲 Simuler une lecture</button></div>
   ${rows?`<table><thead><tr><th>Heure</th><th>Temp.</th><th>Choc</th><th>Humidité</th><th>Batterie</th></tr></thead><tbody>${rows}</tbody></table>`:"<p class=\"muted\">Aucune mesure — le capteur n'a pas encore transmis.</p>"}`,true);
};
window.techSensorSend=async(id)=>{
  const g=(k)=>{const v=document.getElementById(k).value;return v===''?null:Number(v)};
  const d={temp_c:g('ts-temp'),shock_g:g('ts-shock'),humidity:g('ts-hum'),battery:g('ts-bat')};
  try{const r=await api('/parcels/'+id+'/telemetry','POST',d);closeModal();
    toast(r.alerts&&r.alerts.length?('Mesure enregistrée — ALERTE : '+r.alerts.join(' / ')):'Mesure enregistrée ✓',!!(r.alerts&&r.alerts.length));}
  catch(e){toast(e.message,true)};
};
window.techSensorSim=(id)=>{
  document.getElementById('ts-temp').value=(Math.random()*50-5).toFixed(1);
  document.getElementById('ts-shock').value=(Math.random()*4).toFixed(1);
  document.getElementById('ts-hum').value=Math.round(30+Math.random()*60);
  document.getElementById('ts-bat').value=Math.round(20+Math.random()*80);
};
window.techZone=async(id)=>{
  let z;try{z=await api('/parcels/'+id+'/zone')}catch(e){toast(e.message,true);return}
  modal('Affectation au tri — colis #'+id,`<p style="margin:6px 0">Ville : <b>${esc(z.city||'—')}</b> → zone <b class="mono">${esc(z.tracking_zone.code||'—')}</b> · ${esc(z.tracking_zone.label)}</p>
   <p class="form-hint">Règle appliquée : ${esc(z.tracking_zone.rule||'aucune — affectez une zone depuis le panneau Technologies avancées.')}</p>`);
};

/* injection dans la fiche colis (après le rendu de parcel-contacts.js) */
function techInjectRow(id){
  const box=document.querySelector('.modal .parcel-command-actions')||document.querySelector('.modal .parcel-command-grid');
  if(!box||box.querySelector('.tech-row'))return;
  const role=(S&&S.user&&S.user.role)||'';
  const div=document.createElement('div');
  div.className='tech-row flex';
  div.style.cssText='gap:6px;flex-wrap:wrap;margin-top:8px;width:100%';
  div.innerHTML=`${['admin','client','livreur'].includes(role)?`<button class="btn sm" type="button" onclick="techProof(${id})">${icon('shield')}Preuve scellée</button>`:''}
   ${role==='admin'?`<button class="btn sm" type="button" onclick="techPanel()">${icon('scan')}Technologies</button>`:''}`;
  if(div.innerHTML.trim())box.appendChild(div);
}
const techBaseParcelDetail=parcelDetail;
parcelDetail=async function(id){await techBaseParcelDetail.apply(this,arguments);try{techInjectRow(id)}catch(e){}};

/* ---- assistant public (règles) collé au widget de suivi ---- */
window.techAttachAssistant=(ii,oi)=>{
  const input=document.getElementById(ii||'lp-track-input2');
  const box=document.getElementById(oi||'lp-track-out2');
  if(!box||box.querySelector('.tech-assistant'))return;
  const wrap=document.createElement('div');
  wrap.className='tech-assistant card';
  wrap.style.cssText='padding:10px;margin-top:8px';
  wrap.innerHTML=`<b>🤖 Assistant ORIENTAL24</b>
   <div class="form-hint">Question en français ou darija : position, arrivée, code OTP, paiement…</div>
   <div style="display:flex;gap:6px;flex-wrap:wrap;margin:6px 0">
    ${['Où est mon colis ?','Quand l’arrivée ?','Code OTP ?','Paiement COD ?'].map(q=>`<button type="button" class="btn sm tech-achip" data-q="${esc(q)}">${esc(q)}</button>`).join('')}</div>
   <input class="tech-q" placeholder="Votre question…" style="width:100%;padding:8px;border:1px solid #d7deea;border-radius:8px" autocomplete="off">
   <div class="tech-reply form-hint" style="margin-top:6px;min-height:16px"></div>`;
  box.appendChild(wrap);
  const send=async(q)=>{if(!q)return;const t=(input&&input.value||'').trim();
    try{const r=await api('/public/assistant','POST',{q,tracking:t});wrap.querySelector('.tech-reply').textContent='🤖 '+r.reply;}
    catch(e){wrap.querySelector('.tech-reply').textContent='🤖 '+(e.message||'Assistant indisponible.')}};
  wrap.querySelectorAll('.tech-achip').forEach(b=>{b.onclick=()=>send(b.getAttribute('data-q'))});
  wrap.querySelector('.tech-q').addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();const v=e.target.value;e.target.value='';send(v)}});
};
const techBasePublicTrack=window.publicTrack;
window.publicTrack=async function(ev,ii,oi){await techBasePublicTrack.apply(this,arguments);try{techAttachAssistant(ii||'lp-track-input',oi||'lp-track-out');if(ii==='lp-track-input2'||!ii)techAttachAssistant('lp-track-input2','lp-track-out2')}catch(e){}};

/* ===== v1.10.0 « Flotte connectée & livraison augmentée » ===== */
window.smartPanel=async()=>{
  let v,pp,pay,fleet;
  try{[v,pp,pay,fleet]=await Promise.all([api('/vehicles'),api('/pickup-points'),api('/payments'),api('/insights/fleet')]);}
  catch(e){toast(e.message||'Module flotte indisponible',true);return}
  const types=(v.types||[]).map(t=>`<option value="${esc(t.type)}">${esc(t.label)} · ${t.co2_per_km} kg/km · ${t.speed_kmh} km/h</option>`).join('');
  const vRows=(v.rows||[]).map(r=>{
    const m=(v.maintenance||[]).find(x=>x.id===r.id)||{};
    return `<tr><td><b>${esc(r.label)}</b><br><span class="muted" style="font-size:10px">${esc(r.type_label)} · ${esc(r.plate||'sans plaque')}</span></td>
    <td>${esc(r.driver||'—')}</td><td>${Math.round(r.km||0)} km</td>
    <td>${r.battery_pct!=null?Math.round(r.battery_pct)+' %':'—'}</td>
    <td><span class="tag">${esc(r.state||'disponible')}</span></td>
    <td title="${esc((m.reasons||[]).join(' / '))}"><b style="color:${(m.wear_score||0)>=80?'#f87171':((m.wear_score||0)>=50?'#f59e0b':'#0a7a5c')}">${m.wear_score||0}</b>${(m.reasons||[]).length?'<br><span style="font-size:9px;color:#f59e0b">'+esc((m.reasons||[]).join(' · '))+'</span>':''}</td>
    <td style="white-space:nowrap">
     <button class="btn sm" type="button" onclick="smartVState(${r.id},'disponible')">🟢</button>
     <button class="btn sm" type="button" onclick="smartVState(${r.id},'en_tournee')">🚚</button>
     <button class="btn sm" type="button" onclick="smartVState(${r.id},'maintenance')">🔧</button>
     <button class="btn sm" type="button" onclick="smartVTelemetry(${r.id})">📡</button>
     <button class="btn sm" type="button" onclick="smartVService(${r.id})">🛠️</button></td></tr>`;}).join('');
  const alRows=((v.maintenance||[]).filter(m=>(m.reasons||[]).length)).map(m=>`<tr><td>${esc(m.label)}</td><td class="muted" style="font-size:11px">${esc((m.reasons||[]).join(' · '))}</td><td><b>${m.wear_score}</b></td></tr>`).join('');
  const ppRows=(pp.rows||[]).map(r=>`<tr><td><b>${esc(r.name)}</b></td><td>${esc(r.city||'—')}</td><td><span class="tag">${esc(r.kind)}</span></td>
    <td>${r.assigned||0} colis routés</td></tr>`).join('');
  const payRows=(pay.rows||[]).slice(0,12).map(r=>`<tr><td class="mono">${esc(r.reference)}</td><td class="mono">${esc(r.tracking)}</td>
    <td>${Number(r.amount).toFixed(2)} MAD</td><td><span class="tag">${esc(r.method)}</span></td><td><span class="tag">${esc(r.status)}</span></td>
    <td style="white-space:nowrap">${r.links&&r.links.whatsapp?`<a class="btn sm" target="_blank" rel="noopener" href="${r.links.whatsapp}">wa</a> <a class="btn sm" target="_blank" rel="noopener" href="${r.links.sms}">sms</a>`:''}
    ${r.status==='demande'?`<button class="btn sm primary" type="button" onclick="smartPayPaid(${r.id})">💵 Encaissé</button>`:''}</td></tr>`).join('');
  const sla=fleet.sla||{};
  modal('Flotte connectée & livraison augmentée',`
   <p class="form-hint" style="margin:0 0 10px">Véhicules connectés (thermique/électrique/vélo/<b>drone</b>/camion) · maintenance prédictive · points relais · jumeau numérique (simulation avant répartition) · e-paiement/mobile money · décisionnel SLA — 100 % local.</p>
   <div class="stats" style="grid-template-columns:1fr 1fr 1fr 1fr">
    ${stat('Véhicules actifs',(v.rows||[]).length,'','box','navy')}
    ${stat('Points relais',(pp.rows||[]).length,'','mapPin','navy')}
    ${stat('Paiements en attente',(pay.rows||[]).filter(r=>r.status==='demande').length,'','creditCard','orange')}
    ${stat('Délai moyen',sla.avg_delivery_hours!=null?String(sla.avg_delivery_hours):'—','h','clock','green',(sla.first_pass_rate!=null?('1er passage '+sla.first_pass_rate+' %'):''))}</div>
   <h3 style="margin:16px 0 6px">🚚 Flotte &amp; maintenance prédictive</h3>
   ${vRows?`<table><thead><tr><th>Véhicule</th><th>Livreur</th><th>Compteur</th><th>Batterie</th><th>État</th><th>Usure</th><th>Actions</th></tr></thead><tbody>${vRows}</tbody></table>`:'<p class="muted">Aucun véhicule — déclarez-en un ci-dessous.</p>'}
   ${alRows?`<h3 style="margin:14px 0 6px">🔔 Alertes entretien</h3><table><thead><tr><th>Véhicule</th><th>Cause</th><th>Usure</th></tr></thead><tbody>${alRows}</tbody></table>`:''}
   <div class="flex" style="gap:6px;margin-top:8px;flex-wrap:wrap">
    <select id="sv-type" style="padding:6px;border:1px solid #d7deea;border-radius:6px">${types}</select>
    <input id="sv-label" placeholder="Libellé (obligatoire)" style="width:150px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="sv-plate" placeholder="Plaque" style="width:90px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="sv-battery" type="number" min="0" max="100" placeholder="batterie %" style="width:90px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" type="button" onclick="smartVAdd()">Ajouter le véhicule</button></div>
   <h3 style="margin:16px 0 6px">🏢 Points relais</h3>
   ${ppRows?`<table><thead><tr><th>Point</th><th>Ville</th><th>Type</th><th>Colis routés</th></tr></thead><tbody>${ppRows}</tbody></table>`:'<p class="muted">Aucun point relais.</p>'}
   <div class="flex" style="gap:6px;margin-top:8px;flex-wrap:wrap">
    <input id="sp-name" placeholder="Nom du point" style="width:180px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <input id="sp-city" placeholder="Ville" style="width:120px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <select id="sp-kind" style="padding:6px;border:1px solid #d7deea;border-radius:6px"><option value="relais">relais</option><option value="agence">agence</option></select>
    <button class="btn sm primary" type="button" onclick="smartPointAdd()">Créer le point</button></div>
   <h3 style="margin:16px 0 6px">💳 E-paiement &amp; mobile money</h3>
   ${payRows?`<table><thead><tr><th>Référence</th><th>Suivi</th><th>Montant</th><th>Mode</th><th>Statut</th><th>Envoi / encaissement</th></tr></thead><tbody>${payRows}</tbody></table>`:'<p class="muted">Aucune demande — créez-la depuis la fiche colis (bouton Paiement).</p>'}
   <p class="form-hint">Références <span class="mono">PAY-…</span> rapprochables aux factures · envoi par liens WhatsApp/SMS (mobile money, CIH Pay, paiement à la livraison) — aucun agrégateur tiers.</p>
   <h3 style="margin:16px 0 6px">🧬 Jumeau numérique — simuler la journée avant répartition</h3>
   <div class="flex" style="gap:6px;align-items:center;flex-wrap:wrap">
    <input id="sim-trials" type="number" min="5" max="50" value="20" style="width:80px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <button class="btn sm primary" type="button" onclick="smartSimRun()">🎲 Lancer la simulation (Monte-Carlo)</button>
    <button class="btn sm" type="button" onclick="dispatchApply&&dispatchApply()">✅ Répartition recommandée</button></div>
   <div id="sim-out" style="margin-top:8px"></div>
   <h3 style="margin:16px 0 6px">📊 Décisionnel big data &amp; SLA</h3>
   <p class="form-hint">Délai moyen : <b>${sla.avg_delivery_hours!=null?esc(String(sla.avg_delivery_hours)):'—'} h</b> · taux au 1er passage : <b>${sla.first_pass_rate!=null?esc(String(sla.first_pass_rate)):'—'} %</b> · taux à J+1 : <b>${sla.j1_rate!=null?esc(String(sla.j1_rate)):'—'} %</b></p>
   <div class="flex" style="gap:6px;flex-wrap:wrap">
    <button class="btn sm" type="button" onclick="smartCsv('parcels')">⬇️ Colis CSV</button>
    <button class="btn sm" type="button" onclick="smartCsv('events')">⬇️ Événements CSV</button>
    <button class="btn sm" type="button" onclick="smartCsv('deliveries')">⬇️ Livraisons CSV</button>
    <button class="btn sm" type="button" onclick="smartCsv('vehicles')">⬇️ Flotte CSV</button></div>`,true);
};
window.smartVAdd=async()=>{
  const g=id=>{const el=document.getElementById(id);return el?el.value.trim():''};
  if(!g('sv-label')){toast('Libellé obligatoire.',true);return}
  try{await api('/vehicles','POST',{type:g('sv-type'),label:g('sv-label'),plate:g('sv-plate'),battery_pct:g('sv-battery')===''?null:Number(g('sv-battery'))});
    toast('Véhicule enregistré ✓');closeModal();smartPanel();}
  catch(e){toast(e.message,true)}
};
window.smartVState=async(id,st)=>{try{await api('/vehicles/'+id,'PATCH',{state:st});toast('État : '+st);closeModal();smartPanel();}catch(e){toast(e.message,true)}};
window.smartVService=async(id)=>{
  const note=prompt('Entretien effectué — note (vidange, pneus, révision batterie…) :','Entretien périodique');
  if(note===null)return;
  try{const r=await api('/vehicles/'+id+'/service','POST',{note});
    toast('Entretien journalisé ✓ — pensez à prévenir le livreur');
    if(r.links&&r.links.whatsapp)window.open(r.links.whatsapp,'_blank','noopener');
    closeModal();smartPanel();}
  catch(e){toast(e.message,true)}
};
window.smartVTelemetry=async(id)=>{
  const km=prompt('Kilométrage actuel :','0');if(km===null)return;
  const b=prompt('Batterie % (vide si N/A) :','');if(b===null)return;
  try{await api('/vehicles/'+id+'/telemetry','POST',{km:Number(km)||0,battery_pct:b===''?null:Number(b)});
    toast('Télémétrie enregistrée ✓');closeModal();smartPanel();}
  catch(e){toast(e.message,true)}
};
window.smartPointAdd=async()=>{
  const g=id=>{const el=document.getElementById(id);return el?el.value.trim():''};
  if(!g('sp-name')){toast('Nom obligatoire.',true);return}
  try{await api('/pickup-points','POST',{name:g('sp-name'),city:g('sp-city'),kind:g('sp-kind'),lockers:0});
    toast('Point relais créé ✓');closeModal();smartPanel();}
  catch(e){toast(e.message,true)}
};
window.smartPayPaid=async(id)=>{try{await api('/payments/'+id+'/paid','POST',{});toast('Paiement encaissé ✓');closeModal();smartPanel();}catch(e){toast(e.message,true)}};
window.smartSimRun=async()=>{
  const n=Number(document.getElementById('sim-trials').value)||20;
  let j;try{j=await api('/dispatch/simulate?trials='+n)}catch(e){toast(e.message,true);return}
  const s=j.simulation||{};
  const lotRows=(j.lots||[]).map(l=>`<tr><td>${esc(l.name)}</td><td>${l.added}</td><td>${Math.round(l.km_est)} km</td><td>${l.base_min} min</td><td>${l.co2_kg} kg</td></tr>`).join('');
  document.getElementById('sim-out').innerHTML=`
   <div class="stats" style="grid-template-columns:1fr 1fr 1fr 1fr">
    ${stat('À l\u2019heure',String(s.on_time_rate!=null?s.on_time_rate:0),'%','check', (s.on_time_rate||0)>=85?'green':'orange')}
    ${stat('Fin p90',String(s.finish_p90_min||0),'min','clock','navy')}
    ${stat('Lots en retard',String(s.late_lot_rate!=null?s.late_lot_rate:0),'%','alert','orange')}
    ${stat('CO₂ simulé',String(s.co2_kg!=null?s.co2_kg:0),'kg','box','navy')}</div>
   <p class="form-hint">${esc(j.method||'')} — <b>${esc(j.recommendation||'')}</b></p>
   ${lotRows?`<table><thead><tr><th>Livreur</th><th>Colis</th><th>km</th><th>Durée base</th><th>CO₂</th></tr></thead><tbody>${lotRows}</tbody></table>`:''}`;
  toast('Simulation terminée ('+j.trials+' tirages)');
};
window.smartCsv=async(kind)=>{
  try{const r=await fetch('/api/exports/'+kind+'.csv',{credentials:'same-origin'});
    if(!r.ok){throw new Error('Export refusé')}
    const b=await r.blob();const a=document.createElement('a');
    a.href=URL.createObjectURL(b);a.download='oriental24-'+kind+'.csv';document.body.appendChild(a);a.click();a.remove();
    toast('Export '+kind+' téléchargé ✓');}
  catch(e){toast(e.message,true)}
};

/* ---- fiche colis : point relais, paiement ---- */
window.smartPointSet=async(id)=>{
  let pp;try{pp=await api('/pickup-points')}catch(e){toast(e.message,true);return}
  const opts=(pp.rows||[]).map(r=>`<option value="${r.id}">${esc(r.name)} (${esc(r.city||'—')})</option>`).join('');
  modal('Retrait au point relais — colis #'+id,`
   <p class="form-hint">Routage du colis vers un point relais : au dépôt, un <b>code de retrait à 6 chiffres</b> part au client par WhatsApp/SMS, vérifié au comptoir.</p>
   <select id="sp-choose" style="width:100%;padding:8px;border:1px solid #d7deea;border-radius:8px;margin:8px 0">
    <option value="">— domicile (aucun point) —</option>${opts}</select>
   <button class="btn primary sm" type="button" onclick="smartPointSetSave(${id})">Enregistrer le routage</button>`,true);
};
window.smartPointSetSave=async(id)=>{
  const v=document.getElementById('sp-choose').value;
  try{await api('/parcels/'+id+'/pickup-point','POST',{point_id:v?Number(v):null});
    toast(v?'Colis routé vers le point relais ✓':'Retrait à domicile ✓');closeModal();parcelDetail(id);}
  catch(e){toast(e.message,true)}
};
window.smartLocker=async(id)=>{
  let d;try{d=await api('/parcels/'+id+'/locker')}catch(e){toast(e.message,true);return}
  const rows=(d.rows||[]).map(r=>`<tr><td>${esc(r.point_name)}</td><td class="mono"><b style="font-size:16px">${esc(r.code)}</b></td>
    <td class="muted" style="font-size:11px">${esc(String(r.delivered_at||'').slice(0,16))}</td>
    <td>${r.picked_at?'<span class="tag">retiré</span>':`<input id="lk-code-${r.id}" placeholder="code" maxlength="6" style="width:70px;padding:5px;border:1px solid #d7deea;border-radius:6px"> <button class="btn sm primary" type="button" onclick="smartLockerPick(${r.id},${id})">Valider</button>`}</td></tr>`).join('');
  modal('Point de retrait & code — colis #'+id,
   rows?`<table><thead><tr><th>Point</th><th>Code</th><th>Déposé le</th><th>Retrait</th></tr></thead><tbody>${rows}</tbody></table>`:'<p class="muted">Aucun point de retrait affecté — routez le colis vers un point relais, le code sera généré au dépôt.</p>',true);
};
window.smartLockerPick=async(lid,pid)=>{
  const code=document.getElementById('lk-code-'+lid).value.trim();
  try{await api('/lockers/'+lid+'/pick','POST',{code});toast('Colis retiré ✓');closeModal();smartLocker(pid);}
  catch(e){toast(e.message,true)}
};
window.smartPay=async(id)=>{
  modal('Demande de paiement — colis #'+id,`
   <p class="form-hint">E-paiement / mobile money : la demande porte une référence unique <span class="mono">PAY-…</span> et part par lien WhatsApp/SMS (CIH Pay, cash-plus, encaissement livreur) — aucun agrégateur tiers.</p>
   <div class="flex" style="gap:6px;flex-wrap:wrap;margin:8px 0">
    <input id="pay-amount" type="number" step="0.01" placeholder="Montant MAD" style="width:130px;padding:6px;border:1px solid #d7deea;border-radius:6px">
    <select id="pay-method" style="padding:6px;border:1px solid #d7deea;border-radius:6px">
     <option value="lien">Lien de paiement</option><option value="mobile">Mobile money</option><option value="especes">Espèces à la livraison</option></select>
    <button class="btn sm primary" type="button" onclick="smartPaySend(${id})">Créer la demande</button></div>`,true);
};
window.smartPaySend=async(id)=>{
  const amount=Number(document.getElementById('pay-amount').value);
  const method=document.getElementById('pay-method').value;
  try{const r=await api('/parcels/'+id+'/payment','POST',{amount,method});
    closeModal();
    modal('Demande '+r.reference,`<p style="margin:6px 0">${esc(r.text)}</p>
     <div class="flex" style="gap:6px"><a class="btn primary sm" target="_blank" rel="noopener" href="${r.links.whatsapp}">Envoyer WhatsApp</a>
     <a class="btn sm" target="_blank" rel="noopener" href="${r.links.sms}">Envoyer SMS</a></div>`,true);}
  catch(e){toast(e.message,true)}
};

/* injection fiche (après techInjectRow) */
function smartInjectRow(id){
  const box=document.querySelector('.modal .parcel-command-actions')||document.querySelector('.modal .parcel-command-grid');
  if(!box||box.querySelector('.smart-row'))return;
  const role=(S&&S.user&&S.user.role)||'';
  const div=document.createElement('div');
  div.className='smart-row flex';
  div.style.cssText='gap:6px;flex-wrap:wrap;margin-top:6px;width:100%';
  div.innerHTML=`${role==='admin'?`<button class="btn sm" type="button" onclick="smartPointSet(${id})">🏢 Point relais</button>
   <button class="btn sm" type="button" onclick="smartPay(${id})">💳 Paiement</button>`:''}
   ${role==='admin'?`<button class="btn sm" type="button" onclick="smartPanel()">🚚 Flotte &amp; relais</button>`:''}`;
  if(div.innerHTML.trim())box.appendChild(div);
}
const smartBaseInjectRow=techInjectRow;
techInjectRow=function(id){smartBaseInjectRow(id);try{smartInjectRow(id)}catch(e){}};
