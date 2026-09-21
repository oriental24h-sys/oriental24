"""Partner -> ORIENTAL24 intake manifests, reusing operational document locks.
No parcel creation, tracking replacement, financial transaction or automatic receipt.
"""
import csv,io,json,hashlib,re
from flask import request,jsonify,Response
from client_types import tracking_text

KIND='partner_palette'
STATES=('Préparé','En transit','Partiellement reçu','Reçu','Clôturé (écarts)','Annulé')

def register_partner_palettes(app,s):
    conn,auth,user,now,Error,event=(s[k] for k in ['conn','auth','user','now','APIError','event'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS partner_palette_meta(document_id INTEGER PRIMARY KEY REFERENCES ops_documents(id),partner_reference TEXT NOT NULL DEFAULT '',transport TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS partner_palette_keys(actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key));
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
        if u['role']!='admin' and u['role']!='agent' and not(u['role']=='client' and u['client_type']=='societe_livraison'):raise Error('Palettes réservées aux sociétés de livraison, à Admin et aux agents de réception.',403)
    def creator(u):
        if u['role']=='agent':raise Error('La préparation des palettes reste à la société ou à Admin.',403)
    def company(c,cid,active=True):
        if isinstance(cid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(cid)):raise Error('Société invalide.')
        r=c.execute("SELECT * FROM users WHERE id=? AND role='client' AND client_type='societe_livraison'"+(' AND active=1' if active else ''),(cid,)).fetchone()
        if not r:raise Error('Société de livraison active requise.')
        return dict(r)
    def hub(c,hid):
        if isinstance(hid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(hid)):raise Error('Hub de réception invalide.')
        r=c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1',(hid,)).fetchone()
        if not r:raise Error('Choisissez un hub de réception actif. Admin peut le configurer.',409)
        return dict(r)
    def get(c,did,u):
        r=c.execute('SELECT d.*,m.partner_reference,m.transport FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id WHERE d.id=? AND d.kind=?',(did,KIND)).fetchone()
        if not r or(u['role']=='client' and r['client_id']!=u['id']) or(u['role']=='agent' and r['destination_hub_id']!=u['agent_hub_id']):raise Error('Palette introuvable.',404)
        return dict(r)
    def lines(c,did):
        return [dict(r) for r in c.execute('SELECT l.*,p.phone,p.status current_status,p.current_hub_id FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id WHERE l.document_id=? ORDER BY l.id',(did,))]
    def receive_guard(did,u):
        # v1.4.17 · every refused reception is recorded with whom and why (outside the failing transaction).
        if u['role']=='admin':return
        with conn() as gc:
            gc.execute('BEGIN IMMEDIATE')
            row=gc.execute("SELECT destination_hub_id FROM ops_documents WHERE id=? AND kind=?",(did,KIND)).fetchone()
            if u['role'] not in ('admin','agent'):
                if row:audit(gc,did,u,'Réception refusée',{'reason':'Rôle non autorisé à la réception physique','actor_role':u['role'],'actor_hub_id':u['agent_hub_id']})
                block=('Réception physique réservée à Admin et aux agents de réception.',403)
            elif u['role']=='agent' and row and row['destination_hub_id']!=u['agent_hub_id']:
                audit(gc,did,u,'Réception refusée',{'reason':'Agent rattaché à un autre hub','actor_hub_id':u['agent_hub_id'],'palette_hub_id':row['destination_hub_id']})
                block=('Palette introuvable pour votre hub.',404)
            else:block=None
        if block:raise Error(*block)
    def detail(c,d):
        ls=lines(c,d['id']);received=sum(bool(l['received_at']) for l in ls);missing=sum(bool(l['missing_at']) for l in ls)
        return {**d,'lines':ls,'count':len(ls),'received':received,'missing':missing,'remaining':len(ls)-received-missing,'audit':[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM ops_audit a JOIN users u ON u.id=a.actor_id WHERE a.document_id=? ORDER BY a.id DESC',(d['id'],))]}
    def audit(c,did,u,action,details):
        c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(did,u['id'],action,json.dumps(details,ensure_ascii=False),now()))
    def lockcheck(c,p,cid,did=None):
        if p['client_id']!=cid:raise Error('Colis inaccessible pour cette société.',404)
        if p['status']!='Créé' or p['driver_id'] is not None or p['current_hub_id'] is not None or p['invoice_id']:
            raise Error('Palette d’entrée : uniquement des colis Créé, non reçus, non affectés et non facturés.',409)
        if c.execute('SELECT 1 FROM driver_statement_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone():raise Error('Colis verrouillé financièrement.',409)
        if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1 AND document_id<>?',(p['id'],did or -1)).fetchone():raise Error('Colis déjà réservé dans un document actif.',409)
        if c.execute("SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE l.parcel_id=? AND d.kind=? AND l.received_at IS NOT NULL",(p['id'],KIND)).fetchone():raise Error('Colis déjà réceptionné depuis une palette partenaire.',409)
    def revision(d,doc):
        if type(d.get('revision')) is not int or d['revision']!=doc['revision']:raise Error('Palette modifiée. Actualisez avant confirmation.',409)
    def replay(c,u,d,did,action):
        key=d.get('request_key')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de confirmation invalide.')
        fp=hashlib.sha256(json.dumps([did,action,d],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        r=c.execute('SELECT * FROM partner_palette_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
        if r:
            if r['fingerprint']!=fp:raise Error('Clé déjà utilisée pour une autre saisie.',409)
            return fp,{**json.loads(r['result']),'replayed':True}
        return fp,None
    def result(c,u,d,fp,doc,**extra):
        r=dict(ok=True,id=doc['id'],reference=doc['reference'],revision=doc['revision'],status=doc['status'],**extra)
        c.execute('INSERT INTO partner_palette_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)',(u['id'],d['request_key'],fp,json.dumps(r)))
        return jsonify(r)

    @app.get('/api/partner-palettes/config')
    @auth('admin','client','agent')
    def partner_config():
        u=user();access(u)
        with conn() as c:
            if u['role']=='agent':
                hubs=c.execute('SELECT h.id,h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 AND h.id=?',(u['agent_hub_id'],)).fetchall()
            else:
                hubs=c.execute('SELECT h.id,h.name,h.address,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 ORDER BY h.name').fetchall()
            return jsonify(hubs=[dict(r) for r in hubs],companies=[dict(r) for r in c.execute("SELECT id,name,company FROM users WHERE role='client' AND client_type='societe_livraison' AND active=1 ORDER BY company,name")] if u['role']=='admin' else [])

    @app.get('/api/partner-palettes/candidates')
    @auth('admin','client','agent')
    def partner_candidates():
        u=user();access(u);creator(u)
        cid=u['id'] if u['role']=='client' else request.args.get('client_id')
        with conn() as c:
            cl=company(c,cid);rows=[]
            for p in c.execute("SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.client_id=? AND p.status='Créé' AND p.driver_id IS NULL AND p.current_hub_id IS NULL AND p.invoice_id IS NULL ORDER BY p.id DESC",(cl['id'],)).fetchall():
                try:lockcheck(c,p,cl['id'])
                except Error:continue
                rows.append({k:p[k] for k in ['id','tracking','recipient','city','phone']})
            return jsonify(rows=rows,client_id=cl['id'])

    @app.route('/api/partner-palettes',methods=['GET','POST'])
    @auth('admin','client','agent')
    def partner_collection():
        u=user();access(u)
        with conn() as c:
            if request.method=='GET':
                where=['d.kind=?'];args=[KIND]
                if u['role']=='client':where.append('d.client_id=?');args.append(u['id'])
                if u['role']=='agent':where.append('d.destination_hub_id=?');args.append(u['agent_hub_id'])
                state=request.args.get('state','');q=text(request.args,'q',120)
                if state:
                    if state not in STATES:raise Error('État de palette invalide.')
                    where.append('d.status=?');args.append(state)
                if q:
                    where.append("(instr(lower(d.reference),lower(?))>0 OR instr(lower(d.client_name),lower(?))>0 OR instr(lower(m.partner_reference),lower(?))>0 OR EXISTS(SELECT 1 FROM ops_document_lines l WHERE l.document_id=d.id AND instr(lower(l.tracking),lower(?))>0))");args.extend([q]*4)
                try:
                    page=int(request.args.get('page',1));size=int(request.args.get('size',20))
                    if page<1 or size not in [20,50,100]:raise ValueError()
                except (ValueError,TypeError):raise Error('Pagination invalide.')
                sql=' FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id WHERE '+' AND '.join(where)
                total=c.execute('SELECT count(*)'+sql,args).fetchone()[0];page=min(page,max(1,(total+size-1)//size))
                rows=[]
                for row in c.execute('SELECT d.*,m.partner_reference,m.transport'+sql+' ORDER BY d.id DESC LIMIT ? OFFSET ?',args+[size,(page-1)*size]):
                    r=dict(row);counts=c.execute('SELECT count(*),sum(received_at IS NOT NULL),sum(missing_at IS NOT NULL) FROM ops_document_lines WHERE document_id=?',(r['id'],)).fetchone();r.update(count=counts[0],received=counts[1] or 0,missing=counts[2] or 0,remaining=counts[0]-(counts[1] or 0)-(counts[2] or 0));rows.append(r)
                return jsonify(rows=rows,total=total,page=page,size=size)
            creator(u)
            d=body();c.execute('BEGIN IMMEDIATE');fp,prior=replay(c,u,d,None,'create')
            if prior:return jsonify(prior)
            cid=u['id'] if u['role']=='client' else d.get('client_id');cl=company(c,cid);dest=hub(c,d.get('destination_hub_id'))
            ids=d.get('parcel_ids')
            if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(set(ids)):raise Error('Choisissez 1 à 500 colis distincts.')
            ps=[]
            for pid in ids:
                p=c.execute('SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.id=? AND p.client_id=?',(pid,cl['id'])).fetchone()
                if not p:raise Error('Colis inaccessible pour cette société.',404)
                lockcheck(c,p,cl['id']);ps.append(p)
            did=c.execute('INSERT INTO ops_documents(kind,client_id,destination_hub_id,client_name,source_name,destination_name,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)',(KIND,cl['id'],dest['id'],cl['company'] or cl['name'],cl['company'] or cl['name'],dest['name'],text(d,'note',600),u['id'],now())).lastrowid
            ref=f'PP-{did:06d}';c.execute('UPDATE ops_documents SET reference=? WHERE id=?',(ref,did))
            c.execute('INSERT INTO partner_palette_meta(document_id,partner_reference,transport) VALUES(?,?,?)',(did,text(d,'partner_reference',80),text(d,'transport',120)))
            for p in ps:c.execute('INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,?,?,?)',(did,p['id'],p['tracking'],p['recipient'],p['city'],p['status']))
            audit(c,did,u,'Palette préparée',{'parcel_ids':ids,'count':len(ps),'destination_hub_id':dest['id']})
            return result(c,u,d,fp,get(c,did,u))

    @app.get('/api/partner-palettes/<int:did>')
    @auth('admin','client','agent')
    def partner_detail(did):
        u=user();access(u)
        with conn() as c:
            c.execute('BEGIN');return jsonify(detail(c,get(c,did,u)))

    @app.get('/api/partner-palettes/<int:did>/csv')
    @auth('admin','client','agent')
    def partner_csv(did):
        u=user();access(u)
        with conn() as c:
            c.execute('BEGIN');d=detail(c,get(c,did,u))
        def safe(v):
            v=str(v or '');return "'"+v if v.lstrip().startswith(('=','+','-','@')) else v
        buf=io.StringIO();w=csv.writer(buf,delimiter=';');w.writerow(['Palette','Société','Réf. partenaire','Destination','État palette','Tracking original','Destinataire','Ville','Téléphone','Réception','Reçu le','État actuel colis'])
        for l in d['lines']:w.writerow([safe(x) for x in [d['reference'],d['client_name'],d['partner_reference'],d['destination_name'],d['status'],l['tracking'],l['recipient'],l['city'],l['phone'],'Reçu' if l['received_at'] else 'Manquant déclaré' if l['missing_at'] else 'Annulé' if d['status']=='Annulé' else 'À recevoir',l['received_at'],l['current_status']]])
        return Response('\ufeff'+buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':f'attachment; filename="ORIENTAL24-{d["reference"]}.csv"','Cache-Control':'private, no-store'})

    @app.post('/api/partner-palettes/<int:did>/<action>')
    @auth('admin','client','agent','livreur')
    def partner_action(did,action):
        u=user()
        if action not in ['dispatch','cancel','receive','receive-all']:raise Error('Action inconnue.',404)
        # Le blocage de réception est enregistré pour TOUT utilisateur (rôle, hub étranger) avant les autres gardes.
        if action.startswith('receive'):receive_guard(did,u)
        access(u);d=body()
        if action in ['dispatch','cancel']:creator(u)
        if d.get('confirmed') is not True:raise Error('Confirmez explicitement cette opération.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc=get(c,did,u);fp,prior=replay(c,u,d,did,action)
            if prior:return jsonify(prior)
            ls=lines(c,did)
            if action=='receive':
                code=tracking_text(d.get('tracking'),Error);line=next((l for l in ls if l['tracking'].casefold()==code.casefold()),None)
                if not line:raise Error('Ce tracking ne figure pas dans cette palette.',404)
                if line['missing_at']:raise Error('Ce colis a été déclaré manquant : il ne peut pas être réceptionné.',404)
                if line['received_at']:return result(c,u,d,fp,doc,already_received=True,received=0)
            revision(d,doc)
            if action in ['dispatch','cancel']:
                if doc['status']!='Préparé':raise Error('Seule une palette brouillon peut être envoyée ou annulée.',409)
                if action=='cancel':
                    reason=text(d,'reason',600,True);c.execute("UPDATE ops_documents SET status='Annulé',cancel_reason=?,revision=revision+1 WHERE id=?",(reason,did));c.execute('UPDATE ops_document_lines SET active=0 WHERE document_id=?',(did,));audit(c,did,u,'Palette annulée avant envoi',{'reason':reason})
                else:
                    company(c,doc['client_id']);hub(c,doc['destination_hub_id'])
                    for l in ls:
                        p=c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone();lockcheck(c,p,doc['client_id'],did)
                        if not l['active'] or p['tracking']!=l['tracking']:raise Error('Contenu du manifeste modifié.',409)
                    c.execute("UPDATE ops_documents SET status='En transit',dispatched_at=?,revision=revision+1 WHERE id=?",(now(),did));audit(c,did,u,'Envoi palette déclaré',{'count':len(ls)})
                    for l in ls:event(c,l['parcel_id'],l['initial_status'],doc['reference']+' · envoi société déclaré, réception ORIENTAL24 encore attendue',u)
                return result(c,u,d,fp,get(c,did,u))
            if doc['status'] not in ['En transit','Partiellement reçu']:raise Error('La société doit confirmer l’envoi avant réception.',409)
            hub(c,doc['destination_hub_id'])
            pending=[l for l in ls if not l['received_at'] and not l['missing_at']]
            if action=='receive-all' and (type(d.get('expected_remaining')) is not int or d['expected_remaining']!=len(pending)):raise Error('Le nombre de colis restants a changé. Actualisez.',409)
            received=[line] if action=='receive' else pending
            for l in received:
                c.execute('UPDATE ops_document_lines SET active=1 WHERE id=?',(l['id'],))  # réactivation : lockcheck exige une ligne active
                p=c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()
                lockcheck(c,p,doc['client_id'],did)
            at=now()
            for l in received:
                c.execute('UPDATE ops_document_lines SET received_at=?,received_by=?,active=0 WHERE id=?',(at,u['id'],l['id']))
                c.execute("UPDATE parcels SET status='Réceptionné',current_hub_id=?,reason_code=NULL,next_attempt_at=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(doc['destination_hub_id'],at,l['parcel_id']))
                event(c,l['parcel_id'],'Réceptionné',doc['reference']+' · réception physique ORIENTAL24 à '+doc['destination_name'],u)
            complete=len(received)==len(pending)
            c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Reçu' if complete else 'Partiellement reçu',at if complete else None,did))
            audit(c,did,u,'Réception complète confirmée' if action=='receive-all' else 'Colis scanné reçu',{'parcel_ids':[l['parcel_id'] for l in received],'trackings':[l['tracking'] for l in received],'count':len(received),'hub_id':doc['destination_hub_id']})
            return result(c,u,d,fp,get(c,did,u),received=len(received),already_received=False)
