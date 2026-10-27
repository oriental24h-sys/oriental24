"""Return palettes: hub -> vendor flows (« Envoyer retour »), reusing operational document locks.
A parcel becomes « Retourné » only when its physical handover to the vendor is confirmed.
Unbilled parcels then enter the next client invoice with the existing return fee; an existing
invoice is never duplicated and no payment, COD, fee or invoice status is changed automatically.
"""
import csv,io,json,hashlib,re
from flask import request,jsonify,Response

KIND='return_palette'
STATES=('Préparé','En transit','Partiellement remis','Remis','Clôturé (écarts)','Annulé')

def register_return_palettes(app,s):
    conn,auth,user,now,Error,event=(s[k] for k in ['conn','auth','user','now','APIError','event'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS return_palette_meta(document_id INTEGER PRIMARY KEY REFERENCES ops_documents(id),transport TEXT NOT NULL DEFAULT '',tracking_code TEXT NOT NULL DEFAULT '',lots INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS return_palette_keys(actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key));
        ''')
    def body():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def text(d,k,limit,required=False):
        v=d.get(k,'')
        if not isinstance(v,str) or len(v.strip())>limit or (required and not v.strip()):raise Error('Champ invalide : '+k)
        return v.strip()
    def access(u):
        if u['role'] not in ('admin','hub_manager','client'):raise Error('Accès réservé.',403)
    def creator(u):
        if u['role'] not in ('admin','hub_manager'):raise Error('Préparation, envoi et annulation réservés à Admin et aux agents de réception.',403)
    def client(c,cid,active=True):
        if isinstance(cid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(cid)):raise Error('Vendeur invalide.')
        r=c.execute("SELECT * FROM users WHERE id=? AND role='client'"+(' AND active=1' if active else ''),(cid,)).fetchone()
        if not r:raise Error('Vendeur actif requis.')
        return dict(r)
    def hub(c,hid,u):
        if isinstance(hid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(hid)):
            if u['role']=='hub_manager':raise Error('Hub introuvable.',404)
            raise Error('Hub de départ invalide.')
        r=c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1',(hid,)).fetchone()
        if not r:
            if u['role']=='hub_manager':raise Error('Hub introuvable.',404)
            raise Error('Choisissez un hub de départ actif.',409)
        if u['role']=='hub_manager' and u['agent_hub_id']!=r['id']:raise Error('Hub introuvable.',404)
        return dict(r)
    def get(c,did,u):
        r=c.execute('SELECT d.*,m.transport,m.tracking_code,m.lots FROM ops_documents d JOIN return_palette_meta m ON m.document_id=d.id WHERE d.id=? AND d.kind=?',(did,KIND)).fetchone()
        if not r or(u['role']=='hub_manager' and r['destination_hub_id']!=u['agent_hub_id']) or(u['role']=='client' and r['client_id']!=u['id']):raise Error('Palette retour introuvable.',404)
        return dict(r)
    def lines(c,did):
        return [dict(r) for r in c.execute('SELECT l.*,p.phone,p.amount,p.status current_status,p.current_hub_id FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id WHERE l.document_id=? ORDER BY l.id',(did,))]
    def detail(c,d):
        ls=lines(c,d['id']);received=sum(bool(l['received_at']) for l in ls);missing=sum(bool(l['missing_at']) for l in ls)
        hid=d.get('destination_hub_id')
        h=c.execute('SELECT h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=?',(hid,)).fetchone() if hid else None
        cl=c.execute('''SELECT u.name,u.company,u.phone,u.email,COALESCE(a.legal_name,'') legal_name,
            COALESCE(a.billing_address,'') billing_address FROM users u
            LEFT JOIN account_dossiers a ON a.user_id=u.id WHERE u.id=? AND u.role='client' ''',(d.get('client_id'),)).fetchone() if d.get('client_id') else None
        return {**d,
            'hub_name':h['name'] if h else d.get('source_name',''),
            'hub_address':h['address'] if h else '',
            'hub_city':h['city'] if h else '',
            'client_contact_name':cl['name'] if cl else '',
            'client_company':cl['company'] if cl else '',
            'client_phone':cl['phone'] if cl else '',
            'client_email':cl['email'] if cl else '',
            'client_legal_name':cl['legal_name'] if cl else '',
            'client_address':cl['billing_address'] if cl else '',
            'lines':ls,'count':len(ls),'received':received,'missing':missing,
            'remaining':len(ls)-received-missing,
            'audit':[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM ops_audit a JOIN users u ON u.id=a.actor_id WHERE a.document_id=? ORDER BY a.id DESC',(d['id'],))]}
    def receive_guard(did,u):
        # v1.6.5 · réception par le vendef également — toute tentative illicite est consignée (hors transaction).
        if u['role']=='admin':return
        with conn() as gc:
            gc.execute('BEGIN IMMEDIATE')
            row=gc.execute('SELECT destination_hub_id,client_id FROM ops_documents WHERE id=? AND kind=?',(did,KIND)).fetchone()
            if u['role'] not in ('hub_manager','client'):
                if row:audit(gc,did,u,'Remise refusée',{'reason':'Rôle non autorisé à confirmer la remise','actor_role':u['role']})
                block=('Remise réservée à Admin, aux agents de réception et au vendeur destinataire.',403)
            elif u['role']=='hub_manager' and row and row['destination_hub_id']!=u['agent_hub_id']:
                audit(gc,did,u,'Remise refusée',{'reason':'Agent rattaché à un autre hub','actor_hub_id':u['agent_hub_id']})
                block=('Palette retour introuvable.',404)
            elif u['role']=='client' and row and row['client_id']!=u['id']:
                audit(gc,did,u,'Remise refusée',{'reason':'Vendeur non destinataire de la palette'})
                block=('Palette retour introuvable.',404)
            else:block=None
        if block:raise Error(*block)
    def audit(c,did,u,action,details):
        c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(did,u['id'],action,json.dumps(details,ensure_ascii=False),now()))
    def lockcheck(c,p,cid,hid,did=None):
        if p['client_id']!=cid:raise Error('Colis inaccessible pour ce vendeur.',404)
        if p['status'] not in ('Refusé','Retourné'):
            raise Error('Palette retour : uniquement des colis Refusé ou Retourné.',409)
        if p['current_hub_id']!=hid:raise Error('Colis physiquement hors du hub choisi.',409)
        if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1 AND document_id<>?',(p['id'],did or -1)).fetchone():raise Error('Colis déjà réservé dans un document actif.',409)
    def revision(d,doc):
        if type(d.get('revision')) is not int or d['revision']!=doc['revision']:raise Error('Palette modifiée. Actualisez avant confirmation.',409)
    def replay(c,u,d,did,action):
        key=d.get('request_key')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de confirmation invalide.')
        fp=hashlib.sha256(json.dumps([did,action,d],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        r=c.execute('SELECT * FROM return_palette_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
        if r:
            if r['fingerprint']!=fp:raise Error('Clé déjà utilisée pour une autre saisie.',409)
            return fp,{**json.loads(r['result']),'replayed':True}
        return fp,None
    def result(c,u,d,fp,doc,**extra):
        r=dict(ok=True,id=doc['id'],reference=doc['reference'],revision=doc['revision'],status=doc['status'],**extra)
        c.execute('INSERT INTO return_palette_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)',(u['id'],d['request_key'],fp,json.dumps(r)))
        return jsonify(r)

    @app.get('/api/return-palettes/config')
    @auth('admin','hub_manager')
    def return_config():
        u=user();access(u)
        with conn() as c:
            if u['role']=='hub_manager':
                hub_id=u.get('agent_hub_id')
                hubs=c.execute('SELECT h.id,h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 AND h.id=?',(hub_id,)).fetchall()
                clients=c.execute('''SELECT DISTINCT u.id,u.name,u.company,u.client_type FROM users u
                    JOIN parcels p ON p.client_id=u.id WHERE u.role='client' AND u.active=1
                    AND p.current_hub_id=? AND p.status IN ('Refusé','Retourné')
                    AND NOT EXISTS(SELECT 1 FROM ops_document_lines l WHERE l.parcel_id=p.id AND l.active=1)
                    ORDER BY u.company,u.name''',(hub_id,)).fetchall()
            else:
                hubs=c.execute('SELECT h.id,h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 ORDER BY h.name').fetchall()
                clients=c.execute("SELECT id,name,company,client_type FROM users WHERE role='client' AND active=1 ORDER BY company,name").fetchall()
            return jsonify(hubs=[dict(r) for r in hubs],clients=[dict(r) for r in clients])

    @app.get('/api/return-palettes/vendor-counts')
    @auth('admin','hub_manager')
    def return_vendor_counts():
        u=user();access(u)
        with conn() as c:
            h=hub(c,request.args.get('hub_id'),u)
            rows=c.execute('''SELECT p.client_id,COUNT(*) n FROM parcels p WHERE p.status IN ('Refusé','Retourné') AND p.current_hub_id=? AND NOT EXISTS(SELECT 1 FROM ops_document_lines l WHERE l.parcel_id=p.id AND l.active=1) GROUP BY p.client_id''',(h['id'],)).fetchall()
            return jsonify(counts={str(r['client_id']):r['n'] for r in rows})

    @app.get('/api/return-palettes/candidates')
    @auth('admin','hub_manager')
    def return_candidates():
        u=user();access(u)
        with conn() as c:
            cl=client(c,request.args.get('client_id'));h=hub(c,request.args.get('hub_id'),u);rows=[]
            for p in c.execute("SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.client_id=? AND p.status IN ('Refusé','Retourné') AND p.current_hub_id=? ORDER BY p.updated_at DESC",(cl['id'],h['id'])).fetchall():
                try:lockcheck(c,p,cl['id'],h['id'])
                except Error:continue
                rows.append({k:p[k] for k in ['id','tracking','recipient','city','phone','status']})
            return jsonify(rows=rows,client_id=cl['id'],hub_id=h['id'])

    @app.route('/api/return-palettes',methods=['GET','POST'])
    @auth('admin','hub_manager','client')
    def return_collection():
        u=user();access(u)
        with conn() as c:
            if request.method=='GET':
                where=['d.kind=?'];args=[KIND]
                if u['role']=='hub_manager':where.append('d.destination_hub_id=?');args.append(u['agent_hub_id'])
                if u['role']=='client':where.append('d.client_id=?');args.append(u['id'])
                state=request.args.get('state','');q=text(request.args,'q',120)
                if state:
                    if state not in STATES:raise Error('État de palette retour invalide.')
                    where.append('d.status=?');args.append(state)
                if q:
                    where.append("(instr(lower(d.reference),lower(?))>0 OR instr(lower(d.client_name),lower(?))>0 OR instr(lower(COALESCE(m.tracking_code,'')),lower(?))>0 OR EXISTS(SELECT 1 FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id WHERE l.document_id=d.id AND (instr(lower(COALESCE(l.tracking,'')),lower(?))>0 OR instr(lower(COALESCE(p.tracking,'')),lower(?))>0)))");args.extend([q]*5)
                try:
                    page=int(request.args.get('page',1));size=int(request.args.get('size',20))
                    if page<1 or size not in [10,20,30,50,80,100,200,500]:raise ValueError()
                except (ValueError,TypeError):raise Error('Pagination invalide.')
                sql=' FROM ops_documents d JOIN return_palette_meta m ON m.document_id=d.id WHERE '+' AND '.join(where)
                total=c.execute('SELECT count(*)'+sql,args).fetchone()[0];page=min(page,max(1,(total+size-1)//size))
                rows=[]
                for row in c.execute('SELECT d.*,m.transport,m.tracking_code,m.lots'+sql+' ORDER BY d.id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size]):
                    r=dict(row);counts=c.execute('SELECT count(*),sum(received_at IS NOT NULL) FROM ops_document_lines WHERE document_id=?',(r['id'],)).fetchone();r.update(count=counts[0],received=counts[1] or 0,remaining=counts[0]-(counts[1] or 0))
                    r['tracking_matches']=[];r['tracking_match_count']=0
                    if q:
                        found=[];seen_parcels=set()
                        for match in c.execute('''SELECT l.parcel_id,l.tracking snapshot_tracking,p.tracking current_tracking
                                                  FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id
                                                  WHERE l.document_id=? AND (instr(lower(COALESCE(l.tracking,'')),lower(?))>0
                                                    OR instr(lower(COALESCE(p.tracking,'')),lower(?))>0) ORDER BY l.id''',(r['id'],q,q)):
                            if match['parcel_id'] in seen_parcels:continue
                            seen_parcels.add(match['parcel_id'])
                            current=str(match['current_tracking'] or '');snapshot=str(match['snapshot_tracking'] or '')
                            tracking=current if q.lower() in current.lower() else snapshot
                            found.append({'parcel_id':match['parcel_id'],'tracking':tracking or current or snapshot})
                        r['tracking_match_count']=len(found);r['tracking_matches']=found[:5]
                    rows.append(r)
                return jsonify(rows=rows,total=total,page=page,size=size)
            creator(u)
            d=body();c.execute('BEGIN IMMEDIATE');fp,prior=replay(c,u,d,None,'create')
            if prior:return jsonify(prior)
            cl=client(c,d.get('client_id'));src=hub(c,d.get('hub_id'),u)
            flot=d.get('lots',0)
            if isinstance(flot,bool) or flot is None or isinstance(flot,str) or not isinstance(flot,(int,float)) or int(flot)!=flot or not 0<=int(flot)<=500:raise Error('Nombre de lots invalide (0 à 500).')
            ids=d.get('parcel_ids')
            if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(set(ids)):raise Error('Choisissez 1 à 500 colis distincts.')
            ps=[]
            for pid in ids:
                p=c.execute('SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.id=? AND p.client_id=?',(pid,cl['id'])).fetchone()
                if not p:raise Error('Colis inaccessible pour ce vendeur.',404)
                lockcheck(c,p,cl['id'],src['id']);ps.append(p)
            did=c.execute('INSERT INTO ops_documents(kind,client_id,destination_hub_id,client_name,source_name,destination_name,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(KIND,cl['id'],src['id'],cl['company'] or cl['name'],src['name'],cl['company'] or cl['name'],text(d,'note',600),u['id'],now())).lastrowid
            ref=f'PR-{did:06d}';c.execute('UPDATE ops_documents SET reference=? WHERE id=?',(ref,did))
            c.execute('INSERT INTO return_palette_meta(document_id,transport,tracking_code,lots) VALUES(?,?,?,?)',(did,text(d,'transport',120),text(d,'tracking_code',80),int(flot)))
            for p in ps:c.execute('INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,?,?,?)',(did,p['id'],p['tracking'],p['recipient'],p['city'],p['status']))
            audit(c,did,u,'Palette retour préparée',{'parcel_ids':ids,'count':len(ps),'hub_id':src['id'],'vendor_id':cl['id']})
            return result(c,u,d,fp,get(c,did,u))

    @app.get('/api/return-palettes/<int:did>')
    @auth('admin','hub_manager','client')
    def return_detail(did):
        u=user();access(u)
        with conn() as c:return jsonify(detail(c,get(c,did,u)))

    @app.get('/api/return-palettes/<int:did>/csv')
    @auth('admin','hub_manager','client')
    def return_csv(did):
        u=user();access(u)
        with conn() as c:
            d=detail(c,get(c,did,u));buf=io.StringIO();w=csv.writer(buf);w.writerow(['Palette','Hub départ','Vendeur','Transport','Code suivi','Lots','État','Tracking','Destinataire','Ville','Statut initial','Remise','Remise le','Statut actuel'])
            def safe(v):
                v='' if v is None else str(v)
                return "'"+v if v[:1] in ('=','+','-','@') else v
            for l in d['lines']:w.writerow([safe(x) for x in [d['reference'],d['source_name'],d['client_name'],d['transport'],d['tracking_code'],d['lots'],d['status'],l['tracking'],l['recipient'],l['city'],l['initial_status'],'Remis' if l['received_at'] else 'Annulé' if d['status']=='Annulé' else 'À remettre',l['received_at'],l['current_status']]])
            return Response('\ufeff'+buf.getvalue(),200,{'Content-Type':'text/csv; charset=utf-8','Content-Disposition':f'attachment; filename="{d["reference"]}.csv"'})

    @app.post('/api/return-palettes/<int:did>/<action>')
    @auth('admin','hub_manager','client')
    def return_action(did,action):
        u=user();access(u)
        if action not in ['dispatch','cancel','receive','receive-all']:raise Error('Action inconnue.',404)
        if action=='receive-all' and u['role']=='hub_manager':
            raise Error('Le responsable du Hub doit scanner chaque colis individuellement.',403)
        if action in ['receive','receive-all']:receive_guard(did,u)
        else:creator(u)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');d=body();fp,prior=replay(c,u,d,did,action)
            if prior:return jsonify(prior)
            doc=get(c,did,u);revision(d,doc);ls=lines(c,did);at=now()
            if action in ('receive','receive-all') and d.get('confirmed') is not True:
                raise Error('Confirmez la remise physique du colis au vendeur.')
            def line(trk):
                t=text({'tracking':trk},'tracking',160,True)
                l=next((x for x in ls if x['tracking']==t),None)
                if not l:raise Error('Ce tracking ne figure pas dans la palette.',404)
                return l
            if action=='receive':
                line(d.get('tracking'))
                if line(d.get('tracking'))['received_at']:return result(c,u,d,fp,doc,already_received=True,received=0)
            if action in ['dispatch','cancel']:
                if doc['status']!='Préparé':raise Error('Seule une palette retour brouillon peut être envoyée ou annulée.',409)
                if action=='cancel':
                    reason=text(d,'reason',600,True);c.execute("UPDATE ops_documents SET status='Annulé',cancel_reason=?,revision=revision+1 WHERE id=?",(reason,did));c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,));audit(c,did,u,'Palette retour annulée avant envoi',{'reason':reason})
                    return result(c,u,d,fp,get(c,did,u))
                if u['role']=='hub_manager':
                    # tinydl l'agent kd'ha l'envoi depuis son hub (déjà garanti par get())
                    pass
                c.execute("UPDATE ops_documents SET status='En transit',dispatched_at=?,revision=revision+1 WHERE id=?",(at,did));audit(c,did,u,'Retour expédié au vendeur',{'count':len(ls),'transport':doc['transport'],'tracking_code':doc['tracking_code'],'lots':doc['lots']})
                for l in ls:event(c,l['parcel_id'],l['initial_status'],doc['reference']+' · retour expédié au vendeur, remise encore attendue',u)
                return result(c,u,d,fp,get(c,did,u))
            if doc['status'] not in ['En transit','Partiellement remis']:raise Error('Confirmez l’envoi du retour avant la remise au vendeur.',409)
            pending=[l for l in ls if not l['received_at']]
            if action=='receive-all' and (type(d.get('expected_remaining')) is not int or d['expected_remaining']!=len(pending)):raise Error('Le nombre de colis restants a changé. Actualisez.',409)
            received=[line(d.get('tracking'))] if action=='receive' else pending
            collection_apply(c,doc,received,u,action)
            return result(c,u,d,fp,get(c,did,u),received=len(received),already_received=False)

    def collection_apply(c,doc,received,u,action='receive-all'):
        did=doc['id'];pending=[l for l in lines(c,did) if not l['received_at']];at=now()
        for l in received:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()
            if not p or p['status']=='Livré':raise Error('Colis '+l['tracking']+' : un colis « Livré » ne peut pas être confirmé comme retour.',409)
        status_changes=[]
        for l in received:
            p=c.execute('SELECT status FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()
            old_status=p['status']
            c.execute('UPDATE ops_document_lines SET received_at=?,received_by=?,active=0 WHERE id=?',(at,u['id'],l['id']))
            c.execute("UPDATE parcels SET status='Retourné',current_hub_id=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(at,l['parcel_id']))
            note=doc['reference']+' · retour physiquement remis au vendeur · statut '+old_status+' → Retourné'
            event(c,l['parcel_id'],'Retourné',note,u)
            status_changes.append({'parcel_id':l['parcel_id'],'tracking':l['tracking'],'from':old_status,'to':'Retourné'})
        complete=len(received)==len(pending)
        c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Remis' if complete else 'Partiellement remis',at if complete else None,did))
        audit(c,did,u,'Retour remis au vendeur (complet)' if complete else 'Retour remis au vendeur (partiel)',{'parcel_ids':[l['parcel_id'] for l in received],'trackings':[l['tracking'] for l in received],'count':len(received),'status':'Retourné','status_changes':status_changes})

    def collection_load(c,did,u):
        access(u);doc=get(c,did,u)
        return doc,lines(c,did)

    s.setdefault('reception_adapters',{})['return']={'load':collection_load,'apply':collection_apply}

    def dispatch_collection_load(c,did,u):
        creator(u);doc=get(c,did,u)
        doc['hub_snapshot']=hub(c,doc['destination_hub_id'],u)
        return doc,lines(c,did)

    def dispatch_collection_check(c,doc,line,u):
        p=c.execute('SELECT * FROM parcels WHERE id=?',(line['parcel_id'],)).fetchone()
        lockcheck(c,p,doc['client_id'],doc['destination_hub_id'],doc['id'])
        if not line['active'] or line['tracking']!=p['tracking']:raise Error('Contenu du manifeste modifié.',409)

    def dispatch_collection_apply(c,doc,ls,u):
        at=now();did=doc['id']
        c.execute("UPDATE ops_documents SET status='En transit',dispatched_at=?,revision=revision+1 WHERE id=?",(at,did))
        audit(c,did,u,'Retour expédié après collecte des scans',{'count':len(ls),'trackings':[l['tracking'] for l in ls],'transport':doc['transport'],'tracking_code':doc['tracking_code'],'lots':doc['lots']})
        for l in ls:event(c,l['parcel_id'],l['initial_status'],doc['reference']+' · retour expédié au vendeur, remise encore attendue',u)

    s.setdefault('dispatch_adapters',{})['return']={'load':dispatch_collection_load,'check':dispatch_collection_check,'apply':dispatch_collection_apply}
