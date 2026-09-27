"""v1.5.3 « Fin de journée » (Khatm caisse nhar) : instantané journalier par livreur —
livré du jour, COD, commissions (barème à la ville), attendu caisse, remise Admin, écart,
clôture/réouverture tracées. Module branché dans app.py comme driver_finance."""
import json
from flask import request, jsonify


def register_driver_days(app, services):
    conn, auth, user, now, text, Error, event = (services[k] for k in ('conn', 'auth', 'user', 'now', 'text', 'APIError', 'event'))
    team_member_ids = services['team_member_ids']
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS driver_day_closes(
            id INTEGER PRIMARY KEY, driver_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL,
            livres INTEGER NOT NULL, cod_cents INTEGER NOT NULL, commission_cents INTEGER NOT NULL,
            expected_cents INTEGER NOT NULL, received_cents INTEGER NOT NULL, variance_cents INTEGER NOT NULL,
            mode TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Clôturé','Rouvert')),
            reference TEXT, note TEXT,
            closed_by INTEGER NOT NULL REFERENCES users(id), closed_by_name TEXT NOT NULL, closed_at TEXT NOT NULL,
            reopened_by INTEGER REFERENCES users(id), reopen_note TEXT, reopened_at TEXT,
            UNIQUE(driver_id, day));''')

    def cents(v):
        try:
            return int(round(v * 100))
        except (TypeError, ValueError):
            return 0

    def audit(c, did, u, action, details):
        c.execute('INSERT INTO driver_finance_audit(driver_id,statement_id,actor_id,actor_name,action,details,created_at) VALUES(?,NULL,?,?,?,?,?)',
                  (did, u['id'], u['name'], action, json.dumps(details, ensure_ascii=False), now()))

    def rate_for(c, did, city_id, kind):
        o = c.execute('SELECT delivered_cents,returned_cents,refused_cents FROM driver_city_rates WHERE driver_id=? AND city_id=?', (did, city_id)).fetchone()
        b = o or c.execute('SELECT delivered_cents,returned_cents,refused_cents FROM driver_terms WHERE driver_id=?', (did,)).fetchone()
        if not b:
            return 0
        return {'Livré': b['delivered_cents'], 'Retourné': b['returned_cents'], 'Refusé': b['refused_cents']}.get(kind, 0)

    def calc(c, did, day):
        """Live : livrés du jour, COD brut, commissions (barème à la ville), attendu caisse, dernier état de clôture."""
        rows = c.execute("""SELECT id,city_id,status,amount FROM parcels WHERE driver_id=?
                            AND status IN ('Livré','Retourné','Refusé') AND substr(updated_at,1,10)=?""", (did, day)).fetchall()
        livres = [p for p in rows if p['status'] == 'Livré']
        cod = sum(cents(p['amount']) for p in livres)
        commission = sum(rate_for(c, did, p['city_id'], p['status']) for p in rows)
        terms = c.execute('SELECT mode FROM driver_terms WHERE driver_id=?', (did,)).fetchone()
        mode = terms['mode'] if terms else 'gross'
        expected = max(0, cod - commission) if mode == 'net' else cod
        close = c.execute('SELECT * FROM driver_day_closes WHERE driver_id=? AND day=?', (did, day)).fetchone()
        dr = c.execute('SELECT name FROM users WHERE id=?', (did,)).fetchone()
        return {
            'driver_id': did, 'driver': dr['name'] if dr else ('#' + str(did)), 'day': day,
            'livres': len(livres), 'retournes': sum(1 for p in rows if p['status'] == 'Retourné'),
            'refuses': sum(1 for p in rows if p['status'] == 'Refusé'),
            'cod_cents': cod, 'commission_cents': commission, 'expected_cents': expected,
            'mode': mode, 'barème': bool(terms),
            'close': dict(close) if close else None,
            'closed': bool(close and close['status'] == 'Clôturé'),
            'received_cents': close['received_cents'] if close and close['status'] == 'Clôturé' else None,
            'variance_cents': (expected - close['received_cents']) if close and close['status'] == 'Clôturé' else None,
        }

    def valid_day(raw):
        d = (raw or '').strip()
        try:
            from datetime import date as _date
            day = _date.fromisoformat(d)
        except Exception:
            raise Error('Jour invalide (AAAA-MM-JJ).')
        if day > _date.today():
            raise Error('Impossible de clôturer ou consulter un jour futur.')
        return day.isoformat()

    @app.get('/api/driver-days')
    @auth('admin')
    def driver_days_list():
        day = valid_day((request.args.get('day')) or now()[:10])
        with conn() as c:
            rows = [calc(c, r['id'], day) for r in c.execute("SELECT id FROM users WHERE role='livreur' AND active=1 ORDER BY name")]
        return jsonify(rows)

    @app.get('/api/driver-days/me')
    @auth('livreur')
    def driver_day_me():
        u = user()
        day = valid_day((request.args.get('day')) or now()[:10])
        with conn() as c:
            rows = [calc(c, u['id'], day)]
            for mid in team_member_ids(c, u['id']):
                rows.append(calc(c, mid, day))
        return jsonify(rows)

    @app.post('/api/driver-days')
    @auth('admin')
    def driver_day_close():
        d = request.get_json() or {}
        u = user()
        did = d.get('driver_id')
        if type(did) is not int:
            raise Error('Livreur invalide.')
        day = valid_day(d.get('day'))
        amount = d.get('received_mad')
        try:
            received = int(round(float(amount) * 100))
        except (TypeError, ValueError):
            raise Error('Montant de la remise invalide (MAD).')
        if received < 0 or received > 10000000:
            raise Error('Montant de la remise invalide (0 à 100 000 MAD).')
        reference = text(d, 'reference', False, 90)
        note = text(d, 'note', False, 220)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            dr = c.execute("SELECT id,name FROM users WHERE id=? AND role='livreur' AND active=1", (did,)).fetchone()
            if not dr:
                raise Error('Livreur invalide ou inactif.')
            old = c.execute('SELECT status FROM driver_day_closes WHERE driver_id=? AND day=?', (did, day)).fetchone()
            if old and old['status'] == 'Clôturé':
                raise Error('Journée déjà clôturée pour ce livreur.', 409)
            cur = calc(c, did, day)
            variance = cur['expected_cents'] - received
            common = (cur['livres'], cur['cod_cents'], cur['commission_cents'], cur['expected_cents'], received, variance, cur['mode'])
            if old:
                c.execute('''UPDATE driver_day_closes SET livres=?,cod_cents=?,commission_cents=?,expected_cents=?,received_cents=?,variance_cents=?,mode=?,
                             status='Clôturé',reference=?,note=?,closed_by=?,closed_by_name=?,closed_at=?,reopened_by=NULL,reopen_note=NULL,reopened_at=NULL
                             WHERE driver_id=? AND day=?''', common + (reference or None, note or None, u['id'], u['name'], now(), did, day))
            else:
                c.execute('''INSERT INTO driver_day_closes(livres,cod_cents,commission_cents,expected_cents,received_cents,variance_cents,mode,status,reference,note,closed_by,closed_by_name,closed_at,driver_id,day)
                             VALUES(?,?,?,?,?,?,?,'Clôturé',?,?,?,?,?,?,?)''',
                          common + (reference or None, note or None, u['id'], u['name'], now(), did, day))
            audit(c, did, u, 'Journée clôturée', {'day': day, 'expected_cents': cur['expected_cents'], 'received_cents': received, 'variance_cents': variance})
            return jsonify(calc(c, did, day))

    @app.post('/api/driver-days/<int:close_id>/reopen')
    @auth('admin')
    def driver_day_reopen(close_id):
        d = request.get_json() or {}
        u = user()
        note = text(d, 'note', True, 220)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM driver_day_closes WHERE id=?', (close_id,)).fetchone()
            if not row:
                raise Error('Clôture introuvable.', 404)
            if row['status'] != 'Clôturé':
                raise Error('Journée déjà rouverte.', 409)
            c.execute("UPDATE driver_day_closes SET status='Rouvert',reopened_by=?,reopen_note=?,reopened_at=? WHERE id=?",
                      (u['id'], note, now(), close_id))
            audit(c, row['driver_id'], u, 'Journée rouverte', {'day': row['day'], 'note': note})
        return {'ok': True}
