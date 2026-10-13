/* Ramassage live map — extends the existing Tour de contrôle without a mapping JS dependency. */
(function () {
  const TILE = 256;
  const OSM_TILE = 'https://tile.openstreetmap.org';
  const state = {
    data: null, map: null, tiles: null, tileNodes: new Map(), markers: null, routes: null, zonesLayer: null,
    centerLat: 32.35, centerLng: -6.65, zoom: 6, timer: null, resize: null, frame: null,
    selectedJobId: null, selectedDriverId: null, routeKey: '', routeGeo: null,
    routeInfo: null, historyGeo: null, historyLabel: '', placeHubId: null,
    dragging: null, moved: false, lastPoll: null, lastOsrmAt: 0
  };

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const statusLabel = (s) => ({available:'Disponible',busy:'Occupé',rest:'En repos',full:'Chargé',offline:'Hors ligne',gps_off:'GPS désactivé'}[s] || 'Inconnu');
  const statusClass = (s) => ({available:'ok',busy:'busy',rest:'rest',full:'full',offline:'offline',gps_off:'gps'}[s] || 'offline');
  const vehicleGlyph = v => {const t=v?.type||'',label=(v?.label||'').toLowerCase();if(t==='velo')return '🚲';if(t==='drone')return '🛸';if(t==='camion')return '🚚';if(/moto|scooter/.test(label)||t==='moto')return '🏍️';if(t==='electrique')return '⚡';return v?'🚘':'👤';};
  const vehicleSpeed = v => ({velo:15,drone:45,camion:28}[v?.type]||32);
  const distKm = (a,b) => {
    if (!a || !b) return 1e9;
    const rad = x => x * Math.PI / 180;
    const p1=rad(a.lat), p2=rad(b.lat), dp=rad(b.lat-a.lat), dl=rad(b.lng-a.lng);
    const h=Math.sin(dp/2)**2+Math.cos(p1)*Math.cos(p2)*Math.sin(dl/2)**2;
    return 6371*2*Math.atan2(Math.sqrt(h),Math.sqrt(1-h));
  };
  const fmtDistance = n => n == null || !Number.isFinite(Number(n)) ? '—' : Number(n).toFixed(1)+' km';
  const fmtAgo = s => s == null ? 'aucun GPS' : s < 60 ? 'à l’instant' : 'il y a '+Math.floor(s/60)+' min';
  const currentJob = () => (state.data?.ramassage_jobs || []).find(j => j.id === Number(state.selectedJobId));
  const currentDriver = () => (state.data?.map_drivers || []).find(d => d.id === Number(state.selectedDriverId));
  const zoneForJob = job => (state.data?.zones || []).find(z => z.city_id === job?.city_id && z.active);

  function mercator(lat,lng,z) {
    const n=TILE*Math.pow(2,z), latRad=clamp(lat,-85.05112878,85.05112878)*Math.PI/180;
    return {x:(lng+180)/360*n,y:(1-Math.log(Math.tan(latRad)+1/Math.cos(latRad))/Math.PI)/2*n};
  }
  function unmercator(x,y,z) {
    const n=TILE*Math.pow(2,z), lng=x/n*360-180, lat=Math.atan(Math.sinh(Math.PI*(1-2*y/n)))*180/Math.PI;
    return {lat,lng};
  }
  function mapSize() {
    const r=state.map?.getBoundingClientRect();
    return r ? {w:Math.max(1,r.width),h:Math.max(1,r.height)} : {w:1,h:1};
  }
  function pointOnScreen(lat,lng) {
    const {w,h}=mapSize(), c=mercator(state.centerLat,state.centerLng,state.zoom), p=mercator(lat,lng,state.zoom);
    return {x:p.x-c.x+w/2,y:p.y-c.y+h/2};
  }
  function screenToPoint(clientX,clientY) {
    const r=state.map.getBoundingClientRect(), c=mercator(state.centerLat,state.centerLng,state.zoom);
    return unmercator(c.x+clientX-r.left-r.width/2,c.y+clientY-r.top-r.height/2,state.zoom);
  }
  function renderTiles() {
    if (!state.tiles || !state.map) return;
    const {w,h}=mapSize(), z=state.zoom, c=mercator(state.centerLat,state.centerLng,z), n=2**z;
    const left=c.x-w/2, top=c.y-h/2;
    const x0=Math.floor(left/TILE), x1=Math.floor((left+w)/TILE), y0=Math.floor(top/TILE), y1=Math.floor((top+h)/TILE);
    const wanted=new Set();
    for(let ty=y0;ty<=y1;ty++) for(let tx=x0;tx<=x1;tx++) {
      if(ty<0||ty>=n) continue;
      const wrapped=((tx%n)+n)%n,key=`${z}/${wrapped}/${ty}`;wanted.add(key);
      let img=state.tileNodes.get(key);
      if(!img){
        img=document.createElement('img');img.className='rt-tile';img.alt='';img.draggable=false;img.loading='lazy';
        img.referrerPolicy='strict-origin-when-cross-origin';img.src=`${OSM_TILE}/${key}.png`;img.width=TILE;img.height=TILE;
        img.onerror=()=>img.classList.add('rt-tile-error');state.tileNodes.set(key,img);state.tiles.appendChild(img);
      }
      img.style.left=(tx*TILE-left)+'px';img.style.top=(ty*TILE-top)+'px';
    }
    for(const [key,img] of state.tileNodes){if(!wanted.has(key)){img.remove();state.tileNodes.delete(key);}}
  }
  function scheduleMapRender(){
    if(state.frame)return;
    state.frame=requestAnimationFrame(()=>{state.frame=null;renderTiles();renderOverlays();});
  }
  function setCenter(lat,lng,zoom) {
    state.centerLat=clamp(Number(lat),-80,80); state.centerLng=clamp(Number(lng),-180,180);
    if(zoom!=null) state.zoom=clamp(Math.round(Number(zoom)),5,18);
    renderTiles(); renderOverlays();
  }
  function fitPoints(points) {
    const good=(points||[]).filter(p=>p&&Number.isFinite(+p.lat)&&Number.isFinite(+p.lng));
    if(!good.length) return;
    if(good.length===1){setCenter(good[0].lat,good[0].lng,Math.max(state.zoom,13));return;}
    const lats=good.map(p=>+p.lat),lngs=good.map(p=>+p.lng);
    const minLat=Math.min(...lats),maxLat=Math.max(...lats),minLng=Math.min(...lngs),maxLng=Math.max(...lngs);
    const lat=maxLat-minLat,lng=maxLng-minLng;
    const z=lat<0.02&&lng<0.02?15:lat<0.12&&lng<0.12?12:lat<0.5&&lng<0.5?10:lat<2&&lng<2?8:6;
    setCenter((minLat+maxLat)/2,(minLng+maxLng)/2,z);
  }
  function escText(v) { return typeof esc==='function' ? esc(v==null?'':String(v)) : String(v==null?'':v).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])); }

  function suitableDrivers(job) {
    if(!job) return [];
    const target={lat:job.client.lat,lng:job.client.lng};
    return (state.data?.map_drivers||[]).filter(d=>d.online&&d.gps_state==='enabled'&&d.status==='available'&&!d.full_load&&d.vehicle_ok&&d.vehicle&&d.zone_id===job.city_id&&d.pos)
      .map(d=>({...d,distance_km:distKm(d.pos,target),eta_min:Math.max(3,Math.round(distKm(d.pos,target)/vehicleSpeed(d.vehicle)*60+4))}))
      .sort((a,b)=>a.distance_km-b.distance_km||a.id-b.id);
  }

  function renderLists() {
    if(!state.data) return;
    const drivers=state.data.map_drivers||[], jobs=state.data.ramassage_jobs||[];
    const saved=document.getElementById('rt-saved-client');
    if(saved){const current=saved.value;saved.innerHTML=savedClientOptions();if(current)saved.value=current;}
    const citySelect=document.getElementById('rt-city-id');
    if(citySelect){const current=citySelect.value,ready=(state.data.pickup_cities||[]).filter(c=>c.zone_ready);citySelect.innerHTML='<option value="">Détection GPS</option>'+ready.map(c=>`<option value="${c.id}">${escText(c.name)}</option>`).join('');if(current)citySelect.value=current;}
    const jobCount=document.getElementById('rt-job-count');if(jobCount)jobCount.textContent=String((state.data.ramassage_jobs||[]).filter(j=>['pending','assigned','en_route'].includes(j.status)).length);
    const online=drivers.filter(d=>d.online).length;
    const activeCount=jobs.filter(j=>['pending','assigned','en_route'].includes(j.status)).length;
    const activeKpi=document.getElementById('rt-active-kpi');if(activeKpi)activeKpi.textContent=String(activeCount);
    const gpsKpi=document.getElementById('rt-gps-kpi');if(gpsKpi)gpsKpi.textContent=String((state.data.gps_alerts||[]).length);
    const alertBox=document.getElementById('rt-gps-alerts');if(alertBox){const rows=state.data.gps_alerts||[];alertBox.hidden=!rows.length;alertBox.textContent=rows.length?'⚠ GPS désactivé : '+rows.map(x=>x.name).join(' · '):'';}
    const count=document.getElementById('rt-online-count'); if(count) count.textContent=online+' en ligne';
    const refresh=document.getElementById('rt-updated'); if(refresh) refresh.textContent='Actualisé '+new Date().toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
    const check=document.getElementById('rt-auto-dispatch'); if(check) check.checked=!!state.data.auto_dispatch;
    const driverHost=document.getElementById('rt-driver-list');
    if(driverHost) {
      const ordered=[...drivers].sort((a,b)=>Number(b.online)-Number(a.online)||a.name.localeCompare(b.name));
      driverHost.innerHTML=ordered.length?ordered.map(d=>{
        const selected=d.id===Number(state.selectedDriverId), icon=vehicleGlyph(d.vehicle);
        const battery=d.battery_pct==null?'Batterie —':'Batterie '+Math.round(d.battery_pct)+'%';
        const warning=d.gps_state==='disabled'?'GPS désactivé':d.battery_pct!=null&&d.battery_pct<=20?'Batterie faible':!d.vehicle?'Aucun véhicule affecté':'';
        return `<button class="rt-driver-row ${selected?'selected':''}" type="button" onclick="rtSelectDriver(${d.id})">
          <span class="rt-vehicle-icon">${icon}</span><span class="rt-driver-copy"><b>${escText(d.name)}</b>
          <small><i class="rt-dot ${statusClass(d.status)}"></i>${statusLabel(d.status)} · ${escText(d.zone||'Zone inconnue')} · ${fmtAgo(d.pos?.ago_sec)}</small>
          <small>${escText(d.vehicle?.label||'Véhicule non affecté')} · ${battery}${d.full_load?' · ⚠ charge complète':''}${warning?' · ⚠ '+escText(warning):''}</small></span>
          <span class="rt-row-chevron">›</span></button>`;
      }).join(''):'<p class="rt-empty">Aucun livreur enregistré.</p>';
    }
    const jobHost=document.getElementById('rt-job-list');
    if(jobHost) {
      const active=jobs.filter(j=>['pending','assigned','en_route'].includes(j.status)).slice(0,12);
      jobHost.innerHTML=active.length?active.map(j=>{
        const selected=j.id===Number(state.selectedJobId), name=j.client?.name||'Client';
        const assignment=j.driver_name?` · ${escText(j.driver_name)}`:'';
        const canManage=typeof S!=='undefined'&&S.user?.role==='admin';
        const action=j.status==='pending'&&canManage?`<button type="button" class="rt-mini-action" onclick="event.stopPropagation();rtManualAssign(${j.id})">Affecter</button>`:'';
        return `<button class="rt-job-row ${selected?'selected':''}" type="button" onclick="rtSelectJob(${j.id})">
          <span class="rt-job-dot ${escText(j.status)}"></span><span class="rt-job-copy"><b>${escText(name)}</b><small>#${j.id} · ${escText(j.zone||'Zone inconnue')} · ${j.parcels_count} colis${assignment}</small></span>${action}</button>`;
      }).join(''):'<p class="rt-empty">Aucune demande en cours.</p>';
    }
    renderSelected(); renderOverlays();
  }

  function renderSelected() {
    const host=document.getElementById('rt-selected-job'); if(!host) return;
    const job=currentJob();
    if(!job){host.hidden=true;host.innerHTML='';return;}
    host.hidden=false;
    const candidates=suitableDrivers(job), chosen=candidates[0];
    const canManage=typeof S!=='undefined'&&S.user?.role==='admin';
    const info=state.routeInfo;
    const driver=chosen||((job.driver_id)?(state.data?.map_drivers||[]).find(d=>d.id===job.driver_id):null);
    const km=info?.distance_km ?? (driver?.pos?distKm(driver.pos,{lat:job.client.lat,lng:job.client.lng}):null);
    const eta=info?.eta_min ?? (km==null?null:Math.max(3,Math.round(km/vehicleSpeed(driver?.vehicle)*60+4)));
    host.innerHTML=`<div class="rt-selected-head"><div><b>${escText(job.client?.name)}</b><small>Demande #${job.id} · ${escText(job.zone||'Zone inconnue')} · ${job.parcels_count} colis</small></div><button class="rt-close" type="button" onclick="rtSelectJob(null)" aria-label="Fermer">×</button></div>
      <div class="rt-selected-route">${driver?`<b>${escText(driver.name)}</b> · ${fmtDistance(km)} · ETA ~${eta??'—'} min${info?.source==='osrm'?' · route OSRM':''}`:'Aucun livreur approprié en ligne dans cette zone.'}</div>
      <div class="rt-selected-actions"><a class="rt-link-btn" target="_blank" rel="noopener" href="${escText(job.client.maps_url)}">Ouvrir le point</a>${job.status==='pending'&&canManage?`<button class="rt-primary-btn" type="button" onclick="rtManualAssign(${job.id})">Choisir un livreur</button>`:''}${driver?.pos&&driver.phone&&canManage?`<button class="rt-wa-btn" type="button" onclick="rtWhatsapp(${job.id},${driver.id})">WhatsApp au livreur</button>`:''}${job.driver_id?`<span class="rt-assigned-tag">${job.status==='en_route'?'En route':'Affecté à '+escText(job.driver_name||'')}</span>`:''}</div>`;
  }

  function renderOverlays() {
    if(!state.map||!state.data) return;
    const {w,h}=mapSize();
    for(const svg of [state.routes,state.zonesLayer]) if(svg){svg.setAttribute('viewBox',`0 0 ${w} ${h}`);svg.setAttribute('width',w);svg.setAttribute('height',h);svg.replaceChildren();}
    const job=currentJob(), zone=zoneForJob(job);
    if(zone&&state.zonesLayer) {
      const p=pointOnScreen(zone.center_lat,zone.center_lng), latRad=zone.center_lat*Math.PI/180;
      const metersPerPixel=Math.cos(latRad)*2*Math.PI*6378137/(TILE*Math.pow(2,state.zoom));
      const radius=clamp((zone.radius_km*1000)/Math.max(0.01,metersPerPixel),2,3000);
      const c=document.createElementNS('http://www.w3.org/2000/svg','circle');
      c.setAttribute('cx',p.x);c.setAttribute('cy',p.y);c.setAttribute('r',radius);c.setAttribute('class','rt-zone-ring');
      state.zonesLayer.appendChild(c);
    }
    if(state.routes) {
      const addLine=(geo,cls)=>{
        if(!geo||geo.length<2)return;
        const pts=geo.map(p=>{const xy=pointOnScreen(p.lat,p.lng);return `${xy.x},${xy.y}`}).join(' ');
        const line=document.createElementNS('http://www.w3.org/2000/svg','polyline');
        line.setAttribute('points',pts);line.setAttribute('class',cls);state.routes.appendChild(line);
      };
      addLine(state.historyGeo,'rt-history-line'); addLine(state.routeGeo,'rt-route-line');
    }
    const layer=state.markers; layer.replaceChildren();
    const put=(element,lat,lng)=>{
      const xy=pointOnScreen(lat,lng); element.style.left=xy.x+'px';element.style.top=xy.y+'px';layer.appendChild(element);
    };
    (state.data.hubs||[]).forEach(h=>{
      if(h.lat==null||h.lng==null)return;
      const el=document.createElement('button');el.type='button';el.className='rt-marker rt-hub'+(!h.exact_location?' approximate':'');
      el.innerHTML='<span>🏬</span>';el.title=h.name+(h.exact_location?'':' · centre de ville approximatif, emplacement à confirmer');
      el.addEventListener('click',e=>{e.stopPropagation();if(typeof toast==='function')toast(h.name+(h.exact_location?'':' — position approximative'));});
      put(el,h.lat,h.lng);
    });
    const jobs=(state.data.ramassage_jobs||[]).filter(j=>['pending','assigned','en_route'].includes(j.status));
    jobs.forEach(j=>{
      if(!j.client||j.client.lat==null)return;
      const el=document.createElement('button');el.type='button';el.className='rt-marker rt-client '+(j.status==='pending'?'pending':'assigned')+(j.id===Number(state.selectedJobId)?' active':'');
      el.innerHTML='<span>📍</span>';el.title=`${j.client.name} · ramassage #${j.id} · ${j.status}`;
      el.addEventListener('click',e=>{e.stopPropagation();window.rtSelectJob(j.id);});
      put(el,j.client.lat,j.client.lng);
    });
    // Driver-only clustering: as the map zooms in, close-by riders separate naturally.
    const drivers=(state.data.map_drivers||[]).filter(d=>d.pos&&d.pos.lat!=null);
    const groups=[];
    for(const d of drivers){
      const xy=pointOnScreen(d.pos.lat,d.pos.lng);let g=null;
      if(state.zoom<17)g=groups.find(x=>Math.hypot(x.x-xy.x,x.y-xy.y)<44);
      if(g){g.items.push(d);g.x=(g.x*(g.items.length-1)+xy.x)/g.items.length;g.y=(g.y*(g.items.length-1)+xy.y)/g.items.length;}
      else groups.push({x:xy.x,y:xy.y,items:[d]});
    }
    for(const g of groups){
      if(g.items.length>1){
        const el=document.createElement('button');el.type='button';el.className='rt-cluster';el.textContent=String(g.items.length);el.title=g.items.length+' livreurs regroupés';
        el.addEventListener('click',e=>{e.stopPropagation();const lat=g.items.reduce((n,d)=>n+d.pos.lat,0)/g.items.length,lng=g.items.reduce((n,d)=>n+d.pos.lng,0)/g.items.length;setCenter(lat,lng,Math.min(18,state.zoom+2));});
        el.style.left=g.x+'px';el.style.top=g.y+'px';layer.appendChild(el);continue;
      }
      const d=g.items[0],el=document.createElement('button');el.type='button';
      const glyph=vehicleGlyph(d.vehicle);
      el.className='rt-marker rt-driver '+statusClass(d.status)+(d.id===Number(state.selectedDriverId)?' active':'');
      el.innerHTML=`<span>${glyph}</span>${d.battery_pct!=null&&d.battery_pct<=20?'<i class="rt-low-battery">!</i>':''}${d.full_load?'<i class="rt-full-load">▰</i>':''}`;
      el.title=`${d.name} — ${statusLabel(d.status)} · ${fmtAgo(d.pos.ago_sec)}${d.battery_pct==null?'':' · batterie '+Math.round(d.battery_pct)+'%'}`;
      el.addEventListener('click',e=>{e.stopPropagation();window.rtSelectDriver(d.id);});
      put(el,d.pos.lat,d.pos.lng);
    }
  }

  async function drawRoute(job,driver) {
    if(!job||!driver?.pos){state.routeGeo=null;state.routeInfo=null;state.routeKey='';renderSelected();renderOverlays();return;}
    const key=[job.id,driver.id,driver.pos.lat,driver.pos.lng,job.client.lat,job.client.lng].join(':');
    if(key===state.routeKey)return;
    state.routeKey=key;
    const straight=distKm(driver.pos,{lat:job.client.lat,lng:job.client.lng});
    state.routeGeo=[{lat:driver.pos.lat,lng:driver.pos.lng},{lat:job.client.lat,lng:job.client.lng}];
    state.routeInfo={distance_km:straight,eta_min:Math.max(3,Math.round(straight/vehicleSpeed(driver.vehicle)*60+4)),source:'direct'};
    renderSelected();renderOverlays();
    // Aerial vehicles use direct-line estimates; OSRM's public profile is road-driving only.
    if(driver.vehicle?.type==='drone'||Date.now()-state.lastOsrmAt<30000)return;
    // Public OSRM demo router: route geometry/ETA; fall back to the direct-distance estimate if unavailable.
    state.lastOsrmAt=Date.now();
    const url=`https://router.project-osrm.org/route/v1/driving/${driver.pos.lng},${driver.pos.lat};${job.client.lng},${job.client.lat}?overview=full&geometries=geojson`;
    try{
      const r=await fetch(url,{mode:'cors',credentials:'omit',cache:'no-store'});if(!r.ok)throw new Error('route');
      const body=await r.json(),route=body.routes?.[0];if(!route||key!==state.routeKey) return;
      state.routeGeo=(route.geometry?.coordinates||[]).map(p=>({lat:p[1],lng:p[0]}));
      state.routeInfo={distance_km:route.distance/1000,eta_min:Math.max(1,Math.round(route.duration/60)),source:'osrm'};
      renderSelected();renderOverlays();
    }catch(_){/* Keep the honest straight-line distance fallback. */}
  }

  function renderHistorySelects() {
    const select=document.getElementById('rt-history-driver');if(!select)return;
    const old=select.value;
    select.innerHTML='<option value="">Choisir un livreur</option>'+(state.data?.map_drivers||[]).map(d=>`<option value="${d.id}">${escText(d.name)}</option>`).join('');
    if(old)select.value=old;
  }
  function bindMap() {
    state.map.addEventListener('pointerdown',e=>{
      if(e.target.closest('.rt-marker,.rt-cluster,.rt-map-control'))return;
      state.dragging={x:e.clientX,y:e.clientY,cx:mercator(state.centerLat,state.centerLng,state.zoom).x,cy:mercator(state.centerLat,state.centerLng,state.zoom).y};
      state.moved=false;state.map.setPointerCapture?.(e.pointerId);
    });
    state.map.addEventListener('pointermove',e=>{
      if(!state.dragging)return;
      const dx=e.clientX-state.dragging.x,dy=e.clientY-state.dragging.y;
      if(Math.abs(dx)+Math.abs(dy)>4)state.moved=true;
      const pos=unmercator(state.dragging.cx-dx,state.dragging.cy-dy,state.zoom);
      state.centerLat=pos.lat;state.centerLng=pos.lng;scheduleMapRender();
    });
    const finish=()=>{if(state.dragging){state.dragging=null;setTimeout(()=>state.moved=false,60);}};
    state.map.addEventListener('pointerup',finish);state.map.addEventListener('pointercancel',finish);
    state.map.addEventListener('click',async e=>{
      if(state.moved)return;
      if(state.placeHubId){
        const p=screenToPoint(e.clientX,e.clientY),id=state.placeHubId;state.placeHubId=null;
        try{await api(`/control-tower/hubs/${id}/location`,'PATCH',{lat:p.lat,lng:p.lng});if(typeof toast==='function')toast('Position précise du hub enregistrée.');await refreshData();}
        catch(err){if(typeof toast==='function')toast(err.message||'Position du hub refusée',true);}
        return;
      }
    });
    state.map.addEventListener('wheel',e=>{e.preventDefault();setCenter(state.centerLat,state.centerLng,state.zoom+(e.deltaY<0?1:-1));},{passive:false});
  }

  async function refreshData() {
    if(!state.map||!document.getElementById('rt-map'))return;
    try{
      const d=await api('/control-tower/map-data');
      if(!state.map||!document.getElementById('rt-map'))return;
      state.data={...(state.data||{}),...d};
      if(typeof S!=='undefined'&&S.tower)S.tower={...S.tower,...d};
      renderLists();renderHistorySelects();renderOverlays();
      const selected=currentJob();
      if(selected){const nearest=suitableDrivers(selected)[0],assigned=(d.map_drivers||[]).find(x=>x.id===selected.driver_id),routeDriver=nearest||assigned;if(routeDriver?.pos)drawRoute(selected,routeDriver);}
      state.lastPoll=Date.now();
    }catch(e){const label=document.getElementById('rt-updated');if(label)label.textContent='Actualisation impossible · '+(e.message||'réseau');}
  }
  window.rtRefresh=refreshData;

  window.rtMapStart=function(initial){
    window.rtMapStop?.();
    state.map=document.getElementById('rt-map');state.tiles=document.getElementById('rt-map-tiles');
    state.markers=document.getElementById('rt-marker-layer');state.routes=document.getElementById('rt-route-layer');state.zonesLayer=document.getElementById('rt-zone-layer');
    if(!state.map)return;
    state.data=initial||((typeof S!=='undefined'&&S.tower)||{});
    bindMap();renderTiles();renderLists();renderHistorySelects();renderOverlays();
    state.resize=typeof ResizeObserver!=='undefined'?new ResizeObserver(()=>{renderTiles();renderOverlays();}):null;
    if(state.resize)state.resize.observe(state.map);
    state.timer=setInterval(()=>{if(document.visibilityState==='visible')refreshData();},8000);
    // Keep driver/job selection across a poll, but invalidate stale route geometry.
    if(state.selectedJobId){const job=currentJob(), candidates=suitableDrivers(job);if(job)drawRoute(job,candidates[0]||null);}
  };
  window.rtMapStop=function(){
    if(state.timer){clearInterval(state.timer);state.timer=null;}
    if(state.resize){state.resize.disconnect();state.resize=null;}
    if(state.frame){cancelAnimationFrame(state.frame);state.frame=null;}
    state.tileNodes.clear();
    state.map=null;state.tiles=null;state.markers=null;state.routes=null;state.zonesLayer=null;
  };
  window.rtSelectJob=function(id){
    state.selectedJobId=id==null?null:Number(id);state.routeKey='';state.routeInfo=null;state.historyGeo=null;
    const job=currentJob(),candidate=suitableDrivers(job)[0];
    if(job){
      const assigned=(state.data?.map_drivers||[]).find(d=>d.id===job.driver_id),target=candidate||assigned;
      state.selectedDriverId=target?.id??null;
      if(target?.pos)setCenter((target.pos.lat+job.client.lat)/2,(target.pos.lng+job.client.lng)/2,clamp(Math.max(state.zoom,11),11,15));
      else setCenter(job.client.lat,job.client.lng,Math.max(state.zoom,12));
      drawRoute(job,target||null);
    }
    else {state.selectedDriverId=null;state.routeGeo=null;}
    renderLists();
  };
  window.rtSelectDriver=function(id){
    state.selectedDriverId=Number(id);const d=currentDriver(),job=currentJob();
    if(job&&d?.pos){setCenter((d.pos.lat+job.client.lat)/2,(d.pos.lng+job.client.lng)/2,clamp(Math.max(state.zoom,11),11,15));drawRoute(job,d);}
    else if(d?.pos){setCenter(d.pos.lat,d.pos.lng,Math.max(11,state.zoom));}
    renderLists();
  };
  window.rtZoom=function(delta){setCenter(state.centerLat,state.centerLng,state.zoom+Number(delta||0));};
  window.rtFit=function(){
    const points=[];
    (state.data?.map_drivers||[]).forEach(d=>{if(d.pos)points.push(d.pos);});
    (state.data?.hubs||[]).forEach(h=>{if(h.lat!=null)points.push({lat:h.lat,lng:h.lng});});
    (state.data?.ramassage_jobs||[]).filter(j=>['pending','assigned','en_route'].includes(j.status)).forEach(j=>points.push(j.client));
    fitPoints(points);
  };
  window.rtManualAssign=async function(jobId){
    try{
      const d=await api(`/control-tower/ramassage/${jobId}/candidates`),rows=d.candidates||[];
      const job=(state.data?.ramassage_jobs||[]).find(j=>j.id===jobId);
      if(!rows.length){if(typeof toast==='function')toast('Aucun livreur en ligne, disponible, non chargé et dans cette zone.',true);return;}
      modal('Affecter la demande #'+jobId,`<p class="form-hint">Client : <b>${escText(job?.client?.name||'')}</b> · zone ${escText(job?.zone||'')} · les propositions respectent le GPS, le véhicule, la charge et le géorepérage.</p>
        <div class="rt-modal-list">${rows.map(r=>`<button type="button" class="rt-modal-driver" onclick="rtAssign(${jobId},${r.id})"><span><b>${escText(r.name)}</b><small>${escText(r.vehicle?.label||r.vehicle?.type||'Véhicule')} · ${fmtDistance(r.distance_km)} · ETA ~${r.eta_min} min</small></span><b>Choisir</b></button>`).join('')}</div>`);
    }catch(e){if(typeof toast==='function')toast(e.message||'Livreurs disponibles introuvables.',true);}
  };
  window.rtAssign=async function(jobId,driverId){
    try{
      const r=await api(`/control-tower/ramassage/${jobId}/assign`,'POST',{driver_id:driverId});
      const name=r.assignment?.driver||'le livreur';if(typeof closeModal==='function')closeModal();
      if(typeof toast==='function')toast(`Demande #${jobId} affectée à ${name} · ${fmtDistance(r.assignment?.distance_km)} · ETA ~${r.assignment?.eta_min} min.`);
      await refreshData();window.rtSelectJob(jobId);
    }catch(e){if(typeof toast==='function')toast(e.message||'Affectation refusée.',true);}
  };
  window.rtWhatsapp=function(jobId,driverId){
    const job=(state.data?.ramassage_jobs||[]).find(j=>j.id===Number(jobId));
    const driver=(state.data?.map_drivers||[]).find(d=>d.id===Number(driverId));
    if(!job||!driver){if(typeof toast==='function')toast('Sélectionnez une demande et un livreur.',true);return;}
    let digits=String(driver.phone||'').replace(/\D/g,'');if(digits.startsWith('00'))digits=digits.slice(2);if(digits.startsWith('0')&&digits.length===10)digits='212'+digits.slice(1);
    if(!digits){if(typeof toast==='function')toast('Aucun numéro de téléphone enregistré pour ce livreur.',true);return;}
    const km=state.routeInfo?.distance_km??distKm(driver.pos,{lat:job.client.lat,lng:job.client.lng});
    const text=`🚨 طلب رمساج جديد!\n\nالسلام عليكم ${driver.name}، لديك طلب تجميع (Ramassage) قريب من موقعك الحالي.\n\n👤 العميل: ${job.client.name}\n\n📞 رقم الهاتف: ${job.client.phone}\n\n📍 الموقع (المرجو الضغط على الرابط): ${job.client.maps_url}\n\n⏱️ المسافة التقديرية: ${Number(km).toFixed(1)} كيلومتر.\n\nالمرجو التوجه إليه في أقرب وقت.`;
    window.open(`https://wa.me/${digits}?text=${encodeURIComponent(text)}`,'_blank','noopener');
  };
  window.rtSetAutoDispatch=async function(enabled){
    try{await api('/control-tower/settings','PATCH',{auto_dispatch:!!enabled});state.data.auto_dispatch=!!enabled;if(typeof toast==='function')toast(enabled?'Attribution automatique activée.':'Attribution automatique désactivée.');}
    catch(e){const cb=document.getElementById('rt-auto-dispatch');if(cb)cb.checked=!enabled;if(typeof toast==='function')toast(e.message||'Réglage refusé.',true);}
  };
  window.rtUseSavedClient=function(id){
    const c=(state.data?.ramassage_clients||[]).find(x=>x.id===Number(id));if(!c)return;
    const put=(key,value)=>{const el=document.getElementById(key);if(el)el.value=value==null?'':String(value);};
    put('rt-client-name',c.name);put('rt-client-phone',c.phone);put('rt-map-url',c.maps_url);put('rt-city-id',c.city_id);
  };
  window.rtSubmitPickup=async function(event){
    event?.preventDefault?.();
    const value=id=>document.getElementById(id)?.value||'';
    const payload={name:value('rt-client-name').trim(),phone:value('rt-client-phone').trim(),maps_url:value('rt-map-url').trim(),city_id:value('rt-city-id')||null,parcels_count:Number(value('rt-count'))||1};
    try{
      const r=await api('/control-tower/ramassage','POST',payload);
      const form=document.getElementById('rt-pickup-form');if(form){form.reset();const count=document.getElementById('rt-count');if(count)count.value='1';}
      state.selectedJobId=r.job_id;state.routeKey='';
      if(r.auto_dispatched&&typeof toast==='function')toast(`Affectation automatique confirmée : ${r.assignment.driver} · ${fmtDistance(r.assignment.distance_km)} · ETA ~${r.assignment.eta_min} min.`);
      else if(r.warning&&typeof toast==='function')toast(r.warning,true);
      else if(typeof toast==='function')toast('Demande de ramassage enregistrée. Choisissez un livreur dans la liste des demandes.');
      await refreshData();window.rtSelectJob(r.job_id);
    }catch(e){if(typeof toast==='function')toast(e.message||'Création de la demande impossible.',true);}
  };
  window.rtShowHistory=async function(){
    const did=document.getElementById('rt-history-driver')?.value,day=document.getElementById('rt-history-date')?.value;
    if(!did){if(typeof toast==='function')toast('Choisissez un livreur.',true);return;}
    try{
      const r=await api(`/control-tower/route-history/${did}?date=${encodeURIComponent(day||'')}`);
      state.historyGeo=(r.points||[]).filter((_,i)=>i===0||i===(r.points.length-1)||i%Math.max(1,Math.ceil(r.points.length/3000))===0).map(p=>({lat:p.lat,lng:p.lng}));
      state.historyLabel=`${state.data?.map_drivers?.find(d=>d.id===Number(did))?.name||'Livreur'} · ${r.date} · ${r.count} points`;
      state.routeGeo=null;state.routeInfo=null;state.selectedJobId=null;state.selectedDriverId=Number(did);
      if(state.historyGeo.length)fitPoints(state.historyGeo);
      if(typeof toast==='function')toast(state.historyLabel+(r.count?'':' · aucun point enregistré ce jour.'));
      renderLists();renderOverlays();
    }catch(e){if(typeof toast==='function')toast(e.message||'Historique indisponible.',true);}
  };
  window.rtOpenHubSettings=function(){if(typeof navigate==='function')navigate('ops-settings');};
  window.rtBeginHubPlacement=function(){
    const hubs=(state.data?.hubs||[]);
    if(!hubs.length){if(typeof toast==='function')toast('Ajoutez d’abord un hub dans « Hubs & motifs ».');return;}
    modal('Placer précisément un hub sur la carte',`<p class="form-hint">Les hubs sans GPS exact sont affichés au centre de leur ville avec un marqueur approximatif. Choisissez un hub, puis touchez son emplacement réel sur la carte.</p>
      <div class="field"><label for="rt-hub-place-select">Hub</label><select id="rt-hub-place-select">${hubs.map(h=>`<option value="${h.id}">${escText(h.name)} · ${escText(h.city||'')}</option>`).join('')}</select></div>
      <div class="form-actions"><button class="btn" type="button" onclick="closeModal()">Annuler</button><button class="btn primary" type="button" onclick="rtConfirmHubPlacement()">Choisir sur la carte</button></div>`);
  };
  window.rtConfirmHubPlacement=function(){
    const id=Number(document.getElementById('rt-hub-place-select')?.value);if(!id)return;
    state.placeHubId=id;if(typeof closeModal==='function')closeModal();
    if(typeof toast==='function')toast('Touchez le point GPS exact du hub sur la carte.');
  };
  window.rtZoneSettings=function(){
    const zones=state.data?.zones||[],cities=state.data?.pickup_cities||[];
    const first=zones[0], defaultId=first?.city_id||cities.find(c=>c.zone_ready)?.id||cities[0]?.id;
    modal('Zones de ramassage',`<p class="form-hint">Les zones sont des cercles géographiques par ville. Les coordonnées initiales sont des centres approximatifs : vérifiez-les avant d’activer l’auto-affectation. Rayon autorisé : 1–100 km.</p>
      <div class="field"><label for="rt-zone-city">Ville</label><select id="rt-zone-city" onchange="rtZoneFill(this.value)">${cities.map(c=>`<option value="${c.id}" ${c.id===defaultId?'selected':''}>${escText(c.name)}${c.zone_ready?'':' · zone à créer'}</option>`).join('')}</select></div>
      <div class="form-grid"><div class="field"><label for="rt-zone-lat">Centre — latitude</label><input id="rt-zone-lat" type="number" step="0.000001"></div><div class="field"><label for="rt-zone-lng">Centre — longitude</label><input id="rt-zone-lng" type="number" step="0.000001"></div><div class="field"><label for="rt-zone-radius">Rayon (km)</label><input id="rt-zone-radius" type="number" min="1" max="100" step="1"></div></div>
      <div class="form-actions"><button class="btn" type="button" onclick="closeModal()">Fermer</button><button class="btn primary" type="button" onclick="rtSaveZone()">Enregistrer la zone</button></div>`);
    if(defaultId)window.rtZoneFill(defaultId);
  };
  window.rtZoneFill=function(id){
    const z=(state.data?.zones||[]).find(x=>x.city_id===Number(id));
    const set=(n,v)=>{const e=document.getElementById(n);if(e)e.value=v==null?'':String(v);};
    if(z){set('rt-zone-lat',z.center_lat);set('rt-zone-lng',z.center_lng);set('rt-zone-radius',z.radius_km);}
    else{const city=(state.data?.pickup_cities||[]).find(x=>x.id===Number(id));const geo=typeof TOUR_GEO!=='undefined'&&city?TOUR_GEO[city.name]:null;set('rt-zone-lat',geo?.[0]??'');set('rt-zone-lng',geo?.[1]??'');set('rt-zone-radius',20);}
  };
  window.rtSaveZone=async function(){
    const id=Number(document.getElementById('rt-zone-city')?.value),lat=Number(document.getElementById('rt-zone-lat')?.value),lng=Number(document.getElementById('rt-zone-lng')?.value),radius=Number(document.getElementById('rt-zone-radius')?.value);
    try{await api(`/control-tower/zones/${id}`,'PATCH',{center_lat:lat,center_lng:lng,radius_km:radius});if(typeof closeModal==='function')closeModal();if(typeof toast==='function')toast('Zone enregistrée.');await refreshData();}
    catch(e){if(typeof toast==='function')toast(e.message||'Zone refusée.',true);}
  };

  function savedClientOptions() {
    const rows=state.data?.ramassage_clients||[];
    return `<option value="">Nouveau client…</option>`+rows.map(c=>`<option value="${c.id}">${escText(c.name)} · ${escText(c.phone)} · ${escText(c.zone||'')}</option>`).join('');
  }

  window.ramassageControlView=function(d){
    const k=d.kpis||{},drivers=d.map_drivers||d.drivers||[],zones=d.zones||[],jobs=d.ramassage_jobs||[];
    const isAdmin=typeof S!=='undefined'&&S.user?.role==='admin';
    const readyCities=(d.pickup_cities||[]).filter(c=>c.zone_ready);
    const date=new Date().toISOString().slice(0,10);
    const alerts=(d.gps_alerts||[]).map(x=>`${escText(x.name)} — GPS désactivé`).join(' · ');
    return heading('Tour de contrôle — Ramassage','Carte temps réel des livreurs et demandes de collecte · mise à jour automatique toutes les 8 secondes.',
      `<button class="btn sm" type="button" onclick="renderView()">${icon('refresh')}Actualiser</button>${isAdmin?`<button class="btn sm" type="button" onclick="rtZoneSettings()">${icon('pin')}Zones</button><button class="btn sm primary" type="button" onclick="tourDispatchPanel()">${icon('scan')}Répartition colis</button>`:''}`)+
      `<div class="rt-kpis stats">${stat('En tournée',k.out_today||0,'','truck','navy')}${stat('Livrés aujourd’hui',k.delivered_today||0,'','check','green')}${stat('Demandes ramassage actives',`<span id="rt-active-kpi">${jobs.filter(j=>['pending','assigned','en_route'].includes(j.status)).length}</span>`,'','box','orange')}${stat('Alertes GPS',`<span id="rt-gps-kpi">${(d.gps_alerts||[]).length}</span>`,'','alert',(d.gps_alerts||[]).length?'red':'green')}</div>
      <div id="rt-gps-alerts" class="rt-gps-alert" role="alert" ${alerts?'':'hidden'}>${alerts?'⚠ GPS désactivé : '+alerts:''}</div>
      ${(d.hubs||[]).length?'':`<div class="rt-hub-empty">Aucun hub n’est encore configuré : la carte n’invente pas d’emplacement. ${isAdmin?'<button type="button" onclick="rtOpenHubSettings()">Configurer un hub</button>':''}</div>`}
      <section class="rt-layout">
        <div class="rt-map-card">
          <div class="rt-map-top"><div><b>Carte live · Maroc</b><small id="rt-updated">Initialisation…</small></div><span id="rt-online-count" class="rt-online-count">— en ligne</span></div>
          <div id="rt-map" class="rt-map" role="application" aria-label="Carte interactive des livreurs et ramassages">
            <div id="rt-map-tiles" class="rt-map-tiles"></div><svg id="rt-zone-layer" class="rt-svg-layer" aria-hidden="true"></svg><svg id="rt-route-layer" class="rt-svg-layer" aria-hidden="true"></svg><div id="rt-marker-layer" class="rt-marker-layer"></div>
            <div class="rt-map-controls"><button class="rt-map-control" type="button" onclick="rtZoom(1)" aria-label="Zoom avant">+</button><button class="rt-map-control" type="button" onclick="rtZoom(-1)" aria-label="Zoom arrière">−</button><button class="rt-map-control" type="button" onclick="rtFit()" aria-label="Cadrer les marqueurs">⌖</button>${isAdmin?'<button class="rt-map-control" type="button" onclick="rtBeginHubPlacement()" title="Positionner un hub">🏬</button>':''}</div>
            <div class="rt-map-attribution">© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a></div>
            <div class="rt-map-legend"><span><i class="rt-legend-dot green"></i>Disponible</span><span><i class="rt-legend-dot orange"></i>Ramassage</span><span>🏬 Hub</span><span>🏍 / 🚘 Véhicule</span></div>
          </div>
          <div class="rt-route-note">Itinéraire routier via OSRM public quand disponible, sinon distance directe estimée. Le service OSRM reçoit les coordonnées des deux points.</div>
        </div>
        <aside class="rt-side">
          <div class="rt-side-title"><div><b>Dispatch ramassage</b><small>Clients, affectations et présence</small></div><button class="rt-icon-btn" type="button" onclick="rtRefresh()" title="Actualiser">↻</button></div>
          <label class="rt-auto-toggle"><span><b>Attribution automatique</b><small>Le plus proche, même zone, GPS récent, véhicule disponible, non chargé.</small></span><input id="rt-auto-dispatch" type="checkbox" ${d.auto_dispatch?'checked':''} ${isAdmin?'':'disabled'} onchange="rtSetAutoDispatch(this.checked)"><i></i></label>
          <form id="rt-pickup-form" class="rt-pickup-form" onsubmit="rtSubmitPickup(event)">
            ${isAdmin?'':'<div class="rt-agent-note">Consultation de la carte et de l’historique. Les créations, affectations et réglages sont réservés à l’administrateur.</div>'}
            <fieldset ${isAdmin?'':'disabled'} class="rt-form-fields">
            <div class="rt-section-head"><b>Nouvelle demande</b>${isAdmin?'<button class="rt-text-btn" type="button" onclick="rtZoneSettings()">Régler une zone</button>':''}</div>
            <label class="rt-field"><span>Réutiliser un client enregistré</span><select id="rt-saved-client" onchange="rtUseSavedClient(this.value)">${savedClientOptions()}</select></label>
            <div class="rt-two"><label class="rt-field"><span>Nom du client *</span><input id="rt-client-name" maxlength="100" required autocomplete="name" placeholder="Nom / société"></label><label class="rt-field"><span>Téléphone *</span><input id="rt-client-phone" type="tel" maxlength="32" required autocomplete="tel" placeholder="+212…"></label></div>
            <label class="rt-field"><span>Lien Google Maps *</span><input id="rt-map-url" type="text" inputmode="url" maxlength="2048" required placeholder="maps.app.goo.gl/… ou lien Maps complet"></label>
            <div class="rt-two"><label class="rt-field"><span>Zone géographique</span><select id="rt-city-id"><option value="">Détection GPS</option>${readyCities.map(c=>`<option value="${c.id}">${escText(c.name)}</option>`).join('')}</select></label><label class="rt-field rt-count"><span>Colis</span><input id="rt-count" type="number" min="1" max="10000" value="1" required></label></div>
            <button class="rt-primary-btn rt-submit" type="submit">＋ Créer la demande</button>
            <small class="rt-form-hint">Les coordonnées sont extraites côté serveur; le client et son lieu seront mémorisés. Les liens courts nécessitent un accès sortant à Google.</small>
            </fieldset>
          </form>
          <div id="rt-selected-job" class="rt-selected-job" hidden></div>
          <section class="rt-list-section"><div class="rt-section-head"><b>Livreurs</b><span class="rt-muted">Disponibilité &amp; GPS</span></div><div id="rt-driver-list" class="rt-scroll-list"></div></section>
          <section class="rt-list-section"><div class="rt-section-head"><b>Ramassages en cours</b><span id="rt-job-count" class="rt-muted">${jobs.filter(j=>['pending','assigned','en_route'].includes(j.status)).length}</span></div><div id="rt-job-list" class="rt-scroll-list rt-jobs"></div></section>
          <section class="rt-history"><div class="rt-section-head"><b>Historique trajet</b><button class="rt-text-btn" type="button" onclick="rtShowHistory()">Afficher</button></div>
            <div class="rt-history-fields"><select id="rt-history-driver"><option value="">Choisir un livreur</option>${drivers.map(x=>`<option value="${x.id}">${escText(x.name)}</option>`).join('')}</select><input id="rt-history-date" type="date" value="${date}" aria-label="Jour de l’historique"></div>
            <small>Positions GPS conservées 30 jours. Un itinéraire n’apparaît que si le suivi GPS était actif.</small></section>
        </aside>
      </section>
      <div class="rt-lower-grid"><section class="card"><div class="card-head"><h3>Colis sans nouvelle depuis 48 h</h3>${(d.alerts||[]).length?`<span class="tag">${d.alerts.length}</span>`:''}</div>${(d.alerts||[]).length?`<table><thead><tr><th>Suivi</th><th>Destinataire</th><th>Ville</th><th>Statut</th><th>Retard</th><th></th></tr></thead><tbody>${d.alerts.map(a=>`<tr><td class="mono">${escText(a.tracking)}</td><td>${escText(a.recipient)}</td><td>${escText(a.city||'—')}</td><td><span class="tag">${escText(a.status)}</span></td><td style="color:#f59e0b"><b>${a.days} j</b></td><td><button class="btn sm" type="button" onclick="parcelDetail(${a.id})">${icon('eye')}Ouvrir</button></td></tr>`).join('')}</tbody></table>`:'<p class="muted">Aucun colis en silence — tout le monde avance. ✓</p>'}</section>
        <section class="card"><div class="card-head"><h3>Non affectés par ville</h3></div>${(d.unassigned_by_city||[]).length?`<table><thead><tr><th>Ville</th><th>Colis</th><th>IDs</th></tr></thead><tbody>${d.unassigned_by_city.map(x=>`<tr><td>${escText(x.city)}</td><td>${x.count}</td><td class="muted">${escText((x.parcel_ids||[]).slice(0,8).join(', '))}</td></tr>`).join('')}</tbody></table>`:'<p class="muted">Rien à affecter. ✓</p>'}</section></div>`;
  };
})();
