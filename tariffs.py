"""Tarifs par client et par ville. Appliqués une seule fois, à la création du colis.
Aucune rétroactivité : les colis et factures existants conservent leurs montants figés.
"""
from flask import request, jsonify


def register_tariffs(app, s):
    conn, auth, user, now, Error = (s[k] for k in ['conn', 'auth', 'user', 'now', 'APIError'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS client_tariffs(
            client_id INTEGER NOT NULL REFERENCES users(id),
            city_id INTEGER NOT NULL REFERENCES cities(id),
            fee REAL NOT NULL CHECK(fee>=0 AND fee<=10000),
            return_fee REAL NOT NULL CHECK(return_fee>=0 AND return_fee<=10000),
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            PRIMARY KEY(client_id, city_id));
        CREATE TABLE IF NOT EXISTS client_tariff_audit(
            id INTEGER PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES users(id),
            city_id INTEGER NOT NULL REFERENCES cities(id),
            actor_id INTEGER NOT NULL REFERENCES users(id),
            old_fee REAL, old_return_fee REAL,
            new_fee REAL, new_return_fee REAL,
            created_at TEXT NOT NULL);
        ''')

    def fees_for(c, client_id, city):
        r = c.execute('SELECT fee,return_fee FROM client_tariffs WHERE client_id=? AND city_id=?', (client_id, city['id'])).fetchone()
        return (r['fee'], r['return_fee']) if r else (city['fee'], city['return_fee'])

    s['tariff_fees_for'] = fees_for

    def money(v, label):
        try:
            v = float(v)
            if not 0 <= v <= 10000:
                raise ValueError()
            return round(v, 2)
        except (ValueError, TypeError, OverflowError):
            raise Error('Montant invalide : ' + label + ' (0 à 10 000 MAD).')

    def client(c, cid):
        r = c.execute("SELECT * FROM users WHERE id=? AND role='client'", (cid,)).fetchone()
        if not r:
            raise Error('Client introuvable.', 404)
        return dict(r)

    @app.get('/api/clients/<int:cid>/tariffs')
    @auth('admin')
    def tariff_list(cid):
        u = user()
        with conn() as c:
            cl = client(c, cid)
            rows = c.execute('''SELECT ci.id city_id,ci.name city,ci.fee default_fee,ci.return_fee default_return_fee,
                t.fee,t.return_fee,t.updated_at,u.name updated_by
                FROM cities ci LEFT JOIN client_tariffs t ON t.city_id=ci.id AND t.client_id=?
                LEFT JOIN users u ON u.id=t.created_by ORDER BY ci.name''', (cid,)).fetchall()
            audit = c.execute('''SELECT a.*,ci.name city,u.name actor FROM client_tariff_audit a
                JOIN cities ci ON ci.id=a.city_id JOIN users u ON u.id=a.actor_id
                WHERE a.client_id=? ORDER BY a.id DESC LIMIT 100''', (cid,)).fetchall()
            return jsonify(client={'id': cl['id'], 'name': cl['name'], 'company': cl['company'], 'client_type': cl['client_type']},
                           cities=[dict(r) for r in rows], audit=[dict(r) for r in audit])

    @app.put('/api/clients/<int:cid>/tariffs/<int:city_id>')
    @auth('admin')
    def tariff_set(cid, city_id):
        u = user()
        d = request.get_json(silent=True)
        if not isinstance(d, dict) or not set(d) <= {'fee', 'return_fee'} or 'fee' not in d or 'return_fee' not in d:
            raise Error('Frais de livraison et de retour requis, sans autre champ.')
        fee, ret = money(d['fee'], 'livraison'), money(d['return_fee'], 'retour')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            client(c, cid)
            city = c.execute('SELECT * FROM cities WHERE id=?', (city_id,)).fetchone()
            if not city:
                raise Error('Ville introuvable.', 404)
            old = c.execute('SELECT fee,return_fee FROM client_tariffs WHERE client_id=? AND city_id=?', (cid, city_id)).fetchone()
            if old and round(old['fee'], 2) == fee and round(old['return_fee'], 2) == ret:
                return jsonify(ok=True, changed=False)
            c.execute('INSERT INTO client_tariffs(client_id,city_id,fee,return_fee,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?) '
                      'ON CONFLICT(client_id,city_id) DO UPDATE SET fee=excluded.fee,return_fee=excluded.return_fee,updated_at=excluded.updated_at',
                      (cid, city_id, fee, ret, u['id'], now(), now()))
            c.execute('INSERT INTO client_tariff_audit(client_id,city_id,actor_id,old_fee,old_return_fee,new_fee,new_return_fee,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (cid, city_id, u['id'], old['fee'] if old else city['fee'], old['return_fee'] if old else city['return_fee'], fee, ret, now()))
            return jsonify(ok=True, changed=True)

    @app.delete('/api/clients/<int:cid>/tariffs/<int:city_id>')
    @auth('admin')
    def tariff_reset(cid, city_id):
        u = user()
        if request.data:
            raise Error('Suppression de tarif sans contenu de requête.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old = c.execute('SELECT fee,return_fee FROM client_tariffs WHERE client_id=? AND city_id=?', (cid, city_id)).fetchone()
            if not old:
                return jsonify(ok=True, changed=False)
            c.execute('DELETE FROM client_tariffs WHERE client_id=? AND city_id=?', (cid, city_id))
            c.execute('INSERT INTO client_tariff_audit(client_id,city_id,actor_id,old_fee,old_return_fee,new_fee,new_return_fee,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (cid, city_id, u['id'], old['fee'], old['return_fee'], None, None, now()))
            return jsonify(ok=True, changed=True)
