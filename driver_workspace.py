"""Morning dispatch / evening recovery. Physical custody is distinct from closed financial attribution."""
import json,re,hashlib
from flask import request,jsonify
from audit_guard import install_driver_workspace_audit_guards
from hub_access import driver_dispatch_allowed, local_driver_parcel_scope
from hub_analytics import install_driver_receipt_arrival_trigger
import exchange_flow
from parcel_statuses import EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED
from werkzeug.security import generate_password_hash

CLOSED=['Livré','Refusé','Retourné']

def register_driver_workspace(app,s):
    conn,auth,user,parcel,event,now,Error=(s[k] for k in ['conn','auth','user','parcel','event','now','APIError'])
    with conn() as c:
        columns={r['name'] for r in c.execute('PRAGMA table_info(users)')}
        for name,definition in [('driver_city_id','INTEGER REFERENCES cities(id)'),('driver_address',"TEXT NOT NULL DEFAULT ''"),('driver_revision','INTEGER NOT NULL DEFAULT 1'),('driver_blocked','INTEGER NOT NULL DEFAULT 0'),('driver_archived','INTEGER NOT NULL DEFAULT 0')]:
            if name not in columns:c.execute('ALTER TABLE users ADD COLUMN '+name+' '+definition)
        c.executescript('''
        CREATE TABLE IF NOT EXISTS driver_receipts(parcel_id INTEGER PRIMARY KEY REFERENCES parcels(id),driver_id INTEGER NOT NULL REFERENCES users(id),received_at TEXT NOT NULL,hub_id INTEGER REFERENCES ops_hubs(id));
        CREATE TABLE IF NOT EXISTS driver_workspace_audit(id INTEGER PRIMARY KEY,driver_id INTEGER NOT NULL REFERENCES users(id),actor_id INTEGER NOT NULL REFERENCES users(id),action TEXT NOT NULL,parcel_id INTEGER REFERENCES parcels(id),details TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS driver_scan_keys(actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key));
        ''')
        install_driver_receipt_arrival_trigger(c)
        install_driver_workspace_audit_guards(c)
    def driver(c,uid):
        r=c.execute("SELECT id,name,email,phone,company,active,created_at,driver_hub_id,team_lead_id,driver_city_id,driver_address,driver_revision,driver_blocked,driver_archived FROM users WHERE id=? AND role='livreur'",(uid,)).fetchone()
        actor=user()
        if not r or (actor['role']=='agent' and r['driver_hub_id']!=actor.get('agent_hub_id')):
            raise Error('Livreur introuvable.',404)
        return dict(r)
    def custody_parcel(c,pid,u):
        if u['role']!='agent':return parcel(c,pid,u)
        h=u['agent_hub_id']
        row=c.execute(f'SELECT p.id FROM parcels p WHERE p.id=? AND {local_driver_parcel_scope()}',(pid,h,h)).fetchone()
        if not row:raise Error('Colis introuvable dans votre Hub.',404)
        # Scope checked above. Keep the common lock/financial metadata loader.
        return parcel(c,pid,{'role':'admin'})
    def body():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def rev(d,expected):
        if type(d.get('revision')) is not int or d['revision']!=expected:raise Error('Données modifiées. Actualisez avant de confirmer.',409)
    def text(d,k,limit,required=True):
        value=d.get(k,'')
        if not isinstance(value,str) or len(value.strip())>limit or (required and not value.strip()):raise Error('Champ invalide : '+k)
        return value.strip()
    def record(c,uid,u,action,details,pid=None):c.execute('INSERT INTO driver_workspace_audit(driver_id,actor_id,action,parcel_id,details,created_at) VALUES(?,?,?,?,?,?)',(uid,u['id'],action,pid,json.dumps({**details,'actor_hub_id':u.get('agent_hub_id')},ensure_ascii=False),now()))
    def outstanding(c,uid):return c.execute("SELECT count(*) FROM parcels p WHERE p.driver_id=? AND p.status!='Livré' AND NOT EXISTS(SELECT 1 FROM driver_receipts r WHERE r.parcel_id=p.id AND r.driver_id=p.driver_id)",(uid,)).fetchone()[0]
    @app.get('/api/drivers-workspace')
    @auth('admin')
    def driver_list():
        with conn() as c:
            rows=[]
            for r in c.execute("SELECT id FROM users WHERE role='livreur' ORDER BY id"):
                d=driver(c,r['id']);d['outstanding']=outstanding(c,d['id']);d['delivered']=c.execute("SELECT count(*) FROM parcels WHERE driver_id=? AND status='Livré'",(d['id'],)).fetchone()[0];rows.append(d)
            return jsonify(rows)
    @app.route('/api/drivers-workspace/<int:uid>',methods=['GET','PATCH'])
    @auth('admin','agent')
    def driver_info(uid):
        u=user()
        with conn() as c:
            if request.method=='PATCH' and u['role']!='admin':raise Error('Accès non autorisé.',403)
            if request.method=='PATCH':c.execute('BEGIN IMMEDIATE')
            old=driver(c,uid)
            if request.method=='PATCH':
                d=body()
                old_fields={'name','phone','city_id','address','password','revision'}
                if set(d) not in (old_fields,old_fields|{'driver_hub_id'}):raise Error('Champs de la fiche invalides.')
                rev(d,old['driver_revision']);name=text(d,'name',120);phone=text(d,'phone',40);address=text(d,'address',500,False);pw=text(d,'password',128,False);cid=d['city_id']
                new_driver_hub=s['driver_hub_value'](c,d.get('driver_hub_id',old['driver_hub_id']),allow_existing_inactive=old['driver_hub_id'])
                if new_driver_hub!=old['driver_hub_id']:
                    s['validate_driver_hub_mapping'](c,uid,new_driver_hub)
                    s['validate_driver_team_hub'](c,uid,new_driver_hub,lead_id=old['team_lead_id'])
                if not re.fullmatch(r'\+?[0-9]{9,15}',re.sub(r'[ ()-]','',phone)):raise Error('Téléphone invalide.')
                if cid is not None and (type(cid) is not int or not c.execute('SELECT 1 FROM cities WHERE id=?',(cid,)).fetchone()):raise Error('Ville invalide.')
                if pw and len(pw)<10:raise Error('Mot de passe : 10 caractères minimum.')
                if not pw and (name,phone,cid,address,new_driver_hub)==(old['name'],old['phone'],old['driver_city_id'],old['driver_address'],old['driver_hub_id']):return jsonify(ok=True,changed=False)
                c.execute('UPDATE users SET name=?,phone=?,driver_city_id=?,driver_address=?,driver_hub_id=?,driver_revision=driver_revision+1 WHERE id=?',(name,phone,cid,address,new_driver_hub,uid))
                if new_driver_hub!=old['driver_hub_id']:
                    s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='driver_hub_reassigned',
                        entity_type='driver_hub_assignment',entity_id=uid,old_value={'driver_hub_id':old['driver_hub_id']},
                        new_value={'driver_hub_id':new_driver_hub},metadata={'source':'driver_workspace_admin_edit'},created_at=now())
                if pw:
                    c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash(pw),uid));s['security_revoke_user'](c,uid,'Mot de passe réinitialisé par Admin',u['id'])
                record(c,uid,u,'informations modifiées',dict(name=name,phone=phone,city_id=cid,address=address,driver_hub_id=new_driver_hub,password_reset=bool(pw)))
                return jsonify(ok=True,changed=True)
            if u['role']=='agent':
                ids=c.execute(f'SELECT p.id FROM parcels p WHERE p.driver_id=? AND {local_driver_parcel_scope()} AND NOT EXISTS(SELECT 1 FROM driver_receipts r WHERE r.parcel_id=p.id AND r.driver_id=p.driver_id) ORDER BY COALESCE(julianday(p.status_updated_at),julianday(p.created_at),0) DESC,p.id DESC',(uid,u['agent_hub_id'],u['agent_hub_id'])).fetchall()
                ps=[custody_parcel(c,r['id'],u) for r in ids]
            else:ps=[p for p in s['list_parcels'](c,u) if p['driver_id']==uid and not p.get('driver_returned')]
            audit=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM driver_workspace_audit a JOIN users u ON u.id=a.actor_id WHERE driver_id=? ORDER BY a.id DESC LIMIT 200',(uid,))]
            if u['role']=='agent':audit=[a for a in audit if a['details'].get('actor_hub_id')==u['agent_hub_id']]
            return jsonify(driver=old,parcels=ps,audit=audit)
    @app.post('/api/drivers-workspace/<int:uid>/access')
    @auth('admin')
    def driver_access(uid):
        d=body();u=user()
        if set(d)!={'action','reason','revision'} or d.get('action') not in ['block','unblock','archive','restore']:raise Error('Action invalide.')
        reason=text(d,'reason',300);action=d['action']
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');old=driver(c,uid);rev(d,old['driver_revision'])
            if action=='archive' and (outstanding(c,uid) or c.execute("SELECT 1 FROM ops_documents WHERE driver_id=? AND status NOT IN ('Reçu','Annulé')",(uid,)).fetchone()):raise Error('Récupérez les colis non livrés et terminez les documents actifs avant l’archivage.',409)
            blocked=old['driver_blocked'];archived=old['driver_archived']
            if action=='block':blocked=1
            if action=='unblock':blocked=0
            if action=='archive':archived=1
            if action=='restore':archived=0
            active=int(not blocked and not archived)
            if (blocked,archived,active)==(old['driver_blocked'],old['driver_archived'],old['active']):return jsonify(ok=True,changed=False)
            c.execute('UPDATE users SET driver_blocked=?,driver_archived=?,active=?,driver_revision=driver_revision+1 WHERE id=?',(blocked,archived,active,uid))
            if not active:s['security_revoke_user'](c,uid,'Compte '+action+' par Admin',u['id'])
            record(c,uid,u,action,{'reason':reason,'active':active});return jsonify(ok=True,changed=True)
    def check(c,dr,p,mode):
        if mode not in ['assign','receive']:raise Error('Mode invalide.')
        received=c.execute('SELECT * FROM driver_receipts WHERE parcel_id=?',(p['id'],)).fetchone()
        if mode=='receive' and p['status']=='Livré':raise Error('Colis Livré : il reste au livreur pour son suivi financier. Aucune récupération automatique.',409)
        if mode=='receive' and received and received['driver_id']==dr['id'] and p['driver_id'] in [None,dr['id']]:return True
        if p['operations_locked']:raise Error('Colis lié à un document actif : utilisez sa réception dédiée.',409)
        if mode=='assign' and 'damage_hold_open' in s and s['damage_hold_open'](c,p['id']):raise Error('Colis réceptionné endommagé : incident à traiter avant affectation.',409)
        if mode=='assign':
            if not dr['active'] or dr['driver_archived']:raise Error('Livreur bloqué ou archivé : affectation impossible.',409)
            if p['status'] in CLOSED or p['invoice_id'] or p['financial_locked']:raise Error('Colis clôturé ou verrouillé : affectation impossible.',409)
            if p['driver_id'] and p['driver_id']!=dr['id']:raise Error('Récupérez d’abord ce colis auprès de son livreur actuel.',409)
            if type(dr.get('driver_hub_id')) is not int or dr['driver_hub_id']<=0:raise Error('Rattachez ce livreur à un Hub actif avant toute affectation.',409)
            already=p['driver_id']==dr['id'] and p['status'] in ['Reçu par le livreur','En livraison'] and not received
            if already:return True
            if not driver_dispatch_allowed(c,p.get('current_hub_id'),dr.get('driver_hub_id')):
                raise Error('Le colis doit être physiquement au Hub actif rattaché à ce livreur avant sa remise.',409)
            return False
        if p['driver_id']!=dr['id']:raise Error('Ce colis n’est pas affecté à ce livreur.',409)
        if p['status'] not in CLOSED and (p['invoice_id'] or p['financial_locked']):raise Error('Colis ouvert verrouillé financièrement : régularisez le relevé.',409)
        return False
    @app.post('/api/drivers-workspace/<int:uid>/scan-preview')
    @auth('admin','agent')
    def driver_scan_preview(uid):
        d=body();u=user();tracking=text(d,'tracking',80).upper();mode=d.get('mode')
        with conn() as c:
            dr=driver(c,uid)
            lookup='SELECT p.id,cl.company FROM parcels p JOIN users cl ON cl.id=p.client_id WHERE upper(p.tracking)=?'
            args=[tracking]
            if u['role']=='agent':
                lookup+=' AND '+local_driver_parcel_scope();args += [u['agent_hub_id']]*2
            rows=c.execute(lookup,args).fetchall()
            if not rows:raise Error('Référence introuvable.',404)
            if len(rows)>1:raise Error('Référence identique chez plusieurs sociétés ('+', '.join(sorted({r['company'] or '—' for r in rows[:6]}))+') : ouvrez le bon colis via la recherche avant la remise.',409)
            p=custody_parcel(c,rows[0]['id'],u);already=check(c,dr,p,mode);p=s['parcel_contact_info'](c,p)
            # Reprise échange : le scan de descente déclenche la réception au Hub, sans saisie de statut.
            exchange_auto=bool(mode=='receive' and not already and
                (p.get('exchange_of_id') or str(p.get('tracking') or '').upper().startswith('EC'))
                and p.get('status')==EXCHANGE_TO_RECOVER)
            return jsonify(parcel=p,already=already,exchange_auto=exchange_auto)
    @app.post('/api/drivers-workspace/<int:uid>/scan')
    @auth('admin')
    def driver_custody_scan(uid):
        d=body();u=user()
        if set(d)!={'parcel_id','revision','mode','request_key','hub_id','confirmed'} or d['confirmed'] is not True:raise Error('Confirmation de remise physique requise.')
        if type(d['parcel_id']) is not int or d['parcel_id']<=0:raise Error('Colis invalide.')
        key=d['request_key']
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):raise Error('Clé de requête invalide.')
        fp=hashlib.sha256(json.dumps([uid,d],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');dr=driver(c,uid);prior=c.execute('SELECT * FROM driver_scan_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
            if prior:
                if prior['fingerprint']!=fp:raise Error('Clé déjà utilisée pour une autre opération.',409)
                return jsonify(**json.loads(prior['result']),replayed=True)
            exchange_done=[]
            p=parcel(c,d['parcel_id'],u);already=check(c,dr,p,d['mode']);rev(d,p['ops_revision']);hub=d['hub_id']
            if hub is not None and (type(hub) is not int or not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub,)).fetchone()):raise Error('Hub invalide.')
            if d['mode']=='assign' and hub is not None:raise Error('Le départ remet le colis au livreur, pas à un hub.')
            if not already:
                previous={k:p[k] for k in ['status','driver_id','reason_code','next_attempt_at','current_hub_id']}
                if d['mode']=='assign':
                    if p['driver_id']==uid:
                        c.execute('INSERT INTO ops_assignments(parcel_id,old_driver_id,new_driver_id,actor_id,created_at,hub_id) VALUES(?,?,?,?,?,?)',(p['id'],uid,uid,u['id'],now(),p['current_hub_id']))
                    s['ops_change'](c,p,dict(driver_id=uid,status='Reçu par le livreur',revision=d['revision']),u)
                    c.execute("UPDATE parcels SET driver_id=?,status='Reçu par le livreur',updated_at=? WHERE id=?",(uid,now(),p['id']));c.execute('DELETE FROM driver_receipts WHERE parcel_id=?',(p['id'],));status='Reçu par le livreur';note='Remise physique au livreur : '+dr['name']
                else:
                    status=p['status']
                    # Recovery changes custody only: preserve outcome, reasons, appointment,
                    # notes and historical courier/financial attribution for every status.
                    c.execute('UPDATE parcels SET current_hub_id=?,ops_revision=ops_revision+1 WHERE id=?',(hub,p['id']))
                    c.execute('INSERT INTO driver_receipts(parcel_id,driver_id,received_at,hub_id) VALUES(?,?,?,?) ON CONFLICT(parcel_id) DO UPDATE SET driver_id=excluded.driver_id,received_at=excluded.received_at,hub_id=excluded.hub_id',(p['id'],uid,now(),hub));note='Récupéré physiquement à l’agence auprès de '+dr['name']+' · retiré de sa tournée'
                    # Reprise échange (EC…) : la réception au Hub est automatique au scan.
                    if exchange_flow.receive_on_scan(c,p,hub,now):
                        status=EXCHANGE_RECEIVED
                        note='Reprise échange réceptionnée automatiquement au scan de descente · retirée de la tournée de '+dr['name']+' · prête pour une palette retour vers le vendeur'
                        exchange_done.append(p['id'])
                record(c,uid,u,d['mode'],{'before':previous,'hub_id':hub,'financial_attribution_preserved':p['status'] in CLOSED,'exchange_auto_received':p['id'] in exchange_done},p['id']);event(c,p['id'],status,note,u)
            result=dict(ok=True,already=bool(already),parcel_id=p['id'],mode=d['mode'],exchange_received=p['id'] in exchange_done);c.execute('INSERT INTO driver_scan_keys VALUES(?,?,?,?)',(u['id'],key,fp,json.dumps(result)));return jsonify(**result)

    @app.post('/api/drivers-workspace/<int:uid>/scan-batch')
    @auth('admin','agent')
    def driver_custody_scan_batch(uid):
        """Confirm a collected barcode batch atomically after physical custody is verified."""
        d=body();u=user()
        required={'mode','scans','hub_id','request_key','confirmed'}
        if set(d)!=required or d.get('confirmed') is not True:
            raise Error('Confirmation de remise physique requise.')
        mode=d.get('mode')
        if mode not in ['assign','receive']:
            raise Error('Mode invalide.')
        scans=d.get('scans')
        if not isinstance(scans,list) or not 1<=len(scans)<=200:
            raise Error('Sélectionnez entre 1 et 200 colis à confirmer.')
        key=d.get('request_key')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,100}',key):
            raise Error('Clé de requête invalide.')
        hub=d.get('hub_id')
        if u['role']=='agent' and mode=='receive':
            if hub is not None and (type(hub) is not int or hub!=u['agent_hub_id']):
                raise Error('La récupération doit se faire dans votre Hub.',403)
            hub=u['agent_hub_id']
        if hub is not None and (type(hub) is not int or hub<=0):
            raise Error('Hub invalide.')
        normalized=[];seen=set()
        for item in scans:
            if not isinstance(item,dict) or set(item)!={'parcel_id','revision'}:
                raise Error('Détail de scan invalide.')
            pid=item.get('parcel_id');revision=item.get('revision')
            if type(pid) is not int or pid<=0 or type(revision) is not int or revision<0:
                raise Error('Colis ou version invalide.')
            if pid in seen:
                raise Error('Un même colis apparaît plusieurs fois dans ce lot.')
            seen.add(pid);normalized.append({'parcel_id':pid,'revision':revision})
        fingerprint=hashlib.sha256(json.dumps(([uid,d,u.get('agent_hub_id')] if u['role']=='agent' else [uid,d]),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            dr=driver(c,uid)
            prior=c.execute('SELECT * FROM driver_scan_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
            if prior:
                if prior['fingerprint']!=fingerprint:
                    raise Error('Clé déjà utilisée pour une autre opération.',409)
                return jsonify(**json.loads(prior['result']),replayed=True)
            if hub is not None and not c.execute('SELECT 1 FROM ops_hubs WHERE id=? AND active=1',(hub,)).fetchone():
                raise Error('Hub invalide.')
            if mode=='assign' and hub is not None:
                raise Error('Le départ remet les colis au livreur, pas à un hub.')
            checked=[]
            for item in normalized:
                p=custody_parcel(c,item['parcel_id'],u)
                already=check(c,dr,p,mode)
                rev({'revision':item['revision']},p['ops_revision'])
                checked.append((p,already))
            applied=[];already_ids=[];exchange_done=[]
            for p,already in checked:
                if already:
                    already_ids.append(p['id'])
                    continue
                previous={k:p[k] for k in ['status','driver_id','reason_code','next_attempt_at','current_hub_id']}
                if mode=='assign':
                    if p['driver_id']==uid:
                        c.execute('INSERT INTO ops_assignments(parcel_id,old_driver_id,new_driver_id,actor_id,created_at,hub_id) VALUES(?,?,?,?,?,?)',(p['id'],uid,uid,u['id'],now(),p['current_hub_id']))
                    s['ops_change'](c,p,dict(driver_id=uid,status='Reçu par le livreur',revision=p['ops_revision']),u)
                    c.execute("UPDATE parcels SET driver_id=?,status='Reçu par le livreur',updated_at=? WHERE id=?",(uid,now(),p['id']))
                    c.execute('DELETE FROM driver_receipts WHERE parcel_id=?',(p['id'],))
                    status='Reçu par le livreur';note='Remise physique au livreur : '+dr['name']
                else:
                    status=p['status']
                    # Recovery changes custody only: preserve outcome, reasons, appointment,
                    # notes and historical courier/financial attribution for every status.
                    c.execute('UPDATE parcels SET current_hub_id=?,ops_revision=ops_revision+1 WHERE id=?',(hub,p['id']))
                    c.execute('INSERT INTO driver_receipts(parcel_id,driver_id,received_at,hub_id) VALUES(?,?,?,?) ON CONFLICT(parcel_id) DO UPDATE SET driver_id=excluded.driver_id,received_at=excluded.received_at,hub_id=excluded.hub_id',(p['id'],uid,now(),hub))
                    note='Récupéré physiquement à l’agence auprès de '+dr['name']+' · retiré de sa tournée'
                    # Reprise échange (EC…) : la réception au Hub est automatique au scan.
                    if exchange_flow.receive_on_scan(c,p,hub,now):
                        status=EXCHANGE_RECEIVED
                        note='Reprise échange réceptionnée automatiquement au scan de descente · retirée de la tournée de '+dr['name']+' · prête pour une palette retour vers le vendeur'
                        exchange_done.append(p['id'])
                record(c,uid,u,mode,{'before':previous,'hub_id':hub,'financial_attribution_preserved':p['status'] in CLOSED,'exchange_auto_received':p['id'] in exchange_done},p['id'])
                event(c,p['id'],status,note,u)
                applied.append(p['id'])
            result={'ok':True,'mode':mode,'driver_id':uid,'count':len(applied),'parcel_ids':applied,
                    'already':len(already_ids),'already_ids':already_ids,
                    'exchange_received':exchange_done,'exchange_received_count':len(exchange_done)}
            c.execute('INSERT INTO driver_scan_keys VALUES(?,?,?,?)',(u['id'],key,fingerprint,json.dumps(result)))
            return jsonify(**result)
