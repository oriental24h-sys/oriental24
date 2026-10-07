import os, sqlite3, secrets, csv, io, re, base64
from datetime import datetime, timedelta
from functools import wraps
from contextlib import contextmanager
from pathlib import Path
from flask import Flask, request, jsonify, session, render_template, Response
from werkzeug.security import generate_password_hash, check_password_hash

BASE = os.path.dirname(__file__)
app = Flask(__name__)
from runtime import configure
DB = configure(app, BASE)
from parcel_statuses import STATUSES, DRIVER_TRANSITIONS, policy as status_policy
from billing import driver_paid_sql
import client_types

def now(): return datetime.now().isoformat(timespec='seconds')
@contextmanager
def conn():
    c = sqlite3.connect(DB, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise
    finally:
        c.close()

def init_db():
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,phone TEXT DEFAULT '',company TEXT DEFAULT '',active INTEGER DEFAULT 1,team_lead_id INTEGER REFERENCES users(id),portal_token TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS cities(id INTEGER PRIMARY KEY,name TEXT UNIQUE NOT NULL,region TEXT NOT NULL,delivery INTEGER DEFAULT 1,pickup INTEGER DEFAULT 1,fee REAL NOT NULL,return_fee REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS parcels(id INTEGER PRIMARY KEY,tracking TEXT,client_id INTEGER REFERENCES users(id),driver_id INTEGER REFERENCES users(id),recipient TEXT,phone TEXT,address TEXT,city_id INTEGER REFERENCES cities(id),amount REAL,fee REAL,return_fee REAL,status TEXT DEFAULT 'Créé',product TEXT DEFAULT '',note TEXT DEFAULT '',created_at TEXT,updated_at TEXT,invoice_id INTEGER,time_window TEXT DEFAULT '',cod_ack_at TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,parcel_id INTEGER REFERENCES parcels(id),actor_id INTEGER REFERENCES users(id),status TEXT,note TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS tickets(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),subject TEXT,category TEXT,status TEXT DEFAULT 'Ouvert',created_at TEXT);
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,ticket_id INTEGER REFERENCES tickets(id),user_id INTEGER REFERENCES users(id),body TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS pickups(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),city_id INTEGER REFERENCES cities(id),address TEXT,phone TEXT,count INTEGER,date TEXT,status TEXT DEFAULT 'Demandé',created_at TEXT);
        CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES users(id),cod REAL,fees REAL,total REAL,status TEXT DEFAULT 'À régler',created_at TEXT,paid_at TEXT);
        CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES users(id),name TEXT,reference TEXT,quantity INTEGER DEFAULT 0,created_at TEXT);
        CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY,product_id INTEGER REFERENCES products(id),actor_id INTEGER REFERENCES users(id),delta INTEGER,note TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,parcel_id INTEGER REFERENCES parcels(id),user_id INTEGER REFERENCES users(id),amount REAL,reason TEXT,status TEXT DEFAULT 'En attente',created_at TEXT);
        CREATE TABLE IF NOT EXISTS pod_media(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),kind TEXT NOT NULL,mime TEXT NOT NULL,content BLOB NOT NULL,actor_id INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS pallets(id INTEGER PRIMARY KEY,code TEXT UNIQUE,source TEXT,destination TEXT,transport TEXT,count INTEGER,status TEXT DEFAULT 'En transit',created_at TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        ''')
        if 'team_lead_id' not in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:c.execute('ALTER TABLE users ADD COLUMN team_lead_id INTEGER REFERENCES users(id)')
        if 'portal_token' not in {r['name'] for r in c.execute('PRAGMA table_info(users)')}:c.execute('ALTER TABLE users ADD COLUMN portal_token TEXT')
        if 'time_window' not in {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}:c.execute("ALTER TABLE parcels ADD COLUMN time_window TEXT DEFAULT ''")
        if 'cod_ack_at' not in {r['name'] for r in c.execute('PRAGMA table_info(parcels)')}:c.execute('ALTER TABLE parcels ADD COLUMN cod_ack_at TEXT')
        client_types.migrate(c)
        c.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)',('dataset_kind','demo' if app.config['DEMO_MODE'] else 'production'))
        if not app.config['DEMO_MODE'] or c.execute('SELECT count(*) FROM users').fetchone()[0]: return
        
        t=now()
        for name,email,role,company in [('Administrateur','admin@oriental24.ma','admin','ORIENTAL24'),('Yasmine Amrani','client@oriental24.ma','client','Maison Zina'),('Amine El Idrissi','livreur@oriental24.ma','livreur','ORIENTAL24'),('Sara Bennani','sara@example.test','client','Studio Safran'),('Youssef Alaoui','youssef@example.test','livreur','ORIENTAL24')]:
            c.execute('INSERT INTO users(name,email,password,role,company,phone,created_at) VALUES(?,?,?,?,?,?,?)',(name,email,generate_password_hash('Oriental24!Demo'),role,company,'0600000000',t))
        # v1.5.0 « Équipe » : la démo illustre un chef d'équipe — Youssef est sous-livreur d'Amine.
        c.execute('UPDATE users SET team_lead_id=3 WHERE email=?',('youssef@example.test',))
        for name,fee in [('Oujda',25),('Berkane',30),('Nador',35),('Taourirt',35),('Jerada',35),('Saïdia',30),('Driouch',40),('Figuig',45)]:
            c.execute('INSERT INTO cities(name,region,fee,return_fee) VALUES(?,?,?,?)',(name,'Oriental',fee,10))
        c.execute('INSERT INTO settings VALUES(?,?)',('announcement','Bienvenue chez ORIENTAL24. Votre partenaire de proximité dans l’Oriental.'))
        recipients=['Salma A.','Mohamed B.','Imane R.','Yassine M.','Nadia S.','Omar K.','Hajar L.','Mehdi T.','Rania F.','Anas D.']
        # v1.5.5 « Radar fraude » : un numéro distinct par destinataire (agrégat par téléphone lisible en démo).
        rphones=['0610001001','0610001002','0610001003','0610001004','0610001005','0610001006','0610001007','0610001008','0610001009','0610001010']
        for i in range(48):
            d=(datetime.now()-timedelta(days=i%14,hours=i%8)).isoformat(timespec='seconds')
            status=['En livraison','Livré','Livré','Créé','Programmé','Ramassé','Au hub','Livré','Retourné','Refusé','Livré','Livré'][i%12]
            city=i%8+1; fee=c.execute('SELECT fee FROM cities WHERE id=?',(city,)).fetchone()[0]
            client=2 if i%4 else 4; driver=3 if i%3 else 5
            if status=='Créé': driver=None
            c.execute('INSERT INTO parcels(tracking,client_id,driver_id,recipient,phone,address,city_id,amount,fee,return_fee,status,product,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (f'O24-{100001+i}',client,driver,recipients[i%10],rphones[i%10],f'{12+i}, avenue Exemple (démonstration)',city,[249,390,180,520,129,299][i%6],fee,10,status,['Accessoires maison','Coffret soin','Article textile'][i%3],'Données fictives de démonstration',d,d))
            pid=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',(pid,client,'Créé','Colis enregistré',d))
            if status!='Créé': c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',(pid,1,status,'Mise à jour de démonstration',d))
        c.execute('INSERT INTO tickets(user_id,subject,category,created_at) VALUES(?,?,?,?)',(2,'Précision sur une adresse de livraison','Livraison',t))
        c.execute('INSERT INTO messages(ticket_id,user_id,body,created_at) VALUES(?,?,?,?)',(1,2,'Bonjour, comment transmettre un complément d’adresse au livreur ?',t))
        c.execute('INSERT INTO pickups(user_id,city_id,address,phone,count,date,created_at) VALUES(?,?,?,?,?,?,?)',(2,1,'12, avenue Exemple','0600000000',4,datetime.now().date().isoformat(),t))
        c.execute('INSERT INTO products(client_id,name,reference,quantity,created_at) VALUES(?,?,?,?,?)',(2,'Coffret artisanal','ZINA-001',24,t))
        c.execute('INSERT INTO pallets(code,source,destination,transport,count,created_at) VALUES(?,?,?,?,?,?)',('PAL-1001','Hub Oujda','Hub Berkane','Navette régionale',12,t))
        # v1.5.5 « Radar fraude » : deux numéros répétitivement en échec (refus / retours) pour illustrer le score.
        c.execute("UPDATE parcels SET status='Refusé' WHERE recipient='Anas D.'")
        c.execute("UPDATE parcels SET status='Retourné' WHERE recipient='Rania F.'")

        # v1.5.3 « Fin de journée » : activité d'aujourd'hui visible dans la démo (2 livrés Amine, 1 tournée Youssef).
        c.execute('UPDATE parcels SET updated_at=? WHERE id IN (SELECT id FROM parcels ORDER BY id LIMIT 3)',(now(),))
        # v1.5.4 « Paiements vendeurs » : factures client ouvertes de différentes anciennetés pour illustrer l'aging 30/60/90.
        def seed_client_invoice(cid,count,age_days,livres_only=True):
            cond="status='Livré'" if livres_only else "status IN ('Retourné','Refusé')"
            ps=c.execute(f"SELECT * FROM parcels WHERE client_id=? AND invoice_id IS NULL AND {cond} ORDER BY id LIMIT ?",(cid,count)).fetchall()
            if not ps:return
            cod=round(sum(p['amount'] for p in ps if p['status']=='Livré'),2)
            fees=round(sum(p['fee'] if p['status']=='Livré' else p['return_fee'] for p in ps),2)
            at=(datetime.now()-timedelta(days=age_days)).isoformat(timespec='seconds')
            cur=c.execute('INSERT INTO invoices(client_id,cod,fees,total,created_at) VALUES(?,?,?,?,?)',(cid,cod,fees,round(cod-fees,2),at))
            for p in ps:c.execute('UPDATE parcels SET invoice_id=? WHERE id=?',(cur.lastrowid,p['id']))
        # Maison Zina : créances à verser réparties sur les quatre tranches ; Studio Safran : petites dettes retours (« À encaisser »).
        seed_client_invoice(2,2,20);seed_client_invoice(2,2,45);seed_client_invoice(2,2,75);seed_client_invoice(2,3,105)
        seed_client_invoice(4,2,75,False);seed_client_invoice(4,3,105,False)
init_db()

class APIError(Exception):
    def __init__(self,msg,code=400): self.msg,self.code=msg,code
@app.errorhandler(APIError)
def api_error(e): return jsonify(error=e.msg),e.code
@app.errorhandler(sqlite3.IntegrityError)
def integrity(e): return jsonify(error='Cette valeur existe déjà ou une référence est invalide.'),409
@app.after_request
def headers(r):
    r.headers['X-Content-Type-Options']='nosniff'
    r.headers['Referrer-Policy']='same-origin'
    if request.path.startswith('/api/'): r.headers['Cache-Control']='no-store'
    return r

def user():
    with conn() as c:
        u=c.execute('SELECT id,name,email,role,company,phone,active,client_type,agent_hub_id FROM users WHERE id=?',(session.get('uid',-1),)).fetchone()
        if not u or not u['active']:
            session.clear();raise APIError('Connectez-vous pour continuer.',401)
        security_check_session(c,u['id'])
        return dict(u)
def auth(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapped(*a,**kw):
            u=user()
            if roles and u['role'] not in roles: raise APIError('Accès non autorisé.',403)
            if request.method not in ('GET','HEAD'):
                supplied=request.headers.get('X-CSRF-Token','');expected=session.get('csrf')
                if not isinstance(expected,str) or not expected or not supplied or not secrets.compare_digest(supplied.encode(),expected.encode()):
                    raise APIError('Session invalide. Rechargez la page.',403)
            return fn(*a,**kw)
        return wrapped
    return deco

def text(d,k,required=True,maxlen=300):
    v=str(d.get(k,'')).strip()
    if required and not v: raise APIError('Champ obligatoire : '+k)
    if len(v)>maxlen: raise APIError('Champ trop long : '+k)
    return v

def number(d,k,minimum=0,maximum=1000000,integer=False):
    try:
        v=float(d.get(k,''))
        if not minimum<=v<=maximum or (integer and v!=int(v)): raise ValueError()
        return int(v) if integer else round(v,2)
    except (ValueError,TypeError,OverflowError): raise APIError('Valeur invalide : '+k)

def team_member_ids(c,lead_id):
    return [r[0] for r in c.execute("SELECT id FROM users WHERE team_lead_id=? AND role='livreur' AND active=1",(lead_id,))]
def scope(u,alias='p',c=None):
    if u['role']=='agent': return '1=0',[]  # Agents travaillent via les palettes, jamais la liste globale des colis.
    if u['role']=='client': return f'{alias}.client_id=?',[u['id']]
    if u['role']=='livreur':
        # v1.5.0 : un chef d'équipe voit (et pilote via les transitions livreur) les colis de ses livreurs actifs.
        ids=[u['id']]+(team_member_ids(c,u['id']) if c is not None else [])
        inlist=','.join('?'*len(ids))
        return f'{alias}.driver_id IN ({inlist}) AND NOT EXISTS(SELECT 1 FROM driver_receipts dw WHERE dw.parcel_id={alias}.id AND dw.driver_id={alias}.driver_id) AND NOT ({driver_paid_sql(alias)})',ids
    return '1=1',[]

def parcel(c,pid,u):
    cond,args=scope(u,c=c)
    p=c.execute(f'SELECT p.*,EXISTS(SELECT 1 FROM driver_receipts dw WHERE dw.parcel_id=p.id AND dw.driver_id=p.driver_id) driver_returned,EXISTS(SELECT 1 FROM ops_document_lines ol WHERE ol.parcel_id=p.id AND ol.active=1) operations_locked,EXISTS(SELECT 1 FROM driver_statement_lines dl WHERE dl.parcel_id=p.id AND dl.active=1) financial_locked FROM parcels p WHERE p.id=? AND {cond}',[pid]+args).fetchone()
    if not p: raise APIError('Colis introuvable.',404)
    return dict(p)
def event(c,pid,status,note,u):
    c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',(pid,u['id'],status,note,now()))
    if 'ops_notify_event' in globals(): ops_notify_event(c,pid,status,u)
    if 'tech_notify_event' in globals(): tech_notify_event(c,pid,status,u)
def list_parcels(c,u):
    cond,args=scope(u,c=c)
    return [dict(r) for r in c.execute(f'''SELECT p.*,EXISTS(SELECT 1 FROM driver_receipts dw WHERE dw.parcel_id=p.id AND dw.driver_id=p.driver_id) driver_returned,EXISTS(SELECT 1 FROM ops_document_lines ol WHERE ol.parcel_id=p.id AND ol.active=1) operations_locked,EXISTS(SELECT 1 FROM driver_statement_lines dl WHERE dl.parcel_id=p.id AND dl.active=1) financial_locked,ci.name city,cl.name client,cl.company company,CASE WHEN EXISTS(SELECT 1 FROM driver_receipts dw WHERE dw.parcel_id=p.id AND dw.driver_id=p.driver_id) THEN NULL ELSE dr.name END driver,(SELECT label FROM ops_reasons WHERE code=p.reason_code) reason_label
    FROM parcels p JOIN cities ci ON ci.id=p.city_id JOIN users cl ON cl.id=p.client_id LEFT JOIN users dr ON dr.id=p.driver_id WHERE {cond} ORDER BY p.created_at DESC,p.id DESC''',args)]

@app.route('/')
@app.route('/login')
@app.route('/app')
def index(): return render_template('index.html',runtime_config={'demo':app.config['DEMO_MODE'],'registration':app.config['PUBLIC_REGISTRATION'],'version':'1.12.0'})

@app.route('/healthz')
def healthz(): return {'status':'ok','version':'1.12.0','production':app.config['PRODUCTION_MODE']}
PUBLIC_CONTACT_KEYS=('public_whatsapp','public_phone','public_email','public_address','public_hours')   # v1.4.20 · page publique
@app.get('/api/public')
def public():
    with conn() as c:
        contact={r['key']:r['value'] for r in c.execute('SELECT key,value FROM settings WHERE key IN (%s)'%','.join('?'*len(PUBLIC_CONTACT_KEYS)),PUBLIC_CONTACT_KEYS)}
        return jsonify(cities=[dict(r) for r in c.execute('SELECT * FROM cities WHERE delivery=1 ORDER BY name')],brand='ORIENTAL24',contact=contact)
@app.post('/api/login')
def login():
    d=request.get_json() or {}
    with conn() as c:u=c.execute('SELECT * FROM users WHERE lower(email)=?',(str(d.get('email','')).lower().strip(),)).fetchone()
    valid=check_password_hash(u['password'] if u else security_dummy_hash,str(d.get('password','')))
    if not u or not valid or not u['active']:
        security_login_failed(u['id'] if u else None)
        raise APIError('Adresse e-mail ou mot de passe incorrect.',401)
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        fresh=c.execute('SELECT password,active FROM users WHERE id=?',(u['id'],)).fetchone()
        if not fresh or not fresh['active'] or fresh['password']!=u['password']:raise APIError('Identifiants modifiés. Reconnectez-vous.',401)
        security_issue(c,u['id'])
    return jsonify(ok=True)
@app.post('/api/register')
def register():
    d=request.get_json() or {}; email=text(d,'email').lower(); password=text(d,'password',maxlen=128)
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email): raise APIError('Adresse e-mail invalide.')
    if len(password)<10: raise APIError('Le mot de passe doit contenir au moins 10 caractères.')
    with conn() as c:
        kind=client_types.parse_type(d.get('client_type','vendeur'),'client',APIError)
        cur=c.execute('INSERT INTO users(name,email,password,role,company,phone,created_at,client_type) VALUES(?,?,?,?,?,?,?,?)',(text(d,'name'),email,generate_password_hash(password),'client',text(d,'company'),text(d,'phone'),now(),kind))
        client_types.audit(c,cur.lastrowid,cur.lastrowid,None,kind,'Inscription client',now)
        security_issue(c,cur.lastrowid,'Compte créé et session ouverte')
    return jsonify(ok=True)
@app.post('/api/logout')
@auth()
def logout():
    u=user()
    with conn() as c:security_logout(c,u['id'])
    return jsonify(ok=True)
@app.get('/api/bootstrap')
@auth()
def bootstrap():
    u=user()
    with conn() as c:
        if u['role']=='admin':
            users=[dict(r) for r in c.execute("SELECT id,name,email,role,company,phone,active,client_type,agent_hub_id,team_lead_id FROM users ORDER BY id")]
        elif u['role']=='livreur':
            users=[dict(r) for r in c.execute("SELECT id,name,email,role,phone,active,team_lead_id FROM users WHERE team_lead_id=? AND role='livreur' ORDER BY name",(u['id'],))]
        else:users=[]
        cities=[dict(r) for r in c.execute('SELECT * FROM cities ORDER BY name')]
        settings={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
        hubs=[dict(r) for r in c.execute('SELECT h.id,h.name,h.active,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id ORDER BY h.name')] if u['role'] in ('admin','agent') else []
        return jsonify(user=u,csrf=session['csrf'],cities=cities,users=users,parcels=list_parcels(c,u),statuses=STATUSES,status_policy=status_policy(),settings=settings,hubs=hubs)
@app.get('/api/parcels/<int:pid>')
@auth()
def detail(pid):
    with conn() as c:
        c.execute('BEGIN')
        p=parcel(c,pid,user())
        ev=[dict(r) for r in c.execute('SELECT e.*,u.name actor FROM events e JOIN users u ON u.id=e.actor_id WHERE parcel_id=? ORDER BY e.id DESC',(pid,))]
        media=[dict(r) for r in c.execute('SELECT pm.id,pm.kind,pm.mime,pm.created_at,u.name actor FROM pod_media pm JOIN users u ON u.id=pm.actor_id WHERE parcel_id=? ORDER BY pm.id DESC',(pid,))]
        return jsonify(parcel=parcel_contact_info(c,p),events=ev,media=media)
@app.post('/api/parcels')
@auth('admin','client')
def create_parcel():
    d=request.get_json() or {};u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        city=c.execute('SELECT * FROM cities WHERE id=? AND delivery=1',(d.get('city_id'),)).fetchone()
        if not city: raise APIError('Choisissez une ville ouverte à la livraison.')
        cid=u['id'] if u['role']=='client' else d.get('client_id')
        if not c.execute("SELECT id FROM users WHERE id=? AND role='client' AND active=1",(cid,)).fetchone(): raise APIError('Client invalide.')
        phone=text(d,'phone')
        if not re.fullmatch(r'\+?[\d\s-]{9,18}',phone): raise APIError('Numéro de téléphone invalide.')
        track=client_types.tracking_for(c,cid,d.get('tracking'),APIError);t=now()
        fee,ret=globals()['tariff_fees_for'](c,int(cid),dict(city)) if 'tariff_fees_for' in globals() else (city['fee'],city['return_fee'])
        cur=c.execute('INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,product,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(track,cid,text(d,'recipient'),phone,text(d,'address'),city['id'],number(d,'amount'),fee,ret,text(d,'product',False),text(d,'note',False),t,t))
        event(c,cur.lastrowid,'Créé','Colis enregistré',u)
    return jsonify(ok=True,tracking=track)
@app.patch('/api/parcels/<int:pid>')
@auth('admin','livreur')
def update_parcel(pid):
    d=request.get_json() or {};u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        p=parcel(c,pid,u)
        if c.execute('SELECT 1 FROM driver_statement_lines WHERE parcel_id=? AND active=1',(pid,)).fetchone():
            raise APIError('Ce colis est figé dans un relevé livreur. Annulez le relevé avant toute correction.',409)
        if p['invoice_id']: raise APIError('Ce colis est facturé et ne peut plus être modifié.')
        ops_change(c,p,d,u)
        if 'driver_id' in d:
            if u['role']=='livreur':
                team=[u['id']]+team_member_ids(c,u['id'])
                if len(team)<2: raise APIError('Action réservée à l’administration.',403)
                if p['driver_id'] not in team: raise APIError('Ce colis ne fait pas partie de votre équipe.',403)
                tgt=d['driver_id'] or p['driver_id']
                if tgt not in team: raise APIError('Réaffectation limitée à votre équipe.',403)
            elif u['role']!='admin': raise APIError('Action réservée à l’administration.',403)
            if d['driver_id'] and 'damage_hold_open' in globals() and globals()['damage_hold_open'](c,pid):
                raise APIError('Colis réceptionné endommagé : Admin doit traiter l’incident avant toute affectation.',409)
            did=d['driver_id'] or None
            if did and not c.execute("SELECT id FROM users WHERE id=? AND role='livreur' AND active=1",(did,)).fetchone(): raise APIError('Livreur invalide.')
            c.execute('UPDATE parcels SET driver_id=?,updated_at=? WHERE id=?',(did,now(),pid))
            event(c,pid,p['status'],'Affectation du livreur mise à jour',u)
        if 'status' in d:
            s=d['status']
            if s not in STATUSES: raise APIError('Statut invalide.')
            if u['role']=='livreur':
                transitions=DRIVER_TRANSITIONS
                if s not in transitions.get(p['status'],[]): raise APIError('Transition non autorisée pour ce colis.')
            if s=='Livré' and p.get('otp_required'):
                import secrets as _sec
                if not _sec.compare_digest(str(d.get('otp','')),str(p.get('otp_code') or '')):
                    raise APIError('Code client à 4 chiffres requis ou incorrect pour confirmer la livraison.',400)
            note=text(d,'note',False)
            if s=='Livré' and p.get('otp_required'):c.execute('UPDATE parcels SET otp_verified_at=? WHERE id=?',(now(),pid))
            c.execute('UPDATE parcels SET status=?,note=?,updated_at=? WHERE id=?',(s,note or p['note'],now(),pid))
            event(c,pid,s,note or 'Statut mis à jour',u)
    return jsonify(ok=True)
@app.post('/api/parcels/bulk-assign')
@auth('admin','livreur')
def bulk_assign_parcels():
    """v1.5.1 « Dispatch » : affectation en masse de colis à un livreur (ou désaffectation Admin).
    Admin : cible = n'importe quel livreur actif (ou null = désaffecter).
    Chef d'équipe : cible = soi ou un membre actif, colis bornés à son équipe.
    Les colis indisponibles sont ignorés avec motif (rapport), le reste est affecté."""
    d=request.get_json() or {};u=user()
    ids=d.get('parcel_ids')
    if not isinstance(ids,list) or not any(type(x) is int for x in ids) or len(ids)>200: raise APIError('Sélectionnez entre 1 et 200 colis.')
    did=d.get('driver_id')
    if did is not None and type(did) is not int: raise APIError('Livreur invalide.')
    # v1.5.7 « RDV heure creuse » : créneau de livraison optionnel (08h→20h, '' = aucun).
    tw=str(d.get('time_window') or '')
    if tw and (not tw.isdigit() or not (8<=int(tw)<=20)): raise APIError('Créneau RDV invalide (08h à 20h).')
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        target=None
        if did is not None:
            target=c.execute("SELECT id,name FROM users WHERE id=? AND role='livreur' AND active=1",(did,)).fetchone()
            if not target: raise APIError('Livreur invalide ou inactif.')
        team=None
        if u['role']=='livreur':
            team=[u['id']]+team_member_ids(c,u['id'])
            if len(team)<2: raise APIError('Action réservée à l’administration.',403)
            if did is None: raise APIError('Choisissez un membre de votre équipe.')
            if did not in team: raise APIError('Affectation limitée à votre équipe.',403)
        assigned=[];skipped=[]
        for raw in [x for x in ids if type(x) is int][:200]:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(raw,)).fetchone()
            if not p: skipped.append(dict(id=raw,tracking='—',reason='Colis introuvable'));continue
            if team is not None and p['driver_id'] not in team:
                skipped.append(dict(id=p['id'],tracking=p['tracking'],reason='Hors de votre équipe'));continue
            if c.execute('SELECT 1 FROM driver_statement_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone():
                skipped.append(dict(id=p['id'],tracking=p['tracking'],reason='Figé dans un relevé livreur'));continue
            if p['invoice_id']:
                skipped.append(dict(id=p['id'],tracking=p['tracking'],reason='Facturé'));continue
            if 'damage_hold_open' in globals() and globals()['damage_hold_open'](c,p['id']):
                skipped.append(dict(id=p['id'],tracking=p['tracking'],reason='Incident endommagé ouvert'));continue
            if p['status']=='Reçu par le livreur' and p['driver_id']!=(did or None):
                skipped.append(dict(id=p['id'],tracking=p['tracking'],reason='Reçu par le livreur : indiquez d’abord l’état réel de remise'));continue
            c.execute('UPDATE parcels SET driver_id=?,updated_at=?,time_window=? WHERE id=?',(did,now(),tw if did is not None else '',p['id']))
            event(c,p['id'],p['status'],f"Affectation en masse{' → '+target['name'] if target else ' (désaffecté)'}{(' · RDV '+tw+'h-'+str(int(tw)+1)+'h') if tw else ''}",u)
            assigned.append(p['id'])
        if not assigned and skipped: raise APIError('Aucun colis ne peut être affecté : '+skipped[0]['reason'],409)
        driver_name=target['name'] if target else '(désaffecté)'
    return jsonify(ok=True,assigned=assigned,skipped=skipped,driver_id=did,driver=driver_name)
@app.post('/api/parcels/<int:pid>/media')
@auth('admin','livreur')
def upload_parcel_media(pid):
    d=request.get_json(silent=True) or {}
    kind=d.get('kind');url=d.get('data_url') or ''
    if kind not in ['photo','signature']:raise APIError('Type de preuve invalide.')
    m=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)',url)
    if not m:raise APIError('Image invalide : JPEG, PNG ou WebP en data-URL.')
    raw=base64.b64decode(m.group(2),validate=True)
    if not raw or len(raw)>1500000:raise APIError('Image trop lourde (1,5 Mo maximum après compression).')
    u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        p=parcel(c,pid,u)
        c.execute('UPDATE parcels SET ops_revision=ops_revision+1 WHERE id=?',(pid,))
        cur=c.execute('INSERT INTO pod_media(parcel_id,kind,mime,content,actor_id,created_at) VALUES(?,?,?,?,?,?)',(pid,kind,'image/'+m.group(1),raw,u['id'],now()))
        event(c,pid,p['status'],'Preuve ajoutée : '+('photo du colis' if kind=='photo' else 'signature du destinataire'),u)
    return jsonify(ok=True,id=cur.lastrowid)

@app.post('/api/parcels/<int:pid>/cod-ack')
@auth('client')
def parcel_cod_ack(pid):
    """v1.6.0 « Accusé d'encaissement » : le vendeur confirme manuellement avoir reçu
    le règlement COD d'un colis livré (encore non facturé). Trace en chronologie."""
    u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM parcels WHERE id=? AND client_id=?',(pid,u['id'])).fetchone()
        if not p: raise APIError('Colis introuvable dans votre périmètre.',404)
        if p['cod_ack_at']: return jsonify(ok=True,ack=p['cod_ack_at'],already=True)
        if p['status']!='Livré': raise APIError('Accusé réservé aux colis livrés.',409)
        if p['invoice_id']: raise APIError('Colis déjà facturé : le règlement se suit en Facturation.',409)
        c.execute('UPDATE parcels SET cod_ack_at=? WHERE id=?',(now(),pid))
        event(c,pid,p['status'],'Accusé d’encaissement COD enregistré par le vendeur',u)
    return jsonify(ok=True,ack=now())
@app.get('/api/parcels/<int:pid>/media/<int:mid>')
@auth()
def parcel_media(pid,mid):
    with conn() as c:
        parcel(c,pid,user())
        r=c.execute('SELECT * FROM pod_media WHERE id=? AND parcel_id=?',(mid,pid)).fetchone()
        if not r:raise APIError('Preuve introuvable.',404)
        return Response(r['content'],mimetype=r['mime'])
@app.get('/api/audit')
@auth('admin')
def audit_log():
    with conn() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ops_audit'").fetchone():return jsonify(entries=[])
        rows=c.execute('SELECT a.*,u.name actor FROM ops_audit a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 300').fetchall()
    return jsonify(entries=[dict(r) for r in rows])
@app.patch('/api/parcels/<int:pid>/city')
@auth('admin')
def update_parcel_city(pid):
    d=request.get_json(silent=True)
    if not isinstance(d,dict) or set(d)!={'city_id','revision'}:raise APIError('Ville et version requises, sans autre modification.')
    cid=d['city_id']
    if type(cid) is not int or cid<=0 or cid>2147483647:raise APIError('Identifiant de ville invalide.')
    u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE');p=parcel(c,pid,u)
        if p['invoice_id'] or p['financial_locked'] or p['operations_locked'] or p['status'] in ['Livré','Retourné','Refusé']:
            raise APIError('Ville non modifiable : colis clôturé, facturé, rapproché ou lié à un document actif.',409)
        if type(d['revision']) is not int or d['revision']!=p['ops_revision']:raise APIError('Le colis a changé. Actualisez la fiche avant de confirmer.',409)
        city=c.execute('SELECT * FROM cities WHERE id=? AND delivery=1',(cid,)).fetchone()
        if not city:raise APIError('Choisissez une ville ouverte à la livraison.')
        if cid==p['city_id']:return jsonify(ok=True,changed=False)
        previous=c.execute('SELECT name FROM cities WHERE id=?',(p['city_id'],)).fetchone()['name']
        ops_change(c,p,{'revision':d['revision']},u)
        # Existing parcel fees are frozen amounts, not the destination city's current tariff.
        c.execute('UPDATE parcels SET city_id=?,updated_at=? WHERE id=?',(cid,now(),pid))
        event(c,pid,p['status'],'Ville de livraison modifiée : '+previous+' → '+city['name']+' · montant et frais du colis conservés',u)
        return jsonify(ok=True,changed=True)

@app.get('/api/export')
@auth()
def export():
    with conn() as c: rows=list_parcels(c,user())
    out=io.StringIO(); w=csv.writer(out,delimiter=';'); w.writerow(['Suivi','Destinataire','Téléphone','Ville','COD (MAD)','Frais (MAD)','Statut','Livreur'])
    def safe(v):
        v=str(v if v is not None else '')
        return "'"+v if v.startswith(('=','+','-','@','\t','\r')) else v
    for r in rows:w.writerow([safe(r[k]) for k in ['tracking','recipient','phone','city','amount','fee','status','driver']])
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="ORIENTAL24-colis.csv"'})
@app.route('/api/cities',methods=['POST'])
@auth('admin')
def add_city(): return save_city(None)
@app.route('/api/cities/<int:cid>',methods=['PATCH'])
@auth('admin')
def edit_city(cid): return save_city(cid)
def save_city(cid):
    d=request.get_json() or {}
    vals=(text(d,'name'),text(d,'region'),int(bool(d.get('delivery'))),int(bool(d.get('pickup'))),number(d,'fee',maximum=10000),number(d,'return_fee',maximum=10000))
    with conn() as c:
        if cid:
            if not c.execute('SELECT id FROM cities WHERE id=?',(cid,)).fetchone():raise APIError('Ville introuvable.',404)
            c.execute('UPDATE cities SET name=?,region=?,delivery=?,pickup=?,fee=?,return_fee=? WHERE id=?',vals+(cid,))
        else:c.execute('INSERT INTO cities(name,region,delivery,pickup,fee,return_fee) VALUES(?,?,?,?,?,?)',vals)
    return jsonify(ok=True)
@app.patch('/api/settings')
@auth('admin')
def settings():
    d=request.get_json() or {}
    with conn() as c:
        if 'announcement' in d:c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('announcement',text(d,'announcement',False,600)))
        # v1.4.20 · coordonnées de la page publique (bouton WhatsApp, pied de page) ; vide = masqué.
        for k in PUBLIC_CONTACT_KEYS:
            if k in d:
                v=text(d,k,False,300 if k=='public_hours' else 200)
                if k in ('public_whatsapp','public_phone') and v and not re.fullmatch(r'[+\d][\d\s().-]{6,24}',v):raise APIError('Numéro invalide : '+k)
                if k=='public_email' and v and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',v):raise APIError('E-mail invalide.')
                if v:c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,v))
                else:c.execute('DELETE FROM settings WHERE key=?',(k,))   # vide = masqué (en démonstration : coordonnées fictives par défaut)
        # Seuils des alertes de retard, en heures ; 0 désactive la catégorie.
        # v1.22.0 · ancienneté minimale (jours) d'un colis chez nous avant retour au vendeur.
        if 'return_week_days' in d:
            v=d['return_week_days']
            if type(v) is not int or not 1<=v<=90:raise APIError('Seuil invalide : return_week_days (1 à 90 jours).')
            c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',('return_week_days',str(v)))
        for k in ('alert_transit_hours','alert_partial_hours','alert_unassigned_hours'):
            if k in d:
                v=d[k]
                if type(v) is not int or not 0<=v<=720:raise APIError('Seuil invalide : '+k+' (0 à 720 heures).')
                c.execute('INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)',(k,str(v)))
    return jsonify(ok=True)
@app.route('/api/users',methods=['POST'])
@auth('admin')
def add_user():
    d=request.get_json() or {}; role=d.get('role')
    if role not in ['client','livreur','agent']:raise APIError('Rôle invalide.')
    pw=text(d,'password',maxlen=128)
    if len(pw)<10:raise APIError('10 caractères minimum pour le mot de passe.')
    email=text(d,'email').lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise APIError('Adresse e-mail invalide.')
    kind=client_types.parse_type(d.get('client_type','vendeur'),role,APIError)
    with conn() as c:
        hub_id=None
        if role=='agent':
            hub_id=d.get('agent_hub_id')
            if type(hub_id) is not int or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone():raise APIError('Choisissez le hub de réception actif de cet agent.')
        lead=None
        if role=='livreur':
            lead=d.get('team_lead_id')
            if lead:
                if type(lead) is not int or lead<=0 or not c.execute("SELECT 1 FROM users WHERE id=? AND role='livreur' AND active=1 AND team_lead_id IS NULL",(lead,)).fetchone():raise APIError('Chef d’équipe invalide : choisissez un livreur actif non rattaché.')
        uid=c.execute('INSERT INTO users(name,email,password,role,company,phone,created_at,client_type,agent_hub_id,team_lead_id) VALUES(?,?,?,?,?,?,?,?,?,?)',(text(d,'name'),email,generate_password_hash(pw),role,text(d,'company',False),text(d,'phone'),now(),kind,hub_id,lead)).lastrowid
        if role=='client':client_types.audit(c,uid,session['uid'],None,kind,'Création administrative',now)
    return jsonify(ok=True,id=uid)
@app.patch('/api/users/<int:uid>')
@auth('admin')
def edit_user(uid):
    d=request.get_json() or {}
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        v=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not v or v['role']=='admin':raise APIError('Ce compte ne peut pas être modifié ici.')
        if 'client_type' in d:client_types.change_type(c,v,d['client_type'],session['uid'],APIError,now)
        if v['role']=='livreur':
            if v['driver_archived'] and d.get('active'):raise APIError('Désarchivez le livreur depuis sa fiche.',409)
            c.execute('UPDATE users SET driver_blocked=?,driver_revision=driver_revision+1 WHERE id=?',(int(not bool(d.get('active'))),uid))
        hub_id=v['agent_hub_id']
        if v['role']=='agent':
            hub_id=d.get('agent_hub_id',hub_id)
            if type(hub_id) is not int or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub_id,)).fetchone():raise APIError('Choisissez un hub de réception actif pour cet agent.')
        if v['role']=='livreur' and 'team_lead_id' in d:
            lead=d['team_lead_id'] or None
            if lead==uid:raise APIError('Un livreur ne peut pas être son propre chef d’équipe.')
            if lead and not c.execute("SELECT 1 FROM users WHERE id=? AND role='livreur' AND active=1 AND team_lead_id IS NULL",(lead,)).fetchone():raise APIError('Chef d’équipe invalide : livreur actif non rattaché.')
            if c.execute('SELECT 1 FROM users WHERE team_lead_id=? AND active=1',(uid,)).fetchone() and lead:raise APIError('Ce livreur est lui-même chef d’équipe : détachez d’abord son équipe.')
            c.execute('UPDATE users SET team_lead_id=? WHERE id=?',(lead,uid))
        c.execute('UPDATE users SET name=?,phone=?,company=?,active=?,agent_hub_id=? WHERE id=?',(text(d,'name'),text(d,'phone'),text(d,'company',False),int(bool(d.get('active'))),hub_id,uid))
        if not d.get('active') or d.get('password'):
            security_revoke_user(c,uid,'Sessions révoquées par modification administrative',session['uid'])
        if d.get('password'):
            pw=text(d,'password',maxlen=128)
            if len(pw)<10:raise APIError('10 caractères minimum pour le mot de passe.')
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(pw),uid))
    return jsonify(ok=True)
@app.patch('/api/profile')
@auth()
def profile():
    d=request.get_json() or {};u=user()
    if 'client_type' in d:raise APIError('Le type de client se gère par l’administration.',403)
    with conn() as c:
        if u['role']=='livreur':c.execute('UPDATE users SET driver_revision=driver_revision+1 WHERE id=?',(u['id'],))
        c.execute('UPDATE users SET name=?,phone=?,company=? WHERE id=?',(text(d,'name'),text(d,'phone'),text(d,'company',False),u['id']))
        if d.get('password'):
            old=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
            if not check_password_hash(old,str(d.get('current_password',''))):raise APIError('Mot de passe actuel incorrect.')
            pw=text(d,'password',maxlen=128)
            if len(pw)<10:raise APIError('10 caractères minimum.')
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(pw),u['id']))
            security_password_changed(c,u['id'])
    return jsonify(ok=True)
@app.route('/api/tickets',methods=['GET','POST'])
@auth()
def tickets():
    u=user()
    with conn() as c:
        if request.method=='POST':
            d=request.get_json() or {}
            cur=c.execute('INSERT INTO tickets(user_id,subject,category,created_at) VALUES(?,?,?,?)',(u['id'],text(d,'subject'),text(d,'category'),now()))
            c.execute('INSERT INTO messages(ticket_id,user_id,body,created_at) VALUES(?,?,?,?)',(cur.lastrowid,u['id'],text(d,'body',maxlen=3000),now()))
            return jsonify(ok=True)
        sql='SELECT t.*,u.name author,l.parcel_id,l.priority,l.assigned_to,l.first_response_at,p.tracking FROM tickets t JOIN users u ON u.id=t.user_id LEFT JOIN ops_ticket_links l ON l.ticket_id=t.id LEFT JOIN parcels p ON p.id=l.parcel_id';args=[]
        if u['role']!='admin':sql+=' WHERE t.user_id=?';args=[u['id']]
        return jsonify([dict(r) for r in c.execute(sql+' ORDER BY t.id DESC',args)])
@app.route('/api/tickets/<int:tid>',methods=['GET','POST','PATCH'])
@auth()
def ticket(tid):
    u=user();d=request.get_json(silent=True) or {}
    with conn() as c:
        t=c.execute('SELECT t.*,l.parcel_id,l.priority,l.assigned_to,l.first_response_at,p.tracking FROM tickets t LEFT JOIN ops_ticket_links l ON l.ticket_id=t.id LEFT JOIN parcels p ON p.id=l.parcel_id WHERE t.id=?',(tid,)).fetchone()
        if not t or (u['role']!='admin' and t['user_id']!=u['id']):raise APIError('Ticket introuvable.',404)
        if request.method=='POST':
            c.execute('INSERT INTO messages(ticket_id,user_id,body,created_at) VALUES(?,?,?,?)',(tid,u['id'],text(d,'body',maxlen=3000),now()))
            if u['role']=='admin':
                c.execute('UPDATE ops_ticket_links SET first_response_at=COALESCE(first_response_at,?) WHERE ticket_id=?',(now(),tid))
                c.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',(t['user_id'],'Réponse à votre réclamation','TKT-'+str(tid),now()))
        if request.method=='PATCH':
            if u['role']!='admin':raise APIError('Action réservée à l’administration.',403)
            if d.get('status') not in ['Ouvert','En cours','Résolu']:raise APIError('Statut invalide.')
            c.execute('UPDATE tickets SET status=? WHERE id=?',(d['status'],tid))
        return jsonify(ticket=dict(t),attachments=claim_attachments(c,tid),messages=[dict(r) for r in c.execute('SELECT m.*,u.name author,u.role role FROM messages m JOIN users u ON u.id=m.user_id WHERE ticket_id=? ORDER BY m.id',(tid,))])
@app.route('/api/pickups',methods=['GET','POST'])
@auth('admin','client')
def pickups():
    u=user()
    with conn() as c:
        if request.method=='POST':
            d=request.get_json() or {}
            if not c.execute('SELECT id FROM cities WHERE id=? AND pickup=1',(d.get('city_id'),)).fetchone():raise APIError('Ramassage indisponible dans cette ville.')
            date=text(d,'date')
            try:
                if datetime.fromisoformat(date).date()<datetime.now().date():raise ValueError()
            except ValueError:raise APIError('Choisissez une date à partir d’aujourd’hui.')
            c.execute('INSERT INTO pickups(user_id,city_id,address,phone,count,date,created_at) VALUES(?,?,?,?,?,?,?)',(u['id'],d['city_id'],text(d,'address'),text(d,'phone'),number(d,'count',1,10000,True),date,now()))
            return jsonify(ok=True)
        cond='1=1' if u['role']=='admin' else 'p.user_id=?';args=[] if u['role']=='admin' else [u['id']]
        return jsonify([dict(r) for r in c.execute(f'SELECT p.*,u.name client,ci.name city FROM pickups p JOIN users u ON u.id=p.user_id JOIN cities ci ON ci.id=p.city_id WHERE {cond} ORDER BY p.id DESC',args)])
@app.patch('/api/pickups/<int:pid>')
@auth('admin')
def change_pickup(pid):
    d=request.get_json() or {}
    if d.get('status') not in ['Demandé','Planifié','Ramassé','Annulé']:raise APIError('Statut invalide.')
    with conn() as c:c.execute('UPDATE pickups SET status=? WHERE id=?',(d['status'],pid))
    return jsonify(ok=True)
@app.route('/api/invoices',methods=['GET','POST'])
@auth('admin','client')
def invoices():
    u=user()
    with conn() as c:
        if request.method=='POST':
            if u['role']!='admin':raise APIError('Action réservée à l’administration.',403)
            cid=(request.get_json() or {}).get('client_id')
            # BEGIN IMMEDIATE prevents concurrent generation of the same parcel invoice.
            c.execute('BEGIN IMMEDIATE')
            ps=c.execute("SELECT * FROM parcels WHERE client_id=? AND invoice_id IS NULL AND status IN ('Livré','Retourné','Refusé')",(cid,)).fetchall()
            if not ps:raise APIError('Aucun colis clôturé non facturé pour ce client.')
            cod=round(sum(p['amount'] for p in ps if p['status']=='Livré'),2)
            fees=round(sum(p['fee'] if p['status']=='Livré' else p['return_fee'] for p in ps),2)
            cur=c.execute('INSERT INTO invoices(client_id,cod,fees,total,created_at) VALUES(?,?,?,?,?)',(cid,cod,fees,round(cod-fees,2),now()))
            client_invoice_info(c,c.execute('SELECT * FROM invoices WHERE id=?',(cur.lastrowid,)).fetchone())
            for p in ps:
                c.execute('UPDATE parcels SET invoice_id=? WHERE id=?',(cur.lastrowid,p['id']))
                event(c,p['id'],p['status'],f'Facture FAC-{cur.lastrowid:04d} générée',u)
            return jsonify(ok=True)
        cond='1=1' if u['role']=='admin' else 'i.client_id=?';args=[] if u['role']=='admin' else [u['id']]
        return jsonify([client_invoice_info(c,r) for r in c.execute(f'SELECT i.*,u.name client,u.company company FROM invoices i JOIN users u ON u.id=i.client_id WHERE {cond} ORDER BY i.id DESC',args)])
@app.route('/api/invoices/<int:iid>',methods=['GET','PATCH'])
@auth('admin','client')
def invoice(iid):
    u=user()
    with conn() as c:
        if request.method=='PATCH':c.execute('BEGIN IMMEDIATE')
        i=c.execute('SELECT i.*,u.name client,u.company company FROM invoices i JOIN users u ON u.id=i.client_id WHERE i.id=?',(iid,)).fetchone()
        if not i or (u['role']=='client' and i['client_id']!=u['id']):raise APIError('Facture introuvable.',404)
        if request.method=='PATCH':
            if u['role']!='admin':raise APIError('Accès non autorisé.',403)
            settle_client_invoice(c,i,u)
            i=c.execute('SELECT i.*,u.name client,u.company company FROM invoices i JOIN users u ON u.id=i.client_id WHERE i.id=?',(iid,)).fetchone()
        i=client_invoice_info(c,i)
        return jsonify(**client_invoice_history(c,iid),invoice=i,parcels=[dict(r) for r in c.execute('SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE invoice_id=?',(iid,))])
@app.route('/api/products',methods=['GET','POST'])
@auth('admin','client')
def products():
    u=user()
    with conn() as c:
        if request.method=='POST':
            d=request.get_json() or {};cid=u['id'] if u['role']=='client' else d.get('client_id')
            if not c.execute("SELECT id FROM users WHERE id=? AND role='client'",(cid,)).fetchone():raise APIError('Client invalide.')
            c.execute('INSERT INTO products(client_id,name,reference,created_at) VALUES(?,?,?,?)',(cid,text(d,'name'),text(d,'reference'),now()))
            return jsonify(ok=True)
        cond='1=1' if u['role']=='admin' else 'p.client_id=?';args=[] if u['role']=='admin' else [u['id']]
        return jsonify([{**dict(r),'reserved':reserved_stock(c,r['id']),'available':r['quantity']-reserved_stock(c,r['id'])} for r in c.execute(f'SELECT p.*,u.company company FROM products p JOIN users u ON u.id=p.client_id WHERE {cond} ORDER BY p.id DESC',args)])
@app.route('/api/products/<int:pid>/movements',methods=['GET','POST'])
@auth('admin','client')
def movements(pid):
    u=user()
    with conn() as c:
        if request.method=='POST':c.execute('BEGIN IMMEDIATE')
        p=c.execute('SELECT * FROM products WHERE id=?',(pid,)).fetchone()
        if not p or (u['role']=='client' and p['client_id']!=u['id']):raise APIError('Produit introuvable.',404)
        if request.method=='POST':
            if u['role']!='admin':raise APIError('Les mouvements physiques sont validés par l’administration.',403)
            d=request.get_json() or {};delta=number(d,'delta',-100000,100000,True)
            if not delta or p['quantity']+delta<reserved_stock(c,pid):raise APIError('Mouvement invalide ou stock insuffisant.')
            c.execute('UPDATE products SET quantity=quantity+? WHERE id=?',(delta,pid))
            c.execute('INSERT INTO movements(product_id,actor_id,delta,note,created_at) VALUES(?,?,?,?,?)',(pid,u['id'],delta,text(d,'note'),now()))
        return jsonify([dict(r) for r in c.execute('SELECT m.*,u.name actor FROM movements m JOIN users u ON u.id=m.actor_id WHERE product_id=? ORDER BY m.id DESC',(pid,))])
@app.route('/api/requests',methods=['GET','POST'])
@auth()
def price_requests():
    u=user()
    with conn() as c:
        if request.method=='POST':
            d=request.get_json() or {};p=parcel(c,d.get('parcel_id'),u)
            if p['invoice_id'] or p['status'] in ['Livré','Retourné','Refusé']:raise APIError('Le prix d’un colis clôturé ne peut pas être modifié.')
            c.execute('INSERT INTO requests(parcel_id,user_id,amount,reason,created_at) VALUES(?,?,?,?,?)',(p['id'],u['id'],number(d,'amount'),text(d,'reason'),now()))
            event(c,p['id'],p['status'],'Demande de modification de prix déposée',u)
            return jsonify(ok=True)
        cond='1=1' if u['role']=='admin' else 'r.user_id=?';args=[] if u['role']=='admin' else [u['id']]
        return jsonify([dict(r) for r in c.execute(f'SELECT r.*,p.tracking,p.amount old_amount,u.name author FROM requests r JOIN parcels p ON p.id=r.parcel_id JOIN users u ON u.id=r.user_id WHERE {cond} ORDER BY r.id DESC',args)])
@app.patch('/api/requests/<int:rid>')
@auth('admin')
def approve_request(rid):
    d=request.get_json() or {};s=d.get('status')
    if s not in ['Acceptée','Refusée']:raise APIError('Statut invalide.')
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute("SELECT * FROM requests WHERE id=? AND status='En attente'",(rid,)).fetchone()
        if not r:raise APIError('Demande déjà traitée ou introuvable.')
        p=parcel(c,r['parcel_id'],user())
        if s=='Acceptée':
            if p['invoice_id'] or p['status'] in ['Livré','Retourné','Refusé']:raise APIError('Ce colis est déjà clôturé.')
            c.execute('UPDATE parcels SET amount=?,updated_at=? WHERE id=?',(r['amount'],now(),p['id']))
        c.execute('UPDATE requests SET status=? WHERE id=?',(s,rid))
        event(c,p['id'],p['status'],f'Demande de prix {s.lower()} : {r["amount"]} MAD',user())
    return jsonify(ok=True)
@app.route('/api/pallets',methods=['GET','POST'])
@auth('admin')
def pallets():
    with conn() as c:
        if request.method=='POST':
            d=request.get_json() or {}
            c.execute('INSERT INTO pallets(code,source,destination,transport,count,created_at) VALUES(?,?,?,?,?,?)',('PAL-'+secrets.token_hex(3).upper(),text(d,'source'),text(d,'destination'),text(d,'transport'),number(d,'count',1,10000,True),now()))
            return jsonify(ok=True)
        return jsonify([dict(r) for r in c.execute('SELECT * FROM pallets ORDER BY id DESC')])
@app.patch('/api/pallets/<int:pid>')
@auth('admin')
def receive_pallet(pid):
    with conn() as c:c.execute("UPDATE pallets SET status='Réceptionnée' WHERE id=?",(pid,))
    return jsonify(ok=True)

from tariffs import register_tariffs
register_tariffs(app, globals())
from operations import register_operations
register_operations(app, globals())
from driver_finance import register_driver_finance
register_driver_finance(app, globals())
from driver_days import register_driver_days
register_driver_days(app, globals())
from logistics import register_logistics
register_logistics(app, globals())
from fulfillment import register_fulfillment
register_fulfillment(app, globals())
from client_finance import register_client_finance
register_client_finance(app, globals())
from vendor_payables import register_vendor_payables
register_vendor_payables(app, globals())
from accounts import register_accounts
register_accounts(app, globals())
from security import register_security
register_security(app, globals())
from parcel_contacts import register_parcel_contacts
register_parcel_contacts(app, globals())

from claims import register_claims,claim_attachments
register_claims(app, globals())

from announcements import register_announcements
register_announcements(app, globals())

from driver_workspace import register_driver_workspace
register_driver_workspace(app, globals())

from invoice_profile import register_invoice_profile
register_invoice_profile(app, globals())

from billing import register_billing
register_billing(app, globals())

from partner_palettes import register_partner_palettes
register_partner_palettes(app, globals())
from return_palettes import register_return_palettes
register_return_palettes(app, globals())

from return_scan import register_return_scan
register_return_scan(app, globals())
from fusion_reception import register_fusion_reception
register_fusion_reception(app, globals())
from palette_console import register_palette_console
register_palette_console(app, globals())
from tour_control import register_tour_control
register_tour_control(app, globals())
from advanced_tech import register_advanced_tech
register_advanced_tech(app, globals())
from smart_delivery import register_smart_delivery
register_smart_delivery(app, globals())
from smart_warehouse import register_smart_warehouse
register_smart_warehouse(app, globals())
from connected_ops import register_connected_ops
register_connected_ops(app, globals())

from reception_extras import register_reception_extras
register_reception_extras(app, globals())

from partner_api import register_partner_api
register_partner_api(app, globals())

from mobile_app import register_mobile_app
register_mobile_app(app, globals())

from contact_log import register_contact_log
register_contact_log(app, globals())

# Optional demo seeding for the reception agent: set ORIENTAL24_DEMO_AGENT=1 on demo
# instances only (e.g. the preview). Idempotent; production databases are never seeded.
if app.config['DEMO_MODE'] and os.environ.get('ORIENTAL24_DEMO_AGENT')=='1':
    t=now()
    with conn() as c:
        hub=c.execute('SELECT id FROM ops_hubs WHERE active=1 ORDER BY id LIMIT 1').fetchone()
        if hub:hid=hub['id']
        else:
            city=c.execute('SELECT id FROM cities ORDER BY id LIMIT 1').fetchone()
            hid=c.execute("INSERT INTO ops_hubs(name,city_id,address,active,created_at) VALUES(?,?,?,1,?)",('Hub Oujda · démo',city['id'],'Zone logistique — données fictives',t)).lastrowid
        if not c.execute("SELECT 1 FROM users WHERE email='agent@oriental24.ma'").fetchone():
            c.execute('INSERT INTO users(name,email,password,role,company,phone,active,client_type,agent_hub_id,created_at) VALUES(?,?,?,?,?,?,1,?,?,?)',('Nadia Réception','agent@oriental24.ma',generate_password_hash('Oriental24!Demo'),'agent','ORIENTAL24','0600000000','vendeur',hid,t))


# — v1.6.2 « Portail vendeur » : suivi public en lecture seule, sécurisé par un lien à clé.
def portal_token_for(c,u):
    tok=u['portal_token'] if 'portal_token' in u.keys() else None
    if tok: return tok
    tok=secrets.token_urlsafe(24)
    c.execute('UPDATE users SET portal_token=? WHERE id=?',(tok,u['id']))
    return tok
@app.get('/api/portal-link')
@auth('client','admin')
def portal_link():
    u=user()
    with conn() as c:
        ro=user_row(c,u['id']) if 'user_row' in globals() else c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone()
        return jsonify(url='/portail/'+portal_token_for(c,ro))
@app.post('/api/portal-link/rotate')
@auth('client','admin')
def portal_rotate():
    u=user()
    with conn() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('UPDATE users SET portal_token=? WHERE id=?',(secrets.token_urlsafe(24),u['id']))
        ro=c.execute('SELECT portal_token FROM users WHERE id=?',(u['id'],)).fetchone()
    return jsonify(url='/portail/'+ro['portal_token'])

from markupsafe import escape as _mesc
@app.route('/portail/<token>')
def portal_public(token):
    ok = isinstance(token,str) and re.fullmatch(r'[A-Za-z0-9_\-]{24,64}',token or '')
    with conn() as c:
        u=c.execute("SELECT * FROM users WHERE portal_token=? AND role='client' AND active=1",(token,)).fetchone() if ok else None
        if not u or 'portal_token' not in u.keys():
            return Response("""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ORIENTAL24 — Portail</title></head><body style="font-family:system-ui,sans-serif;background:#0a1124;color:#fff;display:grid;place-items:center;min-height:100vh"><div style="max-width:420px;text-align:center"><h1>Lien introuvable</h1><p style="opacity:.75">Ce lien de portail n'existe pas ou a été révoqué. Demandez un nouveau lien à votre contact ORIENTAL24.</p></div></body></html>""",404,content_type='text/html; charset=utf-8')
        rows=[dict(r) for r in c.execute("SELECT p.tracking,p.status,p.amount,ci.name city,p.updated_at FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id WHERE p.client_id=? ORDER BY p.updated_at DESC LIMIT 200",(u['id'],))]
    def esc(x): return str(_mesc(str(x if x is not None else '')))
    body=[]
    for r in rows:
        body.append('<tr><td class="mono">'+esc(r['tracking'])+'</td><td>'+esc(r['city'])+'</td><td><span class="st">'+esc(r['status'])+'</span></td><td class="num">'+format(r['amount'],'.2f')+' MAD</td><td class="muted">'+esc(str(r['updated_at'])[:16])+'</td></tr>')
    body=''.join(body)
    page=f"""<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ORIENTAL24 · Suivi {esc(u['company'] or u['name'])}</title><link rel="icon" href="/static/icon.png"><style>
body{{margin:0;font-family:system-ui,-apple-system,sans-serif;background:#f4f6fb;color:#0d1b33}}
header{{background:linear-gradient(135deg,#0a1124,#123c8f);color:#fff;padding:26px 18px}}
header img{{height:34px;display:block;margin-bottom:14px}}
h1{{margin:0;font-size:20px}}.sub{{opacity:.75;font-size:13px;margin-top:6px}}
main{{max-width:900px;margin:0 auto;padding:22px 16px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 8px 30px rgba(13,27,51,.07)}}
th,td{{padding:11px 12px;text-align:left;font-size:13px;border-bottom:1px solid #edf0f7}}
th{{font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:#5a6b8f;background:#f8fafd}}
.mono{{font-family:ui-monospace,Menlo,monospace;font-weight:700;color:#123c8f}}
.num{{font-weight:700;white-space:nowrap}}.muted{{color:#7c8aa8;font-size:12px}}
.st{{background:#eaf0fb;border-radius:999px;padding:3px 10px;font-weight:700;font-size:12px;color:#123c8f;display:inline-block}}
.note{{color:#5a6b8f;font-size:12px;margin:14px 2px}}footer{{text-align:center;color:#8a97b5;font-size:12px;padding:18px}}
</style></head><body><header><img src="/static/wordmark.png" alt="ORIENTAL24"><h1>Suivi de vos expéditions</h1><div class="sub">{esc(u['company'] or u['name'])} · {len(rows)} derniers colis · lecture seule</div></header><main>
<div class="note">Ce lien est privé : ne le partagez pas. Pour plus de détails (chronologie, facturation), ouvrez votre espace client ORIENTAL24.</div>
<table><thead><tr><th>Référence</th><th>Ville</th><th>Statut</th><th>Montant COD</th><th>Mise à jour</th></tr></thead><tbody>{body or '<tr><td colspan="5" class="muted" style="text-align:center">Aucun colis pour le moment.</td></tr>'}</tbody></table>
</main><footer>ORIENTAL24 · Livraison à domicile · Portail en lecture seule, aucune action possible.</footer></body></html>"""
    return Response(page,200,content_type='text/html; charset=utf-8')

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT',3000)),debug=False)

# Production bootstrap (hosts without shell access, e.g. Render free plan):
# ORIENTAL24_BOOTSTRAP_ADMIN="email|nom|mot_de_passe" crée le premier Admin UNE FOIS,
# uniquement si aucun admin actif n'existe encore (jamais en mode demo).
_boot=os.environ.get('ORIENTAL24_BOOTSTRAP_ADMIN','')
if app.config['PRODUCTION_MODE'] and _boot:
    try:
        from runtime import DEMO_EMAILS as _DEMO_EMAILS
        bemail,bname,bpwd=_boot.split('|',2)
        assert '@' in bemail and bname and len(bpwd)>=12,'format attendu : email|nom|mot_de_passe (>= 12 caractères)'
        assert bemail.lower() not in {e.lower() for e in _DEMO_EMAILS},'e-mail réservé à la démo : choisissez votre propre adresse'
        with conn() as c:
            n_admins=c.execute("SELECT count(*) k FROM users WHERE role='admin' AND active=1").fetchone()['k']
            if n_admins==0 and not c.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)",(bemail,)).fetchone():
                c.execute('INSERT INTO users(name,email,password,role,company,phone,active,client_type,created_at) VALUES(?,?,?,?,?,?,1,?,?)',
                    (bname,bemail,generate_password_hash(bpwd),'admin',bname,'', 'vendeur',now()))
                print('Bootstrap : premier administrateur créé pour',bemail,'— changez le mot de passe puis retirez ORIENTAL24_BOOTSTRAP_ADMIN.')
            else:
                print('Bootstrap : administrateur déjà présent, aucune création.')
    except (ValueError,AssertionError) as e:
        print('Bootstrap ignoré :',e)
