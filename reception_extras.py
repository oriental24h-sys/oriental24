"""Incidents de réception, rôle Agent de réception et alertes de retard.
Aucun colis, montant ou historique n'est supprimé : un écart déclaré reste visible.
"""
import base64, binascii, hashlib, io, json, re, warnings
from PIL import Image, UnidentifiedImageError
from flask import request, jsonify, send_file
from werkzeug.utils import secure_filename

KIND = 'partner_palette'
INCIDENTS = ('missing', 'extra', 'damaged')
PHOTO_LIMIT = 1024 * 1024
ALERT_DEFAULTS = {'alert_transit_hours': 48, 'alert_partial_hours': 24, 'alert_unassigned_hours': 24}


def register_reception_extras(app, s):
    conn, auth, user, now, Error = (s[k] for k in ['conn', 'auth', 'user', 'now', 'APIError'])
    with conn() as c:
        if 'agent_hub_id' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
            c.execute('ALTER TABLE users ADD COLUMN agent_hub_id INTEGER REFERENCES ops_hubs(id)')
        if 'missing_at' not in {r[1] for r in c.execute('PRAGMA table_info(ops_document_lines)')}:
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_at TEXT')
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_by INTEGER REFERENCES users(id)')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS pp_incidents(
            id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL REFERENCES ops_documents(id),
            line_id INTEGER REFERENCES ops_document_lines(id),
            parcel_id INTEGER REFERENCES parcels(id),
            company_id INTEGER NOT NULL REFERENCES users(id),
            hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),
            kind TEXT NOT NULL CHECK(kind IN ('missing','extra','damaged')),
            tracking TEXT NOT NULL,
            note TEXT NOT NULL,
            photo_name TEXT, photo_mime TEXT, photo BLOB, photo_sha256 TEXT, photo_size INTEGER,
            status TEXT NOT NULL DEFAULT 'Ouvert',
            company_response TEXT NOT NULL DEFAULT '',
            responded_by INTEGER REFERENCES users(id), responded_at TEXT,
            resolution TEXT NOT NULL DEFAULT '', resolution_note TEXT NOT NULL DEFAULT '',
            resolved_by INTEGER REFERENCES users(id), resolved_at TEXT,
            created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS pp_incidents_doc ON pp_incidents(document_id, id);
        CREATE INDEX IF NOT EXISTS pp_incidents_parcel ON pp_incidents(parcel_id, kind, resolution);
        ''')
        for k, v in ALERT_DEFAULTS.items():
            c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, str(v)))

    def damage_hold_open(c, pid):
        return bool(c.execute("SELECT 1 FROM pp_incidents WHERE parcel_id=? AND kind='damaged' AND resolution<>'release'", (pid,)).fetchone())

    s['damage_hold_open'] = damage_hold_open

    def body():
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            raise Error('Objet JSON requis.')
        return d

    def text(d, k, limit, required=False):
        v = d.get(k, '')
        if not isinstance(v, str) or len(v.strip()) > limit or (required and not v.strip()):
            raise Error('Champ invalide : ' + k)
        return v.strip()

    def photo(d, required):
        f = d.get('photo')
        if f in (None, ''):
            if required:
                raise Error('Photo obligatoire pour un colis endommagé.')
            return None
        if not isinstance(f, dict) or set(f) != {'name', 'content'} or not isinstance(f['name'], str) or not isinstance(f['content'], str) or len(f['content']) > 1400000:
            raise Error('Photo invalide.')
        try:
            raw = base64.b64decode(f['content'], validate=True)
            if not raw or len(raw) > PHOTO_LIMIT:
                raise ValueError()
        except (ValueError, binascii.Error):
            raise Error('Photo invalide ou supérieure à 1 Mo.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in ['PNG', 'JPEG'] or im.width * im.height > 8000000:
                        raise ValueError()
                    im.load()
                    buf = io.BytesIO()
                    im.convert('RGB').save(buf, format='JPEG', quality=88)
                    raw = buf.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise Error('Photo acceptée : JPG ou PNG, 8 mégapixels maximum.')
        if len(raw) > PHOTO_LIMIT:
            raise Error('Photo supérieure à 1 Mo après traitement.')
        name = secure_filename(f['name'] or 'photo.jpg') or 'photo.jpg'
        return dict(name=name.rsplit('.', 1)[0] + '.jpg', mime='image/jpeg', raw=raw,
                    sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))

    def users_and_doc(c, did, u):
        r = c.execute('SELECT d.*,m.partner_reference FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id WHERE d.id=? AND d.kind=?', (did, KIND)).fetchone()
        if not r:
            raise Error('Palette introuvable.', 404)
        d = dict(r)
        if u['role'] == 'client' and d['client_id'] != u['id']:
            raise Error('Palette introuvable.', 404)
        if u['role'] == 'agent' and d['destination_hub_id'] != u['agent_hub_id']:
            raise Error('Palette introuvable.', 404)
        return d

    def receiver(u):
        if u['role'] not in ('admin', 'agent'):
            raise Error('Réception physique réservée à Admin ou à un agent de réception.', 403)

    def audit(c, did, u, action, details):
        c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)', (did, u['id'], action, json.dumps(details, ensure_ascii=False), now()))

    def notify(c, uid, title, msg, pid=None):
        c.execute('INSERT INTO ops_notifications(user_id,parcel_id,title,body,created_at) VALUES(?,?,?,?,?)', (uid, pid, title, msg, now()))

    def notify_admins(c, title, msg):
        for a in c.execute("SELECT id FROM users WHERE role='admin' AND active=1"):
            notify(c, a['id'], title, msg)

    def replay(c, u, d, did, action):
        key = d.get('request_key')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', key):
            raise Error('Clé de confirmation invalide.')
        fp = hashlib.sha256(json.dumps([did, action, d], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        r = c.execute('SELECT fingerprint,result FROM partner_palette_keys WHERE actor_id=? AND request_key=?', (u['id'], key)).fetchone()
        if r:
            if r['fingerprint'] != fp:
                raise Error('Clé déjà utilisée pour une autre saisie.', 409)
            return fp, json.loads(r['result'])
        return fp, None

    def store(c, u, d, fp, did, action, **result):
        c.execute('INSERT INTO partner_palette_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)', (u['id'], d['request_key'], fp, json.dumps(result)))
        return jsonify(result)

    def pending_of(c, did):
        return [dict(r) for r in c.execute('SELECT l.*,p.status current_status FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id WHERE l.document_id=? AND l.received_at IS NULL AND l.missing_at IS NULL', (did,))]

    def recompute(c, d, at):
        counts = c.execute('SELECT count(*) total,sum(received_at IS NOT NULL) received,sum(missing_at IS NOT NULL) missing FROM ops_document_lines WHERE document_id=?', (d['id'],)).fetchone()
        total, received, missing = counts['total'], counts['received'] or 0, counts['missing'] or 0
        if received + missing < total:
            status = 'Partiellement reçu' if received else d['status']
            c.execute('UPDATE ops_documents SET status=?,revision=revision+1 WHERE id=?', (status, d['id']))
            return status, total - received - missing
        status = 'Reçu' if not missing else 'Clôturé (écarts)'
        c.execute('UPDATE ops_documents SET status=?,completed_at=COALESCE(completed_at,?),revision=revision+1 WHERE id=?', (status, at, d['id']))
        return status, 0

    def incident_json(r, with_company=True):
        out = {k: r[k] for k in ['id', 'document_id', 'line_id', 'parcel_id', 'kind', 'tracking', 'note', 'status', 'company_response', 'responded_at', 'resolution', 'resolution_note', 'resolved_at', 'created_at']}
        out['has_photo'] = r['photo_sha256'] is not None
        out['creator'] = r['creator']
        return out

    SELECT_INC = '''SELECT i.*,u.name creator FROM pp_incidents i JOIN users u ON u.id=i.created_by'''

    @app.get('/api/partner-palettes/<int:did>/incidents')
    @auth('admin', 'client', 'agent')
    def incident_list(did):
        u = user()
        if u['role'] not in ('admin', 'agent') and not (u['role'] == 'client' and u['client_type'] == 'societe_livraison'):
            raise Error('Accès non autorisé.', 403)
        with conn() as c:
            c.execute('BEGIN')
            users_and_doc(c, did, u)
            rows = [incident_json(r) for r in c.execute(SELECT_INC + ' WHERE i.document_id=? ORDER BY i.id DESC', (did,))]
            open_damaged = c.execute("SELECT parcel_id FROM pp_incidents WHERE document_id=? AND kind='damaged' AND resolution<>'release'", (did,)).fetchall()
            return jsonify(rows=rows, damaged_holds=[r['parcel_id'] for r in open_damaged])

    @app.get('/api/partner-palette-incidents/<int:iid>/photo')
    @auth('admin', 'client', 'agent')
    def incident_photo(iid):
        u = user()
        with conn() as c:
            r = c.execute(SELECT_INC + ' WHERE i.id=?', (iid,)).fetchone()
            if not r or r['photo'] is None:
                raise Error('Photo introuvable.', 404)
            users_and_doc(c, r['document_id'], u)
            resp = send_file(io.BytesIO(r['photo']), mimetype=r['photo_mime'], as_attachment=True, download_name=r['photo_name'] or 'photo.jpg', max_age=0)
            resp.headers['Cache-Control'] = 'private, no-store'
            resp.headers['X-Content-Type-Options'] = 'nosniff'
            resp.headers['Content-Security-Policy'] = "sandbox; default-src 'none'"
            return resp

    @app.post('/api/partner-palettes/<int:did>/incidents')
    @auth('admin', 'agent')
    def incident_create(did):
        u = user()
        receiver(u)
        d = body()
        kind = d.get('kind')
        if kind not in INCIDENTS:
            raise Error('Type d’écart invalide.')
        if d.get('confirmed') is not True:
            raise Error('Confirmez explicitement cette déclaration.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc = users_and_doc(c, did, u)
            if not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1', (doc['destination_hub_id'],)).fetchone():
                raise Error('Hub de réception inactif. Réactivez-le avant de continuer.', 409)
            fp, prior = replay(c, u, d, did, 'incident')
            if prior:
                prior['replayed'] = True
                return jsonify(prior)
            if doc['status'] not in ('En transit', 'Partiellement reçu'):
                raise Error('Les écarts se déclarent sur une palette envoyée, avant sa clôture.', 409)
            note = text(d, 'note', 600, True)
            at = now()
            line = parcel_id = None
            tracking = text(d, 'tracking', 80, kind != 'missing')
            if kind in ('missing', 'damaged'):
                lid = d.get('line_id')
                pending = pending_of(c, did)
                if kind == 'missing':
                    line = next((l for l in pending if l['id'] == lid), None)
                    if not line:
                        raise Error('Colis attendu introuvable : il est peut-être déjà reçu ou déclaré. Actualisez.', 404)
                    tracking = line['tracking']
                else:
                    line = next((l for l in pending if l['tracking'].casefold() == tracking.casefold()), None)
                    if not line:
                        raise Error('Ce tracking n’est plus à recevoir dans cette palette. Actualisez.', 404)
                parcel_id = line['parcel_id']
            pic = photo(d, kind == 'damaged')
            iid = c.execute('INSERT INTO pp_incidents(document_id,line_id,parcel_id,company_id,hub_id,kind,tracking,note,photo_name,photo_mime,photo,photo_sha256,photo_size,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (did, line['id'] if line else None, parcel_id, doc['client_id'], doc['destination_hub_id'], kind, tracking, note,
                             pic['name'] if pic else None, pic['mime'] if pic else None, pic['raw'] if pic else None,
                             pic['sha256'] if pic else None, pic['size'] if pic else None, u['id'], at)).lastrowid
            status, remaining = doc['status'], None
            if kind == 'missing':
                c.execute('UPDATE ops_document_lines SET active=0,missing_at=?,missing_by=? WHERE id=?', (at, u['id'], line['id']))
                status, remaining = recompute(c, doc, at)
                audit(c, did, u, 'Colis déclaré manquant', {'tracking': tracking, 'incident_id': iid, 'note': note})
            elif kind == 'damaged':
                c.execute('UPDATE ops_document_lines SET received_at=?,received_by=?,active=0 WHERE id=?', (at, u['id'], line['id']))
                c.execute("UPDATE parcels SET status='Réceptionné',current_hub_id=?,reason_code=NULL,next_attempt_at=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?", (doc['destination_hub_id'], at, parcel_id))
                s['event'](c, parcel_id, 'Réceptionné', doc['reference'] + ' · réceptionné ENDOMMAGÉ à ' + doc['destination_name'] + ' — incident #' + str(iid) + ', affectation suspendue', u)
                status, remaining = recompute(c, doc, at)
                audit(c, did, u, 'Colis reçu endommagé', {'tracking': tracking, 'incident_id': iid, 'note': note})
            else:
                match = c.execute('SELECT id FROM parcels WHERE tracking=? COLLATE NOCASE AND client_id=?', (tracking, doc['client_id'])).fetchone()
                if match:
                    c.execute('UPDATE pp_incidents SET parcel_id=? WHERE id=?', (match['id'], iid))
                audit(c, did, u, 'Colis imprévu constaté', {'tracking': tracking, 'incident_id': iid, 'note': note})
            label = {'missing': 'un colis manquant', 'extra': 'un colis imprévu', 'damaged': 'un colis endommagé'}[kind]
            notify(c, doc['client_id'], 'Incident déclaré sur ' + doc['reference'], 'ORIENTAL24 a déclaré ' + label + ' (' + tracking + '). Ouvrez la palette pour répondre.', parcel_id)
            return store(c, u, d, fp, did, 'incident', ok=True, incident_id=iid, status=status, remaining=remaining)

    @app.post('/api/partner-palettes/<int:did>/close-gaps')
    @auth('admin', 'agent')
    def close_gaps(did):
        u = user()
        receiver(u)
        d = body()
        reason = text(d, 'reason', 600, True)
        if d.get('confirmed') is not True:
            raise Error('Confirmez explicitement la clôture avec écarts.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc = users_and_doc(c, did, u)
            fp, prior = replay(c, u, d, did, 'close-gaps')
            if prior:
                prior['replayed'] = True
                return jsonify(prior)
            if doc['status'] not in ('En transit', 'Partiellement reçu'):
                raise Error('Seule une palette envoyée peut être clôturée avec écarts.', 409)
            pending = pending_of(c, did)
            if type(d.get('expected_remaining')) is not int or d['expected_remaining'] != len(pending) or not pending:
                raise Error('Le nombre de colis restants a changé. Actualisez.', 409)
            at = now()
            ids = []
            for l in pending:
                iid = c.execute('INSERT INTO pp_incidents(document_id,line_id,parcel_id,company_id,hub_id,kind,tracking,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (did, l['id'], l['parcel_id'], doc['client_id'], doc['destination_hub_id'], 'missing', l['tracking'], reason, u['id'], at)).lastrowid
                c.execute('UPDATE ops_document_lines SET active=0,missing_at=?,missing_by=? WHERE id=?', (at, u['id'], l['id']))
                ids.append(iid)
            status, remaining = recompute(c, doc, at)
            # Une clôture manuelle porte toujours au moins un manque : jamais Reçu complet.
            if status == 'Reçu':
                c.execute("UPDATE ops_documents SET status='Clôturé (écarts)' WHERE id=?", (did,))
                status = 'Clôturé (écarts)'
            audit(c, did, u, 'Palette clôturée avec écarts', {'reason': reason, 'missing_trackings': [l['tracking'] for l in pending], 'incident_ids': ids})
            notify(c, doc['client_id'], 'Palette ' + doc['reference'] + ' clôturée avec écarts', str(len(pending)) + ' colis déclaré(s) manquant(s). Ouvrez la palette pour répondre à chaque dossier.')
            return store(c, u, d, fp, did, 'close-gaps', ok=True, status=status, missing=len(pending), incident_ids=ids)

    @app.post('/api/partner-palettes/<int:did>/incidents/<int:iid>/respond')
    @auth('client')
    def incident_respond(did, iid):
        u = user()
        if u['client_type'] != 'societe_livraison':
            raise Error('Réponse réservée à la société de livraison concernée.', 403)
        d = body()
        response = text(d, 'response', 600, True)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc = users_and_doc(c, did, u)
            r = c.execute('SELECT * FROM pp_incidents WHERE id=? AND document_id=?', (iid, did)).fetchone()
            if not r:
                raise Error('Incident introuvable.', 404)
            if r['company_response'] == response:
                return jsonify(ok=True, changed=False)
            c.execute("UPDATE pp_incidents SET company_response=?,responded_by=?,responded_at=?,status='Réponse société' WHERE id=?", (response, u['id'], now(), iid))
            audit(c, did, u, 'Réponse de la société sur un incident', {'incident_id': iid, 'kind': r['kind'], 'tracking': r['tracking']})
            notify_admins(c, 'Réponse société · ' + doc['reference'], (doc['client_name'] or 'La société') + ' a répondu sur l’incident ' + r['kind'] + ' (' + r['tracking'] + ').')
            return jsonify(ok=True, changed=True)

    @app.post('/api/partner-palettes/<int:did>/incidents/<int:iid>/resolve')
    @auth('admin', 'agent')
    def incident_resolve(did, iid):
        u = user()
        receiver(u)
        d = body()
        action = d.get('action')
        note = text(d, 'note', 600, True)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc = users_and_doc(c, did, u)
            r = c.execute('SELECT * FROM pp_incidents WHERE id=? AND document_id=?', (iid, did)).fetchone()
            if not r:
                raise Error('Incident introuvable.', 404)
            if r['kind'] == 'damaged':
                if action not in ('release', 'hold'):
                    raise Error('Choisissez : débloquer le colis pour livraison, ou conserver le blocage.')
                if r['resolution'] == action:
                    return jsonify(ok=True, changed=False)
                c.execute("UPDATE pp_incidents SET resolution=?,resolution_note=?,resolved_by=?,resolved_at=?,status='Traité' WHERE id=?", (action, note, u['id'], now(), iid))
                if action == 'release':
                    s['event'](c, r['parcel_id'], 'Réceptionné', 'Incident endommagé traité : colis débloqué pour affectation — ' + note, u)
            else:
                if action != 'close':
                    raise Error('Action invalide pour ce type d’écart.')
                if r['status'] == 'Traité':
                    return jsonify(ok=True, changed=False)
                c.execute("UPDATE pp_incidents SET resolution='closed',resolution_note=?,resolved_by=?,resolved_at=?,status='Traité' WHERE id=?", (note, u['id'], now(), iid))
            audit(c, did, u, 'Incident traité', {'incident_id': iid, 'kind': r['kind'], 'tracking': r['tracking'], 'resolution': action})
            notify(c, doc['client_id'], 'Incident traité · ' + doc['reference'], 'L’incident ' + r['kind'] + ' (' + r['tracking'] + ') est traité : ' + note, r['parcel_id'])
            return jsonify(ok=True, changed=True)

    def hours(c, key):
        try:
            return max(0, min(720, int(c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()[0])))
        except (TypeError, ValueError):
            return ALERT_DEFAULTS[key]

    @app.get('/api/alerts')
    @auth('admin', 'agent')
    def alerts():
        u = user()
        scoped_hub = u['agent_hub_id'] if u['role'] == 'agent' else None
        with conn() as c:
            c.execute('BEGIN')
            groups = []
            hubcond = ' AND d.destination_hub_id=?' if scoped_hub else ''
            hubargs = (scoped_hub,) if scoped_hub else ()
            transit = hours(c, 'alert_transit_hours')
            if True:
                rows = c.execute("""SELECT d.id,d.reference,d.client_name,d.destination_name,d.dispatched_at,
                    round((julianday('now','localtime')-julianday(d.dispatched_at))*24) age
                    FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id
                    WHERE d.kind='partner_palette' AND d.status='En transit'""" + hubcond +
                    " AND (julianday('now','localtime')-julianday(d.dispatched_at))*24>=? ORDER BY age DESC LIMIT 100", hubargs + (transit,)) if transit else []
                groups.append(dict(kind='transit', limit=transit, title='Palettes envoyées non arrivées',
                                   items=[dict(document_id=r['id'], reference=r['reference'], company=r['client_name'], hub=r['destination_name'], age_hours=r['age']) for r in rows]))
            partial = hours(c, 'alert_partial_hours')
            if True:
                rows = c.execute("""SELECT d.id,d.reference,d.client_name,d.destination_name,d.dispatched_at,
                    round((julianday('now','localtime')-julianday(d.dispatched_at))*24) age
                    FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id
                    WHERE d.kind='partner_palette' AND d.status='Partiellement reçu'""" + hubcond +
                    " AND (julianday('now','localtime')-julianday(d.dispatched_at))*24>=? ORDER BY age DESC LIMIT 100", hubargs + (partial,)) if partial else []
                groups.append(dict(kind='partial', limit=partial, title='Réceptions partielles en attente',
                                   items=[dict(document_id=r['id'], reference=r['reference'], company=r['client_name'], hub=r['destination_name'], age_hours=r['age']) for r in rows]))
            unassigned = hours(c, 'alert_unassigned_hours')
            if True:
                cond = "p.status='Réceptionné' AND p.driver_id IS NULL" + (' AND p.current_hub_id=?' if scoped_hub else '')
                rows = c.execute("""SELECT p.id,p.tracking,cl.company,cl.name client,h.name hub,
                    round((julianday('now','localtime')-julianday(p.updated_at))*24) age
                    FROM parcels p JOIN users cl ON cl.id=p.client_id LEFT JOIN ops_hubs h ON h.id=p.current_hub_id
                    WHERE """ + cond + " AND (julianday('now','localtime')-julianday(p.updated_at))*24>=? ORDER BY age DESC LIMIT 100",
                    ((scoped_hub,) if scoped_hub else ()) + (unassigned,)) if unassigned else []
                groups.append(dict(kind='unassigned', limit=unassigned, title='Colis réceptionnés non affectés',
                                   items=[dict(parcel_id=r['id'], tracking=r['tracking'], company=r['company'] or r['client'], hub=r['hub'], age_hours=r['age']) for r in rows]))
            open_incidents = c.execute("""SELECT i.document_id,i.kind,d.reference,d.client_name FROM pp_incidents i
                JOIN ops_documents d ON d.id=i.document_id WHERE i.status<>'Traité'""" + (' AND d.destination_hub_id=?' if scoped_hub else '') +
                " ORDER BY i.id DESC LIMIT 100", (scoped_hub,) if scoped_hub else ())
            groups.append(dict(kind='incidents', limit=0, title='Incidents de réception ouverts',
                               items=[dict(document_id=r['document_id'], reference=r['reference'], company=r['client_name'], kind=r['kind']) for r in open_incidents]))
            return jsonify(groups=groups)
