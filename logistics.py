"""ORIENTAL24 operational execution. Additive schema, scoped reads and atomic writes.
No external notifications, bank transfers, physical signatures or GPS are simulated here.
"""
import json, secrets, re, hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from flask import request, jsonify

from notification_retention import purge_read_notifications
from claims import prepare_claim
from parcel_statuses import ATTEMPT_SOURCES, ATTEMPT_OUTCOMES
from audit_guard import install_ops_audit_guards, install_departure_reconciliation_guard
from hub_schema import migrate_city_hub_id, assign_cities_to_hub
from hub_cod import resolve_cod_hub
from hub_analytics import install_hub_analytics_schema, hub_operational_metrics, hub_daily_metrics
from hub_access import resolve_routing_hub, central_hub_transfer_allowed, parcel_physically_at_hub, driver_dispatch_allowed, hub_document_lines_at_hub, hub_manager_transfer_scope, ops_manifest_counts, manifest_status_from_counts

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
    generate_password_hash=services['generate_password_hash']
    append_audit_log=services['append_audit_log']
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER NOT NULL REFERENCES cities(id),address TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS ops_hub_name ON ops_hubs(name COLLATE NOCASE);
        CREATE TABLE IF NOT EXISTS hub_cities(
          hub_id INTEGER NOT NULL REFERENCES ops_hubs(id) ON DELETE CASCADE,
          city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
          active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
          is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0,1)),
          created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
          created_at TEXT NOT NULL,
          PRIMARY KEY(hub_id,city_id)
        );
        CREATE INDEX IF NOT EXISTS hub_cities_city_active ON hub_cities(city_id,active,hub_id);
        CREATE INDEX IF NOT EXISTS hub_cities_hub_active ON hub_cities(hub_id,active,city_id);
        CREATE UNIQUE INDEX IF NOT EXISTS hub_cities_one_primary_per_city ON hub_cities(city_id) WHERE is_primary=1;
        CREATE TABLE IF NOT EXISTS ops_reasons(code TEXT PRIMARY KEY,label TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS ops_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),old_driver_id INTEGER,new_driver_id INTEGER,actor_id INTEGER NOT NULL,created_at TEXT NOT NULL,hub_id INTEGER REFERENCES ops_hubs(id));
        CREATE TABLE IF NOT EXISTS ops_attempts(id INTEGER PRIMARY KEY,parcel_id INTEGER NOT NULL REFERENCES parcels(id),driver_id INTEGER,actor_id INTEGER NOT NULL,outcome TEXT NOT NULL,reason_code TEXT,reason_label TEXT,next_attempt_at TEXT,note TEXT NOT NULL,receiver TEXT,amount_cents INTEGER,request_key TEXT NOT NULL UNIQUE,payload_hash TEXT NOT NULL,created_at TEXT NOT NULL,cod_hub_id INTEGER REFERENCES ops_hubs(id),operational_hub_id INTEGER REFERENCES ops_hubs(id));
        CREATE TABLE IF NOT EXISTS ops_documents(id INTEGER PRIMARY KEY,reference TEXT UNIQUE,kind TEXT NOT NULL,client_id INTEGER REFERENCES users(id),driver_id INTEGER REFERENCES users(id),source_hub_id INTEGER REFERENCES ops_hubs(id),destination_hub_id INTEGER REFERENCES ops_hubs(id),client_name TEXT,driver_name TEXT,source_name TEXT,destination_name TEXT,status TEXT NOT NULL DEFAULT 'Préparé',revision INTEGER NOT NULL DEFAULT 1,note TEXT NOT NULL,created_by INTEGER NOT NULL,created_at TEXT NOT NULL,dispatched_at TEXT,completed_at TEXT,cancel_reason TEXT,departure_scan_required INTEGER NOT NULL DEFAULT 0,palette_purpose TEXT NOT NULL DEFAULT 'standard',transport TEXT NOT NULL DEFAULT '',tracking_code TEXT NOT NULL DEFAULT '',lots INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS ops_document_lines(id INTEGER PRIMARY KEY,document_id INTEGER NOT NULL REFERENCES ops_documents(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),tracking TEXT NOT NULL,recipient TEXT NOT NULL,city TEXT NOT NULL,initial_status TEXT NOT NULL,departure_scanned_at TEXT,departure_scanned_by INTEGER REFERENCES users(id),departure_reconciled_at TEXT,departure_reconciled_by INTEGER REFERENCES users(id),departure_reconciliation_reason TEXT,received_at TEXT,received_by INTEGER,active INTEGER NOT NULL DEFAULT 1,return_status TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS ops_one_active_document ON ops_document_lines(parcel_id) WHERE active=1;
        CREATE TABLE IF NOT EXISTS ops_audit(id INTEGER PRIMARY KEY,document_id INTEGER REFERENCES ops_documents(id),actor_id INTEGER NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_notifications(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),parcel_id INTEGER REFERENCES parcels(id),title TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT);
        CREATE INDEX IF NOT EXISTS ops_notice_user ON ops_notifications(user_id,id);
        CREATE INDEX IF NOT EXISTS ops_attempt_parcel ON ops_attempts(parcel_id,id);
        CREATE INDEX IF NOT EXISTS ops_assignment_date ON ops_assignments(created_at,new_driver_id);
        CREATE TABLE IF NOT EXISTS ops_ticket_links(ticket_id INTEGER PRIMARY KEY REFERENCES tickets(id),parcel_id INTEGER NOT NULL REFERENCES parcels(id),priority TEXT NOT NULL,assigned_to INTEGER REFERENCES users(id),first_response_at TEXT);
        CREATE TABLE IF NOT EXISTS ops_batch_previews(token TEXT PRIMARY KEY,owner_id INTEGER NOT NULL,driver_id INTEGER NOT NULL,parcel_ids TEXT NOT NULL,snapshot TEXT NOT NULL,created_at TEXT NOT NULL,committed_at TEXT);
        CREATE TABLE IF NOT EXISTS ops_hub_assignment_keys(actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,payload_hash TEXT NOT NULL,result TEXT NOT NULL,created_at TEXT NOT NULL,PRIMARY KEY(actor_id,request_key));
        ''')
        # Add the direct single-Hub city key. NULL is intentional where no active primary was
        # explicitly selected; route resolution keeps using the Admin-designated Central Hub.
        migrate_city_hub_id(c)
        install_ops_audit_guards(c)
        # Legacy many-to-many rows remain for compatibility during the staged rollout. Keep each
        # Hub's physical city as secondary coverage only; never infer city ownership from creation order.
        for legacy_hub in c.execute('SELECT id,city_id,active FROM ops_hubs ORDER BY id').fetchall():
            if c.execute('SELECT 1 FROM hub_cities WHERE hub_id=? AND city_id=?',(legacy_hub['id'],legacy_hub['city_id'])).fetchone():
                continue
            c.execute('INSERT INTO hub_cities(hub_id,city_id,active,is_primary,created_at) VALUES(?,?,?,?,?)',
                      (legacy_hub['id'],legacy_hub['city_id'],int(bool(legacy_hub['active'])),0,now()))
        document_columns={r['name'] for r in c.execute('PRAGMA table_info(ops_documents)')}
        if 'departure_scan_required' not in document_columns:
            c.execute('ALTER TABLE ops_documents ADD COLUMN departure_scan_required INTEGER NOT NULL DEFAULT 0')
        for key,definition in [('palette_purpose',"TEXT NOT NULL DEFAULT 'standard'"),('transport',"TEXT NOT NULL DEFAULT ''"),('tracking_code',"TEXT NOT NULL DEFAULT ''"),('lots','INTEGER NOT NULL DEFAULT 0')]:
            if key not in document_columns:c.execute(f'ALTER TABLE ops_documents ADD COLUMN {key} {definition}')
        line_columns={r['name'] for r in c.execute('PRAGMA table_info(ops_document_lines)')}
        if 'return_transit_status' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN return_transit_status TEXT')
        if 'return_status' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN return_status TEXT')
        if 'departure_scanned_at' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN departure_scanned_at TEXT')
        if 'departure_scanned_by' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN departure_scanned_by INTEGER')
        if 'departure_reconciled_at' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN departure_reconciled_at TEXT')
        if 'departure_reconciled_by' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN departure_reconciled_by INTEGER')
        if 'departure_reconciliation_reason' not in line_columns:c.execute('ALTER TABLE ops_document_lines ADD COLUMN departure_reconciliation_reason TEXT')
        install_departure_reconciliation_guard(c)
        columns={r['name'] for r in c.execute('PRAGMA table_info(parcels)')}
        for key,definition in [('reason_code','TEXT'),('next_attempt_at','TEXT'),('ops_revision','INTEGER NOT NULL DEFAULT 0'),('current_hub_id','INTEGER REFERENCES ops_hubs(id)'),('origin_hub_id','INTEGER REFERENCES ops_hubs(id)')]:
            if key not in columns:c.execute(f'ALTER TABLE parcels ADD COLUMN {key} {definition}')
        c.execute('CREATE INDEX IF NOT EXISTS parcels_origin_hub_idx ON parcels(origin_hub_id,current_hub_id,status)')
        c.executescript('''
        DROP TRIGGER IF EXISTS parcels_origin_hub_on_physical_arrival;
        CREATE TRIGGER IF NOT EXISTS parcels_origin_hub_on_physical_insert
        AFTER INSERT ON parcels
        WHEN NEW.origin_hub_id IS NULL AND NEW.current_hub_id IS NOT NULL
        BEGIN
          UPDATE parcels SET origin_hub_id=NEW.current_hub_id WHERE id=NEW.id AND origin_hub_id IS NULL;
        END;
        CREATE TRIGGER IF NOT EXISTS parcels_origin_hub_on_physical_arrival
        AFTER UPDATE OF current_hub_id ON parcels
        WHEN NEW.origin_hub_id IS NULL AND NEW.current_hub_id IS NOT NULL
          AND NOT EXISTS(SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
            WHERE l.parcel_id=NEW.id AND d.kind='transfer')
        BEGIN
          UPDATE parcels SET origin_hub_id=NEW.current_hub_id WHERE id=NEW.id AND origin_hub_id IS NULL;
        END;
        ''')
        # Backfill only from documented physical Hub events. City assignment and routing intent
        # are deliberately never used as evidence of original custody.
        if c.execute('SELECT 1 FROM parcels WHERE origin_hub_id IS NULL LIMIT 1').fetchone():
            physical_sql='''
                SELECT l.parcel_id,d.destination_hub_id hub_id,l.received_at event_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.received_at IS NOT NULL AND d.kind='partner_palette' AND d.destination_hub_id IS NOT NULL
                  AND NOT EXISTS(SELECT 1 FROM ops_document_lines x JOIN ops_documents tx ON tx.id=x.document_id
                    WHERE x.parcel_id=l.parcel_id AND tx.kind='transfer')'''
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='driver_receipts'").fetchone():
                physical_sql+=''' UNION ALL SELECT dr.parcel_id,dr.hub_id,dr.received_at FROM driver_receipts dr
                    WHERE dr.hub_id IS NOT NULL AND dr.received_at IS NOT NULL
                      AND NOT EXISTS(SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=dr.parcel_id AND d.kind='transfer')'''
            rows=c.execute(physical_sql+' ORDER BY parcel_id,event_at,hub_id').fetchall()
            events={}
            for r in rows:events.setdefault(r['parcel_id'],[]).append((str(r['event_at']),r['hub_id']))
            for parcel_id,items in events.items():
                first=min(t for t,_ in items);hubs={hid for stamp,hid in items if stamp==first and hid is not None}
                if len(hubs)==1:
                    c.execute('UPDATE parcels SET origin_hub_id=? WHERE id=? AND origin_hub_id IS NULL',(next(iter(hubs)),parcel_id))
        install_hub_analytics_schema(c,now())
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
    def local_manager_hub(c,u):
        hub_id=u.get('agent_hub_id')
        if type(hub_id) is not int or hub_id<=0:raise Error('Ce compte n’est pas rattaché à un Hub actif.',403)
        row=c.execute('SELECT h.id,h.name,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1',(hub_id,)).fetchone()
        if not row:raise Error('Le Hub de ce compte est inactif ou introuvable.',403)
        return dict(row)
    def ensure_home_city_coverage(c,hub_id,city_id,actor_id=None):
        exists=c.execute('SELECT 1 FROM hub_cities WHERE hub_id=? AND city_id=?',(hub_id,city_id)).fetchone()
        if exists:return
        # A Hub's home-city coverage does not make it the city's automatic primary.
        c.execute('INSERT INTO hub_cities(hub_id,city_id,active,is_primary,created_by,created_at) VALUES(?,?,?,?,?,?)',
                  (hub_id,city_id,1,0,actor_id,now()))
    def hub_coverage(c,hub_id):
        return [dict(r) for r in c.execute('''SELECT ci.hub_id,ci.id city_id,1 active,1 is_primary,
                    ci.name city,ci.region,ci.delivery,ci.pickup
             FROM cities ci WHERE ci.hub_id=? ORDER BY ci.name COLLATE NOCASE''',(hub_id,)).fetchall()]
    def create_hub_manager_account(c,hub_id,d,actor):
        name=text(d,'manager_name',maxlen=150)
        email=text(d,'manager_email',maxlen=254).lower()
        phone=text(d,'manager_phone',False,maxlen=40)
        password=text(d,'manager_password',maxlen=128)
        if len(password)<10:raise Error('10 caractères minimum pour le mot de passe du responsable.')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise Error('Adresse e-mail invalide pour le responsable.')
        if c.execute('SELECT 1 FROM users WHERE lower(email)=lower(?)',(email,)).fetchone():raise Error('Cette adresse e-mail est déjà utilisée.',409)
        existing=c.execute("SELECT id,name FROM users WHERE agent_hub_id=? AND role IN ('hub_manager','agent') AND active=1 ORDER BY id LIMIT 1",(hub_id,)).fetchone()
        if existing:raise Error('Ce Hub possède déjà un responsable actif ('+existing['name']+').',409)
        uid=c.execute('''INSERT INTO users(name,email,password,role,company,phone,active,agent_hub_id,created_at)
                         VALUES(?,?,?,'hub_manager','ORIENTAL24',?,1,?,?)''',
                      (name,email,generate_password_hash(password),phone,hub_id,now())).lastrowid
        append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_manager_created',
                         entity_type='hub_manager',entity_id=uid,old_value=None,
                         new_value={'id':uid,'name':name,'email':email,'phone':phone,'hub_id':hub_id,'active':True},
                         metadata={'hub_id':hub_id},created_at=now())
        return uid
    def city_ids_from_body(d):
        raw=d.get('city_ids')
        if raw is None:return None
        if not isinstance(raw,list) or len(raw)>500:raise Error('La liste des villes de couverture est invalide.')
        values=[integer(x,'Ville') for x in raw]
        if len(values)!=len(set(values)):raise Error('Une ville ne peut apparaître qu’une fois.')
        return values
    def current_central_hub(c):
        setting=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
        if not setting:return None,None
        try:hid=int(setting['value'])
        except (TypeError,ValueError):return None,None
        if hid<=0:return None,None
        row=c.execute('SELECT h.id,h.name,h.active,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=?',(hid,)).fetchone()
        return hid,dict(row) if row else None
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
            target=c.execute("SELECT driver_hub_id FROM users WHERE id=? AND role='livreur' AND active=1",(did,)).fetchone() if did else None
            if not target:raise Error('Affectez un livreur actif avant de déclarer la prise en charge.')
            if type(target['driver_hub_id']) is not int or target['driver_hub_id']<=0 or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(target['driver_hub_id'],)).fetchone():raise Error('Le livreur doit être rattaché à un Hub actif avant sa prise en charge.',409)
            if (p['status']!='Reçu par le livreur' or did!=p['driver_id']) and not driver_dispatch_allowed(c,p.get('current_hub_id'),target['driver_hub_id']):
                raise Error('Le colis doit être physiquement enregistré au Hub du livreur avant sa prise en charge.',409)
        if 'driver_id' in d:
            did=integer(d['driver_id']) if d['driver_id'] else None
            if did!=p['driver_id'] and p['status']=='Reçu par le livreur' and d.get('status',p['status'])=='Reçu par le livreur':raise Error('Prise en charge déjà déclarée. Indiquez d’abord l’état réel de remise avant de changer le livreur.',409)
            if did!=p['driver_id']:
                c.execute('INSERT INTO ops_assignments(parcel_id,old_driver_id,new_driver_id,actor_id,created_at,hub_id) VALUES(?,?,?,?,?,?)',(p['id'],p['driver_id'],did,u['id'],now(),p.get('current_hub_id')))
        if d.get('status') in ['Transit','Reçu par le livreur']:
            c.execute('UPDATE parcels SET current_hub_id=NULL WHERE id=?',(p['id'],))
        if 'status' in d:
            c.execute('UPDATE parcels SET reason_code=?,next_attempt_at=?,ops_revision=ops_revision+1 WHERE id=?',(reason['code'] if reason else None,next_at,p['id']))
        else:c.execute('UPDATE parcels SET ops_revision=ops_revision+1 WHERE id=?',(p['id'],))
        return reason,next_at
    def allowed_doc(c,did,u):
        d=c.execute('SELECT * FROM ops_documents WHERE id=?',(did,)).fetchone()
        if not d or (u['role']=='client' and (d['kind']=='transfer' or d['client_id']!=u['id'])) or (u['role']=='livreur' and d['driver_id']!=u['id']):raise Error('Document introuvable.',404)
        if u['role']=='agent' and (d['kind']!='transfer' or u.get('agent_hub_id') not in (d['source_hub_id'],d['destination_hub_id'])):raise Error('Document introuvable.',404)
        return dict(d)
    def document_data(c,d):
        lines=[dict(r) for r in c.execute('''SELECT l.*,p.phone,p.amount,p.status current_status,p.current_hub_id
            FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id
            WHERE l.document_id=? ORDER BY l.id''',(d['id'],))]
        return {**d,'lines':lines,**ops_manifest_counts(lines)}
    def scoped_document_data(c,d,u):
        data=document_data(c,d)
        if u['role']=='agent':
            data['lines']=hub_document_lines_at_hub(data['lines'],u.get('agent_hub_id'))
            for line in data['lines']:
                line.pop('departure_reconciliation_reason',None)
                line.pop('departure_reconciled_by',None)
            data.pop('original_count',None)
            data.pop('departure_reconciled_count',None)
            data['note']=''
            data['cancel_reason']=''
        return data

    services.update(ops_change=change,ops_notify_event=notify_event)

    @app.get(P+'/config')
    @auth('admin','agent')
    def ops_config():
        u=user()
        with conn() as c:
            central_hub_id,central_hub_row=current_central_hub(c)
            if u['role']=='admin':
                hubs=[dict(r) for r in c.execute('SELECT h.*,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id ORDER BY h.name')]
                cities=[dict(r) for r in c.execute('''SELECT ci.id,ci.name,ci.region,ci.delivery,ci.pickup,
                    ci.hub_id,h.name hub_name FROM cities ci LEFT JOIN ops_hubs h ON h.id=ci.hub_id
                    ORDER BY ci.name COLLATE NOCASE''')]
            else:
                hub_id=u.get('agent_hub_id')
                if not hub_id:raise Error('Ce compte n’est pas rattaché à un Hub actif.',403)
                hubs=[dict(r) for r in c.execute('SELECT h.*,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1',(hub_id,))]
                if not hubs:raise Error('Le Hub de ce responsable est inactif ou introuvable.',403)
                cities=[dict(r) for r in c.execute('''SELECT ci.id,ci.name,ci.region,ci.delivery,ci.pickup,
                    ci.hub_id,h.name hub_name FROM cities ci JOIN ops_hubs h ON h.id=ci.hub_id
                    WHERE ci.hub_id=? AND h.active=1 ORDER BY ci.name COLLATE NOCASE''',(hub_id,))]
            for h in hubs:
                coverage=hub_coverage(c,h['id']);h['coverage']=coverage
                h['covered_city_ids']=[x['city_id'] for x in coverage]
                h['primary_city_id']=None
                if u['role']=='admin':
                    managers=[dict(r) for r in c.execute('''SELECT id,name,email,phone,active FROM users
                        WHERE agent_hub_id=? AND role IN ('hub_manager','agent') ORDER BY active DESC,id''',(h['id'],))]
                    active_managers=[m for m in managers if m['active']]
                    h['manager']=active_managers[0] if active_managers else (managers[0] if managers else None)
                    h['active_manager_count']=len(active_managers)
            for city in cities:
                city['hub_ids']=[city['hub_id']] if city.get('hub_id') else []
                city['primary_hub_id']=None
                if city.get('hub_id'):
                    assigned_hub=c.execute('SELECT id FROM ops_hubs WHERE id=? AND active=1',(city['hub_id'],)).fetchone()
                    if assigned_hub:city['primary_hub_id']=assigned_hub['id']
                city['routing_hub_id'],city['routing_hub_source']=resolve_routing_hub(
                    city['primary_hub_id'],central_hub_id,bool(central_hub_row and central_hub_row['active']))
                city['hub_names']=[city['hub_name']] if city.get('hub_name') else []
            if u['role']=='admin':
                palette_targets=[dict(r) for r in c.execute('''SELECT h.id,h.name,ci.name city FROM ops_hubs h
                    JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 ORDER BY h.name''')]
            elif u.get('agent_hub_id')==central_hub_id and central_hub_row and central_hub_row['active']:
                # The Central Hub manager must choose an original Hub, but receives names only—
                # no parcel or other-Hub operational details.
                palette_targets=[dict(r) for r in c.execute('''SELECT h.id,h.name,ci.name city FROM ops_hubs h
                    JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 ORDER BY h.name''')]
            else:
                palette_targets=[{'id':central_hub_row['id'],'name':central_hub_row['name'],'city':central_hub_row['city']}] if central_hub_row and central_hub_row['active'] else []
            return jsonify(reasons=[dict(r) for r in c.execute('SELECT * FROM ops_reasons ORDER BY label')],hubs=hubs,cities=cities,
                palette_targets=palette_targets,central_hub_id=central_hub_id,central_hub=central_hub_row,
                started_at=c.execute("SELECT value FROM settings WHERE key='ops_started_at'").fetchone()[0])

    @app.patch(P+'/central-hub')
    @auth('admin')
    def ops_central_hub_update():
        d=body()
        if set(d)!={'hub_id'}:raise Error('Seul l’identifiant d’un Hub Central actif est requis.')
        hid=integer(d.get('hub_id'),'Hub central');u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            selected=hub(c,hid,True)
            previous_id,previous_hub=current_central_hub(c)
            if previous_id==hid:return jsonify(ok=True,changed=False,central_hub_id=hid)
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(hid),))
            city=c.execute('SELECT name FROM cities WHERE id=?',(selected['city_id'],)).fetchone()
            new_hub={'id':hid,'name':selected['name'],'city':city['name'] if city else None,'active':bool(selected['active'])}
            audit(c,None,u,'Hub Central modifié',{'before_hub_id':previous_id,'after_hub_id':hid,'name':selected['name'],'city':city['name'] if city else None})
            append_audit_log(c,actor_id=u['id'],actor_name=u['name'],action='central_hub_changed',
                             entity_type='setting',entity_id='central_hub_id',old_value=previous_hub,
                             new_value=new_hub,created_at=now())
        return jsonify(ok=True,changed=True,central_hub_id=hid)

    @app.route(P+'/hubs',methods=['POST'])
    @app.route(P+'/hubs/<int:hid>',methods=['PATCH'])
    @auth('admin')
    def ops_hub(hid=None):
        d=body();actor=user();name=text(d,'name',maxlen=100);address=text(d,'address',maxlen=300);cid=integer(d.get('city_id'))
        city_ids=city_ids_from_body(d)
        manager_fields=('manager_name','manager_email','manager_password','manager_phone')
        manager_payload_present=any(key in d for key in manager_fields)
        if not hid and not manager_payload_present:raise Error('Créez le compte du responsable en même temps que le nouveau Hub.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM cities WHERE id=?',(cid,)).fetchone():raise Error('Ville inconnue.')
            previous=None;previous_city_ids=[]
            if hid:
                row=c.execute('SELECT name,city_id,address,active FROM ops_hubs WHERE id=?',(hid,)).fetchone()
                hub(c,hid,False)
                previous=dict(row) if row else None
                previous_city_ids=[r['id'] for r in c.execute('SELECT id FROM cities WHERE hub_id=? ORDER BY id',(hid,))]
                if not bool(d.get('active')):
                    central_id,_=current_central_hub(c)
                    if central_id==hid:raise Error('Désignez un autre Hub Central avant de désactiver celui-ci.',409)
                if previous and (previous['city_id']!=cid or previous['address']!=address):
                    # A saved map pin may belong to its former address; require fresh placement after relocation.
                    c.execute('UPDATE ops_hubs SET lat=NULL,lng=NULL WHERE id=?',(hid,))
                if previous and not previous['active'] and bool(d.get('active')):
                    manager_count=c.execute("SELECT count(*) FROM users WHERE agent_hub_id=? AND active=1 AND role IN ('hub_manager','agent')",(hid,)).fetchone()[0]
                    if manager_count!=1:raise Error('Un Hub ne peut être réactivé qu’avec exactement un responsable actif.',409)
                c.execute('UPDATE ops_hubs SET name=?,city_id=?,address=?,active=? WHERE id=?',(name,cid,address,int(bool(d.get('active'))),hid))
            else:
                hid=c.execute('INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,?,?)',(name,cid,address,now())).lastrowid
            selected_city_owners_before=[]
            if city_ids:
                marks=','.join('?'*len(city_ids))
                selected_city_owners_before=[dict(r) for r in c.execute(f'''SELECT ci.id city_id,ci.name city,ci.hub_id,
                    h.name hub_name FROM cities ci LEFT JOIN ops_hubs h ON h.id=ci.hub_id
                    WHERE ci.id IN ({marks})''',city_ids)]
            if city_ids is not None:
                try:assign_cities_to_hub(c,hid,city_ids,actor['id'],now())
                except ValueError as exc:raise Error(str(exc))
            elif not previous:
                # Compatibility for an older admin screen that still saves coverage separately.
                ensure_home_city_coverage(c,hid,cid,actor['id'])
            manager_id=None
            if manager_payload_present:
                hub(c,hid,True)
                manager_id=create_hub_manager_account(c,hid,d,actor)
            assigned_after=[r['id'] for r in c.execute('SELECT id FROM cities WHERE hub_id=? ORDER BY id',(hid,))]
            current={'id':hid,'name':name,'city_id':cid,'address':address,'active':bool(d.get('active',True)),
                     'assigned_city_ids':assigned_after}
            old_snapshot={'hub':previous,'assigned_city_ids':previous_city_ids,
                          'selected_city_owners':selected_city_owners_before}
            audit(c,None,actor,'Hub configuré',{'hub_id':hid,'name':name,'home_city_id':cid,
                  'city_ids_before':previous_city_ids,'assigned_city_ids':assigned_after,
                  'selected_city_owners_before':selected_city_owners_before})
            append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_configured',
                             entity_type='hub',entity_id=hid,old_value=old_snapshot,new_value=current,
                             metadata={'manager_id':manager_id},created_at=now())
        return jsonify(ok=True,id=hid,manager_id=manager_id)

    @app.post(P+'/hubs/<int:hid>/manager')
    @auth('admin')
    def ops_hub_manager_create(hid):
        d=body();actor=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');hub(c,hid,False)
            manager_id=create_hub_manager_account(c,hid,d,actor)
            audit(c,None,actor,'Responsable de Hub créé',{'hub_id':hid,'manager_id':manager_id})
        return jsonify(ok=True,id=manager_id)

    @app.post(P+'/hubs/<int:hid>/manager/replace')
    @auth('admin')
    def ops_hub_manager_replace(hid):
        d=body();actor=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');hub(c,hid,False)
            previous=[dict(r) for r in c.execute("""SELECT id,name,email FROM users
                WHERE agent_hub_id=? AND active=1 AND role IN ('hub_manager','agent') ORDER BY id""",(hid,)).fetchall()]
            if not previous:raise Error('Aucun responsable actif à remplacer. Utilisez l’ajout de responsable.',409)
            c.execute("UPDATE users SET active=0 WHERE agent_hub_id=? AND active=1 AND role IN ('hub_manager','agent')",(hid,))
            revoke=services.get('security_revoke_user')
            for manager in previous:
                if revoke:revoke(c,manager['id'],'Compte remplacé comme responsable de Hub',actor['id'])
            manager_id=create_hub_manager_account(c,hid,d,actor)
            for manager in previous:
                append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_manager_replaced',
                    entity_type='hub_manager',entity_id=manager['id'],
                    old_value={'id':manager['id'],'name':manager['name'],'email':manager['email'],'hub_id':hid,'active':True},
                    new_value={'id':manager['id'],'name':manager['name'],'email':manager['email'],'hub_id':hid,
                               'active':False,'replaced_by':manager_id},
                    metadata={'hub_id':hid,'replacement_manager_id':manager_id},created_at=now())
            audit(c,None,actor,'Responsable de Hub remplacé',
                  {'hub_id':hid,'old_manager_ids':[m['id'] for m in previous],'new_manager_id':manager_id})
        return jsonify(ok=True,id=manager_id,replaced=[m['id'] for m in previous])

    @app.patch(P+'/hubs/<int:hid>/coverage')
    @auth('admin')
    def ops_hub_coverage_update(hid):
        d=body();actor=user();city_ids=city_ids_from_body(d)
        if city_ids is None:raise Error('La liste des villes attribuées est requise.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');hub(c,hid,False)
            before=hub_coverage(c,hid)
            if city_ids:
                marks=','.join('?'*len(city_ids))
                transfers=[dict(r) for r in c.execute(f'''SELECT ci.id city_id,ci.name city,ci.hub_id,
                    h.name hub_name FROM cities ci LEFT JOIN ops_hubs h ON h.id=ci.hub_id
                    WHERE ci.id IN ({marks})''',city_ids)]
            else:transfers=[]
            try:assign_cities_to_hub(c,hid,city_ids,actor['id'],now())
            except ValueError as exc:raise Error(str(exc))
            after=hub_coverage(c,hid)
            old_value={'hub_id':hid,'cities_before':before,'selected_city_owners_before':transfers}
            new_value={'hub_id':hid,'cities_after':after,'city_ids':city_ids}
            audit(c,None,actor,'Villes attribuées au Hub',{'hub_id':hid,'before':before,'after':after,'previous_owners':transfers})
            append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_city_assignments_changed',
                             entity_type='hub',entity_id=hid,old_value=old_value,new_value=new_value,
                             created_at=now())
            return jsonify(ok=True,hub_id=hid,coverage=after)

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
            cod_hub_id=resolve_cod_hub(c,p['city_id']) if outcome=='Livré' else None
            driver_hub=c.execute("SELECT driver_hub_id FROM users WHERE id=? AND role='livreur' AND active=1",(p['driver_id'],)).fetchone() if p['driver_id'] else None
            operational_hub_id=driver_hub['driver_hub_id'] if driver_hub and type(driver_hub['driver_hub_id']) is int and c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(driver_hub['driver_hub_id'],)).fetchone() else None
            aid=c.execute('''INSERT INTO ops_attempts(parcel_id,driver_id,actor_id,outcome,reason_code,reason_label,
                next_attempt_at,note,receiver,amount_cents,request_key,payload_hash,created_at,cod_hub_id,operational_hub_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(pid,p['driver_id'],u['id'],outcome,reason['code'] if reason else None,
                reason['label'] if reason else None,next_at,note,receiver,cents,key,hashed,now(),cod_hub_id,operational_hub_id)).lastrowid
            if outcome=='Livré':
                append_audit_log(c,actor_id=u['id'],actor_name=u['name'],action='cod_delivery_declared',
                    entity_type='parcel',entity_id=pid,old_value={'cod_cents':None},
                    new_value={'cod_cents':cents,'cod_hub_id':cod_hub_id},metadata={'attempt_id':aid},created_at=now())
            c.execute('UPDATE parcels SET status=?,note=?,updated_at=? WHERE id=?',(outcome,note or p['note'],now(),pid))
            event(c,pid,outcome,('Tentative : '+(reason['label'] if reason else 'livraison déclarée'))+(' · Rendez-vous '+next_at if next_at else '')+(' · '+note if note else ''),u)
            return jsonify(ok=True,id=aid,already_recorded=False)

    @app.get(P+'/documents')
    @auth()
    def ops_documents():
        u=user()
        if u['role']=='admin':where,args='1=1',[]
        elif u['role']=='client':where,args="kind!='transfer' AND client_id=?",[u['id']]
        elif u['role']=='agent' and u.get('agent_hub_id'):where,args="kind='transfer' AND (source_hub_id=? OR destination_hub_id=?)",[u['agent_hub_id'],u['agent_hub_id']]
        elif u['role']=='livreur':where,args='driver_id=?',[u['id']]
        else:where,args='1=0',[]
        with conn() as c:
            return jsonify([scoped_document_data(c,dict(r),u) for r in c.execute('SELECT * FROM ops_documents WHERE '+where+' ORDER BY id DESC LIMIT 500',args).fetchall()])

    @app.get(P+'/palettes')
    @auth('admin','agent')
    def ops_palettes():
        u=user();tab=request.args.get('tab','default')
        if tab not in ('default','retours','a-recevoir'):raise Error('Onglet de palettes invalide.')
        with conn() as c:
            where=["d.kind='transfer'"];args=[]
            local=None;central_id,central=current_central_hub(c)
            if u['role']=='agent':
                local=local_manager_hub(c,u)
                if tab=='default':
                    where.append("d.palette_purpose='standard' AND (d.source_hub_id=? OR d.destination_hub_id=?)")
                    args.extend([local['id'],local['id']])
                elif tab=='retours' and local['id']==central_id:
                    where.append("(d.palette_purpose='return_to_central' AND d.destination_hub_id=?) OR (d.palette_purpose='return_to_origin' AND d.source_hub_id=?)")
                    args.extend([local['id'],local['id']])
                elif tab=='retours':where.append("d.palette_purpose='return_to_central' AND d.source_hub_id=?");args.append(local['id'])
                else:
                    where.append("d.palette_purpose='return_to_origin' AND d.destination_hub_id=? AND d.status IN ('Départ partiel','En transit','Partiellement reçu')")
                    args.append(local['id'])
            elif tab=='retours':where.append("d.palette_purpose IN ('return_to_central','return_to_origin')")
            elif tab=='a-recevoir':
                where.append("d.palette_purpose='return_to_origin' AND d.status IN ('Départ partiel','En transit','Partiellement reçu')")
            else:where.append("d.palette_purpose='standard'")
            if tab=='a-recevoir' and u['role']=='admin':
                # The Admin sees all customer returns routed from the Central Hub to their origin Hubs.
                pass
            if request.args.get('hub_id','').isdigit() and u['role']=='admin':
                hid=int(request.args['hub_id']);where.append('(d.source_hub_id=? OR d.destination_hub_id=?)');args.extend([hid,hid])
            status=request.args.get('status','').strip()
            if status in ('Préparé','Départ partiel','En transit','Partiellement reçu','Reçu','Annulé'):
                where.append('d.status=?');args.append(status)
            query=str(request.args.get('q') or '').strip().lower()[:120]
            if query:
                where.append("(instr(lower(d.reference),?)>0 OR instr(lower(d.source_name),?)>0 OR instr(lower(d.destination_name),?)>0 OR instr(lower(d.transport),?)>0 OR instr(lower(d.tracking_code),?)>0)")
                args.extend([query]*5)
            rows=[]
            for row in c.execute('SELECT d.* FROM ops_documents d WHERE '+' AND '.join('('+w+')' for w in where)+' ORDER BY d.id DESC LIMIT 500',args):
                doc=dict(row)
                summary=c.execute('''SELECT count(*)-COALESCE(sum(departure_reconciled_at IS NOT NULL),0) count,
                    COALESCE(sum(received_at IS NOT NULL AND departure_reconciled_at IS NULL),0) received
                    FROM ops_document_lines WHERE document_id=?''',(doc['id'],)).fetchone()
                doc['count']=summary['count'] or 0;doc['received']=summary['received'] or 0
                doc['remaining']=0 if doc['status']=='Annulé' else max(0,doc['count']-doc['received'])
                if u['role']=='agent':
                    # Only each Hub's own transfer summaries are shown; manifest details remain
                    # hidden until a parcel is physically scanned into that Hub.
                    doc['note']='';doc['cancel_reason']=''
                rows.append(doc)
            return jsonify(tab=tab,rows=rows,total=len(rows),central_hub_id=central_id,
                           hub=local,total_colis=sum(r['count'] for r in rows),page=1,size=30)

    @app.get(P+'/palette-candidates')
    @auth('admin','agent')
    def ops_palette_candidates():
        u=user();mode=request.args.get('mode','standard')
        if mode not in ('standard','return_to_central','return_to_origin','unresolved_origin'):raise Error('Mode de palette invalide.')
        with conn() as c:
            central_id,central=current_central_hub(c)
            if not central or not central.get('active'):raise Error('Aucun Hub Central actif.',409)
            if mode=='unresolved_origin':
                if u['role']!='admin':raise Error('Cette revue est réservée à Admin.',403)
                candidates=c.execute('''SELECT p.id,p.tracking,p.recipient,p.status,p.current_hub_id,p.origin_hub_id,ci.name city
                    FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id
                    WHERE p.current_hub_id=? AND p.origin_hub_id IS NULL AND p.status IN ('Retourné','Refusé')
                      AND NOT EXISTS(SELECT 1 FROM ops_document_lines a WHERE a.parcel_id=p.id AND a.active=1)
                      AND EXISTS(SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=p.id AND l.received_at IS NOT NULL AND d.kind='transfer'
                          AND d.palette_purpose='return_to_central' AND d.destination_hub_id=?
                          AND d.status IN ('Reçu','Partiellement reçu'))
                    ORDER BY p.id DESC LIMIT 500''',(central_id,central_id)).fetchall()
                available=[dict(r) for r in c.execute('SELECT h.id,h.name,ci.name city,h.active FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 AND h.id!=? ORDER BY h.name',(central_id,))]
                result=[]
                for candidate in candidates:
                    item=dict(candidate)
                    sent=c.execute('''SELECT min(COALESCE(l.departure_scanned_at,d.dispatched_at,d.created_at)) sent_at
                        FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=? AND d.kind='transfer' AND d.palette_purpose='return_to_central'
                          AND d.destination_hub_id=? AND l.received_at IS NOT NULL''',(item['id'],central_id)).fetchone()['sent_at']
                    evidence=c.execute('''SELECT d.source_hub_id hub_id,'transfer_departure' evidence_type,l.departure_scanned_at event_at
                        FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=? AND d.kind='transfer' AND d.palette_purpose='standard'
                          AND d.source_hub_id IS NOT NULL AND l.departure_scanned_at IS NOT NULL AND l.departure_scanned_at<=?
                        UNION ALL SELECT d.destination_hub_id,'partner_receipt',l.received_at
                        FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=? AND d.kind='partner_palette' AND d.destination_hub_id IS NOT NULL
                          AND l.received_at IS NOT NULL AND l.received_at<=?
                        UNION ALL SELECT dr.hub_id,'driver_receipt',dr.received_at FROM driver_receipts dr
                        WHERE dr.parcel_id=? AND dr.hub_id IS NOT NULL AND dr.received_at<=?
                        ORDER BY event_at,hub_id''',(item['id'],sent,item['id'],sent,item['id'],sent)).fetchall()
                    by_hub={}
                    for ev in evidence:
                        if ev['hub_id'] is None:continue
                        by_hub.setdefault(ev['hub_id'],[]).append({'type':ev['evidence_type'],'at':ev['event_at']})
                    item['first_return_sent_at']=sent
                    item['physical_evidence']=[{'hub_id':hid,'hub_name':(c.execute('SELECT name FROM ops_hubs WHERE id=?',(hid,)).fetchone() or {'name':'Hub inconnu'})['name'],'events':events} for hid,events in by_hub.items()]
                    result.append(item)
                return jsonify(mode=mode,source_hub_id=central_id,rows=result,available_hubs=available,
                               review_note='Aucune ville ni affectation de route n’est utilisée comme preuve. Admin doit confirmer une référence physique avant le routage.')
            local=local_manager_hub(c,u) if u['role']=='agent' else None
            if u['role']=='agent':source_id=local['id']
            else:
                try:source_id=integer(request.args.get('source_hub_id'),'Hub de départ')
                except Exception:source_id=None
            if mode=='return_to_origin':
                if source_id!=central_id:raise Error('Le tri des retours doit être effectué au Hub Central.',403)
                if u['role']=='agent' and local['id']!=central_id:raise Error('Cette opération est réservée au Hub Central.',403)
                try:dest_id=integer(request.args.get('destination_hub_id'),'Hub d’origine')
                except Exception:dest_id=None
                if not dest_id or dest_id==central_id or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(dest_id,)).fetchone():
                    raise Error('Choisissez un Hub d’origine actif.')
                rows=c.execute('''SELECT p.id,p.tracking,p.recipient,p.status,p.origin_hub_id,ci.name city,
                    oh.name origin_hub FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id
                    LEFT JOIN ops_hubs oh ON oh.id=p.origin_hub_id
                    WHERE p.current_hub_id=? AND p.origin_hub_id=? AND p.status IN ('Retourné','Refusé')
                      AND NOT EXISTS(SELECT 1 FROM ops_document_lines a WHERE a.parcel_id=p.id AND a.active=1)
                      AND EXISTS(SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                        WHERE l.parcel_id=p.id AND l.received_at IS NOT NULL AND d.kind='transfer'
                          AND d.palette_purpose='return_to_central' AND d.destination_hub_id=?
                          AND d.status IN ('Reçu','Partiellement reçu'))
                    ORDER BY p.id DESC LIMIT 500''',(central_id,dest_id,central_id)).fetchall()
                return jsonify(mode=mode,source_hub_id=central_id,destination_hub_id=dest_id,rows=[dict(r) for r in rows])
            if not source_id or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(source_id,)).fetchone():
                raise Error('Hub de départ actif requis.')
            if mode=='return_to_central':
                if source_id==central_id:raise Error('Le Hub Central ne peut pas envoyer un retour vers lui-même.')
                dest_id=central_id
                sql="p.current_hub_id=? AND p.status IN ('Retourné','Refusé')"
            else:
                dest_id=None
                sql="p.current_hub_id=? AND p.status IN ('Ramassé','Au hub','Réceptionné') AND p.invoice_id IS NULL AND NOT EXISTS(SELECT 1 FROM driver_statement_lines s WHERE s.parcel_id=p.id AND s.active=1)"
            rows=c.execute('''SELECT p.id,p.tracking,p.recipient,p.status,p.origin_hub_id,ci.name city,oh.name origin_hub
                FROM parcels p LEFT JOIN cities ci ON ci.id=p.city_id LEFT JOIN ops_hubs oh ON oh.id=p.origin_hub_id
                WHERE '''+sql+''' AND NOT EXISTS(SELECT 1 FROM ops_document_lines a WHERE a.parcel_id=p.id AND a.active=1)
                ORDER BY p.id DESC LIMIT 500''',(source_id,)).fetchall()
            return jsonify(mode=mode,source_hub_id=source_id,destination_hub_id=dest_id,rows=[dict(r) for r in rows])

    @app.post(P+'/parcels/<int:pid>/origin-review')
    @auth('admin')
    def ops_review_return_origin(pid):
        d=body();u=user()
        if set(d)!={'hub_id','reason','evidence_reference','manual_physical_review','confirmed'}:
            raise Error('Hub, motif, référence de preuve et confirmation sont requis.')
        if d.get('confirmed') is not True:raise Error('Confirmez la revue physique du Hub d’origine.')
        if d.get('manual_physical_review') not in (True,False):raise Error('Confirmation de revue manuelle invalide.')
        target_id=integer(d.get('hub_id'),'Hub d’origine')
        reason=text(d,'reason',maxlen=600);evidence_reference=text(d,'evidence_reference',maxlen=160)
        if len(evidence_reference)<3:raise Error('Indiquez une référence de preuve physique vérifiable.')
        if len(reason)<12:raise Error('Le motif de revue doit contenir au moins 12 caractères.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            central_id,central=current_central_hub(c)
            if not central or not central.get('active'):raise Error('Aucun Hub Central actif.',409)
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            if not p:raise Error('Colis introuvable.',404)
            if p['origin_hub_id'] is not None:raise Error('L’origine du colis est déjà enregistrée; toute correction exige une procédure distincte.',409)
            if p['current_hub_id']!=central_id or p['status'] not in ('Retourné','Refusé'):
                raise Error('Seul un retour physiquement reçu au Hub Central peut être revu.',409)
            if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1',(pid,)).fetchone():
                raise Error('Terminez ou annulez le document actif avant la revue.',409)
            if not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1 AND id!=?',(target_id,central_id)).fetchone():
                raise Error('Choisissez un Hub d’origine actif autre que le Hub Central.')
            returned=c.execute('''SELECT min(COALESCE(l.departure_scanned_at,d.dispatched_at,d.created_at)) sent_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.parcel_id=? AND l.received_at IS NOT NULL AND d.kind='transfer'
                  AND d.palette_purpose='return_to_central' AND d.destination_hub_id=?
                  AND d.status IN ('Reçu','Partiellement reçu')''',(pid,central_id)).fetchone()
            if not returned or not returned['sent_at']:raise Error('Aucun retour physiquement réceptionné au Hub Central pour ce colis.',409)
            evidence_rows=c.execute('''SELECT d.source_hub_id hub_id,'transfer_departure' evidence_type,l.departure_scanned_at event_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.parcel_id=? AND d.kind='transfer' AND d.palette_purpose='standard'
                  AND d.source_hub_id=? AND l.departure_scanned_at IS NOT NULL AND l.departure_scanned_at<=?
                UNION ALL SELECT d.destination_hub_id,'partner_receipt',l.received_at
                FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE l.parcel_id=? AND d.kind='partner_palette' AND d.destination_hub_id=?
                  AND l.received_at IS NOT NULL AND l.received_at<=?
                UNION ALL SELECT dr.hub_id,'driver_receipt',dr.received_at FROM driver_receipts dr
                WHERE dr.parcel_id=? AND dr.hub_id=? AND dr.received_at<=?
                ORDER BY event_at LIMIT 1''',(pid,target_id,returned['sent_at'],pid,target_id,returned['sent_at'],pid,target_id,returned['sent_at'])).fetchone()
            if not evidence_rows and not d['manual_physical_review']:
                raise Error('Aucune preuve numérique trouvée à ce Hub. Confirmez une revue manuelle fondée sur un reçu ou registre physique.',409)
            if not evidence_rows and (len(evidence_reference)<8 or len(reason)<24):
                raise Error('Sans trace numérique, une référence physique plus complète et un motif détaillé sont requis.',409)
            cur=c.execute('UPDATE parcels SET origin_hub_id=?,ops_revision=ops_revision+1,updated_at=? WHERE id=? AND origin_hub_id IS NULL',(target_id,now(),pid))
            if cur.rowcount!=1:raise Error('L’origine du colis vient d’être modifiée. Rechargez la page.',409)
            details={'hub_id':target_id,'hub_name':c.execute('SELECT name FROM ops_hubs WHERE id=?',(target_id,)).fetchone()['name'],
                     'reason':reason,'evidence_reference':evidence_reference,'manual_physical_review':bool(d['manual_physical_review']),
                     'digital_evidence':dict(evidence_rows) if evidence_rows else None,'central_hub_id':central_id}
            append_audit_log(c,actor_id=u['id'],actor_name=u['name'],action='parcel_return_origin_reviewed',
                entity_type='parcel_origin_review',entity_id=pid,old_value={'origin_hub_id':None},
                new_value={'origin_hub_id':target_id},metadata=details,created_at=now())
            event(c,pid,p['status'],'Revue Admin : Hub d’origine fixé après contrôle d’une preuve physique ('+evidence_reference+')',u)
            return jsonify(ok=True,parcel_id=pid,origin_hub_id=target_id,evidence_reference=evidence_reference,
                           manual_physical_review=bool(d['manual_physical_review']))

    @app.post(P+'/documents')
    @auth('admin','agent')
    def ops_create_document():
        d=body();u=user();pids=ids(d);kind=d.get('kind')
        if kind not in ['pickup','return','transfer']:raise Error('Type de document invalide.')
        if u['role']=='agent' and kind!='transfer':raise Error('Le Hub Manager peut uniquement préparer des transferts inter-Hubs.',403)
        purpose=d.get('palette_purpose','standard') if kind=='transfer' else 'standard'
        if purpose not in ('standard','return_to_central','return_to_origin'):
            raise Error('Type de palette invalide.')
        transport=str(d.get('transport') or '').strip()
        tracking_code=str(d.get('tracking_code') or '').strip()
        if len(transport)>120 or len(tracking_code)>80:raise Error('Transport ou numéro de suivi trop long.')
        lots=d.get('lots',0)
        if isinstance(lots,bool) or not isinstance(lots,int) or not 0<=lots<=500:raise Error('Nombre de lots invalide (0 à 500).')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            cl=enabled_user(c,d.get('client_id'),'client') if kind!='transfer' else None
            dr=enabled_user(c,d['driver_id'],'livreur') if d.get('driver_id') else None
            if kind=='transfer':
                central_hub_id,central_hub_row=current_central_hub(c)
                central_is_active=bool(central_hub_row and central_hub_row['active'])
                if not central_is_active:raise Error('Configurez un Hub Central actif avant de créer une palette inter-Hubs.',409)
                local=None
                if u['role']=='agent':
                    local=local_manager_hub(c,u)
                    requested=d.get('source_hub_id')
                    if requested not in (None,'') and integer(requested,'Hub de départ')!=local['id']:
                        raise Error('Le Hub de départ doit être votre Hub.',403)
                    src=hub(c,local['id'])
                else:src=hub(c,d.get('source_hub_id'))
                dest=hub(c,d.get('destination_hub_id'))
                if src['id']==dest['id']:raise Error('Choisissez deux hubs différents.')
                if not central_hub_transfer_allowed(src['id'],dest['id'],central_hub_id,central_is_active):
                    raise Error('Chaque palette doit relier le Hub Central actif à un autre Hub; aucun transfert direct entre Hubs secondaires.',409)
                if purpose=='return_to_central' and (src['id']==central_hub_id or dest['id']!=central_hub_id):
                    raise Error('Un retour vers le Hub Central doit partir d’un Hub secondaire et arriver au Hub Central.',409)
                if purpose=='return_to_origin':
                    if src['id']!=central_hub_id or dest['id']==central_hub_id:
                        raise Error('Le retour vers le Hub d’origine doit partir du Hub Central.',409)
                    if u['role']=='agent' and local['id']!=central_hub_id:
                        raise Error('Cette opération est réservée au Hub Central.',403)
            else:
                src=hub(c,d.get('source_hub_id')) if kind!='pickup' else None
                dest=hub(c,d.get('destination_hub_id')) if kind!='return' else None
                if src and dest and src['id']==dest['id']:raise Error('Choisissez deux hubs différents.')
            parcels=[];line_return_status={}
            for pid in pids:
                p=parcel(c,pid,u)
                if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1',(pid,)).fetchone():
                    raise Error('Un colis appartient déjà à un document actif.',409)
                if cl and p['client_id']!=cl['id']:raise Error('Tous les colis doivent appartenir au client du bon.')
                if kind=='transfer':
                    if not parcel_physically_at_hub(p.get('current_hub_id'),src['id']):
                        raise Error('Le colis doit être physiquement enregistré au Hub de départ avant la préparation.',409)
                    if purpose=='standard':
                        guard(c,p)
                        if p['status'] not in ['Ramassé','Au hub','Réceptionné']:
                            raise Error('Palette standard : sélectionnez uniquement des colis reçus physiquement au Hub.')
                    elif purpose=='return_to_central':
                        if p['status'] not in ('Retourné','Refusé'):
                            raise Error('Un retour au Hub Central ne contient que des colis non livrés (Retourné/Refusé).')
                        line_return_status[pid]=p['status']
                    else:
                        if p['origin_hub_id']!=dest['id'] or p['status'] not in ('Retourné','Refusé'):
                            raise Error('Ce colis ne correspond pas au Hub d’origine sélectionné.',409)
                        returned=c.execute('''SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                            WHERE l.parcel_id=? AND l.received_at IS NOT NULL AND d.kind='transfer'
                              AND d.palette_purpose='return_to_central' AND d.destination_hub_id=?
                              AND d.status IN ('Reçu','Partiellement reçu') LIMIT 1''',(pid,src['id'])).fetchone()
                        if not returned:raise Error('Le colis n’a pas été réceptionné au Hub Central depuis un retour de Hub.',409)
                        prior_status=c.execute('''SELECT l.return_status FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                            WHERE l.parcel_id=? AND d.kind='transfer' AND d.palette_purpose='return_to_central'
                              AND l.received_at IS NOT NULL AND d.destination_hub_id=?
                            ORDER BY l.received_at DESC,l.id DESC LIMIT 1''',(pid,src['id'])).fetchone()
                        prior_status=prior_status['return_status'] if prior_status else None
                        if prior_status not in ('Retourné','Refusé'):raise Error('Statut initial du retour non confirmé; révision Admin requise.',409)
                        line_return_status[pid]=p['status']
                else:
                    if kind=='return':
                        if p['status'] not in ['Retourné','Refusé']:raise Error('Un bon de retour ne contient que des colis retournés/refusés.')
                    else:
                        guard(c,p)
                        if kind=='pickup' and p['status'] not in ['Créé','Ramassé']:raise Error('Ramassage : sélectionnez des colis créés ou ramassés.')
                    if kind!='transfer' and src and p['current_hub_id'] and p['current_hub_id']!=src['id']:
                        raise Error('Le hub connu du colis ne correspond pas à l’origine.')
                parcels.append(p)
            did=c.execute('''INSERT INTO ops_documents(kind,client_id,driver_id,source_hub_id,destination_hub_id,
                client_name,driver_name,source_name,destination_name,note,created_by,created_at,
                departure_scan_required,palette_purpose,transport,tracking_code,lots)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (kind,cl['id'] if cl else None,dr['id'] if dr else None,src['id'] if src else None,dest['id'] if dest else None,
                 cl['name'] if cl else None,dr['name'] if dr else None,src['name'] if src else 'Chez le client',
                 dest['name'] if dest else 'Retour au client',text(d,'note',False,600),u['id'],now(),
                 int(kind=='transfer'),purpose,transport,tracking_code,lots)).lastrowid
            prefix={'pickup':'RAM','return':'RET','transfer':{'standard':'TRF','return_to_central':'RET','return_to_origin':'RTO'}[purpose]}[kind]
            reference=prefix+f'-{did:06d}'
            c.execute('UPDATE ops_documents SET reference=? WHERE id=?',(reference,did))
            for p in parcels:
                city=c.execute('SELECT name FROM cities WHERE id=?',(p['city_id'],)).fetchone()[0]
                c.execute('''INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status,return_status)
                    VALUES(?,?,?,?,?,?,?)''',(did,p['id'],p['tracking'],p['recipient'],city,p['status'],line_return_status.get(p['id'])))
            audit(c,did,u,'Palette préparée' if kind=='transfer' else 'Document préparé',
                  {'count':len(parcels),'palette_purpose':purpose,'source_hub_id':src['id'] if src else None,
                   'destination_hub_id':dest['id'] if dest else None,'transport':transport,'tracking_code':tracking_code,'lots':lots})
            for uid in {cl['id'] if cl else None,dr['id'] if dr else None}-{None}:notify(c,uid,'Document préparé',reference)
            return jsonify(ok=True,id=did,reference=reference,palette_purpose=purpose)

    @app.get(P+'/documents/<int:did>')
    @auth()
    def ops_document(did):
        viewer=user()
        with conn() as c:
            d=scoped_document_data(c,allowed_doc(c,did,viewer),viewer)
            def hub_info(hid):
                if not hid:return None
                r=c.execute('SELECT h.id,h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=?',(hid,)).fetchone()
                if not r:return None
                info=dict(r)
                if viewer['role']=='agent' and hid!=viewer.get('agent_hub_id'):info.pop('address',None)
                return info
            d['source_hub']=hub_info(d.get('source_hub_id'))
            d['destination_hub']=hub_info(d.get('destination_hub_id'))
            may_view_client_contact=(viewer['role']=='admin' or (viewer['role']=='client' and viewer['id']==d.get('client_id')))
            if d.get('client_id') and may_view_client_contact:
                cl=c.execute('''SELECT u.name,u.company,u.phone,u.email,COALESCE(a.legal_name,'') legal_name,
                    COALESCE(a.billing_address,'') billing_address FROM users u
                    LEFT JOIN account_dossiers a ON a.user_id=u.id WHERE u.id=? AND u.role='client' ''',(d['client_id'],)).fetchone()
                d['client_contact']={
                    'name':cl['name'] if cl else '',
                    'company':cl['company'] if cl else '',
                    'phone':cl['phone'] if cl else '',
                    'email':cl['email'] if cl else '',
                    'legal_name':cl['legal_name'] if cl else '',
                    'address':cl['billing_address'] if cl else ''}
            else:d['client_contact']=None
            import qrcode, io, base64
            image=qrcode.make(d['reference']);buf=io.BytesIO();image.save(buf,format='PNG');d['qr']='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
            audit_rows=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM ops_audit a JOIN users u ON u.id=a.actor_id WHERE document_id=? ORDER BY a.id DESC',(did,))]
            if viewer['role']=='agent':
                visible_ids={line['parcel_id'] for line in d['lines']};visible_trackings={line['tracking'].upper() for line in d['lines']}
                audit_rows=[row for row in audit_rows
                    if (row['details'].get('parcel_id') is None or (type(row['details'].get('parcel_id')) is int and row['details']['parcel_id'] in visible_ids))
                    and (row['details'].get('tracking') is None or (isinstance(row['details'].get('tracking'),str) and row['details']['tracking'].upper() in visible_trackings))]
                for row in audit_rows:
                    details=row['details']
                    if details.get('parcel_id') is None and details.get('tracking') is None:
                        row['details']={key:details[key] for key in ('count','source_hub_id','destination_hub_id') if key in details}
            d['audit']=audit_rows
            return jsonify(d)

    def check_transfer_city(c,doc,p):
        # Ordinary outbound transfers only. Inbound Central routing and physical
        # returns to origin are separate workflows, not delivery-city routing.
        if doc['kind']!='transfer' or doc.get('palette_purpose','standard')!='standard':return
        central_id,_=current_central_hub(c)
        if doc['destination_hub_id']==central_id:return
        destination=c.execute('SELECT name,active FROM ops_hubs WHERE id=?',(doc['destination_hub_id'],)).fetchone()
        city=c.execute('SELECT name,hub_id FROM cities WHERE id=?',(p['city_id'],)).fetchone()
        if not destination or not destination['active']:
            raise Error('Hub de destination inactif : colis non scanné. Choisissez un autre Hub.',409)
        if not city or city['hub_id']!=doc['destination_hub_id']:
            name=city['name'] if city else 'non renseignée'
            raise Error(f"Colis non scanné : la ville {name} n’est pas rattachée à {destination['name']}. Choisissez un autre Hub.",409)

    @app.post(P+'/documents/<int:did>/departure-scan')
    @auth('admin','agent')
    def ops_document_departure_scan(did):
        d=body();u=user();tracking=text(d,'tracking',maxlen=80).upper()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc=document_data(c,allowed_doc(c,did,u))
            if u['role']=='agent' and not hub_manager_transfer_scope(doc,u.get('agent_hub_id'),'departure'):
                raise Error('Document introuvable.',404)
            if doc['kind']!='transfer' or not doc['departure_scan_required']:
                raise Error('Ce document ne requiert pas les scans de sortie.',409)
            line=next((l for l in doc['lines'] if l['tracking'].upper()==tracking and l['active']),None)
            if not line:
                # Give a routing explanation only for a code physically at the
                # source; never disclose a foreign Hub's parcel or city.
                candidates=c.execute('SELECT * FROM parcels WHERE upper(tracking)=? AND current_hub_id=?',(tracking,doc['source_hub_id'])).fetchall()
                if len(candidates)==1:check_transfer_city(c,doc,candidates[0])
                raise Error('Colis non scanné : cette référence ne figure pas dans ce transfert actif.',404)
            if line['departure_scanned_at']:
                return jsonify(ok=True,already_scanned=True,departure_scanned=doc['departure_scanned'],count=doc['count'],dispatched=bool(doc['dispatched_at']))
            if doc['status'] not in ['Préparé','Départ partiel']:
                raise Error('Le scan de sortie exige un transfert encore en préparation.',409)
            p=parcel(c,line['parcel_id'],u)
            special_return=doc.get('palette_purpose') in ('return_to_central','return_to_origin')
            if special_return:
                if line.get('return_status') not in ('Retourné','Refusé') or p['status']!=line['return_status']:
                    raise Error('Le statut de retour a changé. Faites vérifier le colis par Admin.',409)
            else:guard(c,p,False)
            if not parcel_physically_at_hub(p['current_hub_id'],doc['source_hub_id']):
                raise Error('Le colis n’est plus enregistré physiquement au Hub de départ.',409)
            check_transfer_city(c,doc,p)
            scanned_at=now()
            cur=c.execute('UPDATE ops_document_lines SET departure_scanned_at=?,departure_scanned_by=? WHERE id=? AND departure_scanned_at IS NULL',(scanned_at,u['id'],line['id']))
            if cur.rowcount!=1:raise Error('Le scan vient d’être enregistré. Rechargez le manifeste.',409)
            if doc.get('palette_purpose')=='return_to_central':
                c.execute("UPDATE ops_document_lines SET return_transit_status='Vers Hub Central' WHERE id=?",(line['id'],))
                c.execute("UPDATE parcels SET status='Vers Hub Central',current_hub_id=NULL,next_attempt_at=NULL,reason_code=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(scanned_at,p['id']))
                event(c,p['id'],'Vers Hub Central',doc['reference']+' · retour scanné au départ vers le Hub Central; réception attendue',u)
            elif special_return:
                # Onward sorting from Central preserves the received return state.
                c.execute('UPDATE parcels SET current_hub_id=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?',(scanned_at,p['id']))
                event(c,p['id'],p['status'],doc['reference']+' · scan de sortie Hub; statut financier inchangé',u)
            else:
                c.execute("UPDATE parcels SET status='Transit',current_hub_id=NULL,next_attempt_at=NULL,reason_code=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(scanned_at,p['id']))
                event(c,p['id'],'Transit',doc['reference']+' · scan de sortie du Hub',u)
            departure_scanned=doc['departure_scanned']+1;complete=departure_scanned==doc['count']
            next_status=('Reçu' if doc['received']==doc['count'] else 'Partiellement reçu' if doc['received'] else 'En transit') if complete else 'Départ partiel'
            completed_at=scanned_at if next_status=='Reçu' else None
            c.execute('UPDATE ops_documents SET status=?,dispatched_at=?,completed_at=?,revision=revision+1 WHERE id=?',(next_status,scanned_at if complete else None,completed_at,did))
            audit(c,did,u,'Scan de sortie enregistré',{'tracking':tracking,'parcel_id':p['id'],'source_hub_id':doc['source_hub_id']})
            if complete:audit(c,did,u,'Départ physique confirmé',{'count':doc['count'],'source_hub_id':doc['source_hub_id'],'destination_hub_id':doc['destination_hub_id']})
            return jsonify(ok=True,already_scanned=False,departure_scanned=departure_scanned,count=doc['count'],dispatched=complete,parcel_status='Vers Hub Central' if doc.get('palette_purpose')=='return_to_central' else p['status'] if special_return else 'Transit')

    @app.post(P+'/documents/<int:did>/reconcile-departure')
    @auth('admin')
    def ops_document_reconcile_departure(did):
        d=body();u=user()
        if set(d)!={'line_ids','reason','revision','confirmed'}:raise Error('Lignes, motif, confirmation et version du manifeste sont requis.')
        if d.get('confirmed') is not True:raise Error('Confirmez que les colis sélectionnés sont restés au Hub de départ.')
        raw_ids=d.get('line_ids')
        if not isinstance(raw_ids,list) or not 1<=len(raw_ids)<=100:raise Error('Sélectionnez de 1 à 100 lignes non parties.')
        line_ids=[integer(value,'Ligne') for value in raw_ids]
        if len(line_ids)!=len(set(line_ids)):raise Error('Une ligne ne peut être réconciliée qu’une fois.')
        reason=text(d,'reason',maxlen=600)
        if type(d.get('revision')) is not int:raise Error('Version du manifeste invalide.',409)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            doc=document_data(c,allowed_doc(c,did,u))
            if doc['kind']!='transfer' or not doc['departure_scan_required']:
                raise Error('La réconciliation concerne uniquement les transferts avec scan de sortie.',409)
            if doc['status']!='Départ partiel' or doc['departure_scanned']<=0:
                raise Error('La réconciliation exige un départ partiel encore ouvert.',409)
            if d['revision']!=doc['revision']:raise Error('Le manifeste a changé. Rechargez-le.',409)
            by_id={line['id']:line for line in doc['lines']}
            selected=[]
            for line_id in line_ids:
                line=by_id.get(line_id)
                if (not line or not line['active'] or line['departure_scanned_at'] or line['received_at']
                        or line['departure_reconciled_at']):
                    raise Error('Une ligne sélectionnée n’est plus éligible à la réconciliation.',409)
                p=parcel(c,line['parcel_id'],u)
                special_return=doc.get('palette_purpose') in ('return_to_central','return_to_origin')
                if special_return:
                    if line.get('return_status') not in ('Retourné','Refusé') or p['status']!=line['return_status']:
                        raise Error('Le statut de retour a changé; aucune réconciliation automatique.',409)
                else:guard(c,p,False)
                if not parcel_physically_at_hub(p['current_hub_id'],doc['source_hub_id']):
                    raise Error('Chaque colis retiré doit être physiquement enregistré au Hub de départ.',409)
                selected.append((line,p))
            reconciled_at=now()
            for line,p in selected:
                cur=c.execute('''UPDATE ops_document_lines SET active=0,departure_reconciled_at=?,
                    departure_reconciled_by=?,departure_reconciliation_reason=?
                    WHERE id=? AND active=1 AND departure_scanned_at IS NULL AND received_at IS NULL
                    AND departure_reconciled_at IS NULL''',(reconciled_at,u['id'],reason,line['id']))
                if cur.rowcount!=1:raise Error('Une ligne vient de changer. Rechargez le manifeste.',409)
                c.execute('UPDATE parcels SET ops_revision=ops_revision+1 WHERE id=?',(p['id'],))
            after=document_data(c,doc)
            if after['count']<=0:raise Error('Un manifeste doit garder au moins une ligne active.',409)
            try:next_status=manifest_status_from_counts(after['count'],after['departure_scanned'],after['received'])
            except ValueError:raise Error('Les compteurs du manifeste sont incohérents; aucune réconciliation appliquée.',409)
            completed_at=reconciled_at if next_status=='Reçu' else None
            if next_status!='Départ partiel':
                dispatched_at=c.execute('''SELECT max(departure_scanned_at) FROM ops_document_lines
                    WHERE document_id=? AND departure_reconciled_at IS NULL''',(did,)).fetchone()[0] or reconciled_at
            else:dispatched_at=doc['dispatched_at']
            if next_status=='Reçu':c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,))
            cur=c.execute('''UPDATE ops_documents SET status=?,dispatched_at=?,completed_at=?,revision=revision+1
                WHERE id=? AND revision=?''',(next_status,dispatched_at,completed_at,did,doc['revision']))
            if cur.rowcount!=1:raise Error('Le manifeste vient de changer. Rechargez-le.',409)
            audit(c,did,u,'Colis non partis réconciliés',{'count':len(selected),'reason':reason,
                'remaining_manifest_count':after['count'],'departure_scanned':after['departure_scanned']})
            return jsonify(ok=True,reconciled=len(selected),count=after['count'],
                departure_scanned=after['departure_scanned'],status=next_status,revision=doc['revision']+1)

    @app.post(P+'/documents/<int:did>/<action>')
    @auth('admin','agent')
    def ops_document_action(did,action):
        d=body();u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc=document_data(c,allowed_doc(c,did,u))
            if u['role']=='agent' and (action!='receive' or not hub_manager_transfer_scope(doc,u.get('agent_hub_id'),'arrival')):
                raise Error('Document introuvable.',404)
            if doc['kind']=='partner_palette':raise Error('Utilisez la réception dédiée Palettes partenaires.',409)
            if action=='dispatch' and doc['kind']=='transfer' and doc['departure_scan_required']:
                raise Error('Le départ de ce transfert est confirmé par le scan de chaque colis.',409)
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
                        check_transfer_city(c,doc,p)
                    c.execute("UPDATE ops_documents SET status='En transit',dispatched_at=?,revision=revision+1 WHERE id=?",(now(),did))
                    audit(c,did,u,'Départ confirmé',{'count':doc['count']})
                    for line in doc['lines']:
                        if doc['kind']=='transfer':
                            c.execute("UPDATE parcels SET status='Transit',current_hub_id=NULL,next_attempt_at=NULL,reason_code=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(now(),line['parcel_id']))
                        event(c,line['parcel_id'],'Transit' if doc['kind']=='transfer' else line['initial_status'],doc['reference']+' · départ physique déclaré',u)
            elif action=='receive':
                tracking=text(d,'tracking',maxlen=80).upper()
                line=next((l for l in doc['lines'] if l['tracking'].upper()==tracking),None)
                special_return=doc.get('palette_purpose') in ('return_to_central','return_to_origin')
                if line and line['departure_reconciled_at']:
                    if u['role']=='agent':raise Error('Colis non disponible pour réception à ce Hub.',404)
                    raise Error('Cette ligne a été retirée du manifeste de départ.',409)
                if u['role']=='agent':
                    unavailable='Colis non disponible pour réception à ce Hub.'
                    if not line:raise Error(unavailable,404)
                    p=c.execute('SELECT * FROM parcels WHERE id=?',(line['parcel_id'],)).fetchone()
                    if not p:raise Error(unavailable,404)
                    if line['received_at']:
                        if p['current_hub_id']==u.get('agent_hub_id'):return jsonify(ok=True,already_received=True)
                        raise Error(unavailable,404)
                    if doc['status'] not in ['En transit','Partiellement reçu','Départ partiel']:
                        raise Error(unavailable,404)
                    expected_status=(line.get('return_transit_status') or line.get('return_status')) if special_return else 'Transit'
                    if p['current_hub_id'] is not None or (special_return and line.get('return_status') not in ('Retourné','Refusé')) or p['status']!=expected_status:
                        raise Error(unavailable,404)
                    if doc['departure_scan_required'] and not line['departure_scanned_at']:
                        raise Error(unavailable,404)
                else:
                    if not line:raise Error('Ce colis ne figure pas dans ce document.',404)
                    if doc['kind']=='transfer' and doc['departure_scan_required'] and not line['departure_scanned_at']:
                        raise Error('Le scan de sortie de ce colis est requis avant sa réception.',409)
                    if line['received_at']:return jsonify(ok=True,already_received=True)
                    if doc['status'] not in ['En transit','Partiellement reçu','Départ partiel']:
                        raise Error('Confirmez le départ du document avant réception.',409)
                    p=parcel(c,line['parcel_id'],u)
                if not p:raise Error('Document introuvable.',404)
                if doc['kind']=='transfer' and doc['departure_scan_required']:
                    expected_status=(line.get('return_transit_status') or line.get('return_status')) if special_return else 'Transit'
                    if p['current_hub_id'] is not None or p['status']!=expected_status:
                        raise Error('Le colis n’est pas en transit vers ce Hub ou a déjà été localisé ailleurs.',409)
                if doc['kind']!='return' and not special_return:
                    if u['role']=='agent':
                        try:guard(c,p,False)
                        except Error:raise Error('Colis non disponible pour réception à ce Hub.',404)
                    else:guard(c,p,False)
                if special_return and (line.get('return_status') not in ('Retourné','Refusé') or p['status']!=(line.get('return_transit_status') or line.get('return_status'))):
                    raise Error('Le statut de retour a changé. Faites vérifier le colis par Admin.',409)
                received_at=now()
                c.execute('UPDATE ops_document_lines SET received_at=?,received_by=? WHERE id=?',(received_at,u['id'],line['id']))
                received_count=doc['received']+1
                departures_complete=(not doc['departure_scan_required'] or doc['departure_scanned']==doc['count'])
                complete=departures_complete and received_count==doc['count']
                next_status='Reçu' if complete else 'Partiellement reçu' if departures_complete else 'Départ partiel'
                c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',(next_status,received_at if complete else None,did))
                c.execute('UPDATE parcels SET current_hub_id=?,ops_revision=ops_revision+1,updated_at=? WHERE id=?',(doc['destination_hub_id'],received_at,p['id']))
                received_status='Réceptionné' if doc['kind']=='transfer' else 'Au hub'
                if doc['kind']!='return' and not special_return:
                    c.execute("UPDATE parcels SET status=?,next_attempt_at=NULL,reason_code=NULL,updated_at=? WHERE id=?",(received_status,received_at,p['id']))
                if complete:c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,))
                central_return=doc.get('palette_purpose')=='return_to_central'
                if central_return:
                    c.execute("UPDATE parcels SET status='Retourné',next_attempt_at=NULL,reason_code=NULL WHERE id=?",(p['id'],))
                event_status='Retourné' if central_return else p['status'] if doc['kind']=='return' or special_return else received_status
                event_note=doc['reference']+(' · retour réceptionné physiquement au Hub Central · statut Retourné confirmé' if central_return else ' · réception physique déclarée'+(' · état de retour conservé' if special_return else ''))
                event(c,p['id'],event_status,event_note,u)
                audit(c,did,u,'Colis reçu',{'tracking':tracking,'parcel_id':p['id'],'palette_purpose':doc.get('palette_purpose','standard'),'financial_status_preserved':bool(special_return and not central_return),'previous_status':p['status'],'new_status':event_status})
            else:raise Error('Action inconnue.',404)
            return jsonify(ok=True,already_received=False,parcel_status=event_status if action=='receive' else None)

    @app.post(P+'/assignments/preview')
    @auth('admin')
    def ops_assignment_preview():
        d=body();pids=ids(d);u=user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');dr=enabled_user(c,d.get('driver_id'),'livreur');driver_hub=c.execute('SELECT driver_hub_id FROM users WHERE id=?',(dr['id'],)).fetchone()['driver_hub_id']
            if type(driver_hub) is not int or driver_hub<=0 or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(driver_hub,)).fetchone():raise Error('Le livreur doit être rattaché à un Hub actif avant l’affectation.',409)
            rows=[]
            for pid in pids:
                p=parcel(c,pid,u);guard(c,p)
                if p['status'] in ['Livré','Retourné','Refusé']:raise Error('Affectation groupée réservée aux colis non clôturés.')
                if p['status']=='Reçu par le livreur' and p['driver_id']!=dr['id']:raise Error('Prise en charge déjà déclarée. Indiquez l’état réel de remise avant la réaffectation.',409)
                if p['driver_id']!=dr['id'] and not driver_dispatch_allowed(c,p.get('current_hub_id'),driver_hub):raise Error('Le colis '+p['tracking']+' n’est pas physiquement au Hub du livreur.',409)
                rows.append({'id':pid,'tracking':p['tracking'],'old_driver_id':p['driver_id'],'revision':p['ops_revision'],'status':p['status'],'current_hub_id':p.get('current_hub_id')})
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
            dr=enabled_user(c,draft['driver_id'],'livreur');driver_hub=c.execute('SELECT driver_hub_id FROM users WHERE id=?',(dr['id'],)).fetchone()['driver_hub_id']
            if type(driver_hub) is not int or driver_hub<=0 or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(driver_hub,)).fetchone():raise Error('Le livreur doit être rattaché à un Hub actif avant l’affectation.',409)
            for item in json.loads(draft['snapshot']):
                p=parcel(c,item['id'],u)
                if p['ops_revision']!=item['revision'] or p['status']!=item['status'] or p['driver_id']!=item['old_driver_id'] or p.get('current_hub_id')!=item.get('current_hub_id'):raise Error('Un colis a changé. Recréez un aperçu.',409)
                if p['driver_id']!=dr['id'] and not driver_dispatch_allowed(c,p.get('current_hub_id'),driver_hub):raise Error('Le colis '+p['tracking']+' n’est plus physiquement au Hub du livreur.',409)
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
            purge_read_notifications(c, now())
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

    @app.get(P+'/hub-dashboard')
    @auth('agent')
    def ops_hub_dashboard():
        u=user();hub_id=u.get('agent_hub_id')
        if type(hub_id) is not int or hub_id<=0:raise Error('Ce compte n’est pas rattaché à un Hub actif.',403)
        end=request.args.get('to') or datetime.now().date().isoformat()
        start=request.args.get('from') or (datetime.now()-timedelta(days=6)).date().isoformat()
        try:
            a,b=datetime.strptime(start,'%Y-%m-%d'),datetime.strptime(end,'%Y-%m-%d')
            if a.strftime('%Y-%m-%d')!=start or b.strftime('%Y-%m-%d')!=end or a>b or (b-a).days>365:raise ValueError()
        except ValueError:raise Error('Période invalide (366 jours maximum).')
        with conn() as c:
            hub_row=c.execute('''SELECT h.id,h.name,ci.name city FROM ops_hubs h
                JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1''',(hub_id,)).fetchone()
            if not hub_row:raise Error('Le Hub de ce compte est inactif ou introuvable.',403)
            parcels_here=c.execute('SELECT count(*) FROM parcels WHERE current_hub_id=?',(hub_id,)).fetchone()[0]
            expected_arrivals=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE d.kind='transfer' AND d.destination_hub_id=? AND l.active=1 AND l.received_at IS NULL AND (
                    (d.departure_scan_required=1 AND l.departure_scanned_at IS NOT NULL AND d.status IN ('Départ partiel','En transit','Partiellement reçu'))
                    OR (d.departure_scan_required=0 AND d.status IN ('En transit','Partiellement reçu'))
                )''',(hub_id,)).fetchone()[0]
            inbound_documents=c.execute('''SELECT count(DISTINCT d.id) FROM ops_documents d JOIN ops_document_lines l ON l.document_id=d.id
                WHERE d.kind='transfer' AND d.destination_hub_id=? AND l.active=1 AND l.received_at IS NULL AND (
                    (d.departure_scan_required=1 AND l.departure_scanned_at IS NOT NULL AND d.status IN ('Départ partiel','En transit','Partiellement reçu'))
                    OR (d.departure_scan_required=0 AND d.status IN ('En transit','Partiellement reçu'))
                )''',(hub_id,)).fetchone()[0]
            outbound_documents=c.execute('''SELECT count(*) FROM ops_documents d WHERE d.kind='transfer'
                AND d.source_hub_id=? AND d.status IN ('Préparé','Départ partiel')''',(hub_id,)).fetchone()[0]
            pending_departure_scans=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                JOIN parcels p ON p.id=l.parcel_id WHERE d.kind='transfer' AND d.source_hub_id=?
                AND d.departure_scan_required=1 AND d.status IN ('Préparé','Départ partiel')
                AND l.active=1 AND l.departure_scanned_at IS NULL AND p.current_hub_id=?''',(hub_id,hub_id)).fetchone()[0]
            departure_events=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE d.kind='transfer' AND d.source_hub_id=? AND (
                    (d.departure_scan_required=1 AND substr(l.departure_scanned_at,1,10) BETWEEN ? AND ?)
                    OR (d.departure_scan_required=0 AND substr(d.dispatched_at,1,10) BETWEEN ? AND ?)
                )''',(hub_id,start,end,start,end)).fetchone()[0]
            receipt_events=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                WHERE d.kind='transfer' AND d.destination_hub_id=? AND substr(l.received_at,1,10) BETWEEN ? AND ?''',(hub_id,start,end)).fetchone()[0]
            daily=[dict(r) for r in c.execute('''SELECT day,sum(departures) departures,sum(receipts) receipts FROM (
                    SELECT substr(l.departure_scanned_at,1,10) day,1 departures,0 receipts
                    FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                    WHERE d.kind='transfer' AND d.source_hub_id=? AND d.departure_scan_required=1
                      AND substr(l.departure_scanned_at,1,10) BETWEEN ? AND ?
                    UNION ALL
                    SELECT substr(d.dispatched_at,1,10) day,1 departures,0 receipts
                    FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                    WHERE d.kind='transfer' AND d.source_hub_id=? AND d.departure_scan_required=0
                      AND substr(d.dispatched_at,1,10) BETWEEN ? AND ?
                    UNION ALL
                    SELECT substr(l.received_at,1,10) day,0 departures,1 receipts
                    FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                    WHERE d.kind='transfer' AND d.destination_hub_id=?
                      AND substr(l.received_at,1,10) BETWEEN ? AND ?
                ) GROUP BY day ORDER BY day DESC''',
                (hub_id,start,end,hub_id,start,end,hub_id,start,end)).fetchall()]
            daily=hub_daily_metrics(c,hub_id,start,end,daily)
            metrics=hub_operational_metrics(c,hub_id,start,end)
            metrics_started_at=c.execute("SELECT value FROM settings WHERE key='hub_metrics_started_at'").fetchone()[0]
            today=datetime.now().date()
            windows={}
            for days in (7,30):
                window_from=(today-timedelta(days=days-1)).isoformat();window_to=today.isoformat()
                win_departures=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                    WHERE d.kind='transfer' AND d.source_hub_id=? AND (
                        (d.departure_scan_required=1 AND substr(l.departure_scanned_at,1,10) BETWEEN ? AND ?)
                        OR (d.departure_scan_required=0 AND substr(d.dispatched_at,1,10) BETWEEN ? AND ?)
                    )''',(hub_id,window_from,window_to,window_from,window_to)).fetchone()[0]
                win_receipts=c.execute('''SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
                    WHERE d.kind='transfer' AND d.destination_hub_id=? AND substr(l.received_at,1,10) BETWEEN ? AND ?''',
                    (hub_id,window_from,window_to)).fetchone()[0]
                windows[str(days)]={'from':window_from,'to':window_to,'departures':win_departures,'receipts':win_receipts,
                    'metrics':hub_operational_metrics(c,hub_id,window_from,window_to)}
            return jsonify(hub={'name':hub_row['name'],'city':hub_row['city']},period_from=start,period_to=end,
                parcels_here=parcels_here,expected_arrivals=expected_arrivals,inbound_documents=inbound_documents,
                outbound_documents=outbound_documents,pending_departure_scans=pending_departure_scans,
                departures=departure_events,receipts=receipt_events,daily=daily,metrics=metrics,
                metrics_started_at=metrics_started_at,windows=windows)

    @app.get(P+'/hub/drivers')
    @auth('agent')
    def ops_hub_drivers():
        actor=user()
        with conn() as c:
            local_hub=local_manager_hub(c,actor)
            rows=[dict(r) for r in c.execute('''SELECT u.id,u.name,u.email,u.phone,u.active,u.created_at,u.driver_hub_id,u.team_lead_id,
                    u.driver_revision,u.driver_blocked,u.driver_archived,
                    (SELECT count(*) FROM parcels p WHERE p.driver_id=u.id
                        AND p.status NOT IN ('Livré','Retourné','Refusé','Annulé')
                        AND p.current_hub_id=u.driver_hub_id
                        AND NOT EXISTS(SELECT 1 FROM driver_receipts dr WHERE dr.parcel_id=p.id AND dr.driver_id=p.driver_id)
                    ) assigned_open_count
                FROM users u WHERE u.role='livreur' AND u.driver_hub_id=?
                ORDER BY u.active DESC,u.name COLLATE NOCASE,u.id''',(local_hub['id'],))]
            from hub_access import local_driver_parcel_scope, driver_financial_hub_sql
            for d in rows:
                d['outstanding']=c.execute(f"SELECT count(*) FROM parcels p WHERE p.driver_id=? AND p.status!='Livré' AND {local_driver_parcel_scope()} AND NOT EXISTS(SELECT 1 FROM driver_receipts r WHERE r.parcel_id=p.id AND r.driver_id=p.driver_id)",(d['id'],local_hub['id'],local_hub['id'])).fetchone()[0]
                d['delivered']=c.execute(f"SELECT count(*) FROM parcels p WHERE p.driver_id=? AND p.status='Livré' AND {driver_financial_hub_sql()}=?",(d['id'],local_hub['id'])).fetchone()[0]
            return jsonify(hub=local_hub,drivers=rows)

    @app.post(P+'/hub/drivers')
    @auth('agent')
    def ops_hub_driver_create():
        d=body();actor=user()
        allowed={'name','email','phone','password'}
        if not isinstance(d,dict) or set(d)-allowed or not {'name','email','password'}.issubset(d):raise Error('Champs du compte livreur invalides.')
        name=text(d,'name',maxlen=120)
        email=text(d,'email',maxlen=254).lower()
        phone=text(d,'phone',False,maxlen=40)
        password=text(d,'password',maxlen=128)
        if len(password)<10:raise Error('10 caractères minimum pour le mot de passe du livreur.')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise Error('Adresse e-mail invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            local_hub=local_manager_hub(c,actor)
            if c.execute('SELECT 1 FROM users WHERE lower(email)=lower(?)',(email,)).fetchone():raise Error('Cette adresse e-mail est déjà utilisée.',409)
            uid=c.execute('''INSERT INTO users(name,email,password,role,company,phone,active,created_at,client_type,agent_hub_id,driver_hub_id)
                VALUES(?,?,?,'livreur','ORIENTAL24',?,1,?,'vendeur',NULL,?)''',
                (name,email,generate_password_hash(password),phone,now(),local_hub['id'])).lastrowid
            append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_driver_created',
                entity_type='driver_hub_assignment',entity_id=uid,old_value=None,
                new_value={'driver_id':uid,'name':name,'email':email,'phone':phone,'driver_hub_id':local_hub['id']},
                metadata={'hub_id':local_hub['id']},created_at=now())
            return jsonify(ok=True,id=uid,hub=local_hub)

    @app.patch(P+'/hub/drivers/<int:driver_id>')
    @auth('agent')
    def ops_hub_driver_update(driver_id):
        d=body();actor=user()
        allowed={'name','email','phone','active','password'}
        required={'name','email','phone','active'}
        if set(d)-allowed or not required.issubset(d):raise Error('Champs du compte livreur invalides.')
        name=text(d,'name',maxlen=120);email=text(d,'email',maxlen=254).lower();phone=text(d,'phone',False,maxlen=40)
        active=d.get('active')
        if type(active) is not bool:raise Error('Statut actif invalide.')
        password=d.get('password','')
        if not isinstance(password,str) or len(password)>128 or (password and len(password)<10):raise Error('Un nouveau mot de passe doit contenir au moins 10 caractères.')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email):raise Error('Adresse e-mail invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');local_hub=local_manager_hub(c,actor)
            driver=c.execute("SELECT id,name,email,phone,active,driver_hub_id,team_lead_id,driver_blocked,driver_archived,driver_revision FROM users WHERE id=? AND role='livreur' AND driver_hub_id=?",(driver_id,local_hub['id'])).fetchone()
            if not driver:raise Error('Livreur introuvable dans votre Hub.',404)
            if active and (driver['driver_blocked'] or driver['driver_archived']):raise Error('Utilisez le contrôle Accès pour débloquer ou restaurer ce livreur.',409)
            if c.execute('SELECT 1 FROM users WHERE lower(email)=lower(?) AND id!=?',(email,driver_id)).fetchone():raise Error('Cette adresse e-mail est déjà utilisée.',409)
            assigned=c.execute("SELECT count(*) FROM parcels WHERE driver_id=? AND status NOT IN ('Livré','Retourné','Refusé','Annulé')",(driver_id,)).fetchone()[0]
            if driver['active'] and not active and assigned:
                raise Error('Réaffectez ou clôturez les colis ouverts avant de désactiver ce livreur.',409)
            before={key:driver[key] for key in ('name','email','phone','active','driver_hub_id','team_lead_id')}
            if password:
                c.execute('''UPDATE users SET name=?,email=?,phone=?,active=?,password=?,driver_revision=driver_revision+1 WHERE id=?''',
                    (name,email,phone,int(active),generate_password_hash(password),driver_id))
            else:
                c.execute('''UPDATE users SET name=?,email=?,phone=?,active=?,driver_revision=driver_revision+1 WHERE id=?''',
                    (name,email,phone,int(active),driver_id))
            after={'name':name,'email':email,'phone':phone,'active':active,'driver_hub_id':local_hub['id'],'team_lead_id':driver['team_lead_id']}
            append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_driver_updated',
                entity_type='driver_hub_assignment',entity_id=driver_id,old_value=before,new_value=after,
                metadata={'hub_id':local_hub['id']},created_at=now())
            return jsonify(ok=True,id=driver_id,hub=local_hub)

    @app.post(P+'/hub/drivers/<int:driver_id>/access')
    @auth('admin','agent')
    def ops_hub_driver_access(driver_id):
        d=body();actor=user()
        if set(d)!={'action','reason','revision','confirmed'} or d.get('action') not in ('block','unblock','archive','restore'):
            raise Error('Action d’accès invalide.')
        if d.get('confirmed') is not True:raise Error('Confirmez explicitement cette modification d’accès.')
        reason=text(d,'reason',maxlen=300)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            local_hub=local_manager_hub(c,actor) if actor['role']=='agent' else None
            if actor['role']=='agent':
                driver=c.execute("SELECT id,name,active,driver_hub_id,driver_revision,driver_blocked,driver_archived FROM users WHERE id=? AND role='livreur' AND driver_hub_id=?",(driver_id,local_hub['id'])).fetchone()
            else:
                driver=c.execute("SELECT id,name,active,driver_hub_id,driver_revision,driver_blocked,driver_archived FROM users WHERE id=? AND role='livreur'",(driver_id,)).fetchone()
            if not driver:raise Error('Livreur introuvable dans votre Hub.',404)
            if type(d.get('revision')) is not int or d['revision']!=driver['driver_revision']:
                raise Error('Données modifiées. Actualisez avant de confirmer.',409)
            action=d['action']
            if action=='archive' and (c.execute("SELECT count(*) FROM parcels p WHERE p.driver_id=? AND p.status!='Livré' AND NOT EXISTS(SELECT 1 FROM driver_receipts r WHERE r.parcel_id=p.id AND r.driver_id=p.driver_id)",(driver_id,)).fetchone()[0] or c.execute("SELECT 1 FROM ops_documents WHERE driver_id=? AND status NOT IN ('Reçu','Annulé') LIMIT 1",(driver_id,)).fetchone()):
                raise Error('Récupérez les colis non livrés et terminez les documents actifs avant l’archivage.',409)
            old={'active':driver['active'],'driver_blocked':driver['driver_blocked'],'driver_archived':driver['driver_archived'],'driver_hub_id':driver['driver_hub_id']}
            blocked=driver['driver_blocked'];archived=driver['driver_archived']
            if action=='block':blocked=1
            elif action=='unblock':blocked=0
            elif action=='archive':archived=1
            elif action=='restore':archived=0
            active=int(not blocked and not archived)
            if (blocked,archived,active)==(driver['driver_blocked'],driver['driver_archived'],driver['active']):return jsonify(ok=True,changed=False)
            c.execute('UPDATE users SET driver_blocked=?,driver_archived=?,active=?,driver_revision=driver_revision+1 WHERE id=?',(blocked,archived,active,driver_id))
            revoke_user=services.get('security_revoke_user')
            if not active and revoke_user:
                revoke_user(c,driver_id,'Compte '+action+' par Hub Manager',actor['id'])
            c.execute('INSERT INTO driver_workspace_audit(driver_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',
                      (driver_id,actor['id'],'Hub Manager · '+action,json.dumps({'reason':reason,'active':active,'hub_id':local_hub['id'] if local_hub else None},ensure_ascii=False),now()))
            append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_driver_access_'+action,
                entity_type='driver_hub_access',entity_id=driver_id,old_value=old,
                new_value={'active':active,'driver_blocked':blocked,'driver_archived':archived,'driver_hub_id':driver['driver_hub_id']},
                metadata={'hub_id':local_hub['id'] if local_hub else None,'reason':reason},created_at=now())
            return jsonify(ok=True,changed=True,revision=driver['driver_revision']+1,active=bool(active),blocked=bool(blocked),archived=bool(archived))

    @app.post(P+'/hub/assignments')
    @auth('agent')
    def ops_hub_assignments():
        d=body();actor=user();required={'driver_id','parcel_ids','request_key','confirmed'}
        if set(d)!=required or d.get('confirmed') is not True:raise Error('Confirmez explicitement l’affectation des colis sélectionnés.')
        pids=ids(d);driver_id=integer(d.get('driver_id'),'Livreur');key=text(d,'request_key',maxlen=80)
        if not re.fullmatch('[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de saisie invalide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');local_hub=local_manager_hub(c,actor)
            payload={'hub_id':local_hub['id'],'driver_id':driver_id,'parcel_ids':pids}
            fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            prior=c.execute('SELECT * FROM ops_hub_assignment_keys WHERE actor_id=? AND request_key=?',(actor['id'],key)).fetchone()
            if prior:
                if prior['payload_hash']!=fingerprint:raise Error('Cette clé de saisie correspond à une autre affectation.',409)
                return jsonify(**json.loads(prior['result']),replayed=True)
            target=c.execute("SELECT id,name,driver_hub_id FROM users WHERE id=? AND role='livreur' AND active=1",(driver_id,)).fetchone()
            if not target or target['driver_hub_id']!=local_hub['id']:
                raise Error('Choisissez un livreur actif de votre Hub.',409)
            selected=[]
            for pid in pids:
                p=parcel(c,pid,actor);guard(c,p)
                if not parcel_physically_at_hub(p.get('current_hub_id'),local_hub['id']):
                    raise Error('Un colis sélectionné n’est pas physiquement présent dans votre Hub.',409)
                if p['status'] in ['Livré','Retourné','Refusé','Annulé','Transit','Reçu par le livreur']:
                    raise Error('L’affectation concerne uniquement les colis ouverts et non remis physiquement à un livreur.',409)
                if p['driver_id']!=driver_id and not driver_dispatch_allowed(c,p.get('current_hub_id'),target['driver_hub_id']):
                    raise Error('Le colis doit être physiquement présent dans le Hub actif du livreur.',409)
                selected.append(p)
            changed=[];already=[]
            for p in selected:
                has_receipt=c.execute('SELECT 1 FROM driver_receipts WHERE parcel_id=? AND driver_id=?',(p['id'],driver_id)).fetchone()
                if p['driver_id']==driver_id and not has_receipt:
                    already.append(p['id']);continue
                old_driver=p['driver_id']
                if old_driver!=driver_id:
                    change(c,p,{'driver_id':driver_id},actor)
                    c.execute('UPDATE parcels SET driver_id=?,updated_at=? WHERE id=?',(driver_id,now(),p['id']))
                    c.execute('DELETE FROM driver_receipts WHERE parcel_id=?',(p['id'],))
                else:
                    c.execute('''INSERT INTO ops_assignments(parcel_id,old_driver_id,new_driver_id,actor_id,created_at,hub_id)
                        VALUES(?,?,?,?,?,?)''',(p['id'],old_driver,driver_id,actor['id'],now(),local_hub['id']))
                    c.execute('UPDATE parcels SET ops_revision=ops_revision+1,updated_at=? WHERE id=?',(now(),p['id']))
                    c.execute('DELETE FROM driver_receipts WHERE parcel_id=?',(p['id'],))
                event(c,p['id'],p['status'],'Affectation locale au livreur '+target['name'],actor)
                notify_event(c,p['id'],p['status'],actor)
                append_audit_log(c,actor_id=actor['id'],actor_name=actor['name'],action='hub_parcel_assigned',
                    entity_type='parcel',entity_id=p['id'],old_value={'driver_id':old_driver},
                    new_value={'driver_id':driver_id,'hub_id':local_hub['id']},
                    metadata={'hub_id':local_hub['id'],'source':'hub_manager'},created_at=now())
                changed.append(p['id'])
            result={'ok':True,'assigned':len(changed),'already_assigned':len(already),
                    'parcel_ids':changed,'already_ids':already,'driver_id':driver_id,'hub_id':local_hub['id']}
            c.execute('INSERT INTO ops_hub_assignment_keys(actor_id,request_key,payload_hash,result,created_at) VALUES(?,?,?,?,?)',
                (actor['id'],key,fingerprint,json.dumps(result,ensure_ascii=False),now()))
            return jsonify(**result)

    @app.get(P+'/hub/driver-statements')
    @auth('agent')
    def ops_hub_driver_statements():
        actor=user()
        with conn() as c:
            local_hub=local_manager_hub(c,actor)
            rows=[];totals={'cod_cents':0,'commission_cents':0,'cash_remaining_cents':0,'commission_remaining_cents':0}
            for raw in c.execute('SELECT * FROM driver_statements WHERE hub_id=? ORDER BY id DESC LIMIT 500',(local_hub['id'],)).fetchall():
                statement=services['driver_finance_balances'](c,raw)
                item={key:statement.get(key) for key in ('id','driver_id','driver_name','mode','period_from','period_to','parcel_count',
                    'cod_cents','commission_cents','retained_cents','cash_due_cents','commission_due_cents',
                    'cash_received_cents','commission_paid_cents','cash_remaining_cents','commission_remaining_cents',
                    'status','reference','created_at','cancelled_at')}
                rows.append(item)
                if not item['cancelled_at']:
                    for key in totals:totals[key]+=int(item.get(key) or 0)
            return jsonify(hub=local_hub,rows=rows,count=len(rows),totals=totals,read_only=True)

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
            hubs=[{**dict(h),'parcels_here':c.execute('SELECT count(*) FROM parcels WHERE current_hub_id=?',(h['id'],)).fetchone()[0],'expected':c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.destination_hub_id=? AND l.active=1 AND l.received_at IS NULL AND (d.status IN ('En transit','Partiellement reçu') OR (d.status='Départ partiel' AND l.departure_scanned_at IS NOT NULL))",(h['id'],)).fetchone()[0]} for h in c.execute('SELECT * FROM ops_hubs ORDER BY name').fetchall()]
            hub_activity=[]
            for h in hubs:
                departed=c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.source_hub_id=? AND ((d.departure_scan_required=1 AND l.departure_scanned_at IS NOT NULL AND substr(l.departure_scanned_at,1,10) BETWEEN ? AND ?) OR (d.departure_scan_required=0 AND substr(d.dispatched_at,1,10) BETWEEN ? AND ?))",(h['id'],start,end,start,end)).fetchone()[0]
                received=c.execute("SELECT count(*) FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE d.destination_hub_id=? AND d.kind!='return' AND substr(l.received_at,1,10) BETWEEN ? AND ?",(h['id'],start,end)).fetchone()[0]
                hub_activity.append(dict(id=h['id'],name=h['name'],departed=departed,received=received))
            daily_assignments=[dict(r) for r in c.execute("SELECT substr(a.created_at,1,10) day,a.new_driver_id driver_id,u.name driver,count(*) assignment_events FROM ops_assignments a JOIN users u ON u.id=a.new_driver_id WHERE substr(a.created_at,1,10) BETWEEN ? AND ? GROUP BY day,a.new_driver_id ORDER BY day DESC,driver",(start,end))]
            return jsonify(drivers=drivers,daily=daily,hubs=hubs,hub_activity=hub_activity,daily_assignments=daily_assignments,period_from=start,period_to=end,started_at=c.execute("SELECT value FROM settings WHERE key='ops_started_at'").fetchone()[0])
