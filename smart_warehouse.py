"""v1.11.0 « Entrepôt intelligent & robotique » — complément des technologies d'article :

 1. WMS / entrepôt intelligent : entrepôts + emplacements (allée-position-niveau), mise en stock
    avec emplacement suggéré, picking tournée, sortie d'entrepôt, inventaire tournant, occupation.
 2. Robotique de tri (AGV / bras de picking) : robots avec batterie/état, missions de stockage et
    de picking auto-affectées au robot disponible le mieux chargé, file d'attente si flotte occupée.
 3. Livraison par drone (véhicule aérien) au niveau colis : mode « drone » avec contraintes de
    poids (≤ 2 kg) et de couverture (ville dotée d'un entrepôt), bascule standard/locker/drone.
 4. Contrôle qualité « vision » à la réception : état du colis (intact/abîmé/manquant) + note
    photo, score de conformité, alerte automatique si anomalie.
 5. Synchronisation cloud multi-agences : export/import de snapshot JSON signé SHA-256
    (fusion par tracking, dédoublonnage) — prêt pour un dépôt distant, sans fournisseur.

Tout est local : aucune API robot, aucun fournisseur cloud, aucun modèle de vision externe."""
import hashlib
import json
import random
import time
from flask import request, jsonify

AISLES = ('A', 'B', 'C')
SLOT_POS = 5
SLOT_LEVELS = 2
BOT_KINDS = ('tri', 'picking', 'AGV')
CONDITIONS = {'intact': 100, 'abime': 60, 'manquant': 20}
MODES = ('standard', 'drone', 'locker')
DRONE_MAX_KG = 2.0


def slot_label(aisle, pos, level):
    return '%s-%02d-%d' % (aisle, pos, level)


def sync_material(parcels, events):
    """Materiel canonique du snapshot — serialisation identique cote JS (miroir offline)."""
    rows = sorted('~'.join([str(p.get('tracking') or ''), str(p.get('status') or ''),
                            '%.2f' % (p.get('amount') or 0), '%.2f' % (p.get('weight_kg') or 0.5),
                            str(p.get('created_at') or '')]) for p in parcels)
    return ('|'.join(rows)) + '#ev' + str(len(events))


def sync_checksum(parcels, events):
    return hashlib.sha256(sync_material(parcels, events).encode()).hexdigest()


def register_smart_warehouse(app, s):
    conn, auth, user, now, Error, event, parcel = (s['conn'], s['auth'], s['user'], s['now'], s['APIError'], s['event'], s['parcel'])
    def _fill_slots(c, wid):
        for a in AISLES:
            for p in range(1, SLOT_POS + 1):
                for lv in range(1, SLOT_LEVELS + 1):
                    c.execute('INSERT INTO warehouse_slots(warehouse_id,aisle,pos,level,updated_at) VALUES(?,?,?,?,?)',
                              (wid, a, p, lv, now()))

    def _free_slot(c, wid):
        row = c.execute('''SELECT * FROM warehouse_slots WHERE warehouse_id=? AND busy_parcel_id IS NULL
                           ORDER BY (CASE aisle WHEN 'A' THEN 0 WHEN 'B' THEN 1 ELSE 2 END),level,pos LIMIT 1''', (wid,)).fetchone()
        return row

    def _idle_bot(c, wid):
        rows = [dict(r) for r in c.execute("SELECT * FROM warehouse_bots WHERE (warehouse_id=? OR warehouse_id IS NULL) AND state='idle' AND battery_pct>15 ORDER BY battery_pct DESC", (wid,))]
        return rows[0] if rows else None

    def _queue_mission(c, pid, kind, from_loc, to_loc, wid):
        bot = _idle_bot(c, wid)
        mid = c.execute('INSERT INTO bot_missions(bot_id,parcel_id,kind,from_loc,to_loc,state,created_at) VALUES(?,?,?,?,?,?,?)',
                        (bot['id'] if bot else None, pid, kind, from_loc, to_loc, 'en_cours' if bot else 'en_attente', now())).lastrowid
        if bot:
            c.execute("UPDATE warehouse_bots SET state='mission' WHERE id=?", (bot['id'],))
        return mid

    def _storage(c, pid):
        return c.execute('SELECT ps.*,ws.aisle,ws.pos,ws.level FROM parcel_storage ps LEFT JOIN warehouse_slots ws ON ws.id=ps.slot_id WHERE ps.parcel_id=?', (pid,)).fetchone()

    def _warehouse_for_city(c, city_id):
        return c.execute('SELECT * FROM warehouses WHERE active=1 AND (city_id=? OR city_id IS NULL) ORDER BY city_id IS NULL,id LIMIT 1', (city_id,)).fetchone()

    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER REFERENCES cities(id),active INTEGER DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS warehouse_slots(id INTEGER PRIMARY KEY,warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),aisle TEXT NOT NULL,pos INTEGER NOT NULL,level INTEGER NOT NULL,busy_parcel_id INTEGER,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS parcel_storage(id INTEGER PRIMARY KEY,parcel_id INTEGER UNIQUE NOT NULL REFERENCES parcels(id),warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),slot_id INTEGER REFERENCES warehouse_slots(id),status TEXT NOT NULL DEFAULT 'stock',stored_at TEXT,picked_at TEXT,out_at TEXT,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS warehouse_bots(id INTEGER PRIMARY KEY,warehouse_id INTEGER REFERENCES warehouses(id),name TEXT NOT NULL,kind TEXT NOT NULL DEFAULT 'tri',battery_pct REAL DEFAULT 100,state TEXT NOT NULL DEFAULT 'idle',missions_done INTEGER DEFAULT 0,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bot_missions(id INTEGER PRIMARY KEY,bot_id INTEGER REFERENCES warehouse_bots(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),kind TEXT NOT NULL,from_loc TEXT DEFAULT '',to_loc TEXT DEFAULT '',state TEXT NOT NULL DEFAULT 'en_attente',created_at TEXT NOT NULL,finished_at TEXT);
        CREATE TABLE IF NOT EXISTS reception_checks(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),actor_id INTEGER,condition TEXT NOT NULL,score INTEGER NOT NULL,note TEXT DEFAULT '',photo_ref TEXT DEFAULT '',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sync_snapshots(id INTEGER PRIMARY KEY,direction TEXT NOT NULL,checksum TEXT NOT NULL,items INTEGER DEFAULT 0,merged INTEGER DEFAULT 0,created_at TEXT NOT NULL);
        ''')
        pcols = {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
        if 'delivery_mode' not in pcols:
            c.execute("ALTER TABLE parcels ADD COLUMN delivery_mode TEXT NOT NULL DEFAULT 'standard'")
        if 'weight_kg' not in pcols:
            c.execute('ALTER TABLE parcels ADD COLUMN weight_kg REAL DEFAULT 0.5')
        if not c.execute('SELECT 1 FROM warehouses LIMIT 1').fetchone():
            row = c.execute("SELECT id FROM cities WHERE name='Oujda'").fetchone()
            wid = c.execute('INSERT INTO warehouses(name,city_id,active,created_at) VALUES(?,?,1,?)',
                            ('Entrepôt Oriental24 — Oujda', row['id'] if row else None, now())).lastrowid
            _fill_slots(c, wid)

    # ---------- API : entrepôts & emplacements ----------
    @app.get('/api/warehouses')
    @auth('admin', 'agent')
    def warehouses_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT w.*,ci.name city FROM warehouses w LEFT JOIN cities ci ON ci.id=w.city_id ORDER BY w.id')]
            for r in rows:
                tot = c.execute('SELECT COUNT(*) n FROM warehouse_slots WHERE warehouse_id=?', (r['id'],)).fetchone()['n']
                busy = c.execute('SELECT COUNT(*) n FROM warehouse_slots WHERE warehouse_id=? AND busy_parcel_id IS NOT NULL', (r['id'],)).fetchone()['n']
                r['slots_total'], r['slots_busy'] = tot, busy
        return jsonify(rows=rows)

    @app.post('/api/warehouses')
    @auth('admin')
    def warehouses_add():
        d = request.get_json(silent=True) or {}
        name = str(d.get('name') or '').strip()[:80]
        if not name: raise Error('Nom d’entrepôt obligatoire.')
        with conn() as c:
            if c.execute('SELECT 1 FROM warehouses WHERE name=?', (name,)).fetchone():
                raise Error('Ce nom d’entrepôt existe déjà.')
            cid = d.get('city_id')
            if not cid and d.get('city'):
                row = c.execute('SELECT id FROM cities WHERE name=?', (str(d['city']).strip(),)).fetchone()
                cid = row['id'] if row else None
            wid = c.execute('INSERT INTO warehouses(name,city_id,active,created_at) VALUES(?,?,1,?)', (name, cid, now())).lastrowid
            _fill_slots(c, wid)
        return jsonify(ok=True, id=wid)

    @app.get('/api/warehouses/<int:wid>/slots')
    @auth('admin', 'agent')
    def slots_list(wid):
        with conn() as c:
            rows = [dict(r) for r in c.execute('''SELECT ws.*,p.tracking busy_tracking FROM warehouse_slots ws
                    LEFT JOIN parcels p ON p.id=ws.busy_parcel_id WHERE ws.warehouse_id=? ORDER BY ws.aisle,ws.pos,ws.level''', (wid,))]
        for r in rows:
            r['label'] = slot_label(r['aisle'], r['pos'], r['level'])
        return jsonify(rows=rows)

    # ---------- API : stockage / picking / sortie ----------
    @app.post('/api/parcels/<int:pid>/store')
    @auth('admin', 'agent')
    def parcel_store(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            if _storage(c, pid):
                raise Error('Colis déjà mis en stock.', 409)
            wh = _warehouse_for_city(c, p['city_id']) or None
            if not wh: raise Error('Aucun entrepôt actif pour cette ville.')
            slot = _free_slot(c, wh['id'])
            if not slot: raise Error('Entrepôt complet : aucun emplacement libre.')
            stored = now()
            c.execute('INSERT INTO parcel_storage(parcel_id,warehouse_id,slot_id,status,stored_at,created_at) VALUES(?,?,?,?,?,?)',
                      (pid, wh['id'], slot['id'], 'stock', stored, stored))
            c.execute('UPDATE warehouse_slots SET busy_parcel_id=?,updated_at=? WHERE id=?', (pid, now(), slot['id']))
            lbl = slot_label(slot['aisle'], slot['pos'], slot['level'])
            _queue_mission(c, pid, 'stockage', 'réception', lbl, wh['id'])
            event(c, pid, p['status'], 'Mis en stock — entrepôt « %s », emplacement %s' % (wh['name'], lbl), u)
        return jsonify(ok=True, slot=lbl, warehouse=wh['name'])

    @app.post('/api/parcels/<int:pid>/pick')
    @auth('admin', 'agent')
    def parcel_pick(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            st = _storage(c, pid)
            if not st: raise Error('Colis non stocké — mise en stock d’abord.', 400)
            if st['status'] != 'stock': raise Error('Colis déjà préparé (statut %s).' % st['status'], 409)
            c.execute("UPDATE parcel_storage SET status='pret',picked_at=? WHERE parcel_id=?", (now(), pid))
            lbl = slot_label(st['aisle'], st['pos'], st['level']) if st['aisle'] else '?'
            _queue_mission(c, pid, 'picking', lbl, 'départ', st['warehouse_id'])
            event(c, pid, p['status'], 'Préparé pour la tournée (picking depuis %s)' % lbl, u)
        return jsonify(ok=True)

    @app.post('/api/parcels/<int:pid>/ship-out')
    @auth('admin', 'agent')
    def parcel_ship_out(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            st = _storage(c, pid)
            if not st: raise Error('Colis non stocké.', 400)
            if st['status'] == 'sorti': raise Error('Colis déjà sorti de l’entrepôt.', 409)
            c.execute("UPDATE parcel_storage SET status='sorti',out_at=? WHERE parcel_id=?", (now(), pid))
            if st['slot_id']:
                c.execute('UPDATE warehouse_slots SET busy_parcel_id=NULL,updated_at=? WHERE id=?', (now(), st['slot_id']))
            event(c, pid, p['status'], 'Sortie d’entrepôt — chargé pour la tournée', u)
        return jsonify(ok=True)

    @app.get('/api/parcels/<int:pid>/storage')
    @auth('admin', 'agent', 'livreur')
    def parcel_storage_get(pid):
        u = user()
        with conn() as c:
            p = dict(parcel(c, pid, u))
            st = _storage(c, pid)
            rc = [dict(r) for r in c.execute('SELECT * FROM reception_checks WHERE parcel_id=? ORDER BY id DESC LIMIT 5', (pid,))]
        if not st:
            return jsonify(stored=False, checks=rc, mode=p.get('delivery_mode', 'standard'), weight_kg=p.get('weight_kg'))
        st = dict(st)
        st['label'] = slot_label(st['aisle'], st['pos'], st['level']) if st['aisle'] else None
        st['stored'] = True
        st['checks'] = rc
        st['mode'] = p.get('delivery_mode', 'standard')
        st['weight_kg'] = p.get('weight_kg')
        return jsonify(**st)

    # ---------- API : robots de tri ----------
    @app.get('/api/bots')
    @auth('admin', 'agent')
    def bots_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM warehouse_bots ORDER BY id')]
            missions = [dict(r) for r in c.execute('''SELECT bm.*,p.tracking FROM bot_missions bm JOIN parcels p ON p.id=bm.parcel_id
                        ORDER BY bm.id DESC LIMIT 20''')]
        return jsonify(rows=rows, missions=missions)

    @app.post('/api/bots')
    @auth('admin')
    def bots_add():
        d = request.get_json(silent=True) or {}
        kind = str(d.get('kind') or 'tri')
        if kind not in BOT_KINDS: raise Error('Type de robot inconnu (tri/picking/AGV).')
        name = str(d.get('name') or '').strip()[:60]
        if not name: raise Error('Nom du robot obligatoire.')
        wid = d.get('warehouse_id')
        with conn() as c:
            bid = c.execute('INSERT INTO warehouse_bots(warehouse_id,name,kind,state,created_at) VALUES(?,?,?,?,?)',
                            (wid, name, kind, 'idle', now())).lastrowid
        return jsonify(ok=True, id=bid)

    @app.patch('/api/bots/<int:bid>')
    @auth('admin')
    def bots_patch(bid):
        d = request.get_json(silent=True) or {}
        st = d.get('state')
        with conn() as c:
            b = c.execute('SELECT * FROM warehouse_bots WHERE id=?', (bid,)).fetchone()
            if not b: raise Error('Robot introuvable.', 404)
            if st:
                if st not in ('idle', 'mission', 'charge', 'panne'): raise Error('État inconnu (idle/mission/charge/panne).')
                c.execute('UPDATE warehouse_bots SET state=? WHERE id=?', (st, bid))
        return jsonify(ok=True)

    @app.post('/api/bots/<int:bid>/charge')
    @auth('admin', 'agent')
    def bots_charge(bid):
        with conn() as c:
            b = c.execute('SELECT * FROM warehouse_bots WHERE id=?', (bid,)).fetchone()
            if not b: raise Error('Robot introuvable.', 404)
            c.execute("UPDATE warehouse_bots SET battery_pct=100,state='idle' WHERE id=?", (bid,))
        return jsonify(ok=True)

    @app.post('/api/warehouse/missions/<int:mid>/finish')
    @auth('admin', 'agent')
    def mission_finish(mid):
        with conn() as c:
            m = c.execute('SELECT * FROM bot_missions WHERE id=?', (mid,)).fetchone()
            if not m: raise Error('Mission introuvable.', 404)
            if m['state'] == 'finie': raise Error('Mission déjà terminée.', 409)
            c.execute("UPDATE bot_missions SET state='finie',finished_at=? WHERE id=?", (now(), mid))
            if m['bot_id']:
                drop = random.uniform(3.0, 9.0)
                c.execute('UPDATE warehouse_bots SET missions_done=missions_done+1, battery_pct=MAX(0,battery_pct-?), state=? WHERE id=?',
                          (round(drop, 1), 'idle', m['bot_id']))
                nxt = c.execute("SELECT * FROM bot_missions WHERE state='en_attente' AND bot_id IS NULL ORDER BY id LIMIT 1").fetchone()
                if nxt:
                    c.execute("UPDATE bot_missions SET bot_id=?,state='en_cours' WHERE id=?", (m['bot_id'], nxt['id']))
                    c.execute("UPDATE warehouse_bots SET state='mission' WHERE id=?", (m['bot_id'],))
        return jsonify(ok=True)

    # ---------- API : contrôle qualité réception (« vision ») ----------
    @app.post('/api/parcels/<int:pid>/reception-check')
    @auth('admin', 'agent')
    def reception_check(pid):
        d = request.get_json(silent=True) or {}; u = user()
        cond = str(d.get('condition') or '')
        if cond not in CONDITIONS: raise Error('État inconnu (intact/abime/manquant).')
        note = str(d.get('note') or '')[:200]
        photo = str(d.get('photo_ref') or '')[:120]
        score = CONDITIONS[cond]
        with conn() as c:
            p = parcel(c, pid, u)
            rid = c.execute('INSERT INTO reception_checks(parcel_id,actor_id,condition,score,note,photo_ref,created_at) VALUES(?,?,?,?,?,?,?)',
                            (pid, u['id'], cond, score, note, photo, now())).lastrowid
            txt = 'Contrôle réception : %s (score %d/100)' % (cond, score)
            if note: txt += ' — ' + note
            event(c, pid, p['status'], txt, u)
            if cond != 'intact':
                event(c, pid, p['status'], '⚠️ ALERTE réception — colis %s' % cond, u)
        return jsonify(ok=True, id=rid, score=score)

    @app.get('/api/warehouse/receptions')
    @auth('admin', 'agent')
    def receptions_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('''SELECT rc.*,p.tracking,u.name actor FROM reception_checks rc
                    JOIN parcels p ON p.id=rc.parcel_id LEFT JOIN users u ON u.id=rc.actor_id ORDER BY rc.id DESC LIMIT 30''')]
        return jsonify(rows=rows)

    # ---------- API : livraison par drone ----------
    @app.post('/api/parcels/<int:pid>/delivery-mode')
    @auth('admin')
    def delivery_mode(pid):
        d = request.get_json(silent=True) or {}; u = user()
        mode = str(d.get('mode') or '')
        if mode not in MODES: raise Error('Mode inconnu (standard/drone/locker).')
        with conn() as c:
            p = dict(parcel(c, pid, u))
            if d.get('weight_kg') is not None:
                w = float(d['weight_kg'])
                if not (0 < w <= 30): raise Error('Poids invalide (0–30 kg).')
                c.execute('UPDATE parcels SET weight_kg=? WHERE id=?', (round(w, 2), pid))
                p['weight_kg'] = round(w, 2)
            w = p.get('weight_kg') or 0.5
            if mode == 'drone':
                if w > DRONE_MAX_KG:
                    raise Error('Livraison par drone impossible : %.2f kg > %s kg (limite aérienne).' % (w, DRONE_MAX_KG))
                wh = _warehouse_for_city(c, p['city_id'])
                if not wh: raise Error('Livraison par drone impossible : aucun hub aérien (entrepôt) pour cette ville.')
                drone = c.execute("SELECT 1 FROM vehicles WHERE type='drone' AND active=1").fetchone()
                if not drone: raise Error('Livraison par drone impossible : aucun drone actif dans la flotte.')
            c.execute('UPDATE parcels SET delivery_mode=? WHERE id=?', (mode, pid))
            event(c, pid, p['status'], 'Mode de livraison : %s' % mode, u)
        return jsonify(ok=True, mode=mode)

    # ---------- API : KPI entrepôt ----------
    @app.get('/api/warehouse/kpis')
    @auth('admin', 'agent')
    def warehouse_kpis():
        with conn() as c:
            tot = c.execute('SELECT COUNT(*) n FROM warehouse_slots').fetchone()['n']
            busy = c.execute('SELECT COUNT(*) n FROM warehouse_slots WHERE busy_parcel_id IS NOT NULL').fetchone()['n']
            stored = c.execute("SELECT COUNT(*) n FROM parcel_storage WHERE status='stock'").fetchone()['n']
            ready = c.execute("SELECT COUNT(*) n FROM parcel_storage WHERE status='pret'").fetchone()['n']
            outn = c.execute("SELECT COUNT(*) n FROM parcel_storage WHERE status='sorti'").fetchone()['n']
            bots = [dict(r) for r in c.execute('SELECT * FROM warehouse_bots')]
            done = c.execute("SELECT COUNT(*) n FROM bot_missions WHERE state='finie'").fetchone()['n']
            queue = c.execute("SELECT COUNT(*) n FROM bot_missions WHERE state='en_attente'").fetchone()['n']
            hour_ago = time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(time.time() - 3600))
            last_h = c.execute('SELECT COUNT(*) n FROM bot_missions WHERE finished_at>=?', (hour_ago,)).fetchone()['n']
            checks = c.execute('SELECT COUNT(*) n FROM reception_checks').fetchone()['n']
            alerts = c.execute("SELECT COUNT(*) n FROM reception_checks WHERE condition<>'intact'").fetchone()['n']
        auto = 0
        if done: auto = round(100 * done / max(1, done + queue))
        return jsonify(slots_total=tot, slots_busy=busy, stored=stored, ready=ready, out=outn,
                       bots_total=len(bots), bots_idle=sum(1 for b in bots if b['state'] == 'idle'),
                       missions_done=done, missions_queue=queue, missions_last_hour=last_h,
                       automation_rate=auto, checks=checks, check_alerts=alerts,
                       occupation_pct=round(100 * busy / tot) if tot else 0)

    # ---------- API : synchronisation multi-agences (cloud-ready) ----------
    @app.get('/api/sync/export')
    @auth('admin')
    def sync_export():
        with conn() as c:
            parcels = [dict(r) for r in c.execute('SELECT id,tracking,recipient,phone,address,city_id,status,amount,delivery_mode,weight_kg,created_at FROM parcels ORDER BY id')]
            events = [dict(r) for r in c.execute('SELECT id,parcel_id,status,note,created_at FROM events ORDER BY id')]
        payload = {'format': 'oriental24-sync-1', 'version': '1.11.0', 'generated_at': now(),
                   'counts': {'parcels': len(parcels), 'events': len(events)},
                   'parcels': parcels, 'events': events}
        checksum = sync_checksum(parcels, events)
        with conn() as c:
            c.execute('INSERT INTO sync_snapshots(direction,checksum,items,merged,created_at) VALUES(?,?,?,?,?)',
                      ('export', checksum, len(parcels) + len(events), 0, now()))
        payload['checksum'] = checksum
        return jsonify(**payload)

    @app.post('/api/sync/import')
    @auth('admin')
    def sync_import():
        d = request.get_json(silent=True) or {}
        if d.get('format') != 'oriental24-sync-1': raise Error('Format de snapshot inconnu.')
        checksum = sync_checksum(d.get('parcels') or [], d.get('events') or [])
        if d.get('checksum') != checksum: raise Error('Snapshot falsifié : empreinte SHA-256 invalide.', 400)
        merged = 0
        with conn() as c:
            for p in d.get('parcels') or []:
                if c.execute('SELECT 1 FROM parcels WHERE tracking=?', (p.get('tracking'),)).fetchone(): continue
                c.execute('INSERT INTO parcels(tracking,recipient,phone,address,city_id,status,amount,delivery_mode,weight_kg,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                          (p.get('tracking'), p.get('recipient'), p.get('phone'), p.get('address'), p.get('city_id'),
                           p.get('status') or 'Créé', p.get('amount') or 0, p.get('delivery_mode') or 'standard', p.get('weight_kg') or 0.5,
                           p.get('created_at') or now()))
                merged += 1
            c.execute('INSERT INTO sync_snapshots(direction,checksum,items,merged,created_at) VALUES(?,?,?,?,?)',
                      ('import', checksum, len(d.get('parcels') or []) + len(d.get('events') or []), merged, now()))
        return jsonify(ok=True, merged=merged)

    @app.get('/api/sync/log')
    @auth('admin')
    def sync_log():
        with conn() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM sync_snapshots ORDER BY id DESC LIMIT 20')]
        return jsonify(rows=rows)
