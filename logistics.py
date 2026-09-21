"""ORIENTAL24 operational execution. Additive schema, scoped reads and atomic writes.
No external notifications, bank transfers, physical signatures or GPS are simulated here.
"""
import json, secrets, re, hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import request, jsonify

from claims import prepare_claim
from parcel_statuses import ATTEMPT_SOURCES, ATTEMPT_OUTCOMES

P='/api/logistics'
REASONS=[('absent','Destinataire absent'),('unreachable','Destinataire injoignable'),('address','Adresse à corriger'),('appointment','Rendez-vous demandé'),('refused','Refus du destinataire'),('return','Retour demandé')]

# Reference-inspired follow-up reasons; labels are configurable, not logistics transitions.
REASONS += [('no_answer','Pas de réponse'),('postponed','Reporté'),
 ('voicemail','Occupé - Boîte vocale'),('always_unavailable','Toujours indisponible'),
 ('long_trip','Voyage longue durée'),('exchange_refund','Demande échange/remboursement'),
 ('changed_mind','Changé d’avis'),('wrong_city','Ville incorrecte'),('out_of_area','Hors zone de livraison'),
 ('cancelled_delay','Annulé à cause du retard'),('no_money','Le client n’a pas d’argent'),
 ('bought_elsewhere','Acheté ailleurs'),('duplicate_order','Commande doublée'),
 ('wrong_number','Numéro incorrect'),('travelling','Le client est en voyage'),
 ('not_interested','Client(e) pas intéressé'),('return_agency','Retour envoyé vers agence')]

def register_logistics(app, services):
    conn,auth,user,now,text,Error,event,parcel = (services[k] for k in ['conn','auth','user','now','text','APIError','event','parcel'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER NOT NULL REFERENCES cities(id),address TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS ops_hub_name ON ops_hubs(name COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS ops_reasons(code TEXT PRIMARY KEY,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS ops_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),old_driver_id INTEGER,new_driver_id INTEGER,actor_id INTEGER NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_attempts(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),driver_id INTEGER,actor_id INTEGER NOT NULL,outcome TEXT NOT NULL,reason_code TEXT,reason_label TEXT,next_attempt_at TEXT,note TEXT NOT NULL,receiver TEXT,amount_cents INTEGER,request_key TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_documents(id INTEGER PRIMARY KEY,reference TEXT UNIQUE,kind TEXT NOT NULL,client_id INTEGER REFERENCES users(id),driver_id INTEGER REFERENCES users(id),source_hub_id INTEGER REFERENCES ops_hubs(id),destination_hub_id INTEGER REFERENCES ops_hubs(id),client_name TEXT,driver_name TEXT,source_name TEXT,destination_name TEXT,status TEXT NOT NULL DEFAULT 'Préparé',revision INTEGER NOT NULL DEFAULT 1,note TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,dispatched_at TEXT,completed_at TEXT,cancel_reason TEXT);
        CREATE TABLE IF NOT EXISTS ops_document_lines(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES ops_documents(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),tracking TEXT NOT NULL,recipient TEXT NOT NULL,city TEXT NOT NULL,initial_status TEXT NOT NULL,received_at TEXT,received_by INTEGER,active INTEGER NOT NULL DEFAULT 1);
        CREATE UNIQUE INDEX IF NOT EXISTS ops_one_active_document ON ops_document_lines(parcel_id) WHERE active=1;
        CREATE TABLE IF NOT EXISTS ops_audit(id INTEGER PRIMARY KEY,document_id INTEGER REFERENCES ops_documents(id),actor_id INTEGER NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_notifications(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),parcel_id INTEGER REFERENCES parcels(id),title TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT);
        CREATE INDEX IF NOT EXISTS ops_notice_user ON ops_notifications(user_id,id);
        CREATE INDEX IF NOT EXISTS ops_attempt_parcel ON ops_attempts(parcel_id,id);
        CREATE INDEX IF NOT EXISTS ops_assignment_date ON ops_assignments(created_at,new_driver_id);
        CREATE TABLE IF NOT EXISTS ops_ticket_links(ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),priority TEXT NOT NULL,assigned_to INTEGER REFERENCES users(id),first_response_at TEXT);
        CREATE TABLE IF NOT EXISTS ops_batch_previews(token TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,driver_id INTEGER NOT NULL,parcel_ids TEXT NOT NULL,snapshot TEXT NOT NULL,created_at TEXT NOT NULL,committed_at TEXT);
        ''')
        columns={r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
        for key,definition in [('reason_code','TEXT'),('next_attempt_at','TEXT'),('ops_revision','INTEGER NOT NULL DEFAULT 0'),('current_hub_id','INTEGER REFERENCES ops_hubs(id)')]:
            if key not in columns:c.execute(f'ALTER TABLE parcels ADD COLUMN {key} {definition}')
        c.executemany('INSERT OR IGNORE INTO ops_reasons(code,label) VALUES(?,?)',REASONS)
        c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('ops_started_at',?)",(now(),))

    def body():
        d=request.get_json()
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def integer(v,label='Identifiant'):
        if isinstance(v,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(v)):raise Error(label+' invalide.')
        return int(v)
    def ids(d):
        v=d.get('parcel_ids')
        if not isinstance(v,list) or not 1<=len(v)<=100:raise Error('Sélectionnez de 1 à 100 colis.')
        values=[integer(i) for i in v]
        if len(values)!=len(set(values)):raise Error('Colis répété dans la sélection.')
        return values
    def enabled_user(c,uid,role):
        u=c.execute('SELECT id,name FROM users WHERE id=? AND role=? AND active=1',(integer(uid),role)).fetchone()
        if not u:raise Error('Compte actif introuvable : '+role)
        return u
    def hub(c,hid,active=True):
        h=c.execute('SELECT * FROM ops_hubs WHERE id=?',(integer(hid,'Hub'),)).fetchone()
        if not h or (active and not h['active']):raise Error('Hub actif introuvable.')
        return h
    def guard(c,p,documents=True):
        if p['invoice_id'] or c.execute('SELECT 1 FROM driver_statement_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone():raise Error('Colis verrouillé dans un relevé financier.',409)
        if documents and c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone():raise Error('Colis lié à un document actif. Terminez ou annulez ce document avant modification.',409)
    def audit(c,did,u,action,details):
        c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(did,u['id'],action,json.dumps(details,ensure_ascii=False),now()))
    def notify(c,uid,title,description,pid=None):
        c.execute('INSERT INTO ops_notifications(user_id,parcel_id,title,body,created_at) VALUES(?,?,?,?,?)',(uid,pid,title,description,now()))
    def notify_event(c,pid,status,u):
        p=c.execute('SELECT tracking,client_id,driver_id FROM parcels WHERE id=?',(pid,)).fetchone()
        recipients={p['client_id'],p['driver_id']}-{None,u['id']}
        for uid in recipients:notify(c,uid,'Suivi colis',p['tracking']+' · '+status,pid)
    def planned(value):
        try:
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}',value):raise ValueError()
            dt=datetime.strptime(value,'%Y-%m-%dT%H:%M').replace(tzinfo=ZoneInfo('Africa/Casablanca'))
            if dt<=datetime.now(ZoneInfo('Africa/Casablanca')):raise ValueError()
            return dt.isoformat(timespec='minutes')
        except (ValueError,TypeError):raise Error('Choisissez un rendez-vous futur, heure du Maroc.')
    def revision(p,d):
        if type(d.get('revision')) is not int or d['revision']!=p['ops_revision']:raise Error('Le colis a changé. Rechargez sa fiche.',409)
    def change(c,p,d,u):
        # Called by the existing PATCH endpoint as well: no bypass of document or scheduling locks.
        guard(c,p)
        if 'revision' in d:revision(p,d)
        if d.get('status') and d['status'] not in ['Livré','Refusé','Retourné']:
            c.execute('DELETE FROM driver_receipts WHERE parcel_id=?',(p['id'],))
        reason=None;next_at=None
        if d.get('reason_code'):
            reason=c.execute('SELECT * FROM ops_reasons WHERE code=? AND active=1',(str(d['reason_code']),)).fetchone()
            if not reason:raise Error('Motif inconnu ou désactivé.')
        if d.get('status')=='Programmé':
            if not reason:raise Error('Un motif est obligatoire pour programmer le colis.')
            next_at=planned(d.get('next_attempt_at'))
        if d.get('status')=='Reçu par le livreur':
            did=d.get('driver_id',p['driver_id'])
            if not did or not c.execute("SELECT 1 FROM users WHERE id=? AND role='livreur' AND active=1",(did,)).fetchone():raise Error('Affectez un livreur actif avant de déclarer la prise en charge.')
        if 'driver_id' in d:
            did=integer(d['driver_id']) if d['driver_id'] else None
            if did!=p['driver_id'] and p['status']=='Reçu par le livreur' and d.get('status',p['status'])=='Reçu par le livreur':raise Error('Prise en charge déjà déclarée. Indiquez d’abord l’état réel de remise avant de changer le livreur.',409)
            if did!=p['driver_id']:
                c.execute('INSERT INTO ops_assignments(parcel_id,old_driver_id,new_driver_id,actor_id,created_at) VALUES(?,?,?,?,?)',(p['id'],p['driver_id'],did,u['id'],now()))
        if d.get('status') in ['Transit','Reçu par le livreur']:
            c.execute('UPDATE parcels SET current_hub_id=NULL WHERE id=?',(p['id'],))
        if 'status' in d:
            c.execute('UPDATE parcels SET reason_code=?,next_attempt_at=?,ops_revision=ops_revision+1 WHERE id=?',(reason['code'] if reason else None,next_at,p['id']))
        else:c.execute('UPDATE parcels SET ops_revision=ops_revision+1 WHERE id=?',(p['id'],))
        return reason,next_at
    def allowed_doc(c,did,u):
        d=c.execute('SELECT * FROM ops_documents WHERE id=?',(did,)).fetchone()
        if not d or (u['role']=='client' and (d['kind']=='transfer' or d['client_id']!=u['id'])) or (u['role']=='livreur' and d['driver_id']!=u['id']):raise Error('Document introuvable.',404)
        return dict(d)
    def document_data(c,d):
        lines=[dict(r) for r in c.execute('SELECT * FROM ops_document_lines WHERE document_id=? ORDER BY id',(d['id'],))]
        return {**d,'lines':lines,'count':len(lines),'received':sum(bool(r['received_at']) for r in lines)}

    services.update(ops_change=change,ops_notify_event=notify_event)

    @app.get(P+'/config')
    @auth()
    def ops_config():
        with conn() as c:return jsonify(reasons=[dict(r) for r in c.execute('SELECT * FROM ops_reasons ORDER BY label')],hubs=[dict(r) for r in c.execute('SELECT h.*,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id ORDER BY h.name')],started_at=c.execute("SELECT value FROM settings WHERE key='ops_started_at'").fetchone()[0])

    @app.route(P+'/hubs',methods=['POST'])
    @app.route(P+'/hubs/<int:hid>',methods=['PATCH'])
    @auth('admin')
    def ops_hub(hid=None):
        d=body();name=text(d,'name',maxlen=100);address=text(d,'address',maxlen=300);cid=integer(d.get('city_id'))
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM cities WHERE id=?',(cid,)).fetchone():raise Error('Ville inconnue.')
            if hid:
                hub(c,hid,False);c.execute('UPDATE ops_hubs SET name=?,city_id=?,address=?,active=? WHERE id=?',(name,cid,address,int(bool(d.get('active'))),hid))
            else:hid=c.execute('INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,?,?)',(name,cid,address,now())).lastrowid
            audit(c,None,user(),'Hub configuré',{'hub_id':hid,'name':name})
        return jsonify(ok=True,id=hid)

    @app.route(P+'/reasons',methods=['POST'])
    @auth('admin')
    def ops_reason():
        d=body();code=text(d,'code',maxlen=40);label=text(d,'label',maxlen=100)
        if not re.fullmatch('[a-z][a-z0-9_-]{1,39}',code):raise Error('Code : 2 à 40 lettres minuscules, chiffres, tirets.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('INSERT INTO ops_reasons(code,label,active) VALUES(?,?,?) ON CONFLICT(code) DO UPDATE SET label=excluded.label,active=excluded.active',(code,label,int(bool(d.get('active',True)))))
            audit(c,None,user(),'Motif configuré',{'code':code,'label':label,'active':bool(d.get('active',True))})
        return jsonify(ok=True)

    @app.patch('/api/parcels/<int:pid>/reason')
    @auth('admin','livreur')
    def parcel_reason(pid):
        d=request.get_json(silent=True)
        if not isinstance(d,dict) or set(d)!={'reason_code','revision'}:raise Error('Motif et version requis, sans autre modification.')
        code=d['reason_code'];u=user()
        if code is not None and (not isinstance(code,str) or not re.fullmatch('[a-z][a-z0-9_-]{1,39}',code)):raise Error('Code motif invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');p=parcel(c,pid,u);guard(c,p);revision(p,d)
            if u['role']=='livreur' and p['status'] in ['Livré','Retourné']:raise Error('Colis clôturé. Contactez l’administration.',409)
            reason=c.execute('SELECT * FROM ops_reasons WHERE code=? AND active=1',(code,)).fetchone() if code else None
            if code and not reason:raise Error('Motif inconnu ou désactivé.')
            if code==p['reason_code']:return jsonify(ok=True,changed=False)
            if not code and p['status']=='Programmé':raise Error('Un colis programmé doit conserver un motif.')
            previous=c.execute('SELECT label FROM ops_reasons WHERE code=?',(p['reason_code'],)).fetchone()
            # Do not change status, appointment, free-text delivery note, money, driver or financial dates.
            c.execute('UPDATE parcels SET reason_code=?,ops_revision=ops_revision+1 WHERE id=?',(code,pid))
            label=reason['label'] if reason else 'Aucun motif'
            event(c,pid,p['status'],'Motif de suivi : '+(previous['label'] if previous else 'Aucun motif')+' → '+label,u)
            audit(c,None,u,'Motif de suivi modifié',dict(parcel_id=pid,old_code=p['reason_code'],code=code,label=label))
            return jsonify(ok=True,changed=True)

    @app.get(P+'/parcels/<int:pid>')
    @auth()
    def ops_parcel(pid):
        u=user()
        with conn() as c:
            p=parcel(c,pid,u)
            attempts=[dict(r) for r in c.execute('SELECT a.*,u.name actor FROM ops_attempts a JOIN users u ON u.id=a.actor_id WHERE parcel_id=? ORDER BY a.id DESC',(pid,))]
            links=[dict(r) for r in c.execute('SELECT d.id,d.reference,d.kind,d.status,l.received_at FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE l.parcel_id=? AND (d.client_id=? OR ?=\'admin\' OR d.driver_id=?) ORDER BY d.id DESC',(pid,u['id'],u['role'],u['id']))]
            tickets=[dict(r) for r in c.execute("SELECT t.id,t.subject,t.status,l.priority FROM ops_ticket_links l JOIN tickets t ON t.id=l.ticket_id WHERE l.parcel_id=? AND (t.user_id=? OR ?='admin') ORDER BY t.id DESC",(pid,u['id'],u['role']))]
            return jsonify(parcel=p,attempts=attempts,documents=links,tickets=tickets)

    @app.post(P+'/parcels/<int:pid>/attempts')
    @auth('admin','livreur')
    def ops_attempt(pid):
        d=body();u=user();key=text(d,'request_key',maxlen=80)
        if not re.fullmatch('[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de saisie invalide.')
        outcome=d.get('outcome')
        if outcome not in ATTEMPT_OUTCOMES:raise Error('Résultat invalide.')
        note=text(d,'note',False,600);receiver=text(d,'receiver',False,100)
        hashed=hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');p=parcel(c,pid,u)
            prior=c.execute('SELECT * FROM ops_attempts WHERE request_key=?',(key,)).fetchone()
            if prior:
                if prior['payload_hash']!=hashed or prior['parcel_id']!=pid or prior['actor_id']!=u['id']:raise Error('Clé déjà utilisée pour une autre saisie.',409)
                return jsonify(ok=True,id=prior['id'],already_recorded=True)
            revision(p,d)
            valid=p['status'] in ATTEMPT_SOURCES or (p['status']=='Refusé' and outcome=='Retourné')
            if not valid:raise Error('Une tentative concerne un colis en livraison ou programmé ; un refus peut être retourné.',409)
            if outcome!='Livré' and not d.get('reason_code'):raise Error('Choisissez le motif du résultat.')
            cents=None
            if outcome=='Livré':
                if not receiver:raise Error('Indiquez le nom du réceptionnaire déclaré.')
                from decimal import Decimal, InvalidOperation
                try:
                    val=Decimal(str(d.get('collected_amount','')).replace(',','.'))
                    if not val.is_finite() or val<0 or val!=Decimal(str(p['amount'])):raise ValueError()
                    cents=int(val*100)
                except (ValueError,InvalidOperation):raise Error('Le COD déclaré doit correspondre au montant du colis. Pas d’encaissement partiel dans ce parcours.')
            reason,next_at=change(c,p,{**d,'status':outcome},u)
            aid=c.execute('INSERT INTO ops_attempts(parcel_id,driver_id,actor_id,outcome,reason_code,reason_label,next_attempt_at,note,receiver,amount_cents,request_key,payload_hash,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,p['driver_id'],u['id'],outcome,reason['code'] if reason else None,reason['label'] if reason else None,next_at,note,receiver,cents,key,hashed,now())).lastrowid
            c.execute('UPDATE parcels SET status=?,note=?,updated_at=? WHERE id=?',(outcome,note or p['note'],now(),pid))
            event(c,pid,outcome,('Tentative : '+(reason['label'] if reason else 'livraison déclarée'))+(' · Rendez-vous '+next_at if next_at else '')+(' · '+note if note else ''),u)
            return jsonify(ok=True,id=aid,already_recorded=False)

    @app.get(P+'/documents')
    @auth()
    def ops_documents():
        u=user();where,args=('1=1',[]) if u['role']=='admin' else ("kind!='transfer' AND client_id=?",[u['id']]) if u['role']=='client' else ('driver_id=?',[u['id']])
        with conn() as c:
            return jsonify([document_data(c,dict(r)) for r in c.execute('SELECT * FROM ops_documents WHERE '+where+' ORDER BY id DESC LIMIT 500',args).fetchall()])

    @app.post(P+'/documents')
    @auth('admin')
    def ops_create_document():
        d=body();u=user();pids=ids(d);kind=d.get('kind')
        if kind not in ['pickup','return','transfer']:raise Error('Type de document invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            cl=enabled_user(c,d.get('client_id'),'client') if kind!='transfer' else None
            dr=enabled_user(c,d['driver_id'],'livreur') if d.get('driver_id') else None
            src=hub(c,d.get('source_hub_id')) if kind!='pickup' else None
            dest=hub(c,d.get('destination_hub_id')) if kind!='return' else None
            if src and dest and src['id']==dest['id']:raise Error('Choisissez deux hubs différents.')
            parcels=[]
            for pid in pids:
                p=parcel(c,pid,u)
                if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1',(pid,)).fetchone():raise Error('Un colis appartient déjà à un document actif.',409)
                if cl and p['client_id']!=cl['id']:raise Error('Tous les colis doivent appartenir au client du bon.')
                if kind=='return':
                    if p['status'] not in ['Retourné','Refusé']:raise Error('Un bon de retour ne contient que des colis retournés/refusés.')
                else:
                    guard(c,p)
                    if kind=='pickup' and p['status'] not in ['Créé','Ramassé']:raise Error('Ramassage : sélectionnez des colis créés ou ramassés.')
                    if kind=='transfer' and p['status'] not in ['Ramassé','Au hub','Réceptionné']:raise Error('Transfert : sélectionnez des colis ramassés, au hub ou réceptionnés en agence.')
                if src and p['current_hub_id'] and p['current_hub_id']!=src['id']:raise Error('Le hub connu du colis ne correspond pas à l’origine.')
                parcels.append(p)
            did=c.execute('INSERT INTO ops_documents(kind,client_id,driver_id,source_hub_id,destination_hub_id,client_name,driver_name,source_name,destination_name,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(kind,cl['id'] if cl else None,dr['id'] if dr else None,src['id'] if src else None,dest['id'] if dest else None,cl['name'] if cl else None,dr['name'] if dr else None,src['name'] if src else 'Chez le client',dest['name'] if dest else 'Retour au client',text(d,'note',False,600),u['id'],now())).lastrowid
            reference={'pickup':'RAM','return':'RET','transfer':'TRF'}[kind]+f'-{did:06d}'
            c.execute('UPDATE ops_documents SET reference=? WHERE id=?',(reference,did))
            for p in parcels:
                city=c.execute('SELECT name FROM cities WHERE id=?',(p['city_id'],)).fetchone()[0]
                c.execute('INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,?,?,?)',(did,p['id'],p['tracking'],p['recipient'],city,p['status']))
            audit(c,did,u,'Document préparé',{'count':len(parcels)})
            for uid in {cl['id'] if cl else None,dr['id'] if dr else None}-{None}:notify(c,uid,'Document préparé',reference)
            return jsonify(ok=True,id=did,reference=reference)

    @app.get(P+'/documents/<int:did>')
    @auth()
    def ops_document(did):
        with conn() as c:
            d=document_data(c,allowed_doc(c,did,user()))
            import qrcode, io, base64
            image=qrcode.make(d['reference']);buf=io.BytesIO();image.save(buf,format='PNG');d['qr']='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
            d['audit']=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM ops_audit a JOIN users u ON u.id=a.actor_id WHERE document_id=? ORDER BY a.id DESC',(did,))]
            return jsonify(d)

    @app.post(P+'/documents/<int:did>/<action>')
    @auth('admin')
    def ops_document_action(did,action):
        d=body();u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc=document_data(c,allowed_doc(c,did,u))
            if doc['kind']=='partner_palette':raise Error('Utilisez la réception dédiée Palettes partenaires.',409)
            if action in ['dispatch','cancel']:
                if type(d.get('revision')) is not int or d['revision']!=doc['revision']:raise Error('Le document a changé. Rechargez-le.',409)
                if doc['status']!='Préparé':raise Error('Cette action exige un document encore préparé.',409)
                if action=='cancel':
                    reason=text(d,'reason',maxlen=600)
                    c.execute("UPDATE ops_documents SET status='Annulé',cancel_reason=?,revision=revision+1 WHERE id=?",(reason,did))
                    c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,));audit(c,did,u,'Document annulé',{'reason':reason})
                else:
                    for line in doc['lines']:
                        p=parcel(c,line['parcel_id'],u)
                        if doc['kind']!='return':guard(c,p,False)
                    c.execute("UPDATE ops_documents SET status='En transit',dispatched_at=?,revision=revision+1 WHERE id=?",(now(),did))
                    audit(c,did,u,'Départ confirmé',{'count':doc['count']})
                    for line in doc['lines']:
                        if doc['kind']=='transfer':
                            c.execute("UPDATE parcels SET status='Transit',current_hub_id=NULL,next_attempt_at=NULL,reason_code=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(now(),line['parcel_id']))
                        event(c,line['parcel_id'],'Transit' if doc['kind']=='transfer' else line['initial_status'],doc['reference']+' · départ physique déclaré',u)
            elif action=='receive':
                tracking=text(d,'tracking',maxlen=80).upper()
                line=next((l for l in doc['lines'] if l['tracking'].upper()==tracking),None)
                if not line:raise Error('Ce colis ne figure pas dans ce document.',404)
                if line['received_at']:return jsonify(ok=True,already_received=True)
                if doc['status'] not in ['En transit','Partiellement reçu']:raise Error('Confirmez le départ du document avant réception.',409)
                p=parcel(c,line['parcel_id'],u)
                if doc['kind']!='return':guard(c,p,False)
                c.execute('UPDATE ops_document_lines SET received_at=?,received_by=? WHERE id=?',(now(),u['id'],line['id']))
                complete=doc['received']+1==doc['count']
                c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Reçu' if complete else 'Partiellement reçu',now() if complete else None,did))
                c.execute('UPDATE parcels SET current_hub_id=?,ops_revision=ops_revision+1 WHERE id=?',(doc['destination_hub_id'],p['id']))
                received_status='Réceptionné' if doc['kind']=='transfer' else 'Au hub'
                if doc['kind']!='return':c.execute("UPDATE parcels SET status=?,next_attempt_at=NULL,reason_code=NULL,updated_at=? WHERE id=?",(received_status,now(),p['id']))
                if complete:c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,))
                event(c,p['id'],p['status'] if doc['kind']=='return' else received_status,doc['reference']+' · réception physique déclarée',u)
                audit(c,did,u,'Colis reçu',{'tracking':tracking,'parcel_id':p['id']})
            else:raise Error('Action inconnue.',404)
            return jsonify(ok=True,already_received=False)

    @app.post(P+'/assignments/preview')
    @auth('admin')
    def ops_assignment_preview():
        d=body();pids=ids(d);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');dr=enabled_user(c,d.get('driver_id'),'livreur');rows=[]
            for pid in pids:
                p=parcel(c,pid,u);guard(c,p)
                if p['status'] in ['Livré','Retourné','Refusé']:raise Error('Affectation groupée réservée aux colis non clôturés.')
                if p['status']=='Reçu par le livreur' and p['driver_id']!=dr['id']:raise Error('Prise en charge déjà déclarée. Indiquez l’état réel de remise avant la réaffectation.',409)
                rows.append({'id':pid,'tracking':p['tracking'],'old_driver_id':p['driver_id'],'revision':p['ops_revision'],'status':p['status']})
            token=secrets.token_hex(16)
            c.execute('INSERT INTO ops_batch_previews(token,owner_id,driver_id,parcel_ids,snapshot,created_at) VALUES(?,?,?,?,?,?)',(token,u['id'],dr['id'],json.dumps(pids),json.dumps(rows),now()))
            return jsonify(token=token,driver=dict(dr),parcels=rows)

    @app.post(P+'/assignments/<token>/confirm')
    @auth('admin')
    def ops_assignment_confirm(token):
        u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');draft=c.execute('SELECT * FROM ops_batch_previews WHERE token=? AND owner_id=?',(token,u['id'])).fetchone()
            if not draft:raise Error('Aperçu introuvable.',404)
            if draft['committed_at']:return jsonify(ok=True,already_created=True)
            if datetime.fromisoformat(draft['created_at'])<datetime.now()-timedelta(minutes=30):raise Error('Aperçu expiré.',409)
            dr=enabled_user(c,draft['driver_id'],'livreur')
            for item in json.loads(draft['snapshot']):
                p=parcel(c,item['id'],u)
                if p['ops_revision']!=item['revision'] or p['status']!=item['status']:raise Error('Un colis a changé. Recréez un aperçu.',409)
                if 'damage_hold_open' in services and services['damage_hold_open'](c,p['id']):raise Error('Colis '+p['tracking']+' : incident endommagé à traiter avant affectation.',409)
                change(c,p,{'driver_id':dr['id']},u)
                c.execute('UPDATE parcels SET driver_id=?,updated_at=? WHERE id=?',(dr['id'],now(),p['id']))
                event(c,p['id'],p['status'],'Affectation groupée au livreur '+dr['name'],u)
            c.execute('UPDATE ops_batch_previews SET committed_at=? WHERE token=?',(now(),token))
            return jsonify(ok=True,already_created=False)

    @app.route(P+'/notifications',methods=['GET','PATCH'])
    @auth()
    def ops_notifications():
        u=user()
        with conn() as c:
            if request.method=='PATCH':
                d=body()
                if d.get('all') is True:c.execute('UPDATE ops_notifications SET read_at=COALESCE(read_at,?) WHERE user_id=?',(now(),u['id']))
                else:c.execute('UPDATE ops_notifications SET read_at=COALESCE(read_at,?) WHERE user_id=? AND id=?',(now(),u['id'],integer(d.get('id'))))
            return jsonify(items=[dict(r) for r in c.execute('SELECT * FROM ops_notifications WHERE user_id=? ORDER BY id DESC LIMIT 200',(u['id'],))],unread=c.execute('SELECT count(*) FROM ops_notifications WHERE user_id=? AND read_at IS NULL',(u['id'],)).fetchone()[0])

    @app.post(P+'/parcels/<int:pid>/tickets')
    @auth()
    def ops_create_ticket(pid):
        d=body();u=user();priority=d.get('priority','Normale')
        if priority not in ['Basse','Normale','Haute']:raise Error('Priorité invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');p=parcel(c,pid,u)
            category,key,fingerprint,attachments=prepare_claim(d,Error)
            if key:
                prior=c.execute('SELECT * FROM claim_requests WHERE user_id=? AND request_key=?',(u['id'],key)).fetchone()
                if prior:
                    if prior['parcel_id']!=pid or prior['fingerprint']!=fingerprint:raise Error('Cette clé correspond à une autre réclamation.',409)
                    return jsonify(ok=True,id=prior['ticket_id'],already_created=True)
            tid=c.execute('INSERT INTO tickets(user_id,subject,category,created_at) VALUES(?,?,?,?)',(u['id'],text(d,'subject',maxlen=180), category,now())).lastrowid
            c.execute('INSERT INTO messages(ticket_id,user_id,body,created_at) VALUES(?,?,?,?)',(tid,u['id'],text(d,'body',maxlen=3000),now()))
            c.execute('INSERT INTO ops_ticket_links(ticket_id,parcel_id,priority) VALUES(?,?,?)',(tid,pid,priority))
            for f in attachments:c.execute('INSERT INTO claim_attachments(ticket_id,name,mime,content,sha256,size,created_at) VALUES(?,?,?,?,?,?,?)',(tid,f['name'],f['mime'],f['content'],f['sha256'],f['size'],now()))
            if key:c.execute('INSERT INTO claim_requests(user_id,request_key,parcel_id,fingerprint,ticket_id) VALUES(?,?,?,?,?)',(u['id'],key,pid,fingerprint,tid))
            for row in c.execute("SELECT id FROM users WHERE role='admin' AND active=1"):notify(c,row['id'],'Réclamation liée à un colis',p['tracking']+' · TKT-'+str(tid),pid)
            return jsonify(ok=True,id=tid)

    @app.patch(P+'/tickets/<int:tid>')
    @auth('admin')
    def ops_ticket_assignment(tid):
        d=body();priority=d.get('priority');u=user()
        if priority not in ['Basse','Normale','Haute']:raise Error('Priorité invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM ops_ticket_links WHERE ticket_id=?',(tid,)).fetchone():raise Error('Réclamation liée introuvable.',404)
            assignee=enabled_user(c,d.get('assigned_to'),'admin')
            c.execute('UPDATE ops_ticket_links SET priority=?,assigned_to=? WHERE ticket_id=?',(priority,assignee['id'],tid));notify(c,assignee['id'],'Réclamation affectée','TKT-'+str(tid))
        return jsonify(ok=True)

    @app.get(P+'/analytics')
    @auth('admin')
    def ops_analytics():
        end=request.args.get('to') or datetime.now().date().isoformat();start=request.args.get('from') or (datetime.now()-timedelta(days=6)).date().isoformat()
        try:
            a,b=datetime.strptime(start,'%Y-%m-%d'),datetime.strptime(end,'%Y-%m-%d')
            if a.strftime('%Y-%m-%d')!=start or b.strftime('%Y-%m-%d')!=end or a>b or (b-a).days>365:raise ValueError()
        except ValueError:raise Error('Période invalide (366 jours maximum).')
        with conn() as c:
            drivers=[]
            for u in c.execute("SELECT id,name,active FROM users WHERE role='livreur' ORDER BY name").fetchall():
                assigned=c.execute('SELECT count(*) FROM ops_assignments WHERE new_driver_id=? AND substr(created_at,1,10) BETWEEN ? AND ?',(u['id'],start,end)).fetchone()[0]
                attempts=c.execute("SELECT count(*) total,COALESCE(sum(outcome='Livré'),0) delivered FROM ops_attempts WHERE driver_id=? AND substr(created_at,1,10) BETWEEN ? AND ?",(u['id'],start,end)).fetchone()
                drivers.append({**dict(u),'assignment_events':assigned,'attempts':attempts['total'],'delivered_attempts':attempts['delivered']})
            unknown=c.execute("SELECT count(*) total,COALESCE(sum(outcome='Livré'),0) delivered FROM ops_attempts WHERE driver_id IS NULL AND substr(created_at,1,10) BETWEEN ? AND ?",(start,end)).fetchone()
            if unknown['total']:drivers.append(dict(id=None,name='Sans livreur affecté',active=0,assignment_events=0,attempts=unknown['total'],delivered_attempts=unknown['delivered']))
            daily=[dict(r) for r in c.execute("SELECT substr(a.created_at,1,10) day,a.driver_id,u.name driver,count(*) attempts,sum(a.outcome='Livré') delivered FROM ops_attempts a LEFT JOIN users u ON u.id=a.driver_id WHERE substr(a.created_at,1,10) BETWEEN ? AND ? GROUP BY day,a.driver_id ORDER BY day DESC,driver",(start,end))]
            hubs=[{**dict(h),'parcels_here':c.execute('SELECT count(*) FROM parcels WHERE current_hub_id=?',(h['id'],)).fetchone()[0],'expected':c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.destination_hub_id=? AND l.active=1 AND l.received_at IS NULL AND d.status IN ('En transit','Partiellement reçu')",(h['id'],)).fetchone()[0]} for h in c.execute('SELECT * FROM ops_hubs ORDER BY name').fetchall()]
            hub_activity=[]
            for h in hubs:
                departed=c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.source_hub_id=? AND substr(d.dispatched_at,1,10) BETWEEN ? AND ?",(h['id'],start,end)).fetchone()[0]
                received=c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.destination_hub_id=? AND d.kind!='return' AND substr(l.received_at,1,10) BETWEEN ? AND ?",(h['id'],start,end)).fetchone()[0]
                hub_activity.append(dict(id=h['id'],name=h['name'],departed=departed,received=received))
            daily_assignments=[dict(r) for r in c.execute("SELECT substr(a.created_at,1,10) day,a.new_driver_id driver_id,u.name driver,count(*) assignment_events FROM ops_assignments a JOIN users u ON u.id=a.new_driver_id WHERE substr(a.created_at,1,10) BETWEEN ? AND ? GROUP BY day,a.new_driver_id ORDER BY day DESC,driver",(start,end))]
            return jsonify(drivers=drivers,daily=daily,hubs=hubs,hub_activity=hub_activity,daily_assignments=daily_assignments,period_from=start,period_to=end,started_at=c.execute("SELECT value FROM settings WHERE key='ops_started_at'").fetchone()[0])
