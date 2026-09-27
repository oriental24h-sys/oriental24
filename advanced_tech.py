"""v1.9.0 « Technologies avancées » — pack des technologies de l'article
« أحدث التقنيات المستعملة لدى شركات التوصيل والخدمات اللوجستية » qui manquaient au système :

 1. WhatsApp/SMS automatiques : boîte d'envoi (outbox) + gabarits + liens wa.me/sms prêts
    (l'appareil de l'utilisateur ouvre WhatsApp/SMS — aucune API payante), passerelle optionnelle.
 2. IA/ML : ETA prédictive apprise de l'historique (régression moindres carrés), prévisions de
    volume (moyenne mobile par jour de semaine × tendance), score de risque retard.
 3. IoT : télémétrie colis (température, choc, humidité, batterie) + alertes chaîne du froid/choc.
 4. Blockchain : chaîne de preuve de livraison scellée (SHA-256 liant les événements) + vérification.
 5. Géofencing : alertes automatiques « proche » (2 km) et « arrivé » (500 m) par rayon haversine.
 6. Logistique verte : empreinte CO₂ par tournée (facteur 0,12 kg/km utilitaire).
 7. Assistant conversationnel (règles FR/darija) sur le suivi public — réponses issues d'une
    liste blanche, zéro fuite (jamais d'adresse, de montant ni de nom).
 8. Tri automatisé : zones de tri affectées par motif de ville (étiquettes A5).

Tout est calculé localement : aucune API externe, aucun appel réseau sortant (les liens
WhatsApp/SMS s'ouvrent côté utilisateur ; la passerelle O24_MSG_GATEWAY reste optionnelle)."""
import hashlib, math, re, time, unicodedata
from datetime import datetime, timedelta
from urllib.parse import quote
from flask import request, jsonify
from tour_control import OUT_STATES, OPEN_STATES, GEO, haversine, route_km, order_route, MSG_TEMPLATES

# ---- gabarits de notification : texte figé + variables système uniquement ({tracking}, {code}) ----
NOTIF = {
    'pickup':   'ORIENTAL24 : votre colis {tracking} a été ramassé et rejoint notre réseau de livraison.',
    'out':      'ORIENTAL24 : votre colis {tracking} est en cours de livraison aujourd’hui.',
    'delivered':'ORIENTAL24 : votre colis {tracking} a été livré. Merci de votre confiance !',
    'reported': 'ORIENTAL24 : votre colis {tracking} est reporté — votre livreur reprogramme un passage.',
    'refused':  'ORIENTAL24 : votre colis {tracking} a été refusé à la livraison ; notre équipe vous contacte.',
    'returned': 'ORIENTAL24 : votre colis {tracking} retourne à l’agence après échec de livraison.',
    'otp':      'ORIENTAL24 : code de réception du colis {tracking} = {code}. Ne le communiquez qu’au livreur.',
    'arrived':  'ORIENTAL24 : votre livreur arrive à votre adresse pour le colis {tracking}.',
    'near':     MSG_TEMPLATES['near'],
    'eta10':    MSG_TEMPLATES['eta10'],
    'patience': MSG_TEMPLATES['patience'],
}
STATUS_NOTIF = {'Ramassé': 'pickup', 'En livraison': 'out', 'Livré': 'delivered',
                'Reporté': 'reported', 'Refusé': 'refused', 'Retourné': 'returned'}
MSG_BY_TEXT = {v: k for k, v in MSG_TEMPLATES.items()}
CO2_PER_KM = 0.12  # utilitaire thermique moyen (kg CO₂ / km)

DEFAULT_ZONES = [
    ('A', 'Zone A — Oriental', 'oujda|berkane|nador|jerada|taourirt|guercif|saidia|ahfir|taourirt'),
    ('B', 'Zone B — Nord', 'tanger|tetouan|tétouan|chefchaouen|ouezzane|taounate|sefrou|fes|fès|meknes|meknès|taza'),
    ('C', 'Zone C — Centre', 'rabat|sale|salé|temara|témara|kenitra|kénitra|casablanca|mohammedia|berrechid|settat|jadida|khouribga'),
    ('D', 'Zone D — Sud & Atlas', 'marrakech|agadir|inezgane|essaouira|safi|taroudant|guelmim|laayoune|laâyoune|dakhla|smara|ouarzazate|errachidia|midelt|azilal|mellal|ifran|ifrane|youssoufia'),
]

def norm(s):
    return ''.join(ch for ch in unicodedata.normalize('NFD', str(s or '').lower()) if unicodedata.category(ch) != 'Mn')

def intl_phone(raw):
    d = re.sub(r'\D', '', str(raw or ''))
    if d.startswith('00'): d = d[2:]
    if d.startswith('212'): return d
    if len(d) == 10 and d.startswith('0'): return '212' + d[1:]
    return d if len(d) >= 8 else ''

def wa_link(phone, text):
    p = intl_phone(phone)
    return 'https://wa.me/%s?text=%s' % (p, quote(text)) if p else ''

def sms_link(phone, text):
    p = intl_phone(phone)
    return 'sms:%s?body=%s' % (p, quote(text)) if p else ''

def msg_links(phone, text):
    return {'whatsapp': wa_link(phone, text), 'sms': sms_link(phone, text)}

def _ts(t):
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try: return time.mktime(time.strptime(str(t)[:19], fmt))
        except Exception: pass
    return 0.0

def _solve3(A, b):
    M = [A[i][:] + [b[i]] for i in range(3)]
    for i in range(3):
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        if abs(M[p][i]) < 1e-9: return None
        M[i], M[p] = M[p], M[i]
        for r in range(3):
            if r == i: continue
            f = M[r][i] / M[i][i]
            for cc in range(i, 4): M[r][cc] -= f * M[i][cc]
    return [M[i][3] / M[i][i] for i in range(3)]

def tour_samples(c):
    """(livreur, jour) → (arrêts livrés, km de tournée, minutes en livraison) — socle de l'apprentissage."""
    cities = {r['id']: r['name'] for r in c.execute('SELECT id,name FROM cities')}
    evs = [dict(r) for r in c.execute(
        "SELECT e.actor_id d, substr(e.created_at,1,10) g, e.status s, e.created_at t, p.city_id cid "
        "FROM events e JOIN parcels p ON p.id=e.parcel_id WHERE e.status IN ('En livraison','Livré') "
        "ORDER BY e.created_at")]
    groups = {}
    for e in evs:
        g = groups.setdefault((e['d'], e['g']), {'start': None, 'end': None, 'cities': []})
        if e['s'] == 'En livraison':
            g['start'] = g['start'] or e['t']
        else:
            g['end'] = e['t']; g['cities'].append(e['cid'])
    samples = []
    for g in groups.values():
        if not g['cities'] or not g['start'] or not g['end']: continue
        minutes = (_ts(g['end']) - _ts(g['start'])) / 60.0
        if not (1 <= minutes <= 600): continue
        geos = [GEO.get(cities.get(cid) or '') for cid in g['cities']]
        km = route_km([geos[i] for i in order_route(geos)]) if len(geos) > 1 else 0.0
        samples.append((len(g['cities']), km, minutes))
    return samples

def eta_model(c):
    """IA — régression moindres carrés : minutes ≈ a·arrêts + b·km + c (repli : 18 min/arrêt, 1,875 min/km)."""
    samples = tour_samples(c)
    if len(samples) >= 4:
        X = [[s[0], s[1], 1.0] for s in samples]; y = [s[2] for s in samples]
        A = [[sum(X[k][i] * X[k][j] for k in range(len(X))) for j in range(3)] for i in range(3)]
        B = [sum(X[k][i] * y[k] for k in range(len(X))) for i in range(3)]
        sol = _solve3(A, B)
        if sol and all(abs(v) < 1e6 for v in sol) and sol[0] > 0.5:
            return {'a': round(sol[0], 3), 'b': round(max(sol[1], 0.0), 4), 'c': round(sol[2], 2),
                    'n': len(samples), 'learned': True}
    return {'a': 18.0, 'b': 1.875, 'c': 0.0, 'n': len(samples), 'learned': False}

def forecasts(c):
    """Prévision de volume : moyenne par jour de semaine sur 28 jours × tendance (7 j vs 7 j précédents)."""
    today = datetime.now().date()
    counts = {}
    for r in c.execute("SELECT substr(created_at,1,10) d, COUNT(DISTINCT parcel_id) n FROM events "
                       "WHERE status='Livré' GROUP BY d"):
        counts[r['d']] = r['n']
    hist, last7, prev7 = [], 0, 0
    for i in range(1, 29):
        day = (today - timedelta(days=i)).isoformat()
        n = counts.get(day, 0); hist.append((day, n, (today - timedelta(days=i)).weekday()))
        if i <= 7: last7 += n
        elif i <= 14: prev7 += n
    by_wd = {}
    for _, n, wd in hist: by_wd.setdefault(wd, []).append(n)
    wd_mean = {wd: sum(v) / len(v) for wd, v in by_wd.items()}
    global_mean = (sum(n for _, n, _ in hist) / len(hist)) if hist else 0.0
    trend = 1.0 if not prev7 else min(2.0, max(0.5, last7 / prev7)) if prev7 else (2.0 if last7 else 1.0)
    rows = []
    for i in range(1, 8):
        day = today + timedelta(days=i)
        base = wd_mean.get(day.weekday(), global_mean)
        rows.append({'date': day.isoformat(), 'weekday': day.weekday(),
                     'expected': max(0, round(base * trend))})
    return {'rows': rows, 'trend': round(trend, 2), 'method': 'moyenne jour de semaine (28 j) × tendance 7/7'}

def risk_rows(c):
    """Score de risque retard — barème transparent (silence, report, COD élevé, non affecté)."""
    nowt = time.time()
    rows = []
    marks = '(' + ','.join('?' * len(OPEN_STATES)) + ')'
    for p in c.execute('SELECT p.id,p.tracking,p.status,p.amount,p.driver_id,p.updated_at,ci.name city '
                       'FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE p.status IN ' + marks, list(OPEN_STATES)):
        p = dict(p); age = nowt - _ts(p['updated_at']); score, why = 0, []
        if age >= 2 * 86400: score += 40; why.append('silence > 48 h')
        elif age >= 86400: score += 20; why.append('silence > 24 h')
        if p['status'] in ('Reporté', 'Intéressé'): score += 25; why.append('report/intérêt')
        if p['status'] in ('Réceptionné', 'Au hub') and age >= 86400: score += 15; why.append('immobilisé au hub')
        if (p['amount'] or 0) >= 2000: score += 15; why.append('COD élevé')
        if not p['driver_id'] and p['status'] != 'Créé': score += 10; why.append('sans livreur')
        if score: rows.append({'id': p['id'], 'tracking': p['tracking'], 'city': p['city'] or '',
                               'status': p['status'], 'score': min(100, score), 'reasons': why})
    return sorted(rows, key=lambda r: (-r['score'], r['id']))[:12]

def register_advanced_tech(app, s):
    conn, auth, user, now, Error, event, parcel = (s['conn'], s['auth'], s['user'], s['now'], s['APIError'], s['event'], s['parcel'])
    import sqlite3 as _sq
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),channel TEXT NOT NULL,phone TEXT,code TEXT NOT NULL,text TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',trigger TEXT,created_at TEXT NOT NULL,sent_at TEXT);
        CREATE TABLE IF NOT EXISTS parcel_telemetry(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),temp_c REAL,shock_g REAL,humidity REAL,battery REAL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS proof_seals(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),seal TEXT NOT NULL,head_event INTEGER,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS geofence_hits(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),code TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sort_zones(id INTEGER PRIMARY KEY,code TEXT UNIQUE NOT NULL,label TEXT NOT NULL,pattern TEXT NOT NULL,active INTEGER DEFAULT 1);
        CREATE INDEX IF NOT EXISTS outbox_parcel_idx ON outbox(parcel_id,id);
        CREATE INDEX IF NOT EXISTS telemetry_parcel_idx ON parcel_telemetry(parcel_id,id);
        ''')
        for code, label, pattern in DEFAULT_ZONES:
            c.execute('INSERT OR IGNORE INTO sort_zones(code,label,pattern,active) VALUES(?,?,?,1)', (code, label, pattern))

    # ---------- noyau commun : gabarits, liens, file d'envoi ----------
    def render(code, tracking, otp=None):
        return NOTIF[code].format(tracking=tracking, code=otp or '····')

    def queue(c, pid, tracking, phone, code, text, trigger):
        if not intl_phone(phone): return
        for ch in ('whatsapp', 'sms'):
            c.execute('INSERT INTO outbox(parcel_id,channel,phone,code,text,status,trigger,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (pid, ch, intl_phone(phone), code, text, 'pending', trigger, now()))

    def chain(c, pid):
        rows = [dict(r) for r in c.execute('SELECT id,actor_id,status,note,created_at FROM events WHERE parcel_id=? ORDER BY id', (pid,))]
        h = hashlib.sha256(('%d|GENESIS' % pid).encode()).hexdigest(); out = []
        for r in rows:
            h = hashlib.sha256(('%s|%s|%s|%s|%s|%s' % (h, r['id'], r['actor_id'], r['status'], r['note'], r['created_at'])).encode()).hexdigest()
            out.append((r, h))
        return out

    def seal_now(c, pid, u):
        rows = chain(c, pid)
        if not rows: return
        event(c, pid, rows[-1][0]['status'], 'Preuve scellée (blockchain) : empreinte SHA-256 de la chaîne', u)
        rows = chain(c, pid)  # le scell couvre y compris sa propre trace : chaine close
        c.execute('INSERT INTO proof_seals(parcel_id,seal,head_event,created_at) VALUES(?,?,?,?)',
                  (pid, rows[-1][1], rows[-1][0]['id'], now()))

    def zone_for(city_name):
        target = norm(city_name)
        with conn() as c:
            zs = [dict(r) for r in c.execute('SELECT code,label,pattern FROM sort_zones WHERE active=1 ORDER BY code')]
        for z in zs:
            if any(tok and tok in target for tok in (norm(t).strip() for t in z['pattern'].split('|'))):
                return {'code': z['code'], 'label': z['label'], 'rule': z['pattern']}
        return {'code': None, 'label': 'Non trié', 'rule': ''}

    # ---------- hook événements : notifications auto + scellé de preuve ----------
    def tech_notify_event(c, pid, status, u):
        evs = [dict(r) for r in c.execute('SELECT status,note FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 2', (pid,))]
        if not evs: return
        new, prev = evs[0], (evs[1] if len(evs) > 1 else None)
        p = c.execute('SELECT tracking,phone,otp_code FROM parcels WHERE id=?', (pid,)).fetchone()
        if not p: return
        note = new['note'] or ''
        if note.startswith('Message au client'):
            text = note.split(': ', 1)[1] if ': ' in note else note
            code = MSG_BY_TEXT.get(text, 'patience')
            queue(c, pid, p['tracking'], p['phone'], code, text, 'guidé')
            return
        if note == 'Code client OTP activé' and p['otp_code']:
            queue(c, pid, p['tracking'], p['phone'], 'otp', render('otp', p['tracking'], p['otp_code']), 'otp')
            return
        if prev is not None and new['status'] != prev['status']:
            code = STATUS_NOTIF.get(new['status'])
            if code:
                queue(c, pid, p['tracking'], p['phone'], code, render(code, p['tracking']), 'statut')
            if new['status'] == 'Livré' and not c.execute('SELECT 1 FROM proof_seals WHERE parcel_id=?', (pid,)).fetchone():
                seal_now(c, pid, u)
    s['tech_notify_event'] = tech_notify_event

    # ---------- hook géofence : appelé par /api/driver/position (tour_control) ----------
    def o24_geofence(c, driver_id, lat, lng):
        marks = '(' + ','.join('?' * len(OUT_STATES)) + ')'
        rows = [dict(r) for r in c.execute(
            'SELECT p.id,p.tracking,p.phone,p.status,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id '
            'WHERE p.driver_id=? AND p.status IN ' + marks, [driver_id, *OUT_STATES])]
        u = {'id': driver_id}
        for p in rows:
            g = GEO.get(p['city'] or '')
            if not g: continue
            d = haversine((lat, lng), g)
            if d <= 2.0 and not c.execute("SELECT 1 FROM geofence_hits WHERE parcel_id=? AND code='near'", (p['id'],)).fetchone():
                c.execute("INSERT INTO geofence_hits(parcel_id,code,created_at) VALUES(?,'near',?)", (p['id'], now()))
                c.execute('INSERT INTO parcel_messages(parcel_id,actor_id,code,created_at) VALUES(?,?,?,?)',
                          (p['id'], driver_id, 'near', now()))
                event(c, p['id'], p['status'], 'Message au client : ' + MSG_TEMPLATES['near'], u)
            if d <= 0.5 and not c.execute("SELECT 1 FROM geofence_hits WHERE parcel_id=? AND code='arrived'", (p['id'],)).fetchone():
                c.execute("INSERT INTO geofence_hits(parcel_id,code,created_at) VALUES(?,'arrived',?)", (p['id'], now()))
                event(c, p['id'], p['status'], 'Géofence : livreur à moins de 500 m de la ville de livraison', u)
                queue(c, p['id'], p['tracking'], p['phone'], 'arrived', render('arrived', p['tracking']), 'geofence')
    app.o24_geofence = o24_geofence

    # ---------- modèle ETA partagé (mémoire 60 s) ----------
    _eta_cache = {'t': 0.0, 'm': None}
    def o24_eta():
        if time.time() - _eta_cache['t'] > 60 or _eta_cache['m'] is None:
            with conn() as c: _eta_cache['m'] = eta_model(c)
            _eta_cache['t'] = time.time()
        return _eta_cache['m']
    app.o24_eta = o24_eta
    app.o24_msg_links = msg_links

    # ---------- API : boîte d'envoi WhatsApp/SMS ----------
    @app.get('/api/outbox')
    @auth('admin')
    def outbox_list():
        q = request.args.get('parcel_id', type=int)
        with conn() as c:
            sql = ('SELECT o.*,p.tracking FROM outbox o JOIN parcels p ON p.id=o.parcel_id')
            args = []
            if q: sql += ' WHERE o.parcel_id=?'; args = [q]
            sql += ' ORDER BY o.id DESC LIMIT 80'
            rows = []
            for r in c.execute(sql, args):
                r = dict(r); r['links'] = msg_links(r['phone'], r['text']); rows.append(r)
        return jsonify(rows=rows)

    @app.post('/api/outbox/<int:oid>/sent')
    @auth('admin')
    def outbox_sent(oid):
        with conn() as c:
            r = c.execute('SELECT id FROM outbox WHERE id=?', (oid,)).fetchone()
            if not r: raise Error('Notification introuvable.', 404)
            c.execute("UPDATE outbox SET status='sent_manual',sent_at=? WHERE id=?", (now(), oid))
        return jsonify(ok=True)

    @app.post('/api/parcels/<int:pid>/notify')
    @auth('admin', 'livreur')
    def parcel_notify(pid):
        d = request.get_json(silent=True) or {}; u = user()
        code = d.get('code')
        if code not in NOTIF: raise Error('Notification invalide : choisissez un gabarit préparé.')
        with conn() as c:
            p = parcel(c, pid, u)
            text = render(code, p['tracking'], p.get('otp_code'))
            queue(c, pid, p['tracking'], p['phone'], code, text, 'manuel')
            event(c, pid, p['status'], 'Notification WhatsApp/SMS mise en file : ' + text, u)
        return jsonify(ok=True, text=text, links=msg_links(p['phone'], text))

    # ---------- API : télémétrie IoT ----------
    @app.post('/api/parcels/<int:pid>/telemetry')
    @auth('admin', 'livreur')
    def telemetry_push(pid):
        d = request.get_json(silent=True) or {}; u = user()
        vals = {}
        for k, lo, hi in (('temp_c', -30, 60), ('shock_g', 0, 50), ('humidity', 0, 100), ('battery', 0, 100)):
            if d.get(k) is not None:
                try: v = float(d[k])
                except (TypeError, ValueError): raise Error('Valeur de capteur invalide : ' + k)
                if not lo <= v <= hi: raise Error('Valeur de capteur hors plage : ' + k)
                vals[k] = round(v, 2)
        if not vals: raise Error('Aucune mesure reçue (temp_c, shock_g, humidity ou battery).')
        with conn() as c:
            p = parcel(c, pid, u)
            cols = list(vals)
            c.execute('INSERT INTO parcel_telemetry(parcel_id,%s,created_at) VALUES(%s)' % (','.join(cols), ','.join('?' * (len(cols) + 2))),
                      [pid, *[vals[k] for k in cols], now()])
            alerts = []
            if 'temp_c' in vals and not (2 <= vals['temp_c'] <= 40):
                alerts.append('température hors norme (%.1f °C)' % vals['temp_c'])
            if 'shock_g' in vals and vals['shock_g'] > 3:
                alerts.append('choc détecté (%.1f g)' % vals['shock_g'])
            for a in alerts:
                event(c, pid, p['status'], 'Alerte IoT : ' + a, u)
        return jsonify(ok=True, alerts=alerts, **vals)

    @app.get('/api/parcels/<int:pid>/telemetry')
    @auth('admin', 'livreur')
    def telemetry_list(pid):
        u = user()
        with conn() as c:
            parcel(c, pid, u)
            rows = [dict(r) for r in c.execute('SELECT * FROM parcel_telemetry WHERE parcel_id=? ORDER BY id DESC LIMIT 20', (pid,))]
            n_alerts = c.execute("SELECT COUNT(*) n FROM events WHERE parcel_id=? AND note LIKE 'Alerte IoT%'", (pid,)).fetchone()['n']
        return jsonify(rows=rows, alerts=n_alerts)

    # ---------- API : blockchain (preuve de livraison scellée) ----------
    @app.get('/api/parcels/<int:pid>/proof')
    @auth('admin', 'client', 'livreur')
    def proof_get(pid):
        u = user()
        with conn() as c:
            parcel(c, pid, u)
            rows = chain(c, pid)
            seals = [dict(r) for r in c.execute('SELECT seal,head_event,created_at FROM proof_seals WHERE parcel_id=? ORDER BY id DESC', (pid,))]
        head = rows[-1][1] if rows else None
        verified = None if not seals else (seals[0]['seal'] == head)
        return jsonify(head=head or '', verified=verified,
                       chain=[{'n': i + 1, 'event_id': r['id'], 'status': r['status'], 'note': r['note'] or '', 'date': r['created_at'], 'hash': h[:16]}
                              for i, (r, h) in enumerate(rows)],
                       seals=seals)

    @app.post('/api/parcels/<int:pid>/proof/seal')
    @auth('admin')
    def proof_seal(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            seal_now(c, pid, u)
        return jsonify(ok=True)

    # ---------- API : insights (IA + prévisions + risque + CO₂) ----------
    @app.get('/api/insights')
    @auth('admin')
    def insights():
        with conn() as c:
            model = eta_model(c)
            fc = forecasts(c)
            risk = risk_rows(c)
            samples = tour_samples(c)
            co2_week = round(sum(km for _, km, _ in samples) * CO2_PER_KM, 2)
            today = now()[:10]
            co2_today = 0.0
            drivers = [dict(r) for r in c.execute("SELECT id,name FROM users WHERE role='livreur' AND active=1 ORDER BY name")]
            parcels = [dict(r) for r in c.execute('SELECT p.id,p.driver_id,p.status,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id')]
            for d in drivers:
                geos = [GEO.get(p['city'] or '') for p in parcels if p['driver_id'] == d['id'] and p['status'] in OUT_STATES]
                km = route_km([geos[i] for i in order_route(geos)]) if len(geos) > 1 else 0.0
                d['km_est'], d['co2_kg'] = km, round(km * CO2_PER_KM, 2)
                co2_today += d['co2_kg']
            n_seals = c.execute('SELECT COUNT(*) n FROM proof_seals').fetchone()['n']
            n_outbox = c.execute("SELECT COUNT(*) n FROM outbox WHERE status='pending'").fetchone()['n']
            n_iot = c.execute('SELECT COUNT(*) n FROM parcel_telemetry').fetchone()['n']
        return jsonify(model=model, forecasts=fc, risk=risk,
                       co2={'factor_kg_per_km': CO2_PER_KM, 'today_kg': round(co2_today, 2), 'week_kg': co2_week, 'drivers': drivers},
                       counters={'seals': n_seals, 'outbox_pending': n_outbox, 'telemetry': n_iot})

    # ---------- API : zones de tri ----------
    @app.get('/api/sort-zones')
    @auth('admin', 'agent')
    def zones_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM sort_zones ORDER BY code')]
        return jsonify(rows=rows)

    @app.post('/api/sort-zones')
    @auth('admin')
    def zones_save():
        d = request.get_json(silent=True) or {}
        code = str(d.get('code') or '').strip().upper()[:8]
        label = str(d.get('label') or '').strip()[:80]
        pattern = str(d.get('pattern') or '').strip()[:400]
        if not code or not label or not pattern: raise Error('Code, libellé et motif de villes obligatoires.')
        active = 1 if d.get('active', True) else 0
        with conn() as c:
            c.execute('INSERT INTO sort_zones(code,label,pattern,active) VALUES(?,?,?,?) ON CONFLICT(code) DO UPDATE SET label=excluded.label,pattern=excluded.pattern,active=excluded.active',
                      (code, label, pattern, active))
        return jsonify(ok=True)

    @app.get('/api/parcels/<int:pid>/zone')
    @auth('admin', 'agent', 'livreur')
    def parcel_zone(pid):
        u = user()
        with conn() as c:
            p = c.execute('SELECT p.id,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE p.id=?', (pid,)).fetchone()
            if not p: raise Error('Colis introuvable.', 404)
        return jsonify(tracking_zone=zone_for(p['city']), city=p['city'] or '')

    # ---------- API : assistant conversationnel public (règles, FR/darija) ----------
    A_REPLY = {
        'greet': 'Bonjour ! Assistant ORIENTAL24. Donnez votre numéro de suivi (O24-…) puis demandez : position, arrivée, code…',
        'help': 'Je réponds sur : la position du colis (« où ? »), l’arrivée (« quand ? »), le code OTP, le livreur, le paiement à la livraison et l’adresse.',
        'thanks': 'Avec plaisir ! Je reste disponible pour toute autre question.',
        'fallback': 'Question non reconnue. Essayez : « où est mon colis ? », « quand il arrive ? », « code OTP », « livreur », « paiement ».',
        'otp': 'Le code de réception à 4 chiffres vous est transmis par l’expéditeur (SMS/WhatsApp). Ne le communiquez qu’au livreur.',
        'price': 'Le montant à la livraison (COD) est confirmé par l’expéditeur ; le livreur remet un reçu. Aucun paiement en ligne n’est requis.',
        'address': 'L’adresse se modifie auprès de l’expéditeur tant que le colis n’est pas en tournée.',
        'driver': 'En tournée, le prénom et le téléphone du livreur s’affichent sur votre suivi. Sinon : appelez le support ORIENTAL24.',
        'eta': 'L’arrivée estimée s’affiche sur votre suivi (fenêtre glissante selon le rang du colis dans la tournée).',
        'where': 'Indiquez votre numéro de suivi (O24-…) pour connaître sa position.',
    }
    INTENTS = [('otp', ['code', 'otp']),
               ('eta', ['quand', 'imta', 'eta', 'arrive', 'arrivera', 'arrivée', 'delai', 'délai', 'baqi', 'temps', 'waqt', 'heure']),
               ('price', ['prix', 'montant', 'combien', 'ch7al', 'cod', 'payer', 'paiement', 'khls', 'flous', 'dariba']),
               ('address', ['adresse', 'changer', 'bdel', 'modifier']), ('driver', ['livreur', 'chauffeur', 'appeler', 'telephone', 'téléphone', 'contact', 'nmer']),
               ('where', ['ou', 'où', 'wen', 'fin', 'status', 'statut', 'position', 'situation', 'suivi', 'track', 'kayn', 'mazal', 'wsl']),
               ('greet', ['bonjour', 'bonsoir', 'salam', 'hello', 'salut', 'sbah', 'sba7', 'msa']),
               ('thanks', ['merci', 'chokran', 'thanks', 'thank']),
               ('help', ['aide', 'help', 'question', 'chwya'])]
    _ahits = {}
    app.o24_assistant_hits = _ahits

    @app.post('/api/public/assistant')
    def public_assistant():
        ip = request.remote_addr or '?'
        minute = int(time.time() // 60)
        rec = _ahits.get(ip)
        if not rec or rec[0] != minute: rec = _ahits[ip] = [minute, 0]
        rec[1] += 1
        if rec[1] > 20: raise Error('Trop de questions : réessayez dans une minute.', 429)
        d = request.get_json(silent=True) or {}
        q = norm(d.get('q'))[:200]; tracking = str(d.get('tracking') or '').strip()[:80]
        intent = 'fallback'
        for name, kws in INTENTS:
            if any(re.search(r'(?<![a-z])' + re.escape(k) + r'(?![a-z])', q) for k in kws):
                intent = name; break
        found = None
        if tracking:
            with conn() as c:
                p = c.execute('SELECT p.id,p.tracking,p.status,p.updated_at,ci.name city FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE lower(p.tracking)=lower(?)', (tracking,)).fetchone()
                if p: found = dict(p)
        reply = A_REPLY[intent]
        if found and intent in ('where', 'eta', 'greet'):
            if intent == 'eta':
                reply = 'Colis %s : %s — fenêtre d’arrivée affichée sur le suivi public.' % (found['tracking'], found['status'])
            else:
                reply = 'Colis %s : statut « %s » (%s), dernière étape le %s.' % (
                    found['tracking'], found['status'], found['city'] or 'ville non précisée', str(found['updated_at'])[:16].replace('T', ' '))
            intent = intent + '_found'
        return jsonify(intent=intent, reply=reply,
                       chips=['Où est mon colis ?', 'Quand l’arrivée ?', 'Code OTP ?', 'Livreur', 'Paiement COD ?'])
