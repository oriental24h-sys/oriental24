"""Unified read model and explicit payment actions, backed by the two existing ledgers."""
import csv,io,json,hashlib,re
from decimal import Decimal,ROUND_HALF_UP
from flask import jsonify,request,Response
from invoice_profile import profile

def driver_paid_sql(alias='p'):
    # No deletion/unassignment or physical receipt. A reversal automatically restores visibility.
    return f'''EXISTS(SELECT 1 FROM driver_statement_lines bl JOIN driver_statements bs ON bs.id=bl.statement_id
        WHERE bl.parcel_id={alias}.id AND bl.active=1 AND bs.driver_id={alias}.driver_id AND bs.cancelled_at IS NULL
        AND bs.cash_due_cents=(SELECT COALESCE(sum(bt.amount_cents),0) FROM driver_transactions bt WHERE bt.statement_id=bs.id AND bt.kind='cash' AND bt.voided_at IS NULL)
        AND bs.commission_due_cents=(SELECT COALESCE(sum(bt.amount_cents),0) FROM driver_transactions bt WHERE bt.statement_id=bs.id AND bt.kind='commission' AND bt.voided_at IS NULL))'''

def cent(v):return int((Decimal(str(v))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def state_label(v):return {'Réglée':'Paid','Soldé':'Paid','À régler':'Not Paid','Partiellement réglée':'Partiel'}.get(v,v)
def safe(v):
    if isinstance(v,(int,Decimal)):return v
    v=str(v if v is not None else '')
    return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v

def register_billing(app,s):
    conn,auth,user,now,Error=(s[k] for k in ('conn','auth','user','now','APIError'))
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS billing_action_keys(request_key TEXT PRIMARY KEY,actor_id INTEGER NOT NULL REFERENCES users(id),payload_hash TEXT NOT NULL,created_at TEXT NOT NULL)''')
    def allowed(kind,u):
        if kind not in ('client','livreur'):raise Error('Type de facture invalide.')
        if u['role']!='admin' and u['role']!=kind:raise Error('Accès non autorisé.',403)
    def read(c,kind,iid,u,details=False):
        allowed(kind,u)
        if kind=='livreur':
            raw=s['driver_finance_statement'](c,iid,u);i=s['driver_finance_balances'](c,raw)
            tx=[dict(t) for t in c.execute('SELECT * FROM driver_transactions WHERE statement_id=? ORDER BY id',(iid,))]
            status=state_label(i['status']);cod=i['cod_cents'];fees=i['commission_cents'];net=cod-fees;incoming=i['cash_remaining_cents'];outgoing=i['commission_remaining_cents'];party=i['driver_id'];name=i['driver_name'];email=i['driver_email'];count=i['parcel_count'];reference=i['reference']
            audit=[dict(a) for a in c.execute('SELECT * FROM driver_finance_audit WHERE statement_id=? ORDER BY id',(iid,))]
        else:
            raw=c.execute('SELECT i.*,u.name client,u.company,u.email FROM invoices i JOIN users u ON u.id=i.client_id WHERE i.id=?',(iid,)).fetchone()
            if not raw or (u['role']=='client' and raw['client_id']!=u['id']):raise Error('Facture introuvable.',404)
            i=s['client_invoice_info'](c,raw);tx=[dict(t) for t in c.execute('SELECT * FROM client_receipts WHERE invoice_id=? ORDER BY id',(iid,))]
            status=state_label(i['status']);cod=cent(i['cod']);fees=cent(i['fees']);net=i['total_cents'];incoming=i['remaining_cents'] if net<0 else 0;outgoing=i['remaining_cents'] if net>0 else 0;party=i['client_id'];name=i['company'] or i['client'];email=i['email'];count=c.execute('SELECT count(*) FROM parcels WHERE invoice_id=?',(iid,)).fetchone()[0];reference=f'FAC-{iid:04d}'
            audit=[dict(a) for a in c.execute('SELECT * FROM client_payment_audit WHERE invoice_id=? ORDER BY id',(iid,))]
        updated=max([i['created_at'] or '',i.get('cancelled_at') or '',i.get('paid_at') or '']+[t.get('voided_at') or t['created_at'] for t in tx]+[a['created_at'] for a in audit])
        version=digest([kind,iid,status,incoming,outgoing,[(t['id'],t['amount_cents'],t['voided_at']) for t in tx]])
        r=dict(id=iid,kind=kind,reference=reference,party_id=party,name=name,email=email,state=status,legacy_status=i['status'],cod_cents=cod,fees_cents=fees,net_cents=net,incoming_cents=incoming,outgoing_cents=outgoing,parcel_count=count,created_at=i['created_at'],updated_at=updated,version=version,can_reopen=any(not t['voided_at'] for t in tx))
        if not details:return r
        if kind=='livreur':
            snap=json.loads(raw['print_snapshot']) if raw.get('print_snapshot') else None;meta={p['parcel_id']:p for p in (snap or {}).get('parcels',[])}
            lines=[]
            for row in c.execute('SELECT * FROM driver_statement_lines WHERE statement_id=? ORDER BY id',(iid,)):
                p=dict(row);m=meta.get(p['parcel_id']);lines.append(dict(tracking=p['tracking'],city=p['city'],phone=m['phone'] if m else '',status=p['status'],amount_cents=cent(m['amount']) if m else p['cod_cents'] if p['status']=='Livré' else None,cod_cents=p['cod_cents'],fees_cents=p['commission_cents']))
            issuer=(snap or {}).get('issuer',{});recipient=(snap or {}).get('driver',{})
        else:
            lines=[dict(tracking=p['tracking'],city=p['city'],phone=p['phone'],status=p['status'],amount_cents=cent(p['amount']),cod_cents=cent(p['amount']) if p['status']=='Livré' else 0,fees_cents=cent(p['fee'] if p['status']=='Livré' else p['return_fee'])) for p in c.execute('SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE invoice_id=? ORDER BY p.id',(iid,))]
            issuer=profile(c);recipient={}
        return dict(invoice=r,lines=lines,transactions=tx,issuer=issuer,recipient=recipient,record=i)
    def listing(c,u):
        kind=request.args.get('kind') or ('livreur' if u['role']=='livreur' else 'client');allowed(kind,u)
        table,key=('driver_statements','driver_id') if kind=='livreur' else ('invoices','client_id')
        cond,args=('1=1',[]) if u['role']=='admin' else (key+'=?',[u['id']])
        rows=[read(c,kind,r['id'],u) for r in c.execute(f'SELECT id FROM {table} WHERE {cond} ORDER BY id DESC',args).fetchall()]
        parties=list({r['party_id']:{'id':r['party_id'],'name':r['name']} for r in reversed(rows)}.values())
        q=request.args.get('q','').strip().casefold();party=request.args.get('party','');state=request.args.get('state','');archive=request.args.get('archive','all')
        if state not in ('','Not Paid','Partiel','Paid','Annulé') or archive not in ('all','current','paid'):raise Error('Filtre invalide.')
        bounds=[]
        for keyname in ('from','to'):
            v=request.args.get(keyname,'')
            if v and not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}',v):raise Error('Date de filtre invalide.')
            if v:
                from datetime import datetime
                try:datetime.fromisoformat(v)
                except ValueError:raise Error('Date de filtre invalide.')
            bounds.append(v)
        start,end=bounds
        if start and end and start>end:raise Error('La date de début doit précéder la date de fin.')
        rows=[r for r in rows if (not q or q in (r['reference']+' '+r['name']+' '+r['email']).casefold()) and (not party or str(r['party_id'])==party) and (not state or r['state']==state) and (archive=='all' or (archive=='paid')==(r['state']=='Paid')) and (not start or r['created_at']>=start) and (not end or r['created_at']<=end+':59')]
        totals={k:sum(r[k] for r in rows if r['state']!='Annulé') for k in ('cod_cents','fees_cents','net_cents','incoming_cents','outgoing_cents')}
        return dict(kind=kind,rows=rows,parties=parties,totals=totals,count=len(rows))
    @app.get('/api/billing')
    @auth('admin','client','livreur')
    def billing_list():
        with conn() as c:
            c.execute('BEGIN');result=listing(c,user())
            try:page=int(request.args.get('page','1'));size=int(request.args.get('size','20'))
            except ValueError:raise Error('Pagination invalide.')
            if page<1 or size not in (10,20,50,100):raise Error('Pagination invalide.')
            page=min(page,max(1,(result['count']+size-1)//size));result.update(page=page,size=size,rows=result['rows'][(page-1)*size:page*size]);return jsonify(result)
    @app.get('/api/billing/<kind>/<int:iid>')
    @auth('admin','client','livreur')
    def billing_detail(kind,iid):
        with conn() as c:
            c.execute('BEGIN');return jsonify(read(c,kind,iid,user(),True))
    def payload(action):
        d=request.get_json();fields={'version','request_key','confirmed'}|({'method','reference','payment_date'} if action=='settle' else {'reason'})
        if not isinstance(d,dict) or set(d)!=fields or d['confirmed'] is not True:raise Error('Confirmez explicitement les opérations réellement effectuées.')
        if not isinstance(d['request_key'],str) or not re.fullmatch('[A-Za-z0-9_-]{20,60}',d['request_key']):raise Error('Clé de saisie invalide.')
        if not isinstance(d['version'],str) or not re.fullmatch('[0-9a-f]{64}',d['version']):raise Error('Version invalide.')
        for k in fields-{'version','request_key','confirmed'}:
            if not isinstance(d[k],str) or not d[k].strip() or len(d[k])>(600 if k=='reason' else 100):raise Error('Champ invalide : '+k)
        if action=='settle':
            from datetime import datetime
            from zoneinfo import ZoneInfo
            if d['method'] not in ('Espèces','Virement','Chèque'):raise Error('Mode de règlement invalide.')
            try:
                if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d['payment_date']) or datetime.strptime(d['payment_date'],'%Y-%m-%d').date()>datetime.now(ZoneInfo('Africa/Casablanca')).date():raise ValueError()
            except ValueError:raise Error('Date effective invalide ou future.')
        return d
    @app.post('/api/billing/<kind>/<int:iid>/<action>')
    @auth('admin')
    def billing_action(kind,iid,action):
        if action not in ('settle','reopen'):raise Error('Action inconnue.',404)
        d=payload(action);u=user();h=digest([kind,iid,action,d])
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');r=read(c,kind,iid,u)
            prior=c.execute('SELECT * FROM billing_action_keys WHERE request_key=?',(d['request_key'],)).fetchone()
            if prior:
                if prior['actor_id']!=u['id'] or prior['payload_hash']!=h:raise Error('Clé déjà utilisée pour une autre opération.',409)
                return jsonify(ok=True,already_recorded=True,invoice=r)
            if r['version']!=d['version']:raise Error('Le solde a changé. Fermez et vérifiez un nouvel aperçu.',409)
            if r['state']=='Annulé':raise Error('Cette facture est annulée.',409)
            if action=='settle':
                if r['state']=='Paid':raise Error('Facture déjà Paid. Actualisez la liste.',409)
                if kind=='livreur':
                    for flow,amount in [('cash',r['incoming_cents']),('commission',r['outgoing_cents'])]:
                        if amount:s['add_driver_transaction'](c,iid,u,dict(kind=flow,amount=str(Decimal(amount)/100),method=d['method'],reference=d['reference'],paid_on=d['payment_date'],note='Facturation : passage à Paid confirmé',request_key=d['request_key']+'-'+flow))
                else:
                    i=c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone();amount=r['incoming_cents']+r['outgoing_cents']
                    if amount:s['add_client_receipt'](c,i,u,dict(amount=str(Decimal(amount)/100),method=d['method'],reference=d['reference'],payment_date=d['payment_date'],request_key=d['request_key']))
                    else:s['settle_client_invoice'](c,i,u)
            else:
                if not r['can_reopen']:raise Error('Aucun règlement actif à annuler.',409)
                table,fk,helper=('driver_transactions','statement_id','void_driver_transaction') if kind=='livreur' else ('client_receipts','invoice_id','void_client_receipt')
                for row in c.execute(f'SELECT id FROM {table} WHERE {fk}=? AND voided_at IS NULL ORDER BY id',(iid,)).fetchall():s[helper](c,row['id'],u,d['reason'])
            c.execute('INSERT INTO billing_action_keys VALUES(?,?,?,?)',(d['request_key'],u['id'],h,now()))
            return jsonify(ok=True,already_recorded=False,invoice=read(c,kind,iid,u))
    def csv_response(rows,name):
        out=io.StringIO();w=csv.writer(out,delimiter=';');w.writerows([[safe(v) for v in row] for row in rows]);return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="{name}.csv"','Cache-Control':'no-store'})
    money=lambda v:(Decimal(v)/100).quantize(Decimal('.01')) if v is not None else ''
    @app.get('/api/billing/export')
    @auth('admin','client','livreur')
    def billing_export():
        with conn() as c:
            c.execute('BEGIN');d=listing(c,user());rows=[['Facture','Type','Titulaire','État','COD MAD','Frais MAD','Net MAD','À encaisser MAD','À verser MAD','Émise le','Mise à jour']]+[[r['reference'],r['kind'],r['name'],r['state'],*(money(r[k]) for k in ('cod_cents','fees_cents','net_cents','incoming_cents','outgoing_cents')),r['created_at'],r['updated_at']] for r in d['rows']]
            return csv_response(rows,'ORIENTAL24-facturation-'+d['kind'])
    @app.get('/api/billing/<kind>/<int:iid>/<fmt>')
    @auth('admin','client','livreur')
    def billing_download(kind,iid,fmt):
        if fmt not in ('csv','pdf'):raise Error('Format inconnu.',404)
        with conn() as c:
            c.execute('BEGIN');d=read(c,kind,iid,user(),True)
        r=d['invoice'];name='ORIENTAL24-'+r['reference']
        if fmt=='pdf':
            from billing_pdf import invoice_pdf
            return Response(invoice_pdf(d),mimetype='application/pdf',headers={'Content-Disposition':f'attachment; filename="{name}.pdf"','Cache-Control':'no-store'})
        rows=[['Facture','Type','Titulaire','État facture','Émise le','ID de suivi','Ville','Téléphone','Statut colis','COD nominal MAD','COD livré MAD','Frais MAD','Net ligne MAD']]
        rows += [[r['reference'],kind,r['name'],r['state'],r['created_at'],p['tracking'],p['city'],p['phone'],p['status'],money(p['amount_cents']),money(p['cod_cents']),money(p['fees_cents']),money(p['cod_cents']-p['fees_cents'])] for p in d['lines']]
        return csv_response(rows,name)
