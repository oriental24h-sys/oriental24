"""Manual client settlements; integer cents, immutable receipts and auditable reversals."""
from decimal import Decimal,InvalidOperation,ROUND_HALF_UP
from datetime import date
from zoneinfo import ZoneInfo
from datetime import datetime
import re,json,hashlib,secrets
from flask import request,jsonify

def register_client_finance(app,services):
    conn,auth,user,now,text,Error=(services[k] for k in ['conn','auth','user','now','text','APIError'])
    def cent(v,positive=False):
        try:
            n=Decimal(str(v));c=n*100
            if not n.is_finite() or abs(n)>1000000000 or (positive and (n<=0 or c!=c.to_integral_value())):raise ValueError()
            return int(c.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        except (ValueError,InvalidOperation):raise Error('Montant invalide : deux décimales maximum et strictement positif.')
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS client_invoice_totals(invoice_id INTEGER PRIMARY KEY REFERENCES invoices(id),total_cents INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS client_receipts(id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),method TEXT NOT NULL,reference TEXT NOT NULL,payment_date TEXT,created_at TEXT NOT NULL,actor_id INTEGER REFERENCES users(id),request_key TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,voided_at TEXT,voided_by INTEGER REFERENCES users(id),void_reason TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS client_unique_active_reference ON client_receipts(invoice_id,reference COLLATE NOCASE) WHERE voided_at IS NULL;
        CREATE TABLE IF NOT EXISTS client_payment_audit(id INTEGER PRIMARY KEY,invoice_id INTEGER NOT NULL REFERENCES invoices(id),receipt_id INTEGER REFERENCES client_receipts(id),action TEXT NOT NULL,details TEXT NOT NULL,actor_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
        ''')
    def audit(c,iid,rid,action,details,uid):c.execute('INSERT INTO client_payment_audit(invoice_id,receipt_id,action,details,actor_id,created_at) VALUES(?,?,?,?,?,?)',(iid,rid,action,json.dumps(details,ensure_ascii=False),uid,now()))
    def ensure(c,i):
        if c.execute('SELECT 1 FROM client_invoice_totals WHERE invoice_id=?',(i['id'],)).fetchone():return
        total=cent(i['total']);c.execute('INSERT INTO client_invoice_totals(invoice_id,total_cents,created_at) VALUES(?,?,?)',(i['id'],total,now()))
        if i['status']=='Réglée' and total:
            rid=c.execute('INSERT INTO client_receipts(invoice_id,amount_cents,method,reference,payment_date,created_at,request_key,payload_hash) VALUES(?,?,?,?,?,?,?,?)',(i['id'],abs(total),'Historique importé','Ancienne déclaration de règlement, justificatif non disponible',i['paid_at'][:10] if i['paid_at'] else None,now(),'migration-client-'+str(i['id']),'migration')).lastrowid
            audit(c,i['id'],rid,'migration',{'note':'Ancien statut réglé, aucun virement ni justificatif bancaire vérifié.'},None)
    def info(c,i):
        i=dict(i);ensure(c,i)
        total=c.execute('SELECT total_cents FROM client_invoice_totals WHERE invoice_id=?',(i['id'],)).fetchone()[0]
        paid=c.execute('SELECT COALESCE(sum(amount_cents),0) FROM client_receipts WHERE invoice_id=? AND voided_at IS NULL',(i['id'],)).fetchone()[0]
        return {**i,'total_cents':total,'paid_cents':paid,'remaining_cents':abs(total)-paid,'direction':'Vers le client' if total>0 else 'Dû par le client' if total<0 else 'Sans flux'}
    with conn() as c:
        for row in c.execute('SELECT * FROM invoices').fetchall():ensure(c,row)
    def sync(c,iid):
        i=info(c,c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone())
        status='Réglée' if not i['remaining_cents'] else 'Partiellement réglée' if i['paid_cents'] else 'À régler'
        c.execute('UPDATE invoices SET status=?,paid_at=? WHERE id=?',(status,now() if status=='Réglée' else None,iid))
    def history(c,iid):
        return {'receipts':[dict(r) for r in c.execute('SELECT r.*,u.name actor FROM client_receipts r LEFT JOIN users u ON u.id=r.actor_id WHERE invoice_id=? ORDER BY r.id DESC',(iid,))], 'payment_audit':[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM client_payment_audit a LEFT JOIN users u ON u.id=a.actor_id WHERE invoice_id=? ORDER BY a.id DESC',(iid,))]}
    def add(c,i,u,d):
        key=text(d,'request_key',maxlen=80)
        if not re.fullmatch('[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de règlement invalide.')
        h=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
        prior=c.execute('SELECT * FROM client_receipts WHERE request_key=?',(key,)).fetchone()
        if prior:
            if prior['invoice_id']!=i['id'] or prior['actor_id']!=u['id'] or prior['payload_hash']!=h:raise Error('Clé déjà utilisée pour une autre opération.',409)
            return {'ok':True,'id':prior['id'],'already_recorded':True}
        state=info(c,i);amount=cent(d.get('amount'),True)
        if amount>state['remaining_cents']:raise Error('Ce règlement dépasse le solde restant.',409)
        method=text(d,'method',maxlen=40)
        if method not in ['Espèces','Virement','Chèque','Autre']:raise Error('Mode de règlement invalide.')
        ref=text(d,'reference',maxlen=300);day=text(d,'payment_date',maxlen=10)
        if c.execute('SELECT 1 FROM client_receipts WHERE invoice_id=? AND reference=? COLLATE NOCASE AND voided_at IS NULL',(i['id'],ref)).fetchone():raise Error('Référence déjà enregistrée sur ce relevé.',409)
        try:
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or date.fromisoformat(day)>datetime.now(ZoneInfo('Africa/Casablanca')).date():raise ValueError()
        except ValueError:raise Error('Date effective invalide ou future.')
        rid=c.execute('INSERT INTO client_receipts(invoice_id,amount_cents,method,reference,payment_date,created_at,actor_id,request_key,payload_hash) VALUES(?,?,?,?,?,?,?,?,?)',(i['id'],amount,method,ref,day,now(),u['id'],key,h)).lastrowid
        audit(c,i['id'],rid,'règlement déclaré',{'amount_cents':amount,'direction':state['direction']},u['id']);sync(c,i['id'])
        return {'ok':True,'id':rid,'already_recorded':False}
    def legacy_settle(c,i,u):
        s=info(c,i)
        if not s['remaining_cents']:
            if i['status']!='Réglée':audit(c,i['id'],None,'clôture sans flux',{},u['id']);sync(c,i['id'])
            return
        add(c,i,u,dict(amount=str(Decimal(s['remaining_cents'])/100),method='Autre',reference='Déclaration manuelle du solde via ancien parcours · '+secrets.token_hex(4),payment_date=datetime.now(ZoneInfo('Africa/Casablanca')).date().isoformat(),request_key=secrets.token_hex(16)))
    services.update(client_invoice_info=info,client_invoice_history=history,settle_client_invoice=legacy_settle,add_client_receipt=add)
    @app.post('/api/client-finance/invoices/<int:iid>/receipts')
    @auth('admin')
    def client_receipt_add(iid):
        d=request.get_json();u=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');i=c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone()
            if not i:raise Error('Facture introuvable.',404)
            return jsonify(add(c,i,u,d))
    def void_client_receipt(c,rid,u,reason):
        r=c.execute('SELECT * FROM client_receipts WHERE id=?',(rid,)).fetchone()
        if not r:raise Error('Règlement introuvable.',404)
        if r['voided_at']:return dict(ok=True,already_voided=True)
        c.execute('UPDATE client_receipts SET voided_at=?,voided_by=?,void_reason=? WHERE id=?',(now(),u['id'],reason,rid))
        audit(c,r['invoice_id'],rid,'déclaration annulée',{'reason':reason},u['id']);sync(c,r['invoice_id'])
        return dict(ok=True,already_voided=False)

    services['void_client_receipt']=void_client_receipt

    @app.post('/api/client-finance/receipts/<int:rid>/void')
    @auth('admin')
    def client_receipt_void(rid):
        d=request.get_json();u=user()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        reason=text(d,'reason',maxlen=600)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            return jsonify(void_client_receipt(c,rid,u,reason))
