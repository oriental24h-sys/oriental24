"""Current delivery contact and per-parcel support contact. Never copies competitor contacts."""
import re
from flask import request,jsonify

def register_parcel_contacts(app,services):
    conn,auth,user,parcel,event,now,text,Error=(services[k] for k in ['conn','auth','user','parcel','event','now','text','APIError'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS support_contacts(id INTEGER PRIMARY KEY,name TEXT NOT NULL,phone TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,revision INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS parcel_support(parcel_id INTEGER PRIMARY KEY REFERENCES parcels(id),contact_id INTEGER REFERENCES support_contacts(id),revision INTEGER NOT NULL DEFAULT 0,updated_by INTEGER REFERENCES users(id),updated_at TEXT);
        CREATE TABLE IF NOT EXISTS support_contact_audit(id INTEGER PRIMARY KEY,contact_id INTEGER NOT NULL REFERENCES support_contacts(id),actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,created_at TEXT NOT NULL);
        ''')
    def enrich(c,p):
        row=c.execute('''SELECT ci.name city,cl.name client,cl.company company,
            dr.name driver,dr.phone driver_phone,dr.active driver_active,
            (SELECT label FROM ops_reasons WHERE code=p.reason_code) reason_label,
            sp.contact_id support_contact_id,COALESCE(sp.revision,0) support_revision,
            sc.name support_name,sc.phone support_phone,sc.active support_active
            FROM parcels p JOIN cities ci ON ci.id=p.city_id JOIN users cl ON cl.id=p.client_id
            LEFT JOIN users dr ON dr.id=p.driver_id
            LEFT JOIN parcel_support sp ON sp.parcel_id=p.id LEFT JOIN support_contacts sc ON sc.id=sp.contact_id
            WHERE p.id=?''',(p['id'],)).fetchone()
        result={**p,**dict(row)}
        if p.get('driver_returned'):result.update(driver=None,driver_phone=None,driver_active=None)
        return result
    services['parcel_contact_info']=enrich
    def body():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def check_revision(value,expected):
        if isinstance(value,bool) or not isinstance(value,int):raise Error('Version entière requise.')
        if value!=expected:raise Error('Données modifiées. Actualisez avant de confirmer.',409)
    @app.get('/api/support-contacts')
    @auth('admin')
    def support_contacts_list():
        with conn() as c:return jsonify([dict(r) for r in c.execute('SELECT * FROM support_contacts ORDER BY active DESC,name,id')])
    @app.post('/api/support-contacts')
    @auth('admin')
    def support_contact_create():return save_contact(None)
    @app.patch('/api/support-contacts/<int:cid>')
    @auth('admin')
    def support_contact_update(cid):return save_contact(cid)
    def save_contact(cid):
        d=body();u=user();name=text(d,'name',maxlen=120);phone=text(d,'phone',maxlen=40)
        if not re.fullmatch(r'\+?[0-9]{9,15}',re.sub(r'[ ()-]','',phone)):raise Error('Téléphone invalide : 9 à 15 chiffres, indicatif + facultatif.')
        active=d.get('active',True)
        if not isinstance(active,bool):raise Error('État actif invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if cid is None:
                cid=c.execute('INSERT INTO support_contacts(name,phone,active,created_at) VALUES(?,?,?,?)',(name,phone,int(active),now())).lastrowid
            else:
                r=c.execute('SELECT * FROM support_contacts WHERE id=?',(cid,)).fetchone()
                if not r:raise Error('Contact support introuvable.',404)
                check_revision(d.get('revision'),r['revision'])
                c.execute('UPDATE support_contacts SET name=?,phone=?,active=?,revision=revision+1 WHERE id=?',(name,phone,int(active),cid))
            c.execute('INSERT INTO support_contact_audit(contact_id,actor_id,action,created_at) VALUES(?,?,?,?)',(cid,u['id'],'Coordonnées support enregistrées',now()))
            return jsonify(ok=True,id=cid)
    @app.patch('/api/parcels/<int:pid>/support')
    @auth('admin')
    def parcel_support_assign(pid):
        d=body();u=user();cid=d.get('contact_id')
        if cid is not None and (isinstance(cid,bool) or not isinstance(cid,int) or cid<=0):raise Error('Contact support invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');p=parcel(c,pid,u);old=c.execute('SELECT * FROM parcel_support WHERE parcel_id=?',(pid,)).fetchone()
            check_revision(d.get('revision'),old['revision'] if old else 0)
            contact=c.execute('SELECT * FROM support_contacts WHERE id=? AND active=1',(cid,)).fetchone() if cid else None
            if cid and not contact:raise Error('Choisissez un contact support actif.')
            if (old['contact_id'] if old else None)==cid:return jsonify(ok=True,changed=False)
            # Contact routing is independent from financial/transport state: no money, status,
            # driver, financial date or operational revision is changed by this action.
            c.execute('INSERT INTO parcel_support(parcel_id,contact_id,revision,updated_by,updated_at) VALUES(?,?,1,?,?) ON CONFLICT(parcel_id) DO UPDATE SET contact_id=excluded.contact_id,revision=parcel_support.revision+1,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(pid,cid,u['id'],now()))
            event(c,pid,p['status'],'Support affecté : '+contact['name'] if contact else 'Affectation support retirée',u)
            return jsonify(ok=True,changed=True)
