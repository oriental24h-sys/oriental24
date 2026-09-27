"""v1.5.4 « Paiements vendeurs » : aging 30/60/90 des créances « Vers le client » et règlement groupé, idempotent et auditable."""
import csv,io,json,hashlib,re
from datetime import date,datetime
from decimal import Decimal,ROUND_HALF_UP
from zoneinfo import ZoneInfo
from flask import request,jsonify,Response

def register_vendor_payables(app,services):
    conn,auth,user,now,text,Error=(services[k] for k in ['conn','auth','user','now','text','APIError'])
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS vendor_pay_keys(request_key TEXT PRIMARY KEY,actor_id INTEGER NOT NULL REFERENCES users(id),payload_hash TEXT NOT NULL,total_cents INTEGER NOT NULL,invoice_ids TEXT NOT NULL,created_at TEXT NOT NULL)''')
    dig=lambda x:hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def bucket(days):return 'b0_30' if days<=30 else 'b31_60' if days<=60 else 'b61_90' if days<=90 else 'b90p'
    def aggregate(c):
        # Vieillissement calculé sur la date d'émission des factures ouvertes (identique aux filtres Facturation).
        today=date.today();out=[]
        for u in c.execute("SELECT * FROM users WHERE role='client' AND active=1 ORDER BY name").fetchall():
            inv=[]
            for i in c.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY id',(u['id'],)).fetchall():
                info=services['client_invoice_info'](c,dict(i))
                if not info['remaining_cents']:continue
                age=(today-date.fromisoformat(i['created_at'][:10])).days if i['created_at'] else 0
                inv.append(dict(id=i['id'],reference=f"FAC-{i['id']:04d}",created_at=i['created_at'],age_days=age,bucket=bucket(age),remaining_cents=info['remaining_cents'],direction=info['direction'],status=i['status']))
            ub=c.execute("SELECT amount FROM parcels WHERE client_id=? AND status='Livré' AND invoice_id IS NULL",(u['id'],)).fetchall()
            unbilled=[int((Decimal(str(p['amount']))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) for p in ub]
            if not inv and not unbilled:continue
            owed=sum(i['remaining_cents'] for i in inv if i['direction']=='Vers le client')
            recv=sum(i['remaining_cents'] for i in inv if i['direction']=='Dû par le client')
            buckets={'b0_30':0,'b31_60':0,'b61_90':0,'b90p':0}
            for i in inv:
                if i['direction']=='Vers le client':buckets[i['bucket']]+=i['remaining_cents']
            out.append(dict(client_id=u['id'],vendor=u['company'] or u['name'],email=u['email'],phone=u['phone'] or '',open_count=len(inv),owed_cents=owed,receivable_cents=recv,buckets=buckets,oldest_age_days=max([i['age_days'] for i in inv],default=0),unbilled_count=len(unbilled),unbilled_cents=sum(unbilled),invoices=inv))
        out.sort(key=lambda v:(-v['owed_cents'],-v['oldest_age_days'],v['vendor'].lower()))
        totals=dict(owed_cents=sum(v['owed_cents'] for v in out),receivable_cents=sum(v['receivable_cents'] for v in out),buckets={k:sum(v['buckets'][k] for v in out) for k in ('b0_30','b31_60','b61_90','b90p')},unbilled_count=sum(v['unbilled_count'] for v in out),unbilled_cents=sum(v['unbilled_cents'] for v in out))
        return dict(vendors=out,totals=totals,day=today.isoformat())
    @app.get('/api/vendor-payables')
    @auth('admin')
    def vendor_payables_list():
        with conn() as c:
            c.execute('BEGIN');return jsonify(aggregate(c))
    @app.post('/api/vendor-payables/<int:cid>/pay')
    @auth('admin')
    def vendor_pay(cid):
        d=request.get_json();u=user()
        if not isinstance(d,dict) or set(d)!={'method','reference','payment_date','request_key','confirmed'} or d['confirmed'] is not True:
            raise Error('Confirmez explicitement le règlement réellement effectué.')
        if not isinstance(d['request_key'],str) or not re.fullmatch('[A-Za-z0-9_-]{20,60}',d['request_key']):raise Error('Clé de règlement invalide.')
        if d['method'] not in ('Espèces','Virement','Chèque'):raise Error('Mode de règlement invalide.')
        ref=text(d,'reference',maxlen=200);day=text(d,'payment_date',maxlen=10)
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or date.fromisoformat(day)>datetime.now(ZoneInfo('Africa/Casablanca')).date():raise ValueError()
        except ValueError:raise Error('Date effective invalide ou future.')
        h=dig([cid,d])
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT * FROM vendor_pay_keys WHERE request_key=?',(d['request_key'],)).fetchone()
            if prior:
                if prior['actor_id']!=u['id'] or prior['payload_hash']!=h:raise Error('Clé déjà utilisée pour une autre opération.',409)
                return jsonify(ok=True,already_recorded=True,total_cents=prior['total_cents'],invoice_ids=json.loads(prior['invoice_ids']))
            v=c.execute("SELECT * FROM users WHERE id=? AND role='client'",(cid,)).fetchone()
            if not v:raise Error('Vendeur introuvable.',404)
            ids=[];total=0
            for i in c.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY id',(cid,)).fetchall():
                info=services['client_invoice_info'](c,dict(i))
                if info['remaining_cents'] and info['direction']=='Vers le client':
                    services['add_client_receipt'](c,i,u,dict(amount=str(Decimal(info['remaining_cents'])/100),method=d['method'],reference=ref,payment_date=day,request_key=d['request_key']+'-fac-'+str(i['id'])))
                    ids.append(i['id']);total+=info['remaining_cents']
            if not ids:raise Error('Aucune facture « Vers le client » ouverte pour ce vendeur.',409)
            c.execute('INSERT INTO vendor_pay_keys VALUES(?,?,?,?,?,?)',(d['request_key'],u['id'],h,total,json.dumps(ids),now()))
            return jsonify(ok=True,already_recorded=False,total_cents=total,invoice_ids=ids)
    def sf(v):
        # Injection CSV : préfixe les cellules à formule exécutable.
        v=str(v if v is not None else '')
        return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
    @app.get('/api/vendor-payables/export')
    @auth('admin')
    def vendor_payables_export():
        with conn() as c:
            c.execute('BEGIN');d=aggregate(c)
        m=lambda v:(Decimal(v)/100).quantize(Decimal('.01'))
        lst=[['Vendeur','E-mail','Téléphone','Factures ouvertes','Reste à verser MAD','0-30 j MAD','31-60 j MAD','61-90 j MAD','90+ j MAD','À encaisser MAD','Colis livrés non facturés','COD non facturé MAD','Plus ancienne dette (jours)']]
        for v in d['vendors']:lst.append([sf(v['vendor']),sf(v['email']),sf(v['phone']),v['open_count'],m(v['owed_cents']),m(v['buckets']['b0_30']),m(v['buckets']['b31_60']),m(v['buckets']['b61_90']),m(v['buckets']['b90p']),m(v['receivable_cents']),v['unbilled_count'],m(v['unbilled_cents']),v['oldest_age_days']])
        out=io.StringIO();csv.writer(out,delimiter=';').writerows(lst)
        return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="ORIENTAL24-paiements-vendeurs.csv"','Cache-Control':'no-store'})
