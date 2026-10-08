"""Client parcel feedback and recipient-change requests.

Recipient changes keep before/after contact snapshots, leave tracking and finance
untouched, and append every submission/decision to the parcel event history.
"""
import re
from flask import jsonify, request


def register_client_feedback(app, services):
    conn, auth, user, parcel, event, now, text, Error = (
        services[k] for k in
        ('conn', 'auth', 'user', 'parcel', 'event', 'now', 'text', 'APIError')
    )

    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS recipient_change_requests(
            id INTEGER PRIMARY KEY,
            parcel_id INTEGER NOT NULL REFERENCES parcels(id),
            client_id INTEGER NOT NULL REFERENCES users(id),
            old_recipient TEXT NOT NULL,
            old_phone TEXT NOT NULL DEFAULT '',
            old_city_id INTEGER REFERENCES cities(id),
            old_address TEXT NOT NULL DEFAULT '',
            requested_recipient TEXT NOT NULL,
            requested_phone TEXT NOT NULL DEFAULT '',
            requested_city_id INTEGER REFERENCES cities(id),
            requested_address TEXT NOT NULL DEFAULT '',
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'En attente',
            created_at TEXT NOT NULL,
            reviewed_by INTEGER REFERENCES users(id),
            reviewed_at TEXT,
            admin_note TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_recipient_change_parcel
            ON recipient_change_requests(parcel_id, id DESC);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recipient_change_one_pending
            ON recipient_change_requests(parcel_id) WHERE status='En attente';
        CREATE TABLE IF NOT EXISTS client_service_ratings(
            id INTEGER PRIMARY KEY,
            parcel_id INTEGER NOT NULL REFERENCES parcels(id),
            client_id INTEGER NOT NULL REFERENCES users(id),
            target TEXT NOT NULL CHECK(target IN ('driver','support')),
            stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 5),
            comment TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(parcel_id, client_id, target)
        );
        CREATE INDEX IF NOT EXISTS idx_client_service_ratings_parcel
            ON client_service_ratings(parcel_id, target);
        ''')
        columns = {r['name'] for r in c.execute('PRAGMA table_info(recipient_change_requests)')}
        additions = (
            ('old_phone', "TEXT NOT NULL DEFAULT ''"),
            ('old_city_id', 'INTEGER REFERENCES cities(id)'),
            ('old_address', "TEXT NOT NULL DEFAULT ''"),
            ('requested_phone', "TEXT NOT NULL DEFAULT ''"),
            ('requested_city_id', 'INTEGER REFERENCES cities(id)'),
            ('requested_address', "TEXT NOT NULL DEFAULT ''"),
        )
        for name, declaration in additions:
            if name not in columns:
                c.execute(f'ALTER TABLE recipient_change_requests ADD COLUMN {name} {declaration}')
        # A pending request created by an earlier version changed only the name.
        # Preserve its old behavior safely by treating its other requested fields
        # as unchanged parcel values rather than blanking contact information.
        c.execute('''UPDATE recipient_change_requests SET
            old_phone=CASE WHEN old_phone='' THEN COALESCE((SELECT phone FROM parcels WHERE id=parcel_id),'') ELSE old_phone END,
            old_city_id=COALESCE(old_city_id,(SELECT city_id FROM parcels WHERE id=parcel_id)),
            old_address=CASE WHEN old_address='' THEN COALESCE((SELECT address FROM parcels WHERE id=parcel_id),'') ELSE old_address END,
            requested_phone=CASE WHEN requested_phone='' THEN COALESCE((SELECT phone FROM parcels WHERE id=parcel_id),'') ELSE requested_phone END,
            requested_city_id=COALESCE(requested_city_id,(SELECT city_id FROM parcels WHERE id=parcel_id)),
            requested_address=CASE WHEN requested_address='' THEN COALESCE((SELECT address FROM parcels WHERE id=parcel_id),'') ELSE requested_address END
            WHERE status='En attente' ''')

    def body():
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            raise Error('Objet JSON requis.')
        return d

    @app.post('/api/parcels/<int:pid>/recipient-change-requests')
    @auth('client')
    def recipient_change_request_create(pid):
        d = body()
        u = user()
        new_name = text(d, 'recipient', maxlen=120)
        new_phone = text(d, 'phone', maxlen=18)
        if not re.fullmatch(r'\+?[\d\s-]{9,18}', new_phone):
            raise Error('Numéro de téléphone invalide.')
        raw_city_id = d.get('city_id')
        if isinstance(raw_city_id, bool):
            raise Error('Choisissez une ville ouverte à la livraison.')
        try:
            new_city_id = int(raw_city_id)
            if isinstance(raw_city_id, float) and raw_city_id != new_city_id:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise Error('Choisissez une ville ouverte à la livraison.')
        new_address = text(d, 'address', maxlen=300)
        reason = text(d, 'reason', required=False, maxlen=500)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            p = parcel(c, pid, u)
            if p['status'] in ('Livré', 'Retourné'):
                raise Error('Le changement de destinataire est indisponible pour un colis Livré ou Retourné.', 409)
            new_city = c.execute('SELECT id,name FROM cities WHERE id=? AND (delivery=1 OR id=?)', (new_city_id, p['city_id'])).fetchone()
            if not new_city:
                raise Error('Choisissez une ville ouverte à la livraison.')
            old_name = str(p.get('recipient') or '').strip()
            old_phone = str(p.get('phone') or '').strip()
            old_address = str(p.get('address') or '').strip()
            old_city_id = int(p.get('city_id') or 0)
            old_city = c.execute('SELECT name FROM cities WHERE id=?', (old_city_id,)).fetchone()
            if (new_name.casefold(), new_phone, new_city_id, new_address) == (
                old_name.casefold(), old_phone, old_city_id, old_address
            ):
                raise Error('Modifiez au moins une information du destinataire.')
            pending = c.execute(
                "SELECT id FROM recipient_change_requests WHERE parcel_id=? AND status='En attente'",
                (pid,),
            ).fetchone()
            if pending:
                raise Error('Une demande de changement est déjà en attente.', 409)
            rid = c.execute('''INSERT INTO recipient_change_requests(
                parcel_id,client_id,old_recipient,old_phone,old_city_id,old_address,
                requested_recipient,requested_phone,requested_city_id,requested_address,
                reason,status,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,'En attente',?)''',
                (pid, u['id'], old_name, old_phone, old_city_id, old_address,
                 new_name, new_phone, new_city_id, new_address, reason, now()),
            ).lastrowid
            old_city_name = old_city['name'] if old_city else '—'
            note = (
                f'Demande changement de destinataire déposée : {old_name} → {new_name}'
                f' · Téléphone : {old_phone or "—"} → {new_phone}'
                f' · Ville : {old_city_name} → {new_city["name"]}'
                f' · Adresse : {old_address or "—"} → {new_address}'
            )
            if reason:
                note += f' · Motif : {reason}'
            event(c, pid, p['status'], note, u)
        return jsonify(ok=True, id=rid, status='En attente', tracking=p['tracking'])

    @app.get('/api/recipient-change-requests')
    @auth('admin')
    def recipient_change_requests_list():
        with conn() as c:
            rows = [dict(r) for r in c.execute('''
                SELECT r.*,p.tracking,p.status parcel_status,p.recipient current_recipient,
                       p.phone current_phone,p.address current_address,p.city_id current_city_id,
                       COALESCE(NULLIF(r.old_phone,''),p.phone) old_phone_display,
                       COALESCE(NULLIF(r.old_address,''),p.address) old_address_display,
                       COALESCE(old_city.name,current_city.name) old_city_display,
                       COALESCE(NULLIF(r.requested_phone,''),p.phone) requested_phone_display,
                       COALESCE(NULLIF(r.requested_address,''),p.address) requested_address_display,
                       COALESCE(requested_city.name,current_city.name) requested_city_display,
                       p.invoice_id,cl.name author,cl.company company
                FROM recipient_change_requests r
                JOIN parcels p ON p.id=r.parcel_id
                LEFT JOIN cities old_city ON old_city.id=r.old_city_id
                LEFT JOIN cities requested_city ON requested_city.id=r.requested_city_id
                LEFT JOIN cities current_city ON current_city.id=p.city_id
                JOIN users cl ON cl.id=r.client_id
                ORDER BY CASE WHEN r.status='En attente' THEN 0 ELSE 1 END,
                         r.id DESC
            ''')]
        return jsonify(rows)

    @app.patch('/api/recipient-change-requests/<int:rid>')
    @auth('admin')
    def recipient_change_request_decide(rid):
        d = body()
        decision = d.get('status')
        if decision not in ('Acceptée', 'Refusée'):
            raise Error('Choisissez Accepter ou Refuser.')
        admin_note = text(d, 'admin_note', required=False, maxlen=500)
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            r = c.execute("SELECT * FROM recipient_change_requests WHERE id=? AND status='En attente'", (rid,)).fetchone()
            if not r:
                raise Error('Demande déjà traitée ou introuvable.', 409)
            p = parcel(c, r['parcel_id'], u)
            if decision == 'Acceptée' and p['status'] in ('Livré', 'Retourné'):
                raise Error('Acceptation impossible : la commande est déjà Livrée ou Retournée.', 409)
            if decision == 'Acceptée':
                # Tracking, COD, fees, invoice and status stay untouched.
                new_recipient = r['requested_recipient']
                new_phone = r['requested_phone'] or p['phone']
                new_city_id = int(r['requested_city_id'] or p['city_id'])
                new_address = r['requested_address'] or p['address']
                new_city = c.execute('SELECT name FROM cities WHERE id=? AND (delivery=1 OR id=?)', (new_city_id, p['city_id'])).fetchone()
                if not new_city:
                    raise Error('La ville demandée n’est plus ouverte à la livraison. Refusez la demande ou demandez-en une nouvelle.', 409)
                old_city = c.execute('SELECT name FROM cities WHERE id=?', (p['city_id'],)).fetchone()
                c.execute('''UPDATE parcels
                             SET recipient=?,phone=?,city_id=?,address=?,updated_at=?
                             WHERE id=?''',
                          (new_recipient, new_phone, new_city_id, new_address, now(), p['id']))
                note = (
                    f'Changement des coordonnées du destinataire accepté : {p["recipient"]} → {new_recipient}'
                    f' · Téléphone : {p["phone"] or "—"} → {new_phone}'
                    f' · Ville : {old_city["name"] if old_city else "—"} → {new_city["name"]}'
                    f' · Adresse : {p["address"] or "—"} → {new_address}'
                    f' · Suivi inchangé : {p["tracking"]}'
                )
            else:
                note = (
                    f'Demande de changement de destinataire refusée · coordonnées actuelles conservées : '
                    f'{p["recipient"]} · {p["phone"] or "—"} · {p["address"] or "—"}'
                )
            if admin_note:
                note += f' · Note Admin : {admin_note}'
            c.execute('''UPDATE recipient_change_requests
                         SET status=?,reviewed_by=?,reviewed_at=?,admin_note=? WHERE id=?''',
                      (decision, u['id'], now(), admin_note, rid))
            event(c, p['id'], p['status'], note, u)
        return jsonify(
            ok=True,
            status=decision,
            recipient=(r['requested_recipient'] if decision == 'Acceptée' else p['recipient']),
            phone=(new_phone if decision == 'Acceptée' else p['phone']),
            city_id=(new_city_id if decision == 'Acceptée' else p['city_id']),
            address=(new_address if decision == 'Acceptée' else p['address']),
            tracking=p['tracking'],
        )

    @app.get('/api/parcels/<int:pid>/ratings')
    @auth('admin', 'client')
    def client_parcel_ratings(pid):
        u = user()
        with conn() as c:
            p = parcel(c, pid, u)
            rows = [dict(r) for r in c.execute('''
                SELECT r.id,r.parcel_id,r.client_id,r.target,r.stars,r.comment,r.created_at,r.updated_at,
                       cl.name client
                FROM client_service_ratings r JOIN users cl ON cl.id=r.client_id
                WHERE r.parcel_id=? ORDER BY r.target,r.id
            ''', (p['id'],))]
        return jsonify(ratings=rows)

    @app.post('/api/parcels/<int:pid>/ratings')
    @auth('client')
    def client_parcel_rating_save(pid):
        d = body()
        target = d.get('target')
        stars = d.get('stars')
        if target not in ('driver', 'support'):
            raise Error('Choisissez le livreur ou le support.')
        if isinstance(stars, bool) or not isinstance(stars, int) or not 1 <= stars <= 5:
            raise Error('Choisissez de 1 à 5 étoiles.')
        comment = text(d, 'comment', required=False, maxlen=600)
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            p = parcel(c, pid, u)
            previous = c.execute('''SELECT id,created_at FROM client_service_ratings
                                    WHERE parcel_id=? AND client_id=? AND target=?''',
                                 (pid, u['id'], target)).fetchone()
            t = now()
            c.execute('''INSERT INTO client_service_ratings(
                            parcel_id,client_id,target,stars,comment,created_at,updated_at
                        ) VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(parcel_id,client_id,target) DO UPDATE SET
                            stars=excluded.stars,comment=excluded.comment,updated_at=excluded.updated_at''',
                      (pid, u['id'], target, stars, comment, t, t))
            subject = 'livreur' if target == 'driver' else 'support'
            action = 'mise à jour' if previous else 'enregistrée'
            note = f'Évaluation du {subject} {action} : {stars}/5 étoiles'
            if comment:
                note += f' · Commentaire : {comment}'
            event(c, pid, p['status'], note, u)
            saved = c.execute('''SELECT id,parcel_id,client_id,target,stars,comment,created_at,updated_at
                                 FROM client_service_ratings
                                 WHERE parcel_id=? AND client_id=? AND target=?''',
                              (pid, u['id'], target)).fetchone()
        return jsonify(ok=True, rating=dict(saved))
