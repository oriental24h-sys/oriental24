/* v1.8.0 « Tour de contrôle » : positions live, KPI du jour, carte SVG du Maroc, alertes 48 h,
   répartition intelligente (blocs par ville + 2-opt), code client OTP et suivi public.
   Vue admin/agent — le livreur pousse sa position depuis son app terrain. Aucune API externe. */
const TOUR_GEO={'Oujda':[34.681,-1.912],'Casablanca':[33.573,-7.5898],'Rabat':[34.0209,-6.8416],'Salé':[34.0389,-6.8164],
 'Marrakech':[31.6295,-7.9811],'Tanger':[35.7595,-5.834],'Fès':[34.0331,-5.0003],'Meknès':[33.8935,-5.5473],
 'Agadir':[30.4278,-9.5981],'Tétouan':[35.5785,-5.3684],'Berkane':[34.929,-1.979],'Nador':[35.1684,-2.9284],
 'El Jadida':[33.2309,-8.4997],'Kénitra':[34.261,-6.5802],'Taza':[34.2214,-4.0071],'Ouarzazate':[30.9188,-6.8825],
 'Laâyoune':[27.1536,-13.2033],'Dakhla':[23.6848,-15.9587],'Essaouira':[31.5085,-9.7596],'Safi':[32.3017,-9.2373],
 'Mohammedia':[33.7205,-7.3817],'Témara':[34.267,-6.9126],'Beni Mellal':[32.3373,-6.3498],'Al Hoceïma':[35.2515,-3.9375],
 'Errachidia':[31.9314,-4.4247],'Midelt':[32.6837,-4.7486],'Azilal':[32.0,6.35],'Chefchaouen':[35.1683,-5.2696],
 'Ouezzane':[34.7633,-5.5813],'Taourirt':[34.6867,-1.2653],'Jerada':[34.2967,-1.6353],'Guercif':[34.2264,-2.176],
 'Taounate':[34.5331,-4.4586],'Sefrou':[33.8573,-5.1661],'Ifrane':[33.5253,-5.1098],'Khouribga':[32.8823,-6.909],
 'Berrechid':[33.3664,-7.59],'Settat':[33.0016,-7.6619],'Youssoufia':[32.2747,-8.5278],'Taroudant':[30.4645,-8.8874],
 'Inezgane':[30.3905,-9.5097],'Guelmim':[28.9869,-10.0527],'Smara':[26.7389,-11.6764]};
const tourPx=(lat,lng)=>({x:(lng+17.9)/16.4*1000,y:(36.0-lat)/15.0*900});
const TOUR_OUTLINE=[[-6.3,35.9],[-2.2,35.1],[-1.7,34.5],[-3.7,33.6],[-7.5,30.9],[-8.7,27.7],[-11.96,25.93],[-13.2,24.9],[-15.5,22.5],[-16.0,21.2],[-17.1,21.4],[-15.9,23.1],[-14.9,25.1],[-14.0,26.4],[-12.9,27.9],[-11.1,28.5],[-9.6,30.4],[-9.8,31.5],[-9.2,32.3],[-8.5,33.2],[-7.6,33.6],[-6.8,34.0],[-6.6,34.3],[-5.9,35.3]];
const tourAgo=a=>a==null?'jamais':(a<1?'à l’instant':'il y a '+a+' min');

function tourMap(drivers){
  const pts=TOUR_OUTLINE.map(([la,ln])=>{const p=tourPx(la,ln);return p.x.toFixed(0)+','+p.y.toFixed(0)}).join(' ');
  const dots=drivers.filter(d=>d.pos).map(d=>{const p=tourPx(d.pos.lat,d.pos.lng);
    return `<g style="cursor:pointer" onclick="tourDriver(${d.id})"><title>${esc(d.name)} — ${tourAgo(d.pos.ago_min)}</title>
      <circle cx="${p.x.toFixed(0)}" cy="${p.y.toFixed(0)}" r="15" fill="#f97316" opacity="0.3"><animate attributeName="r" values="11;26;11" dur="2.6s" repeatCount="indefinite"/></circle>
      <circle cx="${p.x.toFixed(0)}" cy="${p.y.toFixed(0)}" r="8" fill="#ea580c" stroke="#fff" stroke-width="2.5"/></g>`}).join('');
  return `<div class="card" style="padding:10px"><div class="card-head"><h3>Livreurs en ligne</h3><span class="date-pill">${drivers.filter(d=>d.pos).length}/${drivers.length} positionnent</span></div>
    <svg viewBox="0 0 1000 900" style="width:100%;height:auto;display:block" role="img" aria-label="Carte des livreurs en tournée">
    <polygon points="${pts}" fill="#0f2f2b" stroke="#12b8a6" stroke-width="3" stroke-linejoin="round"/>${dots}</svg>
    <p class="muted" style="font-size:11px;margin:6px 0 0">Points = dernière position GPS transmise par les livreurs (auto à chaque changement de statut, ou bouton « Position »).</p></div>`;
}
function tourControlView(d){
  const k=d.kpis||{};
  const cards=(d.drivers||[]).map(r=>`<div class="stat"><div class="stat-top">${esc(r.name)}
      <span class="stat-icon ${r.pos?'green':'navy'}">${icon(r.pos?'pin':'clock')}</span></div>
    <div class="stat-value" style="font-size:16px">${r.stops_out} arrêt${r.stops_out>1?'s':''} <small style="font-size:11px">${r.pos?tourAgo(r.pos.ago_min):'sans position'}</small></div>
    <div class="stat-foot">${r.done_today} livré${r.done_today>1?'s':''} · ${(r.cod_today||0).toFixed(0)} MAD COD · ETA ~${r.eta_min} min
      <span class="flex" style="gap:4px;margin-top:6px"><button class="btn sm" type="button" onclick="tourDispatchOne(${r.id},'${esc(r.name)}')">${icon('scan')}Tout envoyer ici</button></span></div></div>`).join('');
  const rows=(d.alerts||[]).map(a=>`<tr><td class="mono">${esc(a.tracking)}</td><td>${esc(a.recipient)}</td><td>${esc(a.city||'—')}</td>
    <td><span class="tag">${esc(a.status)}</span></td><td style="color:#f59e0b"><b>${a.days} j</b></td>
    <td><button class="btn sm" type="button" onclick="parcelDetail(${a.id})">${icon('eye')}Ouvrir</button></td></tr>`).join('');
  const un=(d.unassigned_by_city||[]).map(x=>`<tr><td>${esc(x.city)}</td><td class="mono">${x.count}</td>
    <td class="muted" style="font-size:12px">${x.parcel_ids.slice(0,8).join(', ')}${x.parcel_ids.length>8?' …':''}</td></tr>`).join('');
  return heading('Tour de contrôle','Positions, charge des livreurs, retards et répartition intelligente — actualisation automatique chaque minute.',
      `<button class="btn sm" type="button" onclick="renderView()">${icon('refresh')}Actualiser</button>
       <button class="btn sm" type="button" onclick="techPanel()">${icon('scan')}Technologies</button>
       <button class="btn sm primary" type="button" onclick="tourDispatchPanel()">${icon('scan')}Répartition intelligente</button>`)+
  `<div class="stats">${stat('En tournée',k.out_today||0,'','truck','navy')}${stat('Livrés aujourd’hui',k.delivered_today||0,'','check','green')}
    ${stat('COD encaissé',((k.cod_today||0)/1000).toFixed(1),'k MAD','wallet','orange')}${stat('Silence > 48 h',k.late_48h||0,'','alert',k.late_48h>0?'red':'navy')}
    ${stat('Non affectés',k.unassigned||0,'','box',k.unassigned>0?'orange':'green')}</div>
  <div class="grid" style="grid-template-columns:1fr 1.2fr;gap:12px;align-items:start">${tourMap(d.drivers||[])}
    <div class="card"><div class="card-head"><h3>Équipe du jour</h3><span class="date-pill">${(d.drivers||[]).length} livreurs actifs</span></div>
    <div class="stats" style="grid-template-columns:1fr 1fr">${cards||'<div class="empty">Aucun livreur actif.</div>'}</div></div></div>
  <div class="grid" style="grid-template-columns:1.2fr 1fr;gap:12px;align-items:start">
    <div class="card"><div class="card-head"><h3>Colis sans nouvelle depuis 48 h</h3>${(d.alerts||[]).length?`<span class="tag">${d.alerts.length}</span>`:''}</div>
      ${rows?`<table><thead><tr><th>Suivi</th><th>Destinataire</th><th>Ville</th><th>Statut</th><th>Retard</th><th></th></tr></thead><tbody>${rows}</tbody></table>`:'<p class="muted">Aucun colis en silence — tout le monde avance. ✓</p>'}</div>
    <div class="card"><div class="card-head"><h3>Non affectés par ville</h3></div>
      ${un?`<table><thead><tr><th>Ville</th><th>Colis</th><th>IDs</th></tr></thead><tbody>${un}</tbody></table>`:'<p class="muted">Rien à affecter. ✓</p>'}</div></div>`;
}
window.tourDriver=id=>{
  const r=((S.tower||{}).drivers||[]).find(x=>x.id===id);if(!r)return;
  modal('Livreur — '+r.name,`<div class="stats">
   ${stat('Arrêts en cours',r.stops_out,'','truck','navy')}${stat('Livrés aujourd’hui',r.done_today,'','check','green')}
   ${stat('COD du jour',(r.cod_today||0).toFixed(0),'MAD','wallet','orange')}
   ${stat('Dernière position',r.pos?(Math.round(r.pos.lat*1000)/1000)+', '+(Math.round(r.pos.lng*1000)/1000):'—','','pin',r.pos?'green':'navy',tourAgo(r.pos?r.pos.ago_min:null))}</div>
   ${r.pos?`<div style="margin-top:10px"><a class="btn sm" target="_blank" rel="noopener" href="https://www.google.com/maps?q=${r.pos.lat},${r.pos.lng}">${icon('pin')}Ouvrir dans Google Maps</a></div>`:''}`);};
window.tourDispatchPanel=async()=>{
  let d;try{d=await api('/dispatch/suggest')}catch(e){toast(e.message||'Répartition indisponible',true);return}
  window._tourSugg=d;
  modal('Répartition intelligente',`<p class="form-hint" style="margin-bottom:8px">${d.total} colis non affectés regroupés en blocs par ville, tournées optimisées (2-opt) et charge équilibrée entre livreurs. Appliquer = affectation immédiate via le dispatch existant.</p>
   ${(d.rows||[]).map((r,i)=>`<div class="stat" style="margin:6px 0"><div class="stat-top">${esc(r.name)}
     <span class="stat-icon navy">${icon('scan')}</span></div>
    <div class="stat-value" style="font-size:15px">+${r.added} colis <small>${r.km_est.toFixed(0)} km · ETA ~${r.eta_min} min</small></div>
    <div class="stat-foot">${r.cities.map(esc).join(' · ')} · charge ${r.load_before} → ${r.load_before+r.added}
      <span style="margin-top:6px"><button class="btn sm primary" type="button" onclick="tourApplyRow(${i})">${icon('check')}Appliquer ce lot</button></span></div></div>`).join('')||'<p class="muted">Rien à répartir.</p>'}`);};
window.tourApplyRow=async i=>{
  const r=(window._tourSugg&&window._tourSugg.rows||[])[i];if(!r)return;
  const d=await api('/parcels/bulk-assign','POST',{parcel_ids:r.parcel_ids,driver_id:r.driver_id});
  toast(`${(d.report&&d.report.assigned)||r.parcel_ids.length} colis affectés à ${r.name}.`);closeModal();setTimeout(()=>renderView(),300);};
window.tourDispatchOne=async(id,name)=>{
  let d;try{d=await api('/dispatch/suggest')}catch(e){toast(e.message||'Répartition indisponible',true);return}
  const ids=(d.rows||[]).reduce((a,r)=>a.concat(r.parcel_ids),[]);
  if(!ids.length){toast('Aucun colis non affecté.');return}
  const res=await api('/parcels/bulk-assign','POST',{parcel_ids:ids,driver_id:id});
  toast(`${(res.report&&res.report.assigned)||ids.length} colis affectés à ${name} (blocs entiers par ville, tournées conservées).`);renderView();};
window.openParcelOtp=async id=>{
  const p=await api('/parcels/'+id);const on=!!p.otp_required;
  modal('Code client (OTP) — '+esc(p.tracking),`
   <p class="form-hint" style="margin-bottom:8px">Quand le code est actif, le livreur ne peut marquer « Livré » qu’avec le code à 4 chiffres transmis au client (SMS/WhatsApp). Le code s’affiche ici pour le support.</p>
   ${p.otp_code?`<div class="stat"><div class="stat-top">Code en cours<span class="stat-icon orange">${icon('shield')}</span></div>
     <div class="stat-value mono" style="letter-spacing:8px">${esc(p.otp_code)}</div>
     <div class="stat-foot">${p.otp_verified_at?'✓ vérifié à la livraison ('+esc(String(p.otp_verified_at).slice(0,16))+')':'pas encore vérifié'}</div></div>`:'<p class="muted">Aucun code actif pour ce colis.</p>'}
   <div style="margin-top:10px"><button class="btn primary sm" type="button" id="otp-toggle">${on?'Désactiver le code':'Activer (ou régénérer) le code'}</button></div>`);
  document.getElementById('otp-toggle').onclick=async()=>{
    const r=await api('/parcels/'+id+'/otp','POST',{enabled:!on});
    toast(r.otp?('Code client actif : '+r.otp):'Code client retiré.');closeModal();};};
/* ---- suivi public (page d’accueil, aucune session requise) ---- */
window.publicTrack=async (ev,ii,oi)=>{
  ev&&ev.preventDefault&&ev.preventDefault();
  const el=document.getElementById(ii||'lp-track-input');if(!el)return;
  const code=String(el.value||'').trim();const box=document.getElementById(oi||'lp-track-out');
  if(!code){el.focus();return}
  try{
    const d=await api('/public/track/'+encodeURIComponent(code));
    const hist=(d.history||[]).map(h=>`<li>${esc(h.status)} <span class="muted">${esc(String(h.date||'').slice(0,16).replace('T',' '))}</span></li>`).join('');
    box.innerHTML=`<div class="card" style="padding:12px;margin-top:8px"><b class="mono">${esc(d.tracking)}</b> — <span class="tag">${esc(d.status)}</span>
      ${d.city?`<div class="muted" style="margin-top:4px">${icon('pin')}${esc(d.city)} · dernière étape ${esc(String(d.updated_at||'').slice(0,16).replace('T',' '))}</div>`:''}
      ${d.driver_first_name?`<div style="margin-top:6px">🛵 ${esc(d.driver_first_name)} est en route${d.eta?` · ${esc(d.eta)}`:''} · <a href="tel:${esc(d.driver_phone||'')}" class="mono">${esc(d.driver_phone||'')}</a></div>`:''}
      ${d.gps?`<div class="muted mono" style="font-size:11px;margin-top:2px">position livreur : ${d.gps.lat.toFixed(4)}, ${d.gps.lng.toFixed(4)}</div>`:''}
      ${(d.messages||[]).length?`<div style="margin-top:6px">${d.messages.map(m=>`<div class="form-hint">📨 ${esc(m.text)} <span class="muted">${esc(String(m.date||'').slice(11,16))}</span></div>`).join('')}</div>`:''}
      ${hist?`<details style="margin-top:6px"><summary class="muted" style="cursor:pointer">Dernières étapes</summary><ul style="margin:6px 0 0 16px;font-size:12px">${hist}</ul></details>`:''}</div>`;
  }catch(e){box.innerHTML=`<div class="card" style="padding:12px;margin-top:8px"><p style="color:#f87171">${esc(e.message||'Colis introuvable.')}</p></div>`}
};
window.publicTrack2=ev=>publicTrack(ev,'lp-track-input2','lp-track-out2');
window.lpTrackForm=()=>`<form style="display:flex;gap:8px;flex-wrap:wrap" onsubmit="publicTrack2(event)">
  <input id="lp-track-input2" class="lp-input" placeholder="Votre numéro de suivi (ex. O24-…)" autocomplete="off" style="flex:1;min-width:200px">
  <button class="lp-btn lp-primary" type="submit">Suivre ma commande</button></form><div id="lp-track-out2" style="margin-top:8px"></div>`;
window.trackForm=()=>`<form style="display:flex;gap:8px;max-width:520px" onsubmit="publicTrack(event)">
  <input id="lp-track-input" placeholder="Numéro de suivi (ex. O24-…)" autocomplete="off" style="flex:1">
  <button class="btn primary" type="submit">${icon('eye')}Suivre</button></form><div id="lp-track-out"></div>`;
