"""Driver commission statements and manual cash reconciliation.
Money in this module is represented by integer MAD centimes. No money is transferred.
Issued statements snapshot their terms and parcels. Corrections remain in the audit trail.
"""
import csv
import hashlib
import io
import json
import re
import secrets
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from flask import jsonify, request, Response

from invoice_profile import print_snapshot

PREFIX = '/api/driver-finance'
CLOSED = ('Livré', 'Retourné', 'Refusé')


def register_driver_finance(app, services):
    conn, auth, user, now, text, Error, event = (services[k] for k in ('conn', 'auth', 'user', 'now', 'text', 'APIError', 'event'))
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS driver_terms (
            driver_id INTEGER PRIMARY KEY REFERENCES users(id), mode TEXT NOT NULL CHECK(mode IN ('net','gross')),
            delivered_cents INTEGER NOT NULL CHECK(delivered_cents>=0), returned_cents INTEGER NOT NULL CHECK(returned_cents>=0),
            refused_cents INTEGER NOT NULL CHECK(refused_cents>=0), revision INTEGER NOT NULL,
            updated_by INTEGER NOT NULL REFERENCES users(id), updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS driver_city_rates (
            driver_id INTEGER NOT NULL REFERENCES users(id), city_id INTEGER NOT NULL REFERENCES cities(id),
            delivered_cents INTEGER NOT NULL CHECK(delivered_cents>=0), returned_cents INTEGER NOT NULL CHECK(returned_cents>=0),
            refused_cents INTEGER NOT NULL CHECK(refused_cents>=0), PRIMARY KEY(driver_id,city_id));
        CREATE TABLE IF NOT EXISTS driver_statements (
            id INTEGER PRIMARY KEY, driver_id INTEGER NOT NULL REFERENCES users(id), driver_name TEXT NOT NULL,
            driver_email TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('net','gross')), revision INTEGER NOT NULL,
            period_from TEXT, period_to TEXT, parcel_count INTEGER NOT NULL,
            cod_cents INTEGER NOT NULL, commission_cents INTEGER NOT NULL, retained_cents INTEGER NOT NULL,
            cash_due_cents INTEGER NOT NULL, commission_due_cents INTEGER NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
            cancelled_at TEXT, cancelled_by INTEGER REFERENCES users(id), cancel_reason TEXT);
        CREATE TABLE IF NOT EXISTS driver_statement_lines (
            id INTEGER PRIMARY KEY, statement_id INTEGER NOT NULL REFERENCES driver_statements(id),
            parcel_id INTEGER NOT NULL REFERENCES parcels(id), tracking TEXT NOT NULL, city TEXT NOT NULL,
            status TEXT NOT NULL, cod_cents INTEGER NOT NULL, commission_cents INTEGER NOT NULL,
            rate_source TEXT NOT NULL, closed_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_driver_once ON driver_statement_lines(parcel_id) WHERE active=1;
        CREATE TABLE IF NOT EXISTS driver_statement_previews (
            id TEXT PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES users(id), driver_id INTEGER NOT NULL REFERENCES users(id),
            period_from TEXT, period_to TEXT, fingerprint TEXT NOT NULL, snapshot TEXT NOT NULL,
            created_at TEXT NOT NULL, statement_id INTEGER REFERENCES driver_statements(id));
        CREATE TABLE IF NOT EXISTS driver_transactions (
            id INTEGER PRIMARY KEY, statement_id INTEGER NOT NULL REFERENCES driver_statements(id),
            kind TEXT NOT NULL CHECK(kind IN ('cash','commission')), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
            method TEXT NOT NULL, reference TEXT NOT NULL, ref_key TEXT NOT NULL, paid_on TEXT NOT NULL, note TEXT NOT NULL,
            request_key TEXT NOT NULL UNIQUE, payload_hash TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL, created_at TEXT NOT NULL,
            voided_at TEXT, voided_by INTEGER REFERENCES users(id), void_reason TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_driver_payment_ref ON driver_transactions(statement_id,kind,ref_key) WHERE voided_at IS NULL;
        CREATE TABLE IF NOT EXISTS driver_finance_audit (
            id INTEGER PRIMARY KEY, driver_id INTEGER NOT NULL REFERENCES users(id), statement_id INTEGER REFERENCES driver_statements(id),
            actor_id INTEGER NOT NULL REFERENCES users(id), actor_name TEXT NOT NULL, action TEXT NOT NULL,
            details TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_driver_statements_driver ON driver_statements(driver_id,id);
        CREATE INDEX IF NOT EXISTS idx_driver_tx_statement ON driver_transactions(statement_id);
        ''')

    def cents(value, field='Montant', maximum=1000000000, allow_zero=True):
        try:
            if isinstance(value, bool) or value is None:
                raise ValueError()
            d = Decimal(str(value).strip().replace(',', '.'))
            if not d.is_finite() or d < 0 or d > maximum or d != d.quantize(Decimal('.01')):
                raise ValueError()
            v = int(d*100)
            if not allow_zero and v == 0:
                raise ValueError()
            return v
        except (InvalidOperation, ValueError, TypeError, OverflowError):
            raise Error(f'{field} : montant {"positif" if not allow_zero else "positif ou nul"}, avec deux décimales maximum.')

    def digest(obj):
        return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()

    def payload():
        d = request.get_json()
        if not isinstance(d, dict): raise Error('Objet JSON requis.')
        return d

    def driver(c, did, active=False):
        if isinstance(did, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(did)): raise Error('Livreur invalide.')
        did = int(did)
        row = c.execute("SELECT id,name,email,phone,active FROM users WHERE id=? AND role='livreur'", (did,)).fetchone()
        if not row or (active and not row['active']):
            raise Error('Choisissez un livreur actif.', 400)
        return dict(row)

    def audit(c, did, sid, u, action, details):
        c.execute('INSERT INTO driver_finance_audit(driver_id,statement_id,actor_id,actor_name,action,details,created_at) VALUES(?,?,?,?,?,?,?)',
                  (did, sid, u['id'], u['name'], action, json.dumps(details, ensure_ascii=False), now()))

    def term_data(c, did):
        t = c.execute('SELECT * FROM driver_terms WHERE driver_id=?', (did,)).fetchone()
        if not t:
            return None
        data = dict(t)
        data['overrides'] = [dict(r) for r in c.execute('SELECT r.*,c.name city FROM driver_city_rates r JOIN cities c ON c.id=r.city_id WHERE driver_id=? ORDER BY city_id', (did,))]
        return data

    def check_scope(s, u):
        if not s or (u['role'] == 'livreur' and s['driver_id'] != u['id']):
            raise Error('Relevé introuvable.', 404)

    def statement(c, sid, u):
        s = c.execute('SELECT * FROM driver_statements WHERE id=?', (sid,)).fetchone()
        check_scope(s, u)
        return dict(s)

    def balances(c, s):
        s = dict(s)
        s.pop('print_snapshot', None)  # Large immutable metadata belongs to scoped detail only.
        tx = {r['kind']: r['amount'] for r in c.execute('SELECT kind,SUM(amount_cents) amount FROM driver_transactions WHERE statement_id=? AND voided_at IS NULL GROUP BY kind', (s['id'],))}
        s['cash_received_cents'] = tx.get('cash', 0)
        s['commission_paid_cents'] = tx.get('commission', 0)
        s['cash_remaining_cents'] = 0 if s['cancelled_at'] else s['cash_due_cents']-s['cash_received_cents']
        s['commission_remaining_cents'] = 0 if s['cancelled_at'] else s['commission_due_cents']-s['commission_paid_cents']
        if s['cancelled_at']:
            s['status'] = 'Annulé'
        elif not s['cash_remaining_cents'] and not s['commission_remaining_cents']:
            s['status'] = 'Soldé'
        elif sum(tx.values()):
            s['status'] = 'Partiel'
        else:
            s['status'] = 'À régler'
        s['reference'] = f"DRV-{s['id']:06d}"
        return s

    def parse_period(d):
        values = []
        for key in ('period_from', 'period_to'):
            value = str(d.get(key) or '').strip()
            if value:
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value): raise ValueError()
                    datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    raise Error('Dates invalides pour la période.')
            values.append(value)
        if all(values) and values[0] > values[1]:
            raise Error('La date de début doit précéder la date de fin.')
        return values

    def build_preview(c, did, period_from, period_to):
        dr = driver(c, did)  # Admin may settle historical amounts for blocked/archived accounts.
        terms = term_data(c, dr['id'])
        if not terms:
            raise Error('Configurez et enregistrez le barème de ce livreur avant de générer un relevé.', 409)
        sql = """SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id
            WHERE p.driver_id=? AND p.status IN ('Livré','Retourné','Refusé')
            AND NOT EXISTS(SELECT 1 FROM driver_statement_lines l WHERE l.parcel_id=p.id AND l.active=1)"""
        args = [dr['id']]
        if period_from: sql += ' AND substr(p.updated_at,1,10)>=?'; args.append(period_from)
        if period_to: sql += ' AND substr(p.updated_at,1,10)<=?'; args.append(period_to)
        rows = c.execute(sql+' ORDER BY p.id LIMIT 501', args).fetchall()
        if not rows: raise Error('Aucun colis clôturé non rapproché pour ce livreur et cette période.')
        if len(rows) > 500: raise Error('Plus de 500 colis : réduisez la période pour établir plusieurs relevés.')
        overrides = {r['city_id']: r for r in terms['overrides']}
        lines = []
        for r in rows:
            rate = overrides.get(r['city_id'], terms)
            rate_key = {'Livré':'delivered_cents','Retourné':'returned_cents','Refusé':'refused_cents'}[r['status']]
            lines.append({'parcel_id':r['id'], 'tracking':r['tracking'], 'city':r['city'], 'status':r['status'],
                          'cod_cents':cents(r['amount'], 'COD') if r['status']=='Livré' else 0,
                          'commission_cents':rate[rate_key], 'rate_source':'Ville' if r['city_id'] in overrides else 'Défaut livreur',
                          'closed_at':r['updated_at']})
        cod, commission = sum(r['cod_cents'] for r in lines), sum(r['commission_cents'] for r in lines)
        retained = min(cod, commission) if terms['mode']=='net' else 0
        data = {'driver_id':dr['id'], 'driver_name':dr['name'], 'driver_email':dr['email'], 'mode':terms['mode'],
                'revision':terms['revision'], 'period_from':period_from, 'period_to':period_to,
                'parcel_count':len(lines), 'cod_cents':cod, 'commission_cents':commission, 'retained_cents':retained,
                'cash_due_cents':cod-retained, 'commission_due_cents':commission-retained, 'lines':lines, 'print_snapshot':print_snapshot(c,dr['id'],rows)}
        return data

    @app.get(PREFIX+'/terms')
    @auth('admin', 'livreur')
    def get_terms():
        u = user()
        with conn() as c:
            sql = "SELECT id,name,email,phone,active FROM users WHERE role='livreur'"
            args = []
            if u['role']=='livreur': sql += ' AND id=?'; args.append(u['id'])
            drivers = []
            for row in c.execute(sql+' ORDER BY name', args).fetchall():
                drivers.append({**dict(row), 'terms':term_data(c, row['id'])})
            return jsonify(drivers)

    @app.put(PREFIX+'/terms/<int:did>')
    @auth('admin')
    def save_terms(did):
        u = user(); d = payload(); mode = d.get('mode')
        if mode not in ('net','gross'): raise Error('Choisissez une méthode de règlement.')
        defaults = [cents(d.get(k), 'Commission '+label, maximum=10000) for k,label in [('delivered','livré'),('returned','retourné'),('refused','refusé')]]
        overrides = d.get('overrides', [])
        if not isinstance(overrides,list) or len(overrides)>500: raise Error('Liste des exceptions par ville invalide.')
        revision = d.get('revision')
        if type(revision) is not int or revision < 0: raise Error('Version du barème manquante. Rechargez la page.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            driver(c, did)
            old = term_data(c, did)
            if revision != (old['revision'] if old else 0): raise Error('Ce barème a changé. Rechargez-le avant de modifier.', 409)
            seen = set(); rate_rows = []
            for r in overrides:
                if not isinstance(r,dict): raise Error('Exception de ville invalide.')
                cid = r.get('city_id')
                if type(cid) is not int or cid in seen or not c.execute('SELECT id FROM cities WHERE id=?',(cid,)).fetchone():
                    raise Error('Ville inconnue ou répétée dans les exceptions.')
                seen.add(cid)
                amounts = [cents(r.get(k), 'Commission par ville', maximum=10000) for k in ('delivered','returned','refused')]
                rate_rows.append((did, cid, *amounts))
            c.execute('''INSERT INTO driver_terms(driver_id,mode,delivered_cents,returned_cents,refused_cents,revision,updated_by,updated_at)
                VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(driver_id) DO UPDATE SET mode=excluded.mode,delivered_cents=excluded.delivered_cents,
                returned_cents=excluded.returned_cents,refused_cents=excluded.refused_cents,revision=excluded.revision,updated_by=excluded.updated_by,updated_at=excluded.updated_at''',
                      (did, mode, *defaults, revision+1, u['id'], now()))
            c.execute('DELETE FROM driver_city_rates WHERE driver_id=?', (did,))
            c.executemany('INSERT INTO driver_city_rates(driver_id,city_id,delivered_cents,returned_cents,refused_cents) VALUES(?,?,?,?,?)', rate_rows)
            new = term_data(c, did)
            audit(c, did, None, u, 'Barème enregistré', {'before':old,'after':new})
        return jsonify(ok=True, revision=revision+1)

    @app.get(PREFIX+'/terms/<int:did>/history')
    @auth('admin', 'livreur')
    def terms_history(did):
        u = user()
        if u['role']=='livreur' and did!=u['id']: raise Error('Barème introuvable.',404)
        with conn() as c:
            driver(c, did)
            rows = c.execute('SELECT * FROM driver_finance_audit WHERE driver_id=? AND statement_id IS NULL ORDER BY id DESC LIMIT 100',(did,))
            return jsonify([{**dict(r),'details':json.loads(r['details'])} for r in rows])

    @app.get(PREFIX)
    @auth('admin', 'livreur')
    def overview():
        u=user(); cond,args=('1=1',[]) if u['role']=='admin' else ('s.driver_id=?',[u['id']])
        with conn() as c:
            c.execute('BEGIN')
            rows = c.execute(f'SELECT s.* FROM driver_statements s WHERE {cond} ORDER BY s.id DESC',args).fetchall()
            statements=[balances(c,r) for r in rows]
            active=[r for r in statements if not r['cancelled_at']]
            summary={k:sum(r[k] for r in active) for k in ('cod_cents','commission_cents','cash_remaining_cents','commission_remaining_cents','retained_cents')}
            txs = c.execute(f'''SELECT t.*,s.driver_id,s.driver_name FROM driver_transactions t JOIN driver_statements s ON s.id=t.statement_id
                WHERE {cond} ORDER BY t.id DESC LIMIT 500''', args).fetchall()
            return jsonify(statements=statements,summary=summary,transactions=[dict(r) for r in txs])

    @app.post(PREFIX+'/preview')
    @auth('admin')
    def preview():
        d=payload(); u=user(); start,end=parse_period(d)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            snapshot=build_preview(c,d.get('driver_id'),start,end)
            token=secrets.token_hex(16)
            c.execute('INSERT INTO driver_statement_previews(id,owner_id,driver_id,period_from,period_to,fingerprint,snapshot,created_at) VALUES(?,?,?,?,?,?,?,?)',
                      (token,u['id'],snapshot['driver_id'],start,end,digest(snapshot),json.dumps(snapshot,ensure_ascii=False),now()))
            return jsonify(token=token,**snapshot)

    @app.post(PREFIX+'/preview/<token>/confirm')
    @auth('admin')
    def confirm(token):
        u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            draft=c.execute('SELECT * FROM driver_statement_previews WHERE id=? AND owner_id=?',(token,u['id'])).fetchone()
            if not draft: raise Error('Prévisualisation introuvable.',404)
            if draft['statement_id']:
                return jsonify(ok=True,already_created=True,statement_id=draft['statement_id'])
            if datetime.fromisoformat(draft['created_at'])<datetime.now()-timedelta(minutes=30):
                raise Error('Prévisualisation expirée. Générez un nouvel aperçu.',409)
            snapshot=build_preview(c,draft['driver_id'],draft['period_from'],draft['period_to'])
            if digest(snapshot)!=draft['fingerprint']:
                raise Error('Les colis, le barème ou les coordonnées ont changé. Vérifiez un nouvel aperçu avant de confirmer.',409)
            keys=('driver_id','driver_name','driver_email','mode','revision','period_from','period_to','parcel_count','cod_cents','commission_cents','retained_cents','cash_due_cents','commission_due_cents')
            cur=c.execute(f'INSERT INTO driver_statements({",".join(keys)},created_by,created_at) VALUES({",".join("?" for _ in range(len(keys)+2))})',
                          [snapshot[k] for k in keys]+[u['id'],now()])
            sid=cur.lastrowid
            c.execute('UPDATE driver_statements SET print_snapshot=? WHERE id=?',(json.dumps(snapshot['print_snapshot'],ensure_ascii=False),sid))
            for row in snapshot['lines']:
                c.execute('INSERT INTO driver_statement_lines(statement_id,parcel_id,tracking,city,status,cod_cents,commission_cents,rate_source,closed_at) VALUES(?,?,?,?,?,?,?,?,?)',
                          (sid,*(row[k] for k in ('parcel_id','tracking','city','status','cod_cents','commission_cents','rate_source','closed_at'))))
                event(c,row['parcel_id'],row['status'],f'Relevé livreur DRV-{sid:06d} émis — colis verrouillé',u)
            c.execute('UPDATE driver_statement_previews SET statement_id=? WHERE id=?',(sid,token))
            audit(c,snapshot['driver_id'],sid,u,'Relevé émis',{'cod_cents':snapshot['cod_cents'],'commission_cents':snapshot['commission_cents'],'mode':snapshot['mode'],'revision':snapshot['revision']})
            return jsonify(ok=True,already_created=False,statement_id=sid)

    @app.get(PREFIX+'/statements/<int:sid>')
    @auth('admin', 'livreur')
    def get_statement(sid):
        with conn() as c:
            c.execute('BEGIN')
            raw=statement(c,sid,user())
            printing=json.loads(raw['print_snapshot']) if raw.get('print_snapshot') else None
            s=balances(c,raw)
            lines=[dict(r) for r in c.execute('SELECT * FROM driver_statement_lines WHERE statement_id=? ORDER BY id',(sid,))]
            tx=[dict(r) for r in c.execute('SELECT * FROM driver_transactions WHERE statement_id=? ORDER BY id DESC',(sid,))]
            log=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT * FROM driver_finance_audit WHERE statement_id=? ORDER BY id DESC',(sid,))]
            return jsonify(statement=s,lines=lines,transactions=tx,audit=log,print_snapshot=printing)

    def add_transaction(c,sid,u,d):
        key=text(d,'request_key',maxlen=80)
        if not re.fullmatch('[A-Za-z0-9_-]{20,80}',key): raise Error('Identifiant de saisie invalide. Rouvrez le formulaire.')
        kind=d.get('kind');method=d.get('method')
        if kind not in ('cash','commission'): raise Error('Type de mouvement invalide.')
        if method not in ('Espèces','Virement','Chèque'): raise Error('Mode de paiement invalide.')
        amount=cents(d.get('amount'),allow_zero=False)
        reference=text(d,'reference',maxlen=100);note=text(d,'note',False,600);paid_on=text(d,'paid_on',maxlen=10)
        try:
            day=datetime.strptime(paid_on,'%Y-%m-%d').date()
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',paid_on) or day>datetime.now(ZoneInfo('Africa/Casablanca')).date(): raise ValueError()
        except ValueError: raise Error('La date du règlement doit être valide et ne peut pas être future.')
        tx_payload={'statement_id':sid,'kind':kind,'amount_cents':amount,'method':method,'reference':reference,'note':note,'paid_on':paid_on}
        hashed=digest(tx_payload)
        prior=c.execute('SELECT * FROM driver_transactions WHERE request_key=?',(key,)).fetchone()
        if prior:
            if prior['payload_hash']!=hashed or prior['created_by']!=u['id']: raise Error('Cette clé de saisie a déjà été utilisée pour une autre opération.',409)
            return dict(ok=True,already_recorded=True,transaction_id=prior['id'],voided=bool(prior['voided_at']))
        s=balances(c,statement(c,sid,u))
        if s['cancelled_at']: raise Error('Ce relevé est annulé.',409)
        remaining=s['cash_remaining_cents'] if kind=='cash' else s['commission_remaining_cents']
        if amount>remaining: raise Error('Le montant dépasse le solde restant pour ce flux. Rechargez le relevé.',409)
        if c.execute('SELECT 1 FROM driver_transactions WHERE statement_id=? AND kind=? AND ref_key=? AND voided_at IS NULL',(sid,kind,reference.casefold())).fetchone():
            raise Error('Cette référence de règlement existe déjà pour ce flux et ce relevé.',409)
        cur=c.execute('INSERT INTO driver_transactions(statement_id,kind,amount_cents,method,reference,ref_key,paid_on,note,request_key,payload_hash,created_by,actor_name,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (sid,kind,amount,method,reference,reference.casefold(),paid_on,note,key,hashed,u['id'],u['name'],now()))
        audit(c,s['driver_id'],sid,u,'Remise COD enregistrée' if kind=='cash' else 'Commission payée',{'transaction_id':cur.lastrowid,**tx_payload})
        return dict(ok=True,already_recorded=False,transaction_id=cur.lastrowid)

    services['driver_finance_statement']=statement
    services['driver_finance_balances']=balances
    services['add_driver_transaction']=add_transaction

    @app.post(PREFIX+'/statements/<int:sid>/transactions')
    @auth('admin')
    def record_transaction(sid):
        d=payload();u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            return jsonify(add_transaction(c,sid,u,d))

    def void_driver_transaction(c,tid,u,reason):
        t=c.execute('SELECT * FROM driver_transactions WHERE id=?',(tid,)).fetchone()
        if not t: raise Error('Écriture introuvable.',404)
        if t['voided_at']: raise Error('Cette écriture est déjà annulée.',409)
        s=statement(c,t['statement_id'],u)
        if s['cancelled_at']: raise Error('Ce relevé est annulé.',409)
        c.execute('UPDATE driver_transactions SET voided_at=?,voided_by=?,void_reason=? WHERE id=?',(now(),u['id'],reason,tid))
        audit(c,s['driver_id'],s['id'],u,'Écriture annulée',{'transaction_id':tid,'kind':t['kind'],'amount_cents':t['amount_cents'],'reason':reason})
        return dict(ok=True)
    services['void_driver_transaction']=void_driver_transaction

    @app.post(PREFIX+'/transactions/<int:tid>/void')
    @auth('admin')
    def void_transaction(tid):
        d=payload();reason=text(d,'reason',maxlen=600);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            return jsonify(void_driver_transaction(c,tid,u,reason))

    @app.post(PREFIX+'/statements/<int:sid>/cancel')
    @auth('admin')
    def cancel_statement(sid):
        d=payload();reason=text(d,'reason',maxlen=600);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            s=statement(c,sid,u)
            if s['cancelled_at']: raise Error('Ce relevé est déjà annulé.',409)
            if c.execute('SELECT 1 FROM driver_transactions WHERE statement_id=? AND voided_at IS NULL',(sid,)).fetchone():
                raise Error('Annulez et justifiez d’abord les écritures actives de ce relevé.',409)
            c.execute('UPDATE driver_statements SET cancelled_at=?,cancelled_by=?,cancel_reason=? WHERE id=?',(now(),u['id'],reason,sid))
            c.execute('UPDATE driver_statement_lines SET active=0 WHERE statement_id=?',(sid,))
            audit(c,s['driver_id'],sid,u,'Relevé annulé',{'reason':reason})
            for row in c.execute('SELECT parcel_id FROM driver_statement_lines WHERE statement_id=?',(sid,)).fetchall():
                current=c.execute('SELECT status FROM parcels WHERE id=?',(row['parcel_id'],)).fetchone()
                event(c,row['parcel_id'],current['status'],f'Relevé livreur DRV-{sid:06d} annulé — verrou du relevé libéré',u)
        return jsonify(ok=True)

    @app.get(PREFIX+'/export')
    @auth('admin', 'livreur')
    def export_statements():
        u=user();args=[];sql='SELECT * FROM driver_statements'
        if u['role']=='livreur':sql+=' WHERE driver_id=?';args=[u['id']]
        output=io.StringIO();w=csv.writer(output,delimiter=';')
        w.writerow(['Relevé','Livreur','Méthode','COD MAD','Commission MAD','Retenue MAD','COD restant MAD','Commission restante MAD','Statut','Émis le'])
        def amount(v):return f'{Decimal(v)/100:.2f}'
        def safe(v):
            v=str(v or '')
            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        with conn() as c:
            c.execute('BEGIN')
            for row in c.execute(sql+' ORDER BY id DESC',args).fetchall():
                s=balances(c,row)
                w.writerow([s['reference'],safe(s['driver_name']),s['mode'],*(amount(s[k]) for k in ('cod_cents','commission_cents','retained_cents','cash_remaining_cents','commission_remaining_cents')),s['status'],s['created_at']])
        return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="ORIENTAL24-caisse-livreurs.csv"'})
