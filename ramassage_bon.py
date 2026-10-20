# -*- coding: utf-8 -*-
"""Bons de ramassage initiés par le client vendeur.

Flux :
  1. Le client crée un brouillon de bon en choisissant ses colis « Créé » et le Hub de destination.
  2. Il valide le bon  -> chaque colis passe « Créé » -> « Confirmé ».
  3. Le livreur achemine les colis ; le responsable du Hub destinataire scanne chaque colis
     à la réception -> le colis passe « Confirmé » -> « Ramassé » et est localisé à ce Hub.

Module autonome : il ne touche pas au moteur de documents inter-Hubs (logistics.py).
"""
import re
from flask import jsonify, request

PHONE_RE = re.compile(r'^\+?[\d\s\-]{9,18}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
BON_STATUSES = ('Brouillon', 'Confirmé', 'En cours', 'Reçu', 'Annulé')
ACTIVE_BON_STATUSES = ('Brouillon', 'Confirmé', 'En cours')


def register_ramassage_bon(app, services):
    conn, auth, user, now, text, Error, event = (
        services[k] for k in ['conn', 'auth', 'user', 'now', 'text', 'APIError', 'event'])

    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ramassage_bons(
            id INTEGER PRIMARY KEY,
            reference TEXT UNIQUE NOT NULL,
            client_id INTEGER NOT NULL REFERENCES users(id),
            hub_id INTEGER REFERENCES ops_hubs(id),
            city_id INTEGER REFERENCES cities(id),
            address TEXT NOT NULL,
            phone TEXT NOT NULL,
            pickup_date TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Brouillon',
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            validated_at TEXT,
            validated_by INTEGER,
            completed_at TEXT,
            cancel_reason TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS ramassage_bon_lines(
            id INTEGER PRIMARY KEY,
            bon_id INTEGER NOT NULL REFERENCES ramassage_bons(id),
            parcel_id INTEGER NOT NULL REFERENCES parcels(id),
            tracking TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            received_at TEXT,
            received_by INTEGER,
            UNIQUE(bon_id, parcel_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ramassage_bon_one_active
            ON ramassage_bon_lines(parcel_id) WHERE active=1;
        CREATE INDEX IF NOT EXISTS ramassage_bon_lines_bon ON ramassage_bon_lines(bon_id);
        ''')

    def body():
        d = request.get_json()
        if not isinstance(d, dict):
            raise Error('Objet JSON requis.')
        return d

    def integer(v, label='Identifiant'):
        if isinstance(v, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}', str(v)):
            raise Error(label + ' invalide.')
        return int(v)

    def parcel_ids(d):
        v = d.get('parcel_ids')
        if not isinstance(v, list) or not 1 <= len(v) <= 100:
            raise Error('Sélectionnez de 1 à 100 colis.')
        values = [integer(i, 'Colis') for i in v]
        if len(values) != len(set(values)):
            raise Error('Colis répété dans la sélection.')
        return values

    def active_hub(c, hub_id):
        h = c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1', (hub_id,)).fetchone()
        if not h:
            raise Error('Hub actif introuvable.', 404)
        return h

    def active_line_for_parcel(c, parcel_id):
        return c.execute(
            'SELECT 1 FROM ramassage_bon_lines WHERE parcel_id=? AND active=1', (parcel_id,)).fetchone()

    def own_created_parcel(c, parcel_id, client_id):
        """Un colis éligible : appartient au client, état « Créé », non facturé, hors bon actif."""
        p = c.execute(
            'SELECT * FROM parcels WHERE id=? AND client_id=?', (parcel_id, client_id)).fetchone()
        if not p:
            raise Error('Colis introuvable pour ce client : #%s' % parcel_id, 404)
        if p['status'] != 'Créé':
            raise Error('Le colis %s n’est pas à l’état « Créé ».' % p['tracking'], 409)
        if p['invoice_id'] is not None:
            raise Error('Le colis %s est déjà facturé.' % p['tracking'], 409)
        if active_line_for_parcel(c, parcel_id):
            raise Error('Le colis %s figure déjà dans un bon de ramassage actif.' % p['tracking'], 409)
        return p

    def serialize(c, bon):
        b = dict(bon)
        lines = [dict(r) for r in c.execute(
            '''SELECT l.*, p.status AS parcel_status, p.current_hub_id AS parcel_hub_id,
                      p.recipient AS recipient, p.phone AS recipient_phone, ci.name AS city
               FROM ramassage_bon_lines l JOIN parcels p ON p.id=l.parcel_id
               JOIN cities ci ON ci.id=p.city_id
               WHERE l.bon_id=? ORDER BY l.id''', (b['id'],))]
        b['lines'] = lines
        b['count'] = len(lines)
        b['received'] = sum(1 for l in lines if l['received_at'])
        hub = c.execute('SELECT name FROM ops_hubs WHERE id=?', (b['hub_id'],)).fetchone()
        city = c.execute('SELECT name FROM cities WHERE id=?', (b['city_id'],)).fetchone()
        client = c.execute('SELECT name,company FROM users WHERE id=?', (b['client_id'],)).fetchone()
        b['hub_name'] = hub['name'] if hub else None
        b['city_name'] = city['name'] if city else None
        b['client_name'] = client['name'] if client else None
        b['client_company'] = client['company'] if client else None
        return b

    def load_bon(c, bon_id, u):
        bon = c.execute('SELECT * FROM ramassage_bons WHERE id=?', (bon_id,)).fetchone()
        if not bon:
            raise Error('Bon de ramassage introuvable.', 404)
        # Un client ne voit que ses bons ; un agent que ceux destinés à son Hub (vu via la file dédiée).
        if u['role'] == 'client' and bon['client_id'] != u['id']:
            raise Error('Bon de ramassage introuvable.', 404)
        if u['role'] == 'agent' and bon['hub_id'] != u.get('agent_hub_id'):
            raise Error('Bon de ramassage introuvable.', 404)
        return bon

    def create_bon(c, u, d):
        is_admin = u['role'] == 'admin'
        client_id = u['id'] if u['role'] == 'client' else integer(d.get('client_id'), 'Client')
        client = c.execute(
            "SELECT id FROM users WHERE id=? AND role='client' AND active=1", (client_id,)).fetchone()
        if not client:
            raise Error('Client actif introuvable.', 404)
        hub_id = integer(d.get('hub_id'), 'Hub')
        hub = active_hub(c, hub_id)
        city_id = d.get('city_id')
        if city_id in (None, ''):
            city_id = hub['city_id']
        city_id = integer(city_id, 'Ville')
        city = c.execute('SELECT id FROM cities WHERE id=? AND pickup=1', (city_id,)).fetchone()
        if not city:
            raise Error('Ville fermée au ramassage.', 409)
        address = text(d, 'address', True, 600)
        phone = text(d, 'phone', True, 30)
        if not PHONE_RE.fullmatch(phone):
            raise Error('Téléphone invalide.')
        pickup_date = text(d, 'pickup_date', True, 10)
        if not DATE_RE.fullmatch(pickup_date):
            raise Error('Date de ramassage invalide (AAAA-MM-JJ).')
        note = text(d, 'note', False, 600)
        ids = parcel_ids(d)
        t = now()
        bon_id = c.execute(
            '''INSERT INTO ramassage_bons(reference,client_id,hub_id,city_id,address,phone,pickup_date,
                  note,status,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,'Brouillon',?,?)''',
            ('RB-0000', client_id, hub_id, city_id, address, phone, pickup_date, note, u['id'], t)).lastrowid
        c.execute('UPDATE ramassage_bons SET reference=? WHERE id=?', ('RB-%04d' % bon_id, bon_id))
        for pid in ids:
            p = own_created_parcel(c, pid, client_id)
            c.execute(
                'INSERT INTO ramassage_bon_lines(bon_id,parcel_id,tracking,active) VALUES(?,?,?,1)',
                (bon_id, pid, p['tracking']))
        return bon_id

    # ------------------------------------------------------------------ Liste / détail
    @app.get('/api/ramassage-bons')
    @auth('admin', 'client', 'agent')
    def ramassage_bon_list():
        u = user()
        with conn() as c:
            where, args = '', []
            if u['role'] == 'client':
                where, args = 'WHERE b.client_id=?', [u['id']]
            elif u['role'] == 'agent':
                where, args = 'WHERE b.hub_id=?', [u.get('agent_hub_id')]
            rows = c.execute(
                'SELECT * FROM ramassage_bons b %s ORDER BY b.id DESC LIMIT 500' % where, args).fetchall()
            return jsonify([serialize(c, r) for r in rows])

    @app.get('/api/ramassage-bons/eligible')
    @auth('admin', 'client')
    def ramassage_bon_eligible():
        u = user()
        d = request.args
        client_id = u['id'] if u['role'] == 'client' else integer(d.get('client_id'), 'Client')
        with conn() as c:
            rows = c.execute('''
                SELECT p.id,p.tracking,p.recipient,p.phone,p.address,p.status,ci.name city
                FROM parcels p JOIN cities ci ON ci.id=p.city_id
                WHERE p.client_id=? AND p.status='Créé' AND p.invoice_id IS NULL
                  AND NOT EXISTS(SELECT 1 FROM ramassage_bon_lines l
                                 WHERE l.parcel_id=p.id AND l.active=1)
                ORDER BY p.id DESC LIMIT 500''', (client_id,)).fetchall()
            return jsonify([dict(r) for r in rows])

    @app.get('/api/ramassage-bons/hub/queue')
    @auth('admin', 'agent')
    def ramassage_bon_hub_queue():
        u = user()
        with conn() as c:
            if u['role'] == 'agent':
                hub_id = u.get('agent_hub_id')
                active_hub(c, hub_id)
                rows = c.execute(
                    "SELECT * FROM ramassage_bons WHERE hub_id=? AND status IN ('Confirmé','En cours') ORDER BY id",
                    (hub_id,)).fetchall()
            else:
                hub_id = request.args.get('hub_id')
                sql = "SELECT * FROM ramassage_bons WHERE status IN ('Confirmé','En cours')"
                args = []
                if hub_id:
                    sql += ' AND hub_id=?'
                    args.append(integer(hub_id, 'Hub'))
                rows = c.execute(sql + ' ORDER BY id', args).fetchall()
            return jsonify([serialize(c, r) for r in rows])

    @app.get('/api/ramassage-bons/<int:bon_id>')
    @auth('admin', 'client', 'agent')
    def ramassage_bon_detail(bon_id):
        u = user()
        with conn() as c:
            return jsonify(serialize(c, load_bon(c, bon_id, u)))

    # ------------------------------------------------------------------ Création / édition
    @app.post('/api/ramassage-bons')
    @auth('admin', 'client')
    def ramassage_bon_create():
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon_id = create_bon(c, u, body())
            return jsonify(ok=True, id=bon_id, reference='RB-%04d' % bon_id)

    @app.post('/api/ramassage-bons/<int:bon_id>/lines')
    @auth('admin', 'client')
    def ramassage_bon_add_lines(bon_id):
        u = user()
        d = body()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon = load_bon(c, bon_id, u)
            if bon['status'] != 'Brouillon':
                raise Error('Un bon déjà validé ne peut plus être modifié.', 409)
            for pid in parcel_ids(d):
                p = own_created_parcel(c, pid, bon['client_id'])
                c.execute(
                    'INSERT INTO ramassage_bon_lines(bon_id,parcel_id,tracking,active) VALUES(?,?,?,1)',
                    (bon_id, pid, p['tracking']))
            return jsonify(ok=True)

    @app.route('/api/ramassage-bons/<int:bon_id>/lines/<int:parcel_id>', methods=['DELETE'])
    @auth('admin', 'client')
    def ramassage_bon_remove_line(bon_id, parcel_id):
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon = load_bon(c, bon_id, u)
            if bon['status'] != 'Brouillon':
                raise Error('Un bon déjà validé ne peut plus être modifié.', 409)
            cur = c.execute(
                'UPDATE ramassage_bon_lines SET active=0 WHERE bon_id=? AND parcel_id=? AND active=1',
                (bon_id, parcel_id))
            if not cur.rowcount:
                raise Error('Ligne introuvable dans ce bon.', 404)
            return jsonify(ok=True)

    # ------------------------------------------------------------------ Validation client
    @app.post('/api/ramassage-bons/<int:bon_id>/validate')
    @auth('admin', 'client')
    def ramassage_bon_validate(bon_id):
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon = load_bon(c, bon_id, u)
            if bon['status'] == 'Confirmé':
                return jsonify(ok=True, already_validated=True)
            if bon['status'] != 'Brouillon':
                raise Error('Seul un brouillon peut être validé.', 409)
            lines = c.execute(
                'SELECT * FROM ramassage_bon_lines WHERE bon_id=? AND active=1', (bon_id,)).fetchall()
            if not lines:
                raise Error('Ajoutez au moins un colis avant de valider.', 409)
            t = now()
            for line in lines:
                p = c.execute('SELECT * FROM parcels WHERE id=?', (line['parcel_id'],)).fetchone()
                if not p or p['client_id'] != bon['client_id']:
                    raise Error('Le bon référence un colis qui n’appartient plus au client.', 409)
                if p['status'] != 'Créé' or p['invoice_id'] is not None:
                    raise Error(
                        'Le colis %s ne peut pas être confirmé (état %s).' % (line['tracking'], p['status']), 409)
            for line in lines:
                c.execute(
                    "UPDATE parcels SET status='Confirmé',updated_at=? WHERE id=?", (t, line['parcel_id']))
                event(c, line['parcel_id'], 'Confirmé',
                      bon['reference'] + ' · demande de ramassage validée par le client', u)
            c.execute(
                "UPDATE ramassage_bons SET status='Confirmé',validated_at=?,validated_by=? WHERE id=?",
                (t, u['id'], bon_id))
            return jsonify(ok=True, status='Confirmé')

    @app.post('/api/ramassage-bons/<int:bon_id>/cancel')
    @auth('admin', 'client')
    def ramassage_bon_cancel(bon_id):
        u = user()
        d = body() if request.is_json else {}
        reason = text(d, 'reason', False, 600)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon = load_bon(c, bon_id, u)
            # Le client ne peut annuler que ses brouillons ; l'admin peut aussi libérer un bon confirmé.
            if u['role'] == 'client' and bon['status'] != 'Brouillon':
                raise Error('Le client ne peut annuler qu’un bon encore en brouillon.', 403)
            if bon['status'] not in ('Brouillon', 'Confirmé'):
                raise Error('Ce bon ne peut plus être annulé.', 409)
            t = now()
            if bon['status'] == 'Confirmé':
                for line in c.execute(
                        'SELECT parcel_id FROM ramassage_bon_lines WHERE bon_id=? AND active=1', (bon_id,)):
                    p = c.execute('SELECT status FROM parcels WHERE id=?', (line['parcel_id'],)).fetchone()
                    if p and p['status'] == 'Confirmé':
                        c.execute(
                            "UPDATE parcels SET status='Créé',updated_at=? WHERE id=?", (t, line['parcel_id']))
                        event(c, line['parcel_id'], 'Créé',
                              bon['reference'] + ' · bon annulé, colis remis à l’état « Créé »', u)
            c.execute('UPDATE ramassage_bon_lines SET active=0 WHERE bon_id=?', (bon_id,))
            c.execute(
                "UPDATE ramassage_bons SET status='Annulé',cancel_reason=? WHERE id=?", (reason, bon_id))
            return jsonify(ok=True, status='Annulé')

    # ------------------------------------------------------------------ Réception au Hub
    @app.post('/api/ramassage-bons/<int:bon_id>/receive')
    @auth('admin', 'agent')
    def ramassage_bon_receive(bon_id):
        u = user()
        d = body()
        tracking = text(d, 'tracking', True, 80).upper()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            bon = load_bon(c, bon_id, u)
            if u['role'] == 'agent':
                if bon['hub_id'] != u.get('agent_hub_id'):
                    raise Error('Ce bon n’est pas destiné à votre Hub.', 404)
                active_hub(c, u.get('agent_hub_id'))
            if bon['status'] not in ('Confirmé', 'En cours'):
                raise Error('Ce bon n’est pas en attente de réception.', 409)
            line = c.execute(
                'SELECT * FROM ramassage_bon_lines WHERE bon_id=? AND upper(tracking)=? AND active=1',
                (bon_id, tracking)).fetchone()
            if not line:
                raise Error('Ce colis ne figure pas dans le bon.', 404)
            p = c.execute('SELECT * FROM parcels WHERE id=?', (line['parcel_id'],)).fetchone()
            if line['received_at']:
                if p['current_hub_id'] == bon['hub_id']:
                    return jsonify(ok=True, already_received=True)
                raise Error('Ligne déjà réceptionnée dans un autre contexte.', 409)
            if p['status'] != 'Confirmé':
                raise Error(
                    'Le colis %s n’est pas à l’état « Confirmé » (état %s).' % (tracking, p['status']), 409)
            t = now()
            c.execute(
                "UPDATE parcels SET status='Ramassé',current_hub_id=?,updated_at=? WHERE id=?",
                (bon['hub_id'], t, p['id']))
            c.execute(
                'UPDATE ramassage_bon_lines SET received_at=?,received_by=? WHERE id=?',
                (t, u['id'], line['id']))
            event(c, p['id'], 'Ramassé',
                  bon['reference'] + ' · réception scannée au Hub (' + tracking + ')', u)
            remaining = c.execute(
                'SELECT count(*) k FROM ramassage_bon_lines WHERE bon_id=? AND active=1 AND received_at IS NULL',
                (bon_id,)).fetchone()['k']
            if remaining == 0:
                c.execute(
                    "UPDATE ramassage_bons SET status='Reçu',completed_at=? WHERE id=?", (t, bon_id))
                c.execute('UPDATE ramassage_bon_lines SET active=0 WHERE bon_id=?', (bon_id,))
                next_status = 'Reçu'
            else:
                c.execute("UPDATE ramassage_bons SET status='En cours' WHERE id=?", (bon_id,))
                next_status = 'En cours'
            return jsonify(ok=True, status=next_status, remaining=remaining)
