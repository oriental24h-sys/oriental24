"""Hub commission statements, separate from legacy gross-COD invoices.
Immutable snapshots; Admin-defined rates and daily schedule; no automatic payment.
"""
import csv
import hashlib
import io
import json
import os
import re
import threading
from datetime import datetime, timedelta, date
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo
from flask import jsonify, request, Response
from hub_access import driver_financial_hub_sql
from invoice_profile import issuer_for_actor, hub_identity

TZ = ZoneInfo('Africa/Casablanca')


def local_now():
    return datetime.now(TZ)


def next_due(clock, after):
    h, m = map(int, clock.split(':'))
    due = after.astimezone(TZ).replace(hour=h, minute=m, second=0, microsecond=0)
    if due <= after:
        due = (due + timedelta(days=1)).replace(hour=h, minute=m)
    return due


def amount_cents(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('Montant obligatoire, de 0 à 10 000 MAD avec deux décimales maximum.')
    try:
        n = Decimal(str(value).replace(',', '.'))
        if not n.is_finite() or not 0 <= n <= 10000 or n * 100 != (n * 100).to_integral_value():
            raise ValueError()
        return int(n * 100)
    except (InvalidOperation, ValueError):
        raise ValueError('Montant invalide : de 0 à 10 000 MAD, deux décimales maximum.')


def ensure_schema(c):
    c.executescript('''
    CREATE TABLE IF NOT EXISTS hub_billing_terms(
        hub_id INTEGER PRIMARY KEY REFERENCES ops_hubs(id),
        mode TEXT NOT NULL CHECK(mode IN ('net','gross')),
        delivered_cents INTEGER NOT NULL CHECK(delivered_cents>=0),
        returned_cents INTEGER NOT NULL CHECK(returned_cents>=0),
        refused_cents INTEGER NOT NULL CHECK(refused_cents>=0),
        revision INTEGER NOT NULL,updated_by INTEGER NOT NULL REFERENCES users(id),updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hub_billing_city_config(
        hub_id INTEGER PRIMARY KEY REFERENCES ops_hubs(id));
    CREATE TABLE IF NOT EXISTS hub_billing_city_terms(
        hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),city_id INTEGER NOT NULL REFERENCES cities(id),
        delivered_cents INTEGER NOT NULL CHECK(delivered_cents>=0),
        returned_cents INTEGER NOT NULL CHECK(returned_cents>=0),
        refused_cents INTEGER NOT NULL CHECK(refused_cents>=0),
        revision INTEGER NOT NULL,updated_by INTEGER NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(hub_id,city_id));
    CREATE TABLE IF NOT EXISTS hub_billing_schedule(
        id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,
        time TEXT NOT NULL DEFAULT '23:59',revision INTEGER NOT NULL DEFAULT 0,
        next_run TEXT,last_run TEXT,last_error TEXT NOT NULL DEFAULT '',updated_by INTEGER,updated_at TEXT);
    INSERT OR IGNORE INTO hub_billing_schedule(id) VALUES(1);
    CREATE TABLE IF NOT EXISTS hub_billing_runs(
        id INTEGER PRIMARY KEY,run_key TEXT NOT NULL UNIQUE,cutoff TEXT NOT NULL,
        automatic INTEGER NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,result TEXT NOT NULL,fingerprint TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hub_billing_statements(
        id INTEGER PRIMARY KEY,hub_id INTEGER NOT NULL REFERENCES ops_hubs(id),hub_name TEXT NOT NULL,
        run_id INTEGER NOT NULL REFERENCES hub_billing_runs(id),cutoff TEXT NOT NULL,
        mode TEXT NOT NULL,terms_revision INTEGER NOT NULL,parcel_count INTEGER NOT NULL,
        cod_cents INTEGER NOT NULL,commission_cents INTEGER NOT NULL,retained_cents INTEGER NOT NULL,
        cash_due_cents INTEGER NOT NULL,commission_due_cents INTEGER NOT NULL,
        created_by INTEGER NOT NULL,created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hub_billing_lines(
        id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL REFERENCES hub_billing_statements(id),
        parcel_id INTEGER NOT NULL UNIQUE REFERENCES parcels(id),tracking TEXT NOT NULL,
        city TEXT NOT NULL,status TEXT NOT NULL,cod_cents INTEGER NOT NULL,
        commission_cents INTEGER NOT NULL,closed_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hub_billing_print_snapshots(
        statement_id INTEGER PRIMARY KEY REFERENCES hub_billing_statements(id),payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS hub_billing_receipts(
        id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL UNIQUE REFERENCES hub_billing_statements(id),
        amount_cents INTEGER NOT NULL CHECK(amount_cents>0),method TEXT NOT NULL,
        reference TEXT NOT NULL,paid_on TEXT NOT NULL,created_by INTEGER NOT NULL REFERENCES users(id),
        actor_name TEXT NOT NULL,created_at TEXT NOT NULL,request_key TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL);
    CREATE TRIGGER IF NOT EXISTS hub_billing_receipts_full_amount BEFORE INSERT ON hub_billing_receipts
    WHEN NEW.amount_cents IS NOT (SELECT cash_due_cents FROM hub_billing_statements WHERE id=NEW.statement_id)
    BEGIN SELECT RAISE(ABORT,'Full invoice amount required'); END;
    CREATE INDEX IF NOT EXISTS hub_billing_statements_hub ON hub_billing_statements(hub_id,id);
    ''')
    for table in ('hub_billing_statements', 'hub_billing_lines', 'hub_billing_runs', 'hub_billing_print_snapshots', 'hub_billing_receipts'):
        c.executescript(f'''
        CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
        BEGIN SELECT RAISE(ABORT,'{table} is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
        BEGIN SELECT RAISE(ABORT,'{table} is immutable'); END;
        ''')


def billing_cities(c,hid):
    if 'hub_id' not in {r['name'] for r in c.execute('PRAGMA table_info(cities)')}:return []
    return [dict(r) for r in c.execute("""SELECT ci.id,ci.name,t.delivered_cents,t.returned_cents,t.refused_cents,t.revision
        FROM cities ci LEFT JOIN hub_billing_city_terms t ON t.city_id=ci.id AND t.hub_id=?
        WHERE ci.hub_id=? ORDER BY ci.name,ci.id""",(hid,hid))]


def candidates(c, cutoff):
    # Physical routing/destination city is NOT evidence of a closing operation.
    # Use the recorded closing attempt or courier handoff Hub, just like driver finance.
    # Parcel timestamps use app.now(): naive SERVER-local time, not Morocco wall time.
    cutoff = cutoff.astimezone().replace(tzinfo=None).isoformat(timespec='seconds')
    return [dict(r) for r in c.execute(f'''
        SELECT p.id,p.tracking,p.status,p.amount,p.city_id,ci.name city,
            COALESCE(NULLIF(p.status_updated_at,''),NULLIF(p.updated_at,''),p.created_at) closed_at,
            {driver_financial_hub_sql()} hub_id
        FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id
        WHERE p.status IN ('Livré','Retourné','Refusé')
          AND julianday(COALESCE(NULLIF(p.status_updated_at,''),NULLIF(p.updated_at,''),p.created_at))<=julianday(?)
          AND NOT EXISTS(SELECT 1 FROM hub_billing_lines l WHERE l.parcel_id=p.id)
        ORDER BY p.id''', (cutoff,))]


def statement_summary(row, receipt=None):
    d = dict(row)
    d['reference'] = 'HUB-%06d' % d['id']
    d['state'] = 'Paid' if receipt else 'Not Paid' if d['cash_due_cents'] else 'Solde nul'
    d['paid_cents'] = receipt['amount_cents'] if receipt else 0
    d['cash_remaining_cents'] = d['cash_due_cents']-d['paid_cents']
    d['paid_on'] = receipt['paid_on'] if receipt else None
    d['updated_at'] = receipt['created_at'] if receipt else d['created_at']
    return d


def preview(c, cutoff, hub_id=None):
    terms = {r['hub_id']: dict(r) for r in c.execute('SELECT * FROM hub_billing_terms')}
    hubs = {r['id']: dict(r) for r in c.execute('SELECT id,name,active FROM ops_hubs')}
    grouped = {}
    city_mode={r[0] for r in c.execute('SELECT hub_id FROM hub_billing_city_config')}
    city_terms={(r['hub_id'],r['city_id']):dict(r) for r in c.execute('SELECT * FROM hub_billing_city_terms')}
    missing_cities={}
    missing, unknown = set(), 0
    for p in candidates(c, cutoff):
        hid = p['hub_id']
        if hub_id is not None and hid != hub_id:
            continue
        if hid not in hubs or not hubs[hid]['active']:
            unknown += 1
            continue
        if hid not in terms:
            missing.add(hid)
            continue
        t = terms[hid]
        rate=city_terms.get((hid,p['city_id'])) if hid in city_mode else t
        if rate is None:
            missing_cities[(hid,p['city_id'])]=dict(hub_id=hid,hub_name=hubs[hid]['name'],city_id=p['city_id'],city=p['city'] or 'Ville inconnue')
            continue
        key = {'Livré': 'delivered_cents', 'Retourné': 'returned_cents', 'Refusé': 'refused_cents'}[p['status']]
        cod = int((Decimal(str(p['amount'])) * 100).quantize(Decimal('1'))) if p['status'] == 'Livré' else 0
        if cod < 0:
            raise ValueError('COD négatif : vérifiez la commande '+p['tracking'])
        g = grouped.setdefault(hid, dict(hub_id=hid, hub_name=hubs[hid]['name'], mode=t['mode'],
                                         terms_revision=t['revision'], lines=[]))
        g['lines'].append(dict(parcel_id=p['id'], tracking=p['tracking'], city=p['city'] or '',
                               status=p['status'], cod_cents=cod, commission_cents=rate[key], closed_at=p['closed_at']))
    for g in grouped.values():
        g['parcel_count'] = len(g['lines'])
        g['cod_cents'] = sum(l['cod_cents'] for l in g['lines'])
        g['commission_cents'] = sum(l['commission_cents'] for l in g['lines'])
        g['retained_cents'] = min(g['cod_cents'], g['commission_cents']) if g['mode'] == 'net' else 0
        g['cash_due_cents'] = g['cod_cents'] - g['retained_cents']
        g['commission_due_cents'] = g['commission_cents'] - g['retained_cents']
    data = dict(hubs=list(grouped.values()), missing_terms=[hubs[h] for h in sorted(missing)],
                unassigned_count=unknown, missing_city_terms=list(missing_cities.values()), cutoff=cutoff.isoformat())
    data['snapshot'] = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    return data


def generate(c, cutoff, actor_id, run_key, automatic=False, expected=None, hub_id=None):
    """Caller holds BEGIN IMMEDIATE. Entire run + all Hub invoices commit together."""
    fingerprint_payload=[cutoff.isoformat(),actor_id,automatic,expected]
    if hub_id is not None:fingerprint_payload.append(hub_id)
    fingerprint=hashlib.sha256(json.dumps(fingerprint_payload,sort_keys=True).encode()).hexdigest()
    prior = c.execute('SELECT * FROM hub_billing_runs WHERE run_key=?', (run_key,)).fetchone()
    if prior:
        if prior['fingerprint']!=fingerprint:raise ValueError('Clé déjà utilisée pour une autre génération.')
        return {**json.loads(prior['result']), 'statement_ids':[r[0] for r in c.execute('SELECT id FROM hub_billing_statements WHERE run_id=?',(prior['id'],))], 'replayed': True}
    data = preview(c, cutoff, hub_id=hub_id)
    if expected is not None and data['snapshot'] != expected:
        raise ValueError('Les commandes ou les barèmes ont changé. Rechargez la prévisualisation.')
    at = local_now().isoformat(timespec='seconds')
    run_id = c.execute('INSERT INTO hub_billing_runs(run_key,cutoff,automatic,created_by,created_at,result,fingerprint) VALUES(?,?,?,?,?,?,?)',
                       (run_key, cutoff.isoformat(), int(automatic), actor_id, at,
                        json.dumps(dict(cutoff=data['cutoff'], count=len(data['hubs']),
                                        missing_terms=data['missing_terms'], missing_city_terms=data['missing_city_terms'], unassigned_count=data['unassigned_count'])),fingerprint)).lastrowid
    ids = []
    for g in data['hubs']:
        keys = ('hub_id','hub_name','mode','terms_revision','parcel_count','cod_cents','commission_cents',
                'retained_cents','cash_due_cents','commission_due_cents')
        sid = c.execute('INSERT INTO hub_billing_statements('+','.join(keys)+',run_id,cutoff,created_by,created_at) VALUES('+','.join('?'*14)+')',
                        [g[k] for k in keys]+[run_id,cutoff.isoformat(),actor_id,at]).lastrowid
        actor_row=c.execute('SELECT * FROM users WHERE id=?',(actor_id,)).fetchone()
        actor=dict(actor_row) if actor_row else {}
        printing=dict(issuer=issuer_for_actor(c,actor),recipient=hub_identity(c,g['hub_id']),
                      established_by=actor.get('name',''))
        c.execute('INSERT INTO hub_billing_print_snapshots VALUES(?,?)',(sid,json.dumps(printing,ensure_ascii=False)))
        ids.append(sid)
        c.executemany('''INSERT INTO hub_billing_lines(statement_id,parcel_id,tracking,city,status,cod_cents,commission_cents,closed_at)
                         VALUES(?,?,?,?,?,?,?,?)''',
                      [(sid, l['parcel_id'], l['tracking'], l['city'], l['status'], l['cod_cents'], l['commission_cents'], l['closed_at']) for l in g['lines']])
    return dict(count=len(ids), statement_ids=ids, missing_terms=data['missing_terms'], missing_city_terms=data['missing_city_terms'], unassigned_count=data['unassigned_count'])


def scheduled_tick(conn, at=None):
    at = at or local_now()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        cfg = dict(c.execute('SELECT * FROM hub_billing_schedule WHERE id=1').fetchone())
        if not cfg['enabled'] or not cfg['next_run'] or datetime.fromisoformat(cfg['next_run']) > at:
            return None
        due = datetime.fromisoformat(cfg['next_run'])
        # A disabled/deleted Admin must not keep authorizing scheduled money snapshots.
        actor = c.execute("SELECT id FROM users WHERE id=? AND role='admin' AND active=1", (cfg['updated_by'],)).fetchone()
        if not actor:
            c.execute("UPDATE hub_billing_schedule SET last_error='Admin configurateur inactif : réenregistrez le planning.' WHERE id=1")
            return None
        result = generate(c, due, actor['id'], 'scheduled:'+due.isoformat(), automatic=True)
        c.execute("UPDATE hub_billing_schedule SET next_run=?,last_run=?,last_error='' WHERE id=1",
                  (next_due(cfg['time'], due+timedelta(seconds=1)).isoformat(), at.isoformat()))
        return result


def register_hub_billing(app, s):
    conn, auth, user, Error = (s[k] for k in ('conn','auth','user','APIError'))
    with conn() as c:
        ensure_schema(c)

    def manager(c, u):
        if u['role'] == 'hub_manager':
            h = c.execute('SELECT id,name FROM ops_hubs WHERE id=? AND active=1', (u.get('agent_hub_id'),)).fetchone()
            if not h:
                raise Error('Hub actif requis.',403)
            return dict(h)
        return None

    def detail(c, sid, u):
        h = manager(c,u)
        row = c.execute('SELECT * FROM hub_billing_statements WHERE id=?'+(' AND hub_id=?' if h else ''),
                        [sid]+([h['id']] if h else [])).fetchone()
        if not row:
            raise Error('Facture introuvable.',404)
        receipt=c.execute('SELECT * FROM hub_billing_receipts WHERE statement_id=?',(sid,)).fetchone()
        return dict(invoice=statement_summary(row,receipt),receipt={k:receipt[k] for k in ('id','statement_id','amount_cents','method','reference','paid_on','created_by','actor_name','created_at')} if receipt else None, lines=[dict(r) for r in c.execute('SELECT * FROM hub_billing_lines WHERE statement_id=? ORDER BY id',(sid,))])

    @app.get('/api/hub-billing')
    @auth('admin','hub_manager')
    def hub_billing_list():
        u = user()
        with conn() as c:
            h = manager(c,u)
            rows = c.execute('SELECT * FROM hub_billing_statements'+(' WHERE hub_id=?' if h else '')+' ORDER BY id DESC LIMIT 500', [h['id']] if h else []).fetchall()
            result = dict(hub=h, rows=[statement_summary(r,c.execute('SELECT * FROM hub_billing_receipts WHERE statement_id=?',(r['id'],)).fetchone()) for r in rows], read_only=True)
            if u['role']=='admin':
                result['hubs'] = [dict(r) for r in c.execute('SELECT h.id,h.name,h.active,t.mode,t.delivered_cents,t.returned_cents,t.refused_cents,t.revision FROM ops_hubs h LEFT JOIN hub_billing_terms t ON t.hub_id=h.id ORDER BY h.name')]
                for hub in result['hubs']:
                    hub['cities']=billing_cities(c,hub['id'])
                    hub['city_mode']=bool(c.execute('SELECT 1 FROM hub_billing_city_config WHERE hub_id=?',(hub['id'],)).fetchone())
                result['schedule'] = dict(c.execute('SELECT * FROM hub_billing_schedule WHERE id=1').fetchone())
                result['scheduler_running'] = bool(app.extensions.get('hub_billing_scheduler'))
                last = c.execute('SELECT result FROM hub_billing_runs WHERE automatic=1 ORDER BY id DESC LIMIT 1').fetchone()
                result['last_automatic_result'] = json.loads(last['result']) if last else None
            return jsonify(result)

    @app.get('/api/hub-billing/<int:sid>')
    @auth('admin','hub_manager')
    def hub_billing_detail(sid):
        with conn() as c:
            return jsonify(detail(c,sid,user()))

    @app.post('/api/hub-billing/<int:sid>/paid')
    @auth('admin')
    def hub_billing_paid(sid):
        d=request.get_json(silent=True);u=user()
        required={'amount_cents','method','reference','paid_on','request_key','confirmed'}
        if not isinstance(d,dict) or set(d)!=required or d.get('confirmed') is not True:
            raise Error('Confirmez la réception réelle du montant intégral de la facture.')
        if type(d['amount_cents']) is not int or d['amount_cents']<=0:
            raise Error('Montant intégral obligatoire ; aucun paiement partiel.')
        if d['method'] not in ('Espèces','Virement','Chèque'):
            raise Error('Mode de règlement invalide.')
        if not isinstance(d['reference'],str) or not 1<=len(d['reference'].strip())<=100 or any(ord(ch)<32 for ch in d['reference']):
            raise Error('Référence du règlement obligatoire (100 caractères maximum).')
        if not isinstance(d['request_key'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',d['request_key']):
            raise Error('Identifiant de confirmation invalide.')
        try:
            if not isinstance(d['paid_on'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d['paid_on']) or date.fromisoformat(d['paid_on'])>local_now().date():raise ValueError()
        except ValueError:raise Error('Date du règlement invalide ou future.')
        d={**d,'reference':d['reference'].strip()}
        hashed=hashlib.sha256(json.dumps([sid,u['id'],d],sort_keys=True).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            invoice=detail(c,sid,u)['invoice']
            prior=c.execute('SELECT * FROM hub_billing_receipts WHERE request_key=?',(d['request_key'],)).fetchone()
            if prior:
                if prior['payload_hash']!=hashed:raise Error('Clé déjà utilisée pour un autre règlement.',409)
                return jsonify(ok=True,already_recorded=True,invoice=invoice)
            if invoice['state']=='Paid':raise Error('Cette facture est déjà Paid. Aucun double règlement.',409)
            if d['amount_cents']!=invoice['cash_due_cents']:
                raise Error('Le montant doit correspondre exactement au montant à remettre. Aucun paiement partiel.',409)
            c.execute('''INSERT INTO hub_billing_receipts(statement_id,amount_cents,method,reference,paid_on,
                created_by,actor_name,created_at,request_key,payload_hash) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (sid,d['amount_cents'],d['method'],d['reference'],d['paid_on'],u['id'],u['name'],s['now'](),d['request_key'],hashed))
            s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='hub_invoice_paid',entity_type='hub_invoice',entity_id=sid,
                old_value=dict(state=invoice['state'],cash_remaining_cents=invoice['cash_remaining_cents']),
                new_value=dict(state='Paid',amount_cents=d['amount_cents'],reference=d['reference'],paid_on=d['paid_on'],method=d['method']),created_at=s['now']())
            return jsonify(ok=True,already_recorded=False,invoice=detail(c,sid,u)['invoice'])

    @app.get('/api/hub-billing/<int:sid>/csv')
    @auth('admin','hub_manager')
    def hub_billing_csv(sid):
        with conn() as c:
            d = detail(c,sid,user())
        buf = io.StringIO(); w = csv.writer(buf)
        w.writerow(['Facture','Hub','Tracking','Ville','État colis','COD MAD','Commission MAD','État facture','Reçu MAD','Reste à remettre MAD','Date règlement'])
        def safe(v):
            v = str(v)
            return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        for l in d['lines']:
            w.writerow([d['invoice']['reference'],safe(d['invoice']['hub_name']),safe(l['tracking']),safe(l['city']),l['status'],f"{l['cod_cents']/100:.2f}",f"{l['commission_cents']/100:.2f}",d['invoice']['state'],f"{d['invoice']['paid_cents']/100:.2f}",f"{d['invoice']['cash_remaining_cents']/100:.2f}",d['invoice']['paid_on'] or ''])
        return Response('\ufeff'+buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="{d["invoice"]["reference"]}.csv"'})

    @app.get('/api/hub-billing/<int:sid>/pdf')
    @auth('admin','hub_manager')
    def hub_billing_pdf(sid):
        from billing_pdf import invoice_pdf
        with conn() as c:
            c.execute('BEGIN')
            d=detail(c,sid,user());i=d['invoice']
            row=c.execute('SELECT payload FROM hub_billing_print_snapshots WHERE statement_id=?',(sid,)).fetchone()
            snap=json.loads(row['payload']) if row else {}
        recipient=snap.get('recipient',{})
        r=dict(id=i['id'],kind='hub',reference=i['reference'],name=i['hub_name'],email=recipient.get('email',''),
               state=i['state'],parcel_count=i['parcel_count'],created_at=i['created_at'],cod_cents=i['cod_cents'],
               fees_cents=i['commission_cents'],net_cents=i['cod_cents']-i['commission_cents'],
               incoming_cents=i['cash_remaining_cents'],outgoing_cents=i['commission_due_cents'])
        receipt=d['receipt']
        transactions=[dict(receipt,kind='cash',voided_at=None,void_reason=None)] if receipt else []
        data=dict(invoice=r,record=i,issuer=snap.get('issuer',{}),recipient=recipient,transactions=transactions,
                  established_by=snap.get('established_by',''),lines=[dict(tracking=l['tracking'],city=l['city'],phone='',
                  status=l['status'],cod_cents=l['cod_cents'],amount_cents=l['cod_cents'] if l['status']=='Livré' else None,
                  fees_cents=l['commission_cents']) for l in d['lines']])
        return Response(invoice_pdf(data),mimetype='application/pdf',headers={
            'Content-Disposition':f'attachment; filename="{i["reference"]}.pdf"','Cache-Control':'no-store'})

    @app.put('/api/hub-billing/terms/<int:hid>')
    @auth('admin')
    def hub_billing_save_terms(hid):
        d = request.get_json(silent=True)
        if not isinstance(d,dict) or d.get('mode') not in ('net','gross') or type(d.get('revision')) is not int:
            raise Error('Méthode, montants et version requis.')
        city_payload=d.get('cities')
        city_values=None
        try:
            if 'cities' in d:
                if not isinstance(city_payload,list) or not city_payload:raise ValueError('Configurez les villes de ce Hub avant de saisir leur barème.')
                city_values={}
                for city in city_payload:
                    if not isinstance(city,dict) or type(city.get('city_id')) is not int or city['city_id'] in city_values:raise ValueError('Ville invalide ou en double.')
                    city_values[city['city_id']]=[amount_cents(city.get(k)) for k in ('delivered','returned','refused')]
                values=[0,0,0]  # Unused legacy columns; city mode never falls back to them.
            else:values = [amount_cents(d.get(k)) for k in ('delivered','returned','refused')]
        except ValueError as e:
            raise Error(str(e))
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hid,)).fetchone():
                raise Error('Hub actif introuvable.',404)
            old = c.execute('SELECT * FROM hub_billing_terms WHERE hub_id=?',(hid,)).fetchone()
            old_city_terms=[dict(r) for r in c.execute('SELECT * FROM hub_billing_city_terms WHERE hub_id=?',(hid,))]
            revision = old['revision'] if old else 0
            if d['revision'] != revision:
                raise Error('Le barème a changé. Rechargez-le.',409)
            if city_values is not None:
                assigned={city['id'] for city in billing_cities(c,hid)}
                if set(city_values)!=assigned:raise Error('Saisissez un barème pour chaque ville actuellement rattachée à ce Hub, sans ville étrangère. Rechargez la liste.',409)
                for cid,rates in city_values.items():
                    c.execute('''INSERT INTO hub_billing_city_terms VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(hub_id,city_id) DO UPDATE SET delivered_cents=excluded.delivered_cents,
                        returned_cents=excluded.returned_cents,refused_cents=excluded.refused_cents,
                        revision=excluded.revision,updated_by=excluded.updated_by,updated_at=excluded.updated_at''',
                        (hid,cid,*rates,revision+1,u['id'],s['now']()))
                c.execute('INSERT OR IGNORE INTO hub_billing_city_config VALUES(?)',(hid,))
            elif c.execute('SELECT 1 FROM hub_billing_city_config WHERE hub_id=?',(hid,)).fetchone():
                raise Error('Ce Hub utilise des barèmes par ville. Rechargez le formulaire.',409)
            c.execute('''INSERT INTO hub_billing_terms VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(hub_id) DO UPDATE SET
                mode=excluded.mode,delivered_cents=excluded.delivered_cents,returned_cents=excluded.returned_cents,
                refused_cents=excluded.refused_cents,revision=excluded.revision,updated_by=excluded.updated_by,updated_at=excluded.updated_at''',
                      (hid,d['mode'],*values,revision+1,u['id'],s['now']()))
            s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='hub_billing_terms_changed',entity_type='hub',entity_id=hid,
                                  old_value={'terms':dict(old) if old else None,'cities':old_city_terms},new_value=dict(cities=city_values,mode=d['mode'],delivered_cents=values[0],returned_cents=values[1],refused_cents=values[2],revision=revision+1),created_at=s['now']())
        return jsonify(ok=True)

    @app.put('/api/hub-billing/schedule')
    @auth('admin')
    def hub_billing_save_schedule():
        d = request.get_json(silent=True);u=user()
        if not isinstance(d,dict) or type(d.get('enabled')) is not bool or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',str(d.get('time',''))) or type(d.get('revision')) is not int:
            raise Error('Heure HH:MM, activation et version requises.')
        at=local_now()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            old=dict(c.execute('SELECT * FROM hub_billing_schedule WHERE id=1').fetchone())
            if old['revision']!=d['revision']:raise Error('Le planning a changé. Rechargez-le.',409)
            due=next_due(d['time'],at).isoformat() if d['enabled'] else None
            c.execute('UPDATE hub_billing_schedule SET enabled=?,time=?,revision=revision+1,next_run=?,updated_by=?,updated_at=?,last_error=? WHERE id=1',
                      (int(d['enabled']),d['time'],due,u['id'],at.isoformat(),''))
            s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='hub_billing_schedule_changed',entity_type='setting',entity_id='hub_billing_schedule',old_value=old,new_value=d,created_at=s['now']())
        return jsonify(ok=True,next_run=due)

    @app.get('/api/hub-billing/preview')
    @auth('admin')
    def hub_billing_preview():
        cutoff=local_now().replace(microsecond=0)
        raw_hub_id=request.args.get('hub_id')
        hub_id=None
        if raw_hub_id is not None:
            try:hub_id=int(raw_hub_id)
            except (TypeError,ValueError):raise Error('Hub invalide.')
            if hub_id<=0:raise Error('Hub invalide.')
        with conn() as c:
            if hub_id is not None and not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone():raise Error('Hub actif introuvable.',404)
            return jsonify(preview(c,cutoff,hub_id=hub_id))

    @app.post('/api/hub-billing/generate')
    @auth('admin')
    def hub_billing_generate():
        d=request.get_json(silent=True);u=user()
        if not isinstance(d,dict) or d.get('confirmed') is not True or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',str(d.get('request_key',''))):
            raise Error('Prévisualisation et confirmation requises.')
        try:
            cutoff=datetime.fromisoformat(d['cutoff'])
            if cutoff.tzinfo is None or cutoff>local_now():raise ValueError()
        except (ValueError,TypeError,KeyError):
            raise Error('Date de prévisualisation invalide.')
        hub_id=d.get('hub_id')
        if hub_id is not None and (type(hub_id) is not int or hub_id<=0):raise Error('Hub invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if hub_id is not None and not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone():raise Error('Hub actif introuvable.',404)
            try:
                result=generate(c,cutoff,u['id'],'manual:'+d['request_key'],expected=d.get('snapshot') or 'invalid',hub_id=hub_id)
            except ValueError as e:raise Error(str(e),409)
        return jsonify(result)

    # Production web process stays awake on the existing paid persistent-disk deployment.
    # No second Render worker (which cannot mount this SQLite disk) is needed.
    enabled=os.getenv('ORIENTAL24_HUB_BILLING_SCHEDULER','1' if app.config.get('PRODUCTION_MODE') else '0')=='1'
    if enabled:
        stop=threading.Event()
        def loop():
            while not stop.wait(30):
                try:
                    scheduled_tick(conn)
                except Exception as exc:
                    app.logger.exception('Hub billing scheduler failed')
                    try:
                        with conn() as c:c.execute('UPDATE hub_billing_schedule SET last_error=? WHERE id=1',(str(exc)[:300],))
                    except Exception:pass
        thread=threading.Thread(target=loop,name='hub-billing-scheduler',daemon=True)
        app.extensions['hub_billing_scheduler']=dict(thread=thread,stop=stop)
        thread.start()
