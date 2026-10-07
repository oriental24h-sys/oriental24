"""v1.20.1 « Journal des contacts » — appels et messages WhatsApp du livreur dans la chronologie.

Chaque appel passé au destinataire et chaque message WhatsApp préparé/envoyé depuis le terrain est
horodaté (date + heure) et inscrit dans la « Chronologie d'activité » du colis :

    Livreur Amine El Idrissi : appel au destinataire Rania F. (0610001009) · durée 1:23
    Livreur Amine El Idrissi : message WhatsApp au destinataire Rania F. (0610001009) : « … »

La durée est mesurée sur l'appareil (décollage de l'application → retour dans l'application).
L'enregistrement est automatique : le livreur n'a aucune étape à répéter. Le résultat
(abouti / sans réponse / occupé / à rappeler) et la durée restent corrigeables après coup
(PATCH), et une trace peut être supprimée (DELETE).

Aucune API payante, aucun opérateur : l'application ouvre le composeur (`tel:`) ou WhatsApp
(`wa.me`) ; le serveur ne fait que conserver la trace.
"""
import re
from flask import request, jsonify

KIND_STATUS = {'appel': 'Appel client', 'whatsapp': 'WhatsApp client'}
OUTCOMES = {
    'abouti': '',
    'sans_reponse': 'sans réponse',
    'occupe': 'occupé',
    'rappeler': 'à rappeler',
    'annule': 'appel annulé',
}
MAX_DURATION = 4 * 3600          # 4 h : au-delà, la mesure est considérée comme aberrante.
PHONE_RE = re.compile(r'[+\d][\d\s().-]{5,24}')


def register_contact_log(app, services):
    conn, auth, user, parcel, now, Error = (services[k] for k in
                                            ['conn', 'auth', 'user', 'parcel', 'now', 'APIError'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS contact_logs(
          id INTEGER PRIMARY KEY, parcel_id INTEGER NOT NULL REFERENCES parcels(id),
          actor_id INTEGER REFERENCES users(id), kind TEXT NOT NULL,
          phone TEXT DEFAULT '', recipient TEXT DEFAULT '', duration_s INTEGER,
          outcome TEXT DEFAULT 'abouti', message TEXT DEFAULT '', role TEXT DEFAULT '',
          started_at TEXT DEFAULT '', created_at TEXT NOT NULL, event_id INTEGER);
        CREATE INDEX IF NOT EXISTS contact_logs_parcel ON contact_logs(parcel_id,id DESC);
        CREATE INDEX IF NOT EXISTS contact_logs_actor ON contact_logs(actor_id,created_at);
        ''')

    def fmt_dur(sec):
        sec = max(0, int(sec))
        if sec < 60:
            return '0:%02d' % sec
        h, rem = divmod(sec, 3600)
        m, s = divmod(rem, 60)
        return ('%d:%02d:%02d' % (h, m, s)) if h else ('%d:%02d' % (m, s))

    def build_note(kind, actor_name, recipient, phone, duration, outcome, message):
        """« Livreur <nom> : appel au destinataire <qui> (<num>) · durée <m:ss> »"""
        who = ('destinataire ' + recipient) if recipient else 'destinataire'
        target = '%s%s' % (who, (' (' + phone + ')') if phone else '')
        lead = ('Livreur ' + actor_name + ' : ') if actor_name else ''
        if kind == 'whatsapp':
            note = lead + 'message WhatsApp au ' + target
            if message:
                note += ' : « ' + message + ' »'
            return note
        note = lead + 'appel au ' + target
        label = OUTCOMES.get(outcome, '')
        if label:
            note += ' · ' + label + ((' (' + fmt_dur(duration) + ')') if duration else '')
        elif duration:
            note += ' · durée ' + fmt_dur(duration)
        else:
            note += ' · durée non mesurée'
        return note

    def actor_name(c, uid):
        if not uid:
            return ''
        r = c.execute('SELECT name FROM users WHERE id=?', (uid,)).fetchone()
        return r['name'] if r else ''

    def row_json(row, pid):
        return {
            'id': row['id'], 'parcel_id': pid, 'kind': row['kind'], 'phone': row['phone'],
            'recipient': row['recipient'], 'duration_s': row['duration_s'], 'outcome': row['outcome'],
            'message': row['message'], 'started_at': row['started_at'], 'created_at': row['created_at'],
            'event_id': row['event_id'], 'actor': row['actor'] if 'actor' in row.keys() else '',
            'label': 'Appel' if row['kind'] == 'appel' else 'WhatsApp',
            'duration_label': fmt_dur(row['duration_s']) if row['duration_s'] is not None else '',
            'note': row['note'] if 'note' in row.keys() else '',
        }

    def valid_duration(value):
        if value in (None, ''):
            return None
        if type(value) is not int or value < 0 or value > MAX_DURATION:
            raise Error("Durée d'appel invalide (secondes, 4 h maximum).")
        return value

    def clean_phone(value):
        phone = str(value or '').strip()[:25]
        if phone and not PHONE_RE.fullmatch(phone):
            raise Error('Numéro de téléphone invalide.')
        return phone

    @app.post('/api/parcels/<int:pid>/contact-log')
    @auth('admin', 'livreur', 'agent')
    def contact_log_add(pid):
        d = request.get_json(silent=True) or {}
        u = user()
        kind = str(d.get('kind') or '').strip().lower()
        if kind not in KIND_STATUS:
            raise Error('Type de contact invalide : « appel » ou « whatsapp » attendu.')
        outcome = str(d.get('outcome') or 'abouti').strip().lower()
        if outcome not in OUTCOMES:
            raise Error('Résultat de contact invalide.')
        duration = valid_duration(d.get('duration_s'))
        phone = clean_phone(d.get('phone'))
        recipient = str(d.get('recipient') or '').strip()[:80]
        message = str(d.get('message') or '').strip()[:300]
        started = str(d.get('started_at') or '').strip()[:25]
        t = now()
        created = started if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', started or '') and started <= t else t
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            parcel(c, pid, u)
            note = build_note(kind, u['name'], recipient, phone, duration, outcome, message)
            ev = c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',
                           (pid, u['id'], KIND_STATUS[kind], note, created))
            cur = c.execute('''INSERT INTO contact_logs(parcel_id,actor_id,kind,phone,recipient,duration_s,
                outcome,message,role,started_at,created_at,event_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (pid, u['id'], kind, phone, recipient, duration, outcome, message, u['role'],
                             started, created, ev.lastrowid))
            row = c.execute('SELECT * FROM contact_logs WHERE id=?', (cur.lastrowid,)).fetchone()
        return jsonify(ok=True, id=cur.lastrowid, event_id=ev.lastrowid, status=KIND_STATUS[kind], note=note,
                       created_at=created, duration_s=duration,
                       duration_label=(fmt_dur(duration) if duration is not None else ''),
                       row=row_json(row, pid))

    @app.patch('/api/parcels/<int:pid>/contact-log/<int:cid>')
    @auth('admin', 'livreur', 'agent')
    def contact_log_edit(pid, cid):
        """Correction après coup (durée et/ou résultat) : la chronologie suit immédiatement."""
        d = request.get_json(silent=True) or {}
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            parcel(c, pid, u)
            row = c.execute('SELECT * FROM contact_logs WHERE id=? AND parcel_id=?', (cid, pid)).fetchone()
            if not row:
                raise Error('Trace introuvable.', 404)
            if u['role'] != 'admin' and row['actor_id'] != u['id']:
                raise Error('Seul l’auteur ou un administrateur peut modifier cette trace.', 403)
            fields, args = [], []
            if 'outcome' in d:
                outcome = str(d.get('outcome') or '').strip().lower()
                if outcome not in OUTCOMES:
                    raise Error('Résultat de contact invalide.')
                fields.append('outcome=?'); args.append(outcome)
            if 'duration_s' in d:
                fields.append('duration_s=?'); args.append(valid_duration(d.get('duration_s')))
            if 'message' in d:
                fields.append('message=?'); args.append(str(d.get('message') or '').strip()[:300])
            if not fields:
                raise Error('Aucune correction fournie (durée, résultat ou message).')
            c.execute('UPDATE contact_logs SET %s WHERE id=?' % ','.join(fields), args + [cid])
            fresh = c.execute('SELECT * FROM contact_logs WHERE id=?', (cid,)).fetchone()
            note = build_note(fresh['kind'], actor_name(c, fresh['actor_id']), fresh['recipient'],
                              fresh['phone'], fresh['duration_s'], fresh['outcome'], fresh['message'])
            if fresh['event_id']:
                c.execute('UPDATE events SET note=? WHERE id=? AND parcel_id=?', (note, fresh['event_id'], pid))
        return jsonify(ok=True, id=cid, note=note,
                       duration_s=fresh['duration_s'], outcome=fresh['outcome'],
                       duration_label=(fmt_dur(fresh['duration_s']) if fresh['duration_s'] is not None else ''))

    @app.delete('/api/parcels/<int:pid>/contact-log/<int:cid>')
    @auth('admin', 'livreur', 'agent')
    def contact_log_delete(pid, cid):
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            parcel(c, pid, u)
            row = c.execute('SELECT * FROM contact_logs WHERE id=? AND parcel_id=?', (cid, pid)).fetchone()
            if not row:
                raise Error('Trace introuvable.', 404)
            if u['role'] != 'admin' and row['actor_id'] != u['id']:
                raise Error('Seul l’auteur ou un administrateur peut supprimer cette trace.', 403)
            c.execute('DELETE FROM contact_logs WHERE id=?', (cid,))
            if row['event_id']:
                c.execute('DELETE FROM events WHERE id=? AND parcel_id=?', (row['event_id'], pid))
        return jsonify(ok=True, deleted=cid)

    @app.get('/api/parcels/<int:pid>/contact-log')
    @auth('admin', 'livreur', 'agent')
    def contact_log_list(pid):
        u = user()
        with conn() as c:
            parcel(c, pid, u)
            rows = [dict(r) for r in c.execute('''SELECT cl.id,cl.kind,cl.phone,cl.recipient,cl.duration_s,cl.outcome,
                cl.message,cl.started_at,cl.created_at,cl.event_id,us.name actor,us.role role,ev.note note
                FROM contact_logs cl LEFT JOIN users us ON us.id=cl.actor_id
                LEFT JOIN events ev ON ev.id=cl.event_id
                WHERE cl.parcel_id=? ORDER BY cl.id DESC LIMIT 200''', (pid,))]
        for r in rows:
            r['duration_label'] = fmt_dur(r['duration_s']) if r['duration_s'] is not None else ''
            r['label'] = 'Appel' if r['kind'] == 'appel' else 'WhatsApp'
        calls = [r for r in rows if r['kind'] == 'appel']
        return jsonify(rows=rows, count=len(rows), calls=len(calls),
                       whatsapp=len([r for r in rows if r['kind'] == 'whatsapp']),
                       call_seconds=sum(r['duration_s'] or 0 for r in calls))
