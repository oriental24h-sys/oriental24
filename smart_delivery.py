"""v1.10.0 « Flotte connectée & livraison augmentée » — complément des technologies avancées :

 1. Flotte connectée : véhicules par livreur (thermique / électrique / vélo / drone / camion),
    CO₂ et vitesse par type (le drone = « livraison par véhicule aérien », prêt côté logiciel).
 2. Maintenance prédictive : usure kilométrique + entretien + alertes batterie (électrique/drone),
    score d'usure transparent et remise à zéro à l'atelier.
 3. Points relais & casiers intelligents (smart lockers) : routage du colis vers un point, dépôt
    avec CODE DE RETRAIT à 6 chiffres (transmis WhatsApp/SMS), retrait vérifié en temps constant.
 4. Jumeau numérique : simulation de la journée (Monte-Carlo sur le modèle ETA appris) avant
    d'appliquer la répartition — achèvement estimé, taux à l'heure, CO₂, recommandation.
 5. E-paiement / mobile money : demandes de paiement digitalisées (référence unique + liens
    wa.me/sms + passage à l'encaissement horodaté, rapprochable aux factures).
 6. Décisionnel big data & SLA : exports CSV complets (colis, événements, livraisons, flotte) et
    engagements de service (délai moyen, taux au 1er passage, taux à J+1).

Tout est local : aucune API de paiement, aucune cartographie, aucun fournisseur externe."""
import csv, io, random, secrets as _sec, time
from datetime import datetime
from flask import request, jsonify, Response
from tour_control import GEO, haversine, route_km, order_route
from advanced_tech import msg_links, intl_phone, _ts, CO2_PER_KM  # helpers éprouvés v1.9.0

VEHICLES = {
    'thermique': {'label': 'Utilitaire thermique', 'co2_per_km': 0.12, 'speed_kmh': 32, 'service_km': 10000},
    'electrique': {'label': 'Électrique',        'co2_per_km': 0.04, 'speed_kmh': 32, 'service_km': 15000},
    'velo':       {'label': 'Vélo cargo',        'co2_per_km': 0.0,  'speed_kmh': 15, 'service_km': 2000},
    'drone':      {'label': 'Drone (aérien)',    'co2_per_km': 0.02, 'speed_kmh': 60, 'service_km': 500},
    'camion':     {'label': 'Camion',            'co2_per_km': 0.25, 'speed_kmh': 28, 'service_km': 20000},
}
POINT_KINDS = ('relais', 'casier', 'agence')
TPL = {
    'locker':   'ORIENTAL24 : votre colis {tracking} vous attend au point relais {point}. Code de retrait : {code}.',
    'payment':  'ORIENTAL24 : demande de paiement {amount} MAD pour le colis {tracking} (référence {ref}).',
    'entretien': 'ORIENTAL24 atelier : {label} — entretien dû (compteur {km} km). Merci de planifier le passage.',
}


def wear_score(km, service_km, battery_pct=None):
    """Score d'usure 0–100 : part kilométrique depuis le dernier entretien + malus batterie
    faible (véhicules électriques/drones) — plafonné à 100."""
    base = 100 * max(0.0, float(km or 0)) / max(1.0, float(service_km or 1))
    if battery_pct is not None and battery_pct < 25:
        base += (25 - battery_pct) * 1.75  # batterie à 5 % ⇒ +35 pts
    return min(100.0, round(base, 1))

def render_tpl(tpl_name, **kw):
    t = TPL[tpl_name]
    for k, v in kw.items(): t = t.replace('{' + k + '}', str(v))
    return t


def register_smart_delivery(app, s):
    conn, auth, user, now, Error, event, parcel = (s['conn'], s['auth'], s['user'], s['now'], s['APIError'], s['event'], s['parcel'])
    import sqlite3 as _sq
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS vehicles(id INTEGER PRIMARY KEY,driver_id INTEGER REFERENCES users(id),label TEXT NOT NULL,type TEXT NOT NULL DEFAULT 'thermique',plate TEXT DEFAULT '',km REAL DEFAULT 0,service_km REAL DEFAULT 0,service_at TEXT,battery_pct REAL,state TEXT NOT NULL DEFAULT 'disponible',active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS service_logs(id INTEGER PRIMARY KEY,vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),km REAL DEFAULT 0,note TEXT DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pickup_points(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER REFERENCES cities(id),address TEXT DEFAULT '',kind TEXT NOT NULL DEFAULT 'relais',lockers INTEGER DEFAULT 0,active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS locker_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),point_id INTEGER NOT NULL REFERENCES pickup_points(id),code TEXT NOT NULL,delivered_at TEXT,picked_at TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS payment_requests(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),amount REAL NOT NULL,method TEXT NOT NULL DEFAULT 'especes',status TEXT NOT NULL DEFAULT 'demande',reference TEXT UNIQUE NOT NULL,created_at TEXT NOT NULL,paid_at TEXT);
        ''')
        vcols = {r['name'] for r in c.execute('PRAGMA table_info(vehicles)')}
        if 'state' not in vcols:
            c.execute("ALTER TABLE vehicles ADD COLUMN state TEXT NOT NULL DEFAULT 'disponible'")
        cols = {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
        if 'pickup_point_id' not in cols:
            c.execute('ALTER TABLE parcels ADD COLUMN pickup_point_id INTEGER REFERENCES pickup_points(id)')
        # v1.15.0 : plus de « casier » — on normalise l'ancien libellé s'il existe déjà
        c.execute("UPDATE pickup_points SET name='Point relais Oujda Centre', kind='relais' "
                  "WHERE name='Casier intelligent Oujda Centre'")
        if not c.execute('SELECT 1 FROM pickup_points LIMIT 1').fetchone():
            seed = [
                ('Point relais Oujda Centre', 'Oujda', 'Avenue Mohammed V — démo', 'relais', 0),
                ('Point relais Casablanca Maârif', 'Casablanca', 'Boulevard Bir Anzarane — démo', 'relais', 0),
                ('Point relais Agadir Talborjt', 'Agadir', 'Rue Oued Souss — démo', 'relais', 0),
            ]
            for name, city_name, addr, kind, lock in seed:
                row = c.execute('SELECT id FROM cities WHERE name=?', (city_name,)).fetchone()  # FK sûre : boot production sans villes = city_id NULL
                c.execute('INSERT INTO pickup_points(name,city_id,address,kind,lockers,active,created_at) VALUES(?,?,?,?,?,1,?)',
                          (name, row['id'] if row else None, addr, kind, lock, now()))

    def vehicle_of(c, driver_id):
        if not driver_id: return None
        return c.execute('SELECT * FROM vehicles WHERE driver_id=? AND active=1 ORDER BY id LIMIT 1', (driver_id,)).fetchone()

    def co2_of(c, driver_id, km):
        v = vehicle_of(c, driver_id)
        factor = VEHICLES[v['type']]['co2_per_km'] if v else CO2_PER_KM
        return round(km * factor, 2)
    app.o24_co2 = co2_of

    def maintenance_rows(c):
        rows = []
        for v in c.execute('SELECT * FROM vehicles WHERE active=1 ORDER BY id'):
            v = dict(v); spec = VEHICLES.get(v['type'], VEHICLES['thermique'])
            due = (v['service_km'] or 0) + spec['service_km'] - (v['km'] or 0)
            age_days = max(0, int((time.time() - _ts(v['service_at'] or v['created_at'])) / 86400)) if (v['service_at'] or v['created_at']) else 0
            since = max(0.0, (v['km'] or 0) - (v['service_km'] or 0))
            score = min(100, wear_score(since, spec['service_km'], v['battery_pct'] if v['type'] in ('electrique', 'drone') else None) + (10 if age_days > 180 else 0))
            why = []
            if due <= max(200.0, spec['service_km'] * 0.1): why.append('entretien dû sous %d km' % max(0, int(due)))
            if age_days > 180: why.append('entretien > 6 mois')
            if v['type'] in ('electrique', 'drone') and v['battery_pct'] is not None and v['battery_pct'] < 20:
                why.append('batterie faible (%d %%)' % int(v['battery_pct']))
            rows.append({'id': v['id'], 'label': v['label'], 'type': v['type'], 'plate': v['plate'] or '',
                         'driver_id': v['driver_id'], 'km': v['km'] or 0, 'km_before_service': round(max(0, due)),
                         'wear_score': score, 'reasons': why})
        return sorted(rows, key=lambda r: (-r['wear_score'], r['id']))

    def queue_tpl(c, pid, phone, code, text, trigger):
        if not intl_phone(phone): return
        for ch in ('whatsapp', 'sms'):
            c.execute('INSERT INTO outbox(parcel_id,channel,phone,code,text,status,trigger,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (pid, ch, intl_phone(phone), code, text, 'pending', trigger, now()))

    # ---------- chaînage du hook événements (après advanced_tech) : casier au dépôt ----------
    _prev = s.get('tech_notify_event')
    def smart_event(c, pid, status, u):
        if _prev: _prev(c, pid, status, u)
        ev = c.execute('SELECT status,note FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 1', (pid,)).fetchone()
        if not ev or ev['status'] != 'Livré':
            return
        note = ev['note'] or ''
        if note.startswith('Dépôt au point relais') or note.startswith('Colis retiré'):
            return  # événements émis par ce hook : anti-récursion
        p = c.execute('SELECT p.id,p.tracking,p.phone,p.pickup_point_id,pp.name point_name,pp.kind FROM parcels p '
                      'LEFT JOIN pickup_points pp ON pp.id=p.pickup_point_id WHERE p.id=?', (pid,)).fetchone()
        if not p or not p['pickup_point_id'] or p['kind'] == 'agence': return
        if c.execute('SELECT 1 FROM locker_assignments WHERE parcel_id=?', (pid,)).fetchone(): return
        code = ''.join(_sec.choice('0123456789') for _ in range(6))
        c.execute('INSERT INTO locker_assignments(parcel_id,point_id,code,delivered_at,created_at) VALUES(?,?,?,?,?)',
                  (pid, p['pickup_point_id'], code, now(), now()))
        text = render_tpl('locker', tracking=p['tracking'], point=p['point_name'], code=code)
        queue_tpl(c, pid, p['phone'], 'locker', text, 'casier')
        event(c, pid, 'Livré', 'Dépôt au point relais « %s » — code de retrait %s' % (p['point_name'], code), u)
    s['tech_notify_event'] = smart_event

    # ---------- API : flotte ----------
    @app.get('/api/vehicles')
    @auth('admin', 'livreur')
    def vehicles_list():
        u = user()
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE active=1 ORDER BY id DESC')]
            if u['role'] == 'livreur':
                rows = [r for r in rows if r['driver_id'] == u['id']]
            for r in rows:
                r['type_label'] = VEHICLES.get(r['type'], VEHICLES['thermique'])['label']
                r['co2_per_km'] = VEHICLES.get(r['type'], VEHICLES['thermique'])['co2_per_km']
            maint = [m for m in maintenance_rows(c) if u['role'] != 'livreur' or m['driver_id'] == u['id']]   # DANS le bloc
        return jsonify(rows=rows, types=[{'type': k, **v} for k, v in VEHICLES.items()], maintenance=maint)

    @app.post('/api/vehicles')
    @auth('admin')
    def vehicles_add():
        d = request.get_json(silent=True) or {}
        vtype = str(d.get('type') or 'thermique')
        if vtype not in VEHICLES: raise Error('Type de véhicule inconnu.')
        label = str(d.get('label') or '').strip()[:60]
        if not label: raise Error('Libellé obligatoire.')
        plate = str(d.get('plate') or '').strip()[:20]
        km = float(d.get('km') or 0); battery = d.get('battery_pct')
        battery = None if battery in (None, '') else max(0.0, min(100.0, float(battery)))
        did = d.get('driver_id')
        with conn() as c:
            if did is not None and not c.execute("SELECT 1 FROM users WHERE id=? AND role='livreur'", (did,)).fetchone():
                raise Error('Livreur invalide.')
            if did:
                c.execute('UPDATE vehicles SET active=0 WHERE driver_id=?', (did,))
            vid = c.execute('INSERT INTO vehicles(driver_id,label,type,plate,km,service_km,battery_pct,state,active,created_at) VALUES(?,?,?,?,?,?,?,?,1,?)',
                            (did, label, vtype, plate, km, km, battery, 'disponible', now())).lastrowid
        return jsonify(ok=True, id=vid)

    @app.post('/api/vehicles/<int:vid>/telemetry')
    @auth('admin', 'livreur')
    def vehicles_telemetry(vid):
        d = request.get_json(silent=True) or {}; u = user()
        with conn() as c:
            v = c.execute('SELECT * FROM vehicles WHERE id=?', (vid,)).fetchone()
            if not v: raise Error('Véhicule introuvable.', 404)
            if u['role'] == 'livreur' and v['driver_id'] != u['id']: raise Error('Véhicule hors de votre équipe.', 403)
            km = d.get('km'); battery = d.get('battery_pct')
            if km is not None: c.execute('UPDATE vehicles SET km=? WHERE id=?', (max(0.0, float(km)), vid))
            if battery not in (None, ''): c.execute('UPDATE vehicles SET battery_pct=? WHERE id=?', (max(0.0, min(100.0, float(battery))), vid))
        return jsonify(ok=True)

    @app.post('/api/vehicles/<int:vid>/service')
    @auth('admin')
    def vehicles_service(vid):
        d = request.get_json(silent=True) or {}
        with conn() as c:
            v = c.execute('SELECT * FROM vehicles WHERE id=?', (vid,)).fetchone()
            if not v: raise Error('Véhicule introuvable.', 404)
            c.execute('INSERT INTO service_logs(vehicle_id,km,note,created_at) VALUES(?,?,?,?)',
                      (vid, v['km'] or 0, str(d.get('note') or 'Entretien')[:200], now()))
            c.execute('UPDATE vehicles SET service_km=?,service_at=? WHERE id=?', (v['km'] or 0, now(), vid))
            drv = c.execute('SELECT name,phone FROM users WHERE id=?', (v['driver_id'],)).fetchone() if v['driver_id'] else None
            text = render_tpl('entretien', label=v['label'], km=int(v['km'] or 0))
            links = msg_links(drv['phone'] if drv else '', text)
        return jsonify(ok=True, text=text, links=links)

    @app.patch('/api/vehicles/<int:vid>')
    @auth('admin', 'livreur')
    def vehicles_patch(vid):
        d = request.get_json(silent=True) or {}; u = user()
        st = d.get('state')
        with conn() as c:
            v = c.execute('SELECT * FROM vehicles WHERE id=?', (vid,)).fetchone()
            if not v: raise Error('Véhicule introuvable.', 404)
            if u['role'] == 'livreur' and v['driver_id'] != u['id']: raise Error('Véhicule hors de votre équipe.', 403)
            if st:
                if st not in ('disponible', 'en_tournee', 'maintenance', 'garage'):
                    raise Error('État inconnu (disponible/en_tournee/maintenance/garage).')
                if st == 'en_tournee' and v['state'] != 'disponible':
                    raise Error('Seul un véhicule disponible peut partir en tournée.')
                c.execute('UPDATE vehicles SET state=? WHERE id=?', (st, vid))
        return jsonify(ok=True)

    @app.get('/api/vehicles/alerts')
    @auth('admin', 'livreur')
    def vehicles_alerts():
        u = user()
        with conn() as c:
            alerts = []
            for m in maintenance_rows(c):
                if u['role'] == 'livreur' and m['driver_id'] != u['id']: continue
                for why in m['reasons']:
                    alerts.append({'vehicle_id': m['id'], 'label': m['label'], 'text': why,
                                   'level': 'alerte' if 'batterie' in why else 'info', 'wear_score': m['wear_score']})
        return jsonify(alerts=alerts)

    # ---------- API : points relais & casiers ----------
    @app.get('/api/pickup-points')
    @auth('admin', 'agent', 'livreur')
    def points_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT pp.*,ci.name city FROM pickup_points pp LEFT JOIN cities ci ON ci.id=pp.city_id ORDER BY pp.name')]
            for r in rows:
                r['assigned'] = c.execute('SELECT COUNT(*) n FROM parcels WHERE pickup_point_id=?', (r['id'],)).fetchone()['n']
                r['free'] = max(0, (r['lockers'] or 0) - r['assigned'])
        return jsonify(rows=rows)

    @app.post('/api/pickup-points')
    @auth('admin')
    def points_add():
        d = request.get_json(silent=True) or {}
        name = str(d.get('name') or '').strip()[:80]
        kind = str(d.get('kind') or 'relais')
        if not name or kind not in POINT_KINDS: raise Error('Nom et type (relais/casier/agence) obligatoires.')
        lockers = int(d.get('lockers') or 0)
        with conn() as c:
            if c.execute('SELECT 1 FROM pickup_points WHERE name=?', (name,)).fetchone():
                raise Error('Ce nom de point existe déjà.')
            cid = d.get('city_id')
            if not cid and d.get('city'):
                row = c.execute('SELECT id FROM cities WHERE name=?', (str(d['city']).strip(),)).fetchone()
                cid = row['id'] if row else None
            pid = c.execute('INSERT INTO pickup_points(name,city_id,address,kind,lockers,active,created_at) VALUES(?,?,?,?,?,1,?)',
                            (name, cid, str(d.get('address') or '')[:120], kind, max(0, lockers), now())).lastrowid
        return jsonify(ok=True, id=pid)

    @app.post('/api/parcels/<int:pid>/pickup-point')
    @auth('admin')
    def parcel_point(pid):
        d = request.get_json(silent=True) or {}; u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            point_id = d.get('point_id') or d.get('pickup_point_id')
            if point_id:
                pt = c.execute('SELECT * FROM pickup_points WHERE id=? AND active=1', (point_id,)).fetchone()
                if not pt: raise Error('Point relais introuvable ou inactif.')
                c.execute('UPDATE parcels SET pickup_point_id=? WHERE id=?', (point_id, pid))
                event(c, pid, p['status'], 'Retrait prévu au point relais « %s »' % pt['name'], u)
            else:
                c.execute('UPDATE parcels SET pickup_point_id=NULL WHERE id=?', (pid,))
                event(c, pid, p['status'], 'Retrait à domicile (point relais retiré)', u)
        return jsonify(ok=True)

    @app.get('/api/parcels/<int:pid>/locker')
    @auth('admin', 'agent', 'livreur')
    def parcel_locker(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u) if u['role'] != 'agent' else dict(c.execute('SELECT * FROM parcels WHERE id=?', (pid,)).fetchone() or {})
            if not p: raise Error('Colis introuvable.', 404)
            rows = [dict(r) for r in c.execute('SELECT la.*,pp.name point_name FROM locker_assignments la JOIN pickup_points pp ON pp.id=la.point_id WHERE la.parcel_id=? ORDER BY la.id DESC', (pid,))]
        return jsonify(rows=rows)

    @app.post('/api/lockers/<int:lid>/pick')
    @auth('admin', 'agent', 'livreur')
    def locker_pick(lid):
        d = request.get_json(silent=True) or {}; u = user()
        code = str(d.get('code') or '')
        with conn() as c:
            la = c.execute('SELECT la.*,p.tracking FROM locker_assignments la JOIN parcels p ON p.id=la.parcel_id WHERE la.id=?', (lid,)).fetchone()
            if not la: raise Error('Casier introuvable.', 404)
            if la['picked_at']: raise Error('Colis déjà retiré.', 409)
            if not _sec.compare_digest(code, la['code']): raise Error('Code de retrait incorrect.', 400)
            c.execute('UPDATE locker_assignments SET picked_at=? WHERE id=?', (now(), lid))
            event(c, la['parcel_id'], 'Livré', 'Colis retiré au point relais (code vérifié)', u)
        return jsonify(ok=True)

    # ---------- API : e-paiement / mobile money ----------
    @app.post('/api/parcels/<int:pid>/payment')
    @auth('admin')
    def payment_add(pid):
        d = request.get_json(silent=True) or {}; u = user()
        method = str(d.get('method') or 'especes')
        if method not in ('especes', 'mobile', 'lien'): raise Error('Mode de paiement invalide (especes/mobile/lien).')
        with conn() as c:
            p = parcel(c, pid, u)
            amount = float(d.get('amount') if d.get('amount') is not None else (p['amount'] or 0))
            if not (0 < amount <= 100000): raise Error('Montant invalide.')
            ref = 'PAY-' + _sec.token_hex(4).upper()
            req_id = c.execute('INSERT INTO payment_requests(parcel_id,amount,method,status,reference,created_at) VALUES(?,?,?,?,?,?)',
                               (pid, amount, method, 'demande', ref, now())).lastrowid
            text = render_tpl('payment', amount=('%.2f' % amount), tracking=p['tracking'], ref=ref)
            queue_tpl(c, pid, p['phone'], 'payment', text, 'paiement')
            event(c, pid, p['status'], 'Demande de paiement %s (%.2f MAD, réf. %s)' % (method, amount, ref), u)
        return jsonify(ok=True, id=req_id, reference=ref, text=text, links=msg_links(p['phone'], text))

    @app.post('/api/payments/<int:rid>/paid')
    @auth('admin')
    def payment_paid(rid):
        u = user()
        with conn() as c:
            r = c.execute('SELECT * FROM payment_requests WHERE id=?', (rid,)).fetchone()
            if not r: raise Error('Demande introuvable.', 404)
            if r['status'] == 'paye': raise Error('Déjà encaissée.', 409)
            c.execute("UPDATE payment_requests SET status='paye',paid_at=? WHERE id=?", (now(), rid))
            st = c.execute('SELECT status FROM parcels WHERE id=?', (r['parcel_id'],)).fetchone()
            event(c, r['parcel_id'], st['status'] if st else 'Livré', 'Paiement encaissé (%.2f MAD, réf. %s)' % (r['amount'], r['reference']), u)
        return jsonify(ok=True)

    @app.get('/api/payments')
    @auth('admin')
    def payments_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT pr.*,p.tracking,p.phone FROM payment_requests pr JOIN parcels p ON p.id=pr.parcel_id ORDER BY pr.id DESC LIMIT 100')]
        for r in rows:
            r['links'] = msg_links(r.get('phone'), render_tpl('payment', amount=('%.2f' % r['amount']), tracking=r['tracking'], ref=r['reference']))
        return jsonify(rows=rows)

    # ---------- API : jumeau numérique (simulation de journée) ----------
    @app.get('/api/dispatch/simulate')
    @auth('admin')
    def dispatch_simulate():
        trials = request.args.get('trials', 20, type=int)
        if trials < 5 or trials > 50: raise Error('Tirages Monte-Carlo entre 5 et 50.')
        with conn() as c:
            pend = [dict(r) for r in c.execute('SELECT p.id,p.city_id,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE p.status=\'Créé\' AND p.driver_id IS NULL ORDER BY p.city_id,p.id')]
            drivers = [dict(r) for r in c.execute("SELECT id,name FROM users WHERE role='livreur' AND active=1 ORDER BY name")]
            model = (getattr(app, 'o24_eta', None) or (lambda: {'a': 18.0, 'b': 1.875, 'learned': False}))()
            a, b = (float(model['a']), float(model['b'])) if model.get('learned') else (18.0, 1.875)
        if not pend or not drivers: raise Error('Simulation impossible : il faut des colis non affectés et des livreurs actifs.')
        blocks = {}
        for p in pend: blocks.setdefault(p['city_id'], []).append(p)
        loads = {d['id']: 0 for d in drivers}
        proj = dict(loads); assign = {d['id']: [] for d in drivers}
        for cid, ps in sorted(blocks.items(), key=lambda x: (-len(x[1]), str(x[0]))):
            d0 = min(proj, key=lambda k: (proj[k], next(d['name'] for d in drivers if d['id'] == k)))
            assign[d0].extend(p['id'] for p in ps); proj[d0] += len(ps)
        cities = {p['city_id']: p['city'] for p in pend}
        lots = []
        for d in drivers:
            ids = assign[d['id']]
            if not ids: continue
            ps = [p for p in pend if p['id'] in set(ids)]
            geos = [GEO.get(cities.get(p['city_id']) or '') for p in ps]
            km = route_km([geos[i] for i in order_route(geos)])
            with conn() as c: co2 = co2_of(c, d['id'], km)
            base = a * len(ps) + b * km
            lots.append({'driver_id': d['id'], 'name': d['name'], 'added': len(ps), 'km_est': km, 'base_min': round(base), 'co2_kg': co2})
        rnd = random.Random(int(time.time() // 86400))
        finishes, ontime, risks = [], 0, 0
        for _ in range(trials):
            worst = 0
            for lot in lots:
                jitter = 1 + rnd.uniform(-0.15, 0.15)
                minutes = lot['base_min'] * jitter + rnd.uniform(0, 25)  # imprévus terrain
                worst = max(worst, minutes)
                if minutes > 480: risks += 1
                else: ontime += 1
            finishes.append(worst)
        total = max(1, trials * max(1, len(lots)))
        finish_p90 = sorted(finishes)[int(0.9 * (len(finishes) - 1))] if finishes else 0
        on_time_rate = round(100 * ontime / total)
        rec = 'Lot sain : appliquez la répartition.' if on_time_rate >= 85 and finish_p90 <= 540 else \
              ('Charge limite : réduisez les lots ou ajoutez un livreur avant d\'appliquer.' if on_time_rate >= 60 else
               'Surcharge probable : ne pas appliquer en l\'état — rééquilibrez (2 lots ou plus).')
        return jsonify(trials=trials, lots=lots,
                       simulation={'on_time_rate': on_time_rate, 'finish_p90_min': round(finish_p90),
                                   'late_lot_rate': round(100 * (total - ontime) / total), 'co2_kg': round(sum(l['co2_kg'] for l in lots), 2)},
                       recommendation=rec,
                       method='Monte-Carlo %d tirages sur le modèle ETA (±15 %% + imprévus 0–25 min)' % trials)

    # ---------- API : décisionnel & SLA & flotte (regroupé) ----------
    @app.get('/api/insights/fleet')
    @auth('admin')
    def insights_fleet():
        with conn() as c:
            veh = [dict(r) for r in c.execute('SELECT * FROM vehicles WHERE active=1 ORDER BY id')]
            maint = maintenance_rows(c)
            lockers = [dict(r) for r in c.execute('SELECT la.*,pp.name point_name,p.tracking FROM locker_assignments la '
                                                  'JOIN pickup_points pp ON pp.id=la.point_id JOIN parcels p ON p.id=la.parcel_id ORDER BY la.id DESC LIMIT 12')]
            pays = [dict(r) for r in c.execute('SELECT pr.*,p.tracking FROM payment_requests pr JOIN parcels p ON p.id=pr.parcel_id ORDER BY pr.id DESC LIMIT 12')]
            # SLA : délais Création → Livré, taux au 1er passage, taux à J+1
            delivered = [dict(r) for r in c.execute(
                'SELECT p.id,p.created_at,p.updated_at,EXISTS(SELECT 1 FROM events e WHERE e.parcel_id=p.id AND e.status IN (\'Reporté\',\'Programmé\')) had_retry '
                "FROM parcels p WHERE p.status='Livré'")]
            delays = []
            for d in delivered:
                h = (_ts(d['updated_at']) - _ts(d['created_at'])) / 3600.0
                if 0 <= h <= 24 * 30: delays.append(h)
            n = max(1, len(delays))
            sla = {'delivered': len(delays),
                   'avg_delivery_hours': round(sum(delays) / n, 1) if delays else 0,
                   'first_pass_rate': round(100 * sum(0 if d['had_retry'] else 1 for d in delivered) / n),
                   'j1_rate': round(100 * sum(1 for h in delays if h <= 24) / n)}
        return jsonify(vehicles=veh, maintenance=maint, lockers=lockers, payments=pays, sla=sla,
                       types=[{'type': k, **v} for k, v in VEHICLES.items()])

    # ---------- API : exports CSV (big data) ----------
    QUERIES = {
        'parcels': 'SELECT p.id,p.tracking,p.status,p.amount,p.created_at,p.updated_at,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id ORDER BY p.id',
        'events': 'SELECT id,parcel_id,actor_id,status,note,created_at FROM events ORDER BY id',
        'deliveries': "SELECT p.id,p.tracking,p.updated_at delivered_at,p.driver_id FROM parcels p WHERE p.status='Livré' ORDER BY p.updated_at",
        'vehicles': 'SELECT id,driver_id,label,type,plate,km,battery_pct,active FROM vehicles ORDER BY id',
    }

    @app.get('/api/exports/<kind>.csv')
    @auth('admin')
    def exports_csv(kind):
        q = QUERIES.get(kind)
        if not q: raise Error('Export inconnu (parcels, events, deliveries, vehicles).', 404)
        with conn() as c:
            cur = c.execute(q)
            cols = [d[0] for d in cur.description]
            rows = [dict(r) for r in cur]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader(); w.writerows(rows)   # entête toujours présente, même export vide
        return Response(buf.getvalue(), 200, content_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition': 'attachment; filename="oriental24-%s.csv"' % kind})
