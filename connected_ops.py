"""v1.12.0 « Exécution terrain & RFID » — dernières technologies d'article :

 1. RFID temps réel : tags EPC par colis, portail de lecture multiple (scan de masse),
    inventaire tournant par balayage (attendu vs lu, écarts).
 2. Picking guidé « pick-by-voice » : sessions multi-colis à chemin d'allées optimisé
    (séquence A-01-1…C-05-2), étapes confirmables, messages vocaux prêts (SpeechSynthesis UI).
 3. Captation dimensionnelle : longueur × largeur × hauteur → poids volumétrique (÷5000)
    et classe de volume (S/M/L/XL) — socle du plan de chargement.
 4. Plan de chargement véhicule : ordre de déchargement inverse de la tournée (LIFO),
    zones de soute, poids/volumes cumulés, alerte surcharge.
 5. (Interface vocale livreur : côté navigateur — Web Speech API — bouton 🎙️ dans la fiche,
    repli tactile si le navigateur ne reconnaît pas la voix.)

Tout est local : aucun middleware RFID payant, aucun fournisseur cloud, aucun service vocal."""
import secrets as _sec
from flask import request, jsonify

from tour_control import GEO, order_route, route_km

VOL_DIV = 5000.0          # convention aérienne : 6 000 cm³ ≈ 1 kg volumétrique (ici ÷5000 cm³/kg)
MAX_KG_VAN = 350.0
LOAD_ZONES = ('arrière droit', 'arrière gauche', 'centre droit', 'centre gauche', 'avant droit', 'avant gauche')


def vol_class(litres):
    if litres < 25: return 'S'
    if litres < 60: return 'M'
    if litres < 150: return 'L'
    return 'XL'


def dims_payload(row):
    l, w, h = row.get('dim_l') or 0, row.get('dim_w') or 0, row.get('dim_h') or 0
    litres = round(l * w * h / 1000.0, 2) if l and w and h else 0.0
    vol_kg = round(l * w * h / VOL_DIV, 2) if l and w and h else 0.0
    return {'dim_l': l, 'dim_w': w, 'dim_h': h, 'litres': litres, 'vol_kg': vol_kg,
            'vol_class': vol_class(litres) if litres else None}


def ensure_rfid(c, pid):
    row = c.execute('SELECT rfid_tag FROM parcels WHERE id=?', (pid,)).fetchone()
    if row and row['rfid_tag']:
        return row['rfid_tag']
    tag = 'EPC-' + _sec.token_hex(5).upper()
    c.execute('UPDATE parcels SET rfid_tag=? WHERE id=?', (tag, pid))
    return tag


def register_connected_ops(app, s):
    conn, auth, user, now, Error, event, parcel = (s['conn'], s['auth'], s['user'], s['now'], s['APIError'], s['event'], s['parcel'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS rfid_reads(id INTEGER PRIMARY KEY,tag TEXT NOT NULL,parcel_id INTEGER,portal TEXT DEFAULT '',batch TEXT DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pick_sessions(id INTEGER PRIMARY KEY,actor_id INTEGER,status TEXT NOT NULL DEFAULT 'en_cours',steps_done INTEGER DEFAULT 0,started_at TEXT NOT NULL,finished_at TEXT);
        CREATE TABLE IF NOT EXISTS pick_steps(id INTEGER PRIMARY KEY,session_id INTEGER NOT NULL REFERENCES pick_sessions(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),slot_label TEXT DEFAULT '',tracking TEXT DEFAULT '',seq INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'en_attente',confirmed_at TEXT);
        ''')
        pcols = {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
        for col, decl in (('rfid_tag', 'TEXT'), ('dim_l', 'REAL'), ('dim_w', 'REAL'), ('dim_h', 'REAL')):
            if col not in pcols:
                c.execute('ALTER TABLE parcels ADD COLUMN %s %s' % (col, decl))

    def _dims_row(c, pid):
        return c.execute('SELECT dim_l,dim_w,dim_h,weight_kg,rfid_tag FROM parcels WHERE id=?', (pid,)).fetchone()

    # ---------- API : captation dimensionnelle ----------
    @app.post('/api/parcels/<int:pid>/dimensions')
    @auth('admin', 'agent')
    def dimensions_set(pid):
        d = request.get_json(silent=True) or {}; u = user()
        wants_dims = any(k in d for k in ('dim_l', 'dim_w', 'dim_h'))
        vals = {}
        if wants_dims:
            for k in ('dim_l', 'dim_w', 'dim_h'):
                v = d.get(k)
                if v is None: raise Error('Dimensions L×l×h obligatoires (cm).')
                v = float(v)
                if not (1 <= v <= 200): raise Error('Dimension hors bornes (1–200 cm).')
                vals[k] = round(v, 1)
        with conn() as c:
            p = parcel(c, pid, u)
            if wants_dims:
                c.execute('UPDATE parcels SET dim_l=?,dim_w=?,dim_h=? WHERE id=?', (vals['dim_l'], vals['dim_w'], vals['dim_h'], pid))
            if 'rfid_tag' in d and str(d.get('rfid_tag') or '').strip():
                tag = str(d['rfid_tag']).strip().upper()[:32]
                c.execute('UPDATE parcels SET rfid_tag=? WHERE id=?', (tag, pid))
                event(c, pid, p['status'], 'Tag RFID %s attaché au colis' % tag, u)
            elif 'rfid_tag' in d:
                tag = ensure_rfid(c, pid)
                event(c, pid, p['status'], 'Tag RFID %s généré et attaché' % tag, u)
            if d.get('weight_kg') is not None:
                w = float(d['weight_kg'])
                if not (0 < w <= 30): raise Error('Poids invalide (0–30 kg).')
                c.execute('UPDATE parcels SET weight_kg=? WHERE id=?', (round(w, 2), pid))
            row = dict(_dims_row(c, pid))
            info = dims_payload(row)
            if wants_dims:
                event(c, pid, p['status'], 'Dimensions captées : %g×%g×%g cm — %s kg volumétriques (classe %s)'
                      % (vals['dim_l'], vals['dim_w'], vals['dim_h'], info['vol_kg'], info['vol_class']), u)
        out = dict(info); out['ok'] = True; out['rfid_tag'] = row.get('rfid_tag')
        return jsonify(**out)

    @app.get('/api/parcels/<int:pid>/dimensions')
    @auth('admin', 'agent', 'livreur')
    def dimensions_get(pid):
        u = user()
        with conn() as c:
            parcel(c, pid, u)
            row = dict(_dims_row(c, pid))
        return jsonify(**dims_payload(row))

    # ---------- API : RFID ----------
    @app.post('/api/rfid/scan')
    @auth('admin', 'agent')
    def rfid_scan():
        d = request.get_json(silent=True) or {}; u = user()
        portal = str(d.get('portal') or 'Portail principal')[:60]
        batch = _sec.token_hex(4).upper()
        tags = d.get('tags')
        with conn() as c:
            if not tags:
                n = min(20, max(1, int(d.get('count') or 5)))
                rows = c.execute('SELECT id,rfid_tag FROM parcels ORDER BY id DESC LIMIT 40').fetchall()
                picks = rows[:n] if rows else []
                tags = []
                for r in picks:
                    tags.append(ensure_rfid(c, r['id']))
            matched, unmatched = [], []
            for t in tags:
                t = str(t).strip().upper()
                row = c.execute('SELECT id,tracking,status,rfid_tag FROM parcels WHERE rfid_tag=?', (t,)).fetchone()
                if row:
                    c.execute('INSERT INTO rfid_reads(tag,parcel_id,portal,batch,created_at) VALUES(?,?,?,?,?)',
                              (t, row['id'], portal, batch, now()))
                    matched.append({'tag': t, 'parcel_id': row['id'], 'tracking': row['tracking'], 'status': row['status']})
                else:
                    c.execute('INSERT INTO rfid_reads(tag,parcel_id,portal,batch,created_at) VALUES(?,?,?,?,?)',
                              (t, None, portal, batch, now()))
                    unmatched.append(t)
            for m in matched:
                event(c, m['parcel_id'], 'RFID', 'Lecture RFID portail « %s »' % portal, u)
        return jsonify(ok=True, batch=batch, portal=portal, matched=matched, unmatched=unmatched)

    @app.get('/api/rfid/inventory')
    @auth('admin', 'agent')
    def rfid_inventory():
        with conn() as c:
            expected = [dict(r) for r in c.execute('SELECT id,tracking,status,rfid_tag FROM parcels WHERE rfid_tag IS NOT NULL ORDER BY id')]
            last_batch = c.execute('SELECT batch FROM rfid_reads ORDER BY id DESC LIMIT 1').fetchone()
            reads = []
            batch = last_batch['batch'] if last_batch else None
            if batch:
                reads = [dict(r) for r in c.execute('SELECT * FROM rfid_reads WHERE batch=? ORDER BY id', (batch,))]
            read_ids = {r['parcel_id'] for r in reads if r['parcel_id']}
        missing = [p for p in expected if p['id'] not in read_ids][-15:]
        return jsonify(expected=len(expected), read=sum(1 for r in reads if r['parcel_id']),
                       unknown=sum(1 for r in reads if not r['parcel_id']), batch=batch,
                       missing=missing, reads=reads[-30:])

    # ---------- API : picking guidé (pick-by-voice) ----------
    @app.post('/api/pick-sessions')
    @auth('admin', 'agent')
    def pick_session_create():
        d = request.get_json(silent=True) or {}; u = user()
        ids = d.get('parcel_ids') or []
        if not ids: raise Error('Liste de colis obligatoire (parcel_ids).')
        with conn() as c:
            steps = []
            for pid in ids:
                p = parcel(c, int(pid), u)
                st = c.execute('SELECT ps.status,ws.aisle,ws.pos,ws.level FROM parcel_storage ps LEFT JOIN warehouse_slots ws ON ws.id=ps.slot_id WHERE ps.parcel_id=?', (p['id'],)).fetchone()
                if not st or st['status'] != 'stock':
                    raise Error('Colis %s non en stock — picking impossible.' % p['tracking'])
                lbl = '%s-%02d-%d' % (st['aisle'], st['pos'], st['level'])
                steps.append({'pid': p['id'], 'tracking': p['tracking'], 'slot': lbl,
                              'ord': (st['aisle'], st['level'], st['pos'])})
            steps.sort(key=lambda x: x['ord'])   # chemin d'allées : A→B→C, niveau bas, positions croissantes
            sid = c.execute('INSERT INTO pick_sessions(actor_id,status,started_at) VALUES(?,?,?)',
                            (u['id'], 'en_cours', now())).lastrowid
            for i, st in enumerate(steps, 1):
                c.execute('INSERT INTO pick_steps(session_id,parcel_id,slot_label,tracking,seq,state) VALUES(?,?,?,?,?,?)',
                          (sid, st['pid'], st['slot'], st['tracking'], i, 'en_attente'))
            event(c, steps[0]['pid'], 'Picking', 'Session de picking guidée ouverte (%d colis)' % len(steps), u)
        return jsonify(ok=True, id=sid, steps=len(steps), order=[x['slot'] for x in steps])

    @app.get('/api/pick-sessions/<int:sid>')
    @auth('admin', 'agent')
    def pick_session_get(sid):
        with conn() as c:
            sess = c.execute('SELECT * FROM pick_sessions WHERE id=?', (sid,)).fetchone()
            if not sess: raise Error('Session introuvable.', 404)
            steps = [dict(r) for r in c.execute('SELECT * FROM pick_steps WHERE session_id=? ORDER BY seq', (sid,))]
        nxt = next((st for st in steps if st['state'] == 'en_attente'), None)
        for st in steps:
            st['voice'] = ('Emplacement %s, colis %s. Confirmez la prise.' % (st['slot_label'], st['tracking'])) if st['state'] == 'en_attente' else ('Colis %s confirmé.' % st['tracking'])
        return jsonify(id=sid, status=sess['status'], steps=steps,
                       done=sum(1 for st in steps if st['state'] == 'finie'),
                       next_step=nxt)

    @app.post('/api/pick-sessions/<int:sid>/steps/<int:step_id>/confirm')
    @auth('admin', 'agent')
    def pick_step_confirm(sid, step_id):
        u = user()
        with conn() as c:
            st = c.execute('SELECT * FROM pick_steps WHERE id=? AND session_id=?', (step_id, sid)).fetchone()
            if not st: raise Error('Étape introuvable.', 404)
            if st['state'] == 'finie': raise Error('Étape déjà confirmée.', 409)
            c.execute("UPDATE pick_steps SET state='finie',confirmed_at=? WHERE id=?", (now(), step_id))
            done = c.execute("SELECT COUNT(*) n FROM pick_steps WHERE session_id=? AND state='finie'", (sid,)).fetchone()['n']
            total = c.execute('SELECT COUNT(*) n FROM pick_steps WHERE session_id=?', (sid,)).fetchone()['n']
            if done >= total:
                c.execute("UPDATE pick_sessions SET status='finie',steps_done=?,finished_at=? WHERE id=?", (done, now(), sid))
            else:
                c.execute('UPDATE pick_sessions SET steps_done=? WHERE id=?', (done, sid))
            event(c, st['parcel_id'], 'Picking', 'Picking guidé : %s confirmé (étape %d)' % (st['slot_label'], st['seq']), u)
        return jsonify(ok=True, done=done, total=total)

    @app.get('/api/pick-sessions')
    @auth('admin', 'agent')
    def pick_sessions_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM pick_sessions ORDER BY id DESC LIMIT 15')]
        return jsonify(rows=rows)

    # ---------- API : plan de chargement ----------
    @app.get('/api/load-plan')
    @auth('admin', 'agent', 'livreur')
    def load_plan():
        u = user()
        did = request.args.get('driver_id', type=int) or (u['id'] if u['role'] == 'livreur' else None)
        if not did: raise Error('driver_id obligatoire.')
        with conn() as c:
            rows = [dict(r) for r in c.execute('''SELECT p.id,p.tracking,p.city_id,p.status,p.weight_kg,p.dim_l,p.dim_w,p.dim_h,ci.name city
                    FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id
                    WHERE p.driver_id=? AND p.status NOT IN ('Livré','Retourné','Annulé') ORDER BY p.id''', (did,))]
        if not rows: raise Error('Aucun colis ouvert pour ce livreur.')
        geos = [GEO.get(r['city'] or '') for r in rows]
        order = order_route(geos) if len(rows) > 1 else list(range(len(rows)))
        km = route_km([geos[i] for i in order]) if len(rows) > 1 else 0.0
        # ordre de déchargement = ordre de la route → chargement LIFO (le dernier livré monte en premier)
        plan = []
        total_kg = 0.0
        for unload_seq, idx in enumerate(order, 1):
            r = rows[idx]
            info = dims_payload(r)
            load_seq = len(order) - unload_seq + 1
            zone = LOAD_ZONES[(load_seq - 1) % len(LOAD_ZONES)]
            kg = r['weight_kg'] or 0.5
            total_kg += kg
            plan.append({'unload_seq': unload_seq, 'load_seq': load_seq, 'tracking': r['tracking'],
                         'city': r['city'] or '—', 'zone': zone, 'weight_kg': kg,
                         'vol_kg': info['vol_kg'], 'vol_class': info['vol_class'],
                         'dims': '%g×%g×%g' % (info['dim_l'], info['dim_w'], info['dim_h']) if info['dim_l'] else None})
        plan.sort(key=lambda x: x['load_seq'])
        return jsonify(driver_id=did, stops=len(order), km_est=round(km, 1),
                       total_kg=round(total_kg, 2), overload=total_kg > MAX_KG_VAN,
                       max_kg=MAX_KG_VAN,
                       plan=plan,
                       method='Ordre de route 2-opt inversé (LIFO) — le premier livré est au plus près de la porte.')

    # ---------- API : chantier vocal (commandes préparées) ----------
    @app.get('/api/voice-commands')
    @auth('admin', 'agent', 'livreur')
    def voice_commands():
        return jsonify(commands=[
            {'key': 'suivant', 'say': 'colis suivant', 'label': 'Colis suivant'},
            {'key': 'pris', 'say': 'colis pris', 'label': 'Colis ramassé'},
            {'key': 'livre', 'say': 'livré', 'label': 'Marquer livré'},
            {'key': 'appeler', 'say': 'appeler client', 'label': 'Appeler le client'},
            {'key': 'confirmer', 'say': 'confirmer', 'label': "Confirmer l'étape picking"},
        ], note='Reconnaissance vocale navigateur (Web Speech API) — liste blanche, repli tactile.')
