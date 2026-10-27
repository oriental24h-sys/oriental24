"""v1.5.3 « Fin de journée » (Khatm caisse nhar) : instantané journalier par livreur —
livré du jour, COD, commissions (barème à la ville), attendu caisse, remise Admin, écart,
clôture/réouverture tracées. Module branché dans app.py comme driver_finance."""
import json
from datetime import datetime, date as _date, time as _time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from flask import request, jsonify

MOROCCO_TZ = ZoneInfo("Africa/Casablanca")


def local_day_bounds(day):
    """Convert a Morocco business day to the server-local naive timestamp format used by app.now()."""
    start = datetime.combine(_date.fromisoformat(day), _time.min, tzinfo=MOROCCO_TZ)
    end = datetime.combine(_date.fromisoformat(day) + timedelta(days=1), _time.min, tzinfo=MOROCCO_TZ)
    return (start.astimezone().replace(tzinfo=None).isoformat(timespec='seconds'),
            end.astimezone().replace(tzinfo=None).isoformat(timespec='seconds'))


def register_driver_days(app, services):
    conn, auth, user, now, text, Error, event = (services[k] for k in ('conn', 'auth', 'user', 'now', 'text', 'APIError', 'event'))
    team_member_ids = services['team_member_ids']
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS driver_day_closes(
            id INTEGER PRIMARY KEY, driver_id INTEGER NOT NULL REFERENCES users(id), day TEXT NOT NULL,
            livres INTEGER NOT NULL, retournes INTEGER NOT NULL DEFAULT 0, refuses INTEGER NOT NULL DEFAULT 0,
            cod_cents INTEGER NOT NULL, commission_cents INTEGER NOT NULL,
            expected_cents INTEGER NOT NULL, received_cents INTEGER NOT NULL, variance_cents INTEGER NOT NULL,
            mode TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Clôturé','Rouvert')),
            reference TEXT, note TEXT,
            closed_by INTEGER NOT NULL REFERENCES users(id), closed_by_name TEXT NOT NULL, closed_at TEXT NOT NULL,
            reopened_by INTEGER REFERENCES users(id), reopen_note TEXT, reopened_at TEXT,
            UNIQUE(driver_id, day));''')
        close_columns = {r['name'] for r in c.execute('PRAGMA table_info(driver_day_closes)')}
        if 'retournes' not in close_columns:
            c.execute('ALTER TABLE driver_day_closes ADD COLUMN retournes INTEGER NOT NULL DEFAULT 0')
        if 'refuses' not in close_columns:
            c.execute('ALTER TABLE driver_day_closes ADD COLUMN refuses INTEGER NOT NULL DEFAULT 0')

    def cents(v):
        try:
            if isinstance(v, bool) or v is None:
                return 0
            amount = Decimal(str(v))
            if not amount.is_finite():
                return 0
            return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
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
        day_start, day_end = local_day_bounds(day)
        rows = c.execute("""SELECT id,city_id,status,amount FROM parcels WHERE driver_id=?
                            AND status IN ('Livré','Retourné','Refusé')
                            AND COALESCE(NULLIF(status_updated_at,''),updated_at)>=?
                            AND COALESCE(NULLIF(status_updated_at,''),updated_at)<?""",
                         (did, day_start, day_end)).fetchall()
        livres = [p for p in rows if p['status'] == 'Livré']
        cod = sum(cents(p['amount']) for p in livres)
        commission = sum(rate_for(c, did, p['city_id'], p['status']) for p in rows)
        terms = c.execute('SELECT mode FROM driver_terms WHERE driver_id=?', (did,)).fetchone()
        mode = terms['mode'] if terms else 'gross'
        expected = max(0, cod - commission) if mode == 'net' else cod
        close = c.execute('SELECT * FROM driver_day_closes WHERE driver_id=? AND day=?', (did, day)).fetchone()
        dr = c.execute('SELECT name FROM users WHERE id=?', (did,)).fetchone()
        closed = bool(close and close['status'] == 'Clôturé')
        # Une journée clôturée doit afficher son instantané comptable, pas les colis modifiés après clôture.
        if closed:
            livres_count = close['livres']
            cod = close['cod_cents']
            commission = close['commission_cents']
            expected = close['expected_cents']
            mode = close['mode']
            returned_count = close['retournes'] if 'retournes' in close.keys() else sum(1 for p in rows if p['status'] == 'Retourné')
            refused_count = close['refuses'] if 'refuses' in close.keys() else sum(1 for p in rows if p['status'] == 'Refusé')
        else:
            livres_count = len(livres)
            returned_count = sum(1 for p in rows if p['status'] == 'Retourné')
            refused_count = sum(1 for p in rows if p['status'] == 'Refusé')
        return {
            'driver_id': did, 'driver': dr['name'] if dr else ('#' + str(did)), 'day': day,
            'livres': livres_count, 'retournes': returned_count,
            'refuses': refused_count,
            'cod_cents': cod, 'commission_cents': commission, 'expected_cents': expected,
            'mode': mode, 'barème': bool(terms),
            'close': dict(close) if close else None,
            'closed': closed,
            'received_cents': close['received_cents'] if closed else None,
            'variance_cents': (close['expected_cents'] - close['received_cents']) if closed else None,
        }

    def valid_day(raw):
        d = (raw or '').strip() if isinstance(raw, str) else ''
        try:
            if not __import__('re').fullmatch(r'\d{4}-\d{2}-\d{2}', d):
                raise ValueError()
            day = _date.fromisoformat(d)
        except (TypeError, ValueError):
            raise Error('Jour invalide (AAAA-MM-JJ).')
        if day > datetime.now(MOROCCO_TZ).date():
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
            if isinstance(amount, bool) or amount is None:
                raise ValueError()
            received_decimal = Decimal(str(amount).strip().replace(',', '.'))
            if not received_decimal.is_finite() or received_decimal != received_decimal.quantize(Decimal('.01')):
                raise ValueError()
            received = int((received_decimal * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        except (InvalidOperation, TypeError, ValueError, OverflowError):
            raise Error('Montant de la remise invalide : utilisez MAD avec deux décimales maximum.')
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
            common = (cur['livres'], cur['retournes'], cur['refuses'], cur['cod_cents'], cur['commission_cents'], cur['expected_cents'], received, variance, cur['mode'])
            if old:
                c.execute('''UPDATE driver_day_closes SET livres=?,retournes=?,refuses=?,cod_cents=?,commission_cents=?,expected_cents=?,received_cents=?,variance_cents=?,mode=?,
                             status='Clôturé',reference=?,note=?,closed_by=?,closed_by_name=?,closed_at=?,reopened_by=NULL,reopen_note=NULL,reopened_at=NULL
                             WHERE driver_id=? AND day=?''', common + (reference or None, note or None, u['id'], u['name'], now(), did, day))
            else:
                c.execute('''INSERT INTO driver_day_closes(livres,retournes,refuses,cod_cents,commission_cents,expected_cents,received_cents,variance_cents,mode,status,reference,note,closed_by,closed_by_name,closed_at,driver_id,day)
                             VALUES(?,?,?,?,?,?,?,?,?,'Clôturé',?,?,?,?,?,?,?)''',
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
