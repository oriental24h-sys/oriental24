"""v1.8.0 — « Tour de contrôle » : positions GPS des livreurs, tableau de bord temps réel,
répartition intelligente des colis non affectés (blocs par ville + 2-opt), ETA estimée,
code client OTP comme preuve de livraison et lien de suivi public limité.
Tout est calculé localement : aucune API de cartographie ni service externe."""
import math,secrets,time
from flask import request,jsonify

OPEN_STATES=('Transit','Créé','Ramassé','Au hub','Réceptionné','Reçu par le livreur','En livraison','Programmé','Reporté','Intéressé')
OUT_STATES=('En livraison','Programmé')
# v1.8.1 « Messagerie guidée » : messages prêts à l'emploi, jamais de texte libre (aucune fuite possible).
MSG_TEMPLATES={'near':'Le livreur est proche de votre adresse.','eta10':'Le livreur arrivera dans environ 10 minutes.','patience':'Merci de patienter : votre livreur est en route.'}

# centroides approximatifs lat/lng — suffisants pour rapprocher des villes entre elles
GEO={'Oujda':(34.681,-1.912),'Casablanca':(33.573,-7.5898),'Rabat':(34.0209,-6.8416),'Salé':(34.0389,-6.8164),
 'Marrakech':(31.6295,-7.9811),'Tanger':(35.7595,-5.834),'Fès':(34.0331,-5.0003),'Meknès':(33.8935,-5.5473),
 'Agadir':(30.4278,-9.5981),'Tétouan':(35.5785,-5.3684),'Berkane':(34.929,-1.979),'Nador':(35.1684,-2.9284),
 'El Jadida':(33.2309,-8.4997),'Kénitra':(34.261,-6.5802),'Taza':(34.2214,-4.0071),'Ouarzazate':(30.9188,-6.8825),
 'Laâyoune':(27.1536,-13.2033),'Dakhla':(23.6848,-15.9587),'Essaouira':(31.5085,-9.7596),'Safi':(32.3017,-9.2373),
 'Mohammedia':(33.7205,-7.3817),'Témara':(34.267,-6.9126),'Beni Mellal':(32.3373,-6.3498),'Al Hoceïma':(35.2515,-3.9375),
 'Errachidia':(31.9314,-4.4247),'Midelt':(32.6837,-4.7486),'Azilal':(32.0,6.35),'Chefchaouen':(35.1683,-5.2696),
 'Ouezzane':(34.7633,-5.5813),'Taourirt':(34.6867,-1.2653),'Jerada':(34.2967,-1.6353),'Guercif':(34.2264,-2.176),
 'Taounate':(34.5331,-4.4586),'Sefrou':(33.8573,-5.1661),'Ifrane':(33.5253,-5.1098),'Khouribga':(32.8823,-6.909),
 'Berrechid':(33.3664,-7.59),'Settat':(33.0016,-7.6619),'Youssoufia':(32.2747,-8.5278),'Taroudant':(30.4645,-8.8874),
 'Inezgane':(30.3905,-9.5097),'Guelmim':(28.9869,-10.0527),'Smara':(26.7389,-11.6764)}

def haversine(a,b):
    if not a or not b:return 25.0
    la1,lo1=map(math.radians,a);la2,lo2=map(math.radians,b)
    return round(6371.0*math.acos(min(1.0,max(-1.0,math.sin(la1)*math.sin(la2)+math.cos(la1)*math.cos(la2)*math.cos(lo2-lo1)))),2)

def route_km(geos):
    return round(sum(haversine(x,y) for x,y in zip(geos,geos[1:]) if x and y),2) if len(geos)>1 else 0.0

def order_route(geos):
    """ordre de tournée : plus proche voisin puis 2-opt — geos : liste de coordonnées ou None."""
    n=len(geos)
    if n<3:return list(range(n))
    cur=[0];rest=list(range(1,n))
    while rest:
        last=cur[-1]
        best=min(rest,key=lambda i:(9e9 if not geos[last] or not geos[i] else haversine(geos[last],geos[i]),i))
        cur.append(best);rest.remove(best)
    tour=cur;improved=True
    while improved:
        improved=False
        for i in range(1,len(tour)-1):
            for j in range(i+1,len(tour)):
                t2=tour[:i]+tour[i:j+1][::-1]+tour[j+1:]
                if route_km([geos[k] for k in t2])<route_km([geos[k] for k in tour])-0.01:
                    tour,improved=t2,True;break
            if improved:break
    return tour

def register_tour_control(app,s):
    conn,auth,user,now,Error,event,parcel=(s['conn'],s['auth'],s['user'],s['now'],s['APIError'],s['event'],s['parcel'])
    import sqlite3 as _sq
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS driver_positions(id INTEGER PRIMARY KEY,driver_id INTEGER NOT NULL REFERENCES users(id),lat REAL NOT NULL,lng REAL NOT NULL,city_id INTEGER REFERENCES cities(id),created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS driver_positions_driver_idx ON driver_positions(driver_id,id);
        CREATE TABLE IF NOT EXISTS parcel_messages(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),actor_id INTEGER NOT NULL REFERENCES users(id),code TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
        for col in ("otp_required INTEGER NOT NULL DEFAULT 0","otp_code TEXT","otp_verified_at TEXT"):
            try:c.execute('ALTER TABLE parcels ADD COLUMN '+col)
            except _sq.OperationalError as e:
                if 'duplicate column' not in str(e).lower():raise
    def parse(t):
        for fmt in ('%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S'):
            try:return time.mktime(time.strptime(str(t)[:19],fmt))
            except Exception:pass
        return 0.0
    # v1.9.0 : ETA prédictive (modèle appris par advanced_tech) — repli sur la formule d'origine.
    def eta_params():
        fn=getattr(app,'o24_eta',None)
        try:m=fn() if fn else None
        except Exception:m=None
        return (float(m['a']),float(m['b'])) if m and m.get('learned') else (18.0,1.875)
    def tour_minutes(stops,km=0.0):
        a,b=eta_params();return max(5,round(a*stops+b*km))

    @app.post('/api/driver/position')
    @auth('livreur')
    def driver_position():
        d=request.get_json(silent=True) or {};u=user()
        lat,lng=d.get('lat'),d.get('lng')
        if not (isinstance(lat,(int,float)) and isinstance(lng,(int,float)) and -90<=lat<=90 and -180<=lng<=180):
            raise Error('Position invalide : latitude/longitude requises.')
        with conn() as c:
            c.execute('INSERT INTO driver_positions(driver_id,lat,lng,city_id,created_at) VALUES(?,?,?,?,?)',
             (u['id'],round(float(lat),6),round(float(lng),6),d.get('city_id'),now()))
            keep=c.execute('SELECT COALESCE(MAX(id),1)-48 m FROM driver_positions WHERE driver_id=?',(u['id'],)).fetchone()['m']
            c.execute('DELETE FROM driver_positions WHERE driver_id=? AND id<?',(u['id'],max(1,keep)))
            n=c.execute('SELECT COUNT(*) n FROM driver_positions WHERE driver_id=? AND created_at>=?',(u['id'],time.strftime('%Y-%m-%dT%H:%M:%S',time.localtime(time.time()-12*3600)))).fetchone()['n']
            fn=getattr(app,'o24_geofence',None)  # v1.9.0 : alertes automatiques proche/arrivé
            if fn: fn(c,u['id'],float(lat),float(lng))
        return jsonify(ok=True,points=n)

    @app.get('/api/control-tower')
    @auth('admin','agent')
    def control_tower():
        t=now()[:10]
        with conn() as c:
            drivers=[dict(r) for r in c.execute("SELECT id,name,phone FROM users WHERE role='livreur' AND active=1 ORDER BY name")]
            parcels=[dict(r) for r in c.execute('SELECT p.id,p.tracking,p.recipient,p.status,p.amount,p.driver_id,p.updated_at,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id')]
            pos={}
            for r in c.execute('SELECT driver_id,MAX(id) mid FROM driver_positions GROUP BY driver_id'):
                row=c.execute('SELECT lat,lng,created_at FROM driver_positions WHERE id=?',(r['mid'],)).fetchone()
                if row and time.time()-parse(row['created_at'])<=12*3600:pos[r['driver_id']]=dict(row)
        rows=[]
        for d in drivers:
            mine=[p for p in parcels if p['driver_id']==d['id']]
            out=[p for p in mine if p['status'] in OUT_STATES]
            done=[p for p in mine if p['status']=='Livré' and str(p['updated_at'])[:10]==t]
            p0=pos.get(d['id'])
            geos=[GEO.get(p['city'] or '') for p in out]
            km_out=route_km([geos[i] for i in order_route(geos)]) if len(geos)>1 else 0.0
            _co2=getattr(app,'o24_co2',None)  # v1.10.0 : facteur selon le type de véhicule (drone/électrique/vélo…)
            if _co2:  # hors du with(conn) d'origine : connexion fraîche indispensable
                with conn() as c2: co2_out=_co2(c2,d['id'],km_out)
            else: co2_out=round(km_out*0.12,2)
            rows.append({'id':d['id'],'name':d['name'],'phone':d['phone'],'stops_out':len(out),'done_today':len(done),
             'cod_today':round(sum(p['amount'] or 0 for p in done),2),'eta_min':tour_minutes(len(out),km_out)+10,
             'km_est':km_out,'co2_kg':co2_out,
             'pos':({'lat':p0['lat'],'lng':p0['lng'],'ago_min':max(0,int((time.time()-parse(p0['created_at']))/60))} if p0 else None)})
        lates=[{'id':p['id'],'tracking':p['tracking'],'recipient':p['recipient'],'city':p['city'],'status':p['status'],
                'days':max(1,int((time.time()-parse(p['updated_at']))/86400))}
               for p in parcels if p['status'] in OPEN_STATES and p['status']!='Créé' and time.time()-parse(p['updated_at'])>=2*86400]
        unassigned={}
        for p in parcels:
            if p['status']=='Créé' and not p['driver_id']:unassigned.setdefault(p['city'] or 'Sans ville',[]).append(p['id'])
        return jsonify(drivers=rows,kpis={'out_today':sum(r['stops_out'] for r in rows),'delivered_today':sum(r['done_today'] for r in rows),
         'cod_today':round(sum(r['cod_today'] for r in rows),2),'late_48h':len(lates),'unassigned':sum(len(v) for v in unassigned.values()),
         'co2_kg_today':round(sum(r['co2_kg'] for r in rows),2)},
         alerts=lates[:12],unassigned_by_city=[{'city':k,'count':len(v),'parcel_ids':v} for k,v in sorted(unassigned.items(),key=lambda x:(-x[1][0] if isinstance(x[1],list) else 0,-len(x[1]),str(x[0])))])

    @app.get('/api/dispatch/suggest')
    @auth('admin')
    def dispatch_suggest():
        with conn() as c:
            pend=[dict(r) for r in c.execute('SELECT p.id,p.city_id,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE p.status=\'Créé\' AND p.driver_id IS NULL ORDER BY p.city_id,p.id')]
            drivers=[dict(r) for r in c.execute("SELECT id,name FROM users WHERE role='livreur' AND active=1 ORDER BY name")]
            marks='('+','.join('?'*len(OPEN_STATES))+')'
            loads={d['id']:c.execute('SELECT COUNT(*) n FROM parcels WHERE driver_id=? AND status IN '+marks,[d['id'],*OPEN_STATES]).fetchone()['n'] for d in drivers}
        if not pend:raise Error('Aucun colis non affecté à répartir.')
        if not drivers:raise Error('Aucun livreur actif : impossible de proposer une répartition.')
        blocks={}
        for p in pend:blocks.setdefault(p['city_id'],[]).append(p)
        proj=dict(loads);assign={d['id']:[] for d in drivers}
        for cid,ps in sorted(blocks.items(),key=lambda x:(-len(x[1]),str(x[0]))):
            d0=min(proj,key=lambda k:(proj[k],next(d['name'] for d in drivers if d['id']==k)))
            assign[d0].extend(p['id'] for p in ps);proj[d0]+=len(ps)
        cities={p['city_id']:p['city'] for p in pend}
        rows=[]
        for d in drivers:
            ids=assign[d['id']]
            if not ids:continue
            ps=[p for p in pend if p['id'] in set(ids)]
            geos=[GEO.get(cities.get(p['city_id']) or '') for p in ps]
            ps=[ps[i] for i in order_route(geos)]
            km=route_km([g for g in geos if g])
            with conn() as c2:  # v1.10.0 : facteur CO₂ selon le véhicule du livreur pressenti
                co2_fn=getattr(app,'o24_co2',None)
                co2_lot=co2_fn(c2,d['id'],km) if co2_fn else round(km*0.12,2)
            rows.append({'driver_id':d['id'],'name':d['name'],'load_before':loads[d['id']],'added':len(ps),
             'cities':sorted({p['city'] or 'Sans ville' for p in ps}),'parcel_ids':[p['id'] for p in ps],
             'km_est':km,'eta_min':tour_minutes(len(ps),km),'co2_kg':co2_lot})
        return jsonify(rows=rows,total=len(pend))

    @app.post('/api/parcels/<int:pid>/otp')
    @auth('admin')
    def parcel_otp(pid):
        d=request.get_json(silent=True) or {};u=user()
        on=bool(d.get('enabled'))
        with conn() as c:
            p=c.execute('SELECT id,status,otp_code FROM parcels WHERE id=?',(pid,)).fetchone()
            if not p:raise Error('Colis introuvable.',404)
            new=''.join(secrets.choice('0123456789') for _ in range(4)) if (on and not p['otp_code']) else (p['otp_code'] if on else None)
            c.execute('UPDATE parcels SET otp_required=?,otp_code=? WHERE id=?',(1 if on else 0,new,pid))
            event(c,pid,p['status'],'Code client OTP '+('activé' if on else 'retiré'),u)
        return jsonify(ok=True,otp=(new if on else None))

    @app.post('/api/parcels/<int:pid>/messages')
    @auth('admin','livreur')
    def parcel_message(pid):
        d=request.get_json(silent=True) or {};u=user()
        code=d.get('code')
        if code not in MSG_TEMPLATES:raise Error('Message invalide : choisissez un message préparé.')
        with conn() as c:
            p=parcel(c,pid,u)
            c.execute('INSERT INTO parcel_messages(parcel_id,actor_id,code,created_at) VALUES(?,?,?,?)',(pid,u['id'],code,now()))
            event(c,pid,p['status'],'Message au client : '+MSG_TEMPLATES[code],u)
        lk=getattr(app,'o24_msg_links',None)  # v1.9.0 : liens WhatsApp/SMS prêts à l'envoi
        return jsonify(ok=True,text=MSG_TEMPLATES[code],links=(lk(p['phone'],MSG_TEMPLATES[code]) if lk else {}))

    hits={}
    app.o24_track_hits=hits
    @app.get('/api/public/track/<tracking>')
    def public_track(tracking):
        ip=request.remote_addr or '?'
        minute=int(time.time()//60)
        rec=hits.get(ip)
        if not rec or rec[0]!=minute:rec=hits[ip]=[minute,0]
        rec[1]+=1
        if rec[1]>30:raise Error('Trop de consultations : réessayez dans une minute.',429)
        with conn() as c:
            p=c.execute('SELECT p.id,p.tracking,p.status,p.updated_at,p.driver_id,ci.name city,d.name driver,d.phone driver_phone '
             "FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id LEFT JOIN users d ON d.id=p.driver_id WHERE lower(p.tracking)=lower(?)",(str(tracking)[:80],)).fetchone()
            if not p:raise Error('Colis introuvable.',404)
            ev=[dict(r) for r in c.execute('SELECT status,created_at FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 8',(p['id'],))]
            msgs=[{'text':MSG_TEMPLATES.get(r['code'],r['code']),'date':r['created_at']} for r in c.execute('SELECT code,created_at FROM parcel_messages WHERE parcel_id=? ORDER BY id DESC LIMIT 3',(p['id'],))]
            pos=None;eta=None
            if p['status'] in OUT_STATES:
                r0=c.execute('SELECT lat,lng,created_at FROM driver_positions WHERE driver_id=? ORDER BY id DESC LIMIT 1',(p['driver_id'],)).fetchone() if p['driver_id'] else None
                if r0 and time.time()-parse(r0['created_at'])<=12*3600:pos={'lat':r0['lat'],'lng':r0['lng']}
                marks='('+','.join('?'*len(OUT_STATES))+')'
                ahead=c.execute('SELECT COUNT(*) n FROM parcels WHERE driver_id=? AND id!=? AND status IN '+marks,[p['driver_id'],p['id'],*OUT_STATES]).fetchone()['n'] if p['driver_id'] else 0
                a,_b=eta_params()  # v1.9.0 : fenêtre glissante pilotée par le modèle prédictif
                eta='+ %d à %d min'%(max(5,int(ahead*a*0.83)),max(15,int(ahead*a*1.39)+20))
        return jsonify(found=True,tracking=p['tracking'],status=p['status'],city=p['city'] or '',updated_at=str(p['updated_at']),
         history=[{'status':e['status'],'date':e['created_at']} for e in ev],
         messages=msgs,
         **({'driver_first_name':(p['driver'] or '').split(' ')[0],'driver_phone':p['driver_phone'],'eta':eta,'gps':pos} if p['status'] in OUT_STATES else {}))
