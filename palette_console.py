"""v1.6.7 — Console « Palettes » du hub, miroir de l'ancien écran de réception (admin/agent).
Tabs Default (palettes société -> hub), Retours (palettes retour hub -> vendeur), A recevoir
(ce qui attend encore une réponse, avec relance automatique après 7 jours sans réponse du vendeur).
Réception = scan des colis cochés ; clôture = les non scannés passent « non réceptionnés » et
l'expéditeur est notifié. Envoi de retour : transport + vendeur + lots + scan des trackings, la
palette naît déjà « En transit ». Aucun effet financier. Les images jointes (Attachement) sont
stocknées en base comme les preuves de colis, jamais sur disque."""
import base64,csv,hashlib,io,json,re,datetime
from flask import request,jsonify,Response
from client_types import tracking_text

PKIND='partner_palette'
RKIND='return_palette'
KINDS={'partner':PKIND,'return':RKIND}
PARTNER_CLOSED=('Reçu','Clôturé (écarts)','Annulé')
RETURN_CLOSED=('Remis','Clôturé (écarts)','Annulé')
RELANCE_DAYS=7

def register_palette_console(app,s):
    conn,auth,user,now,Error,event=(s[k] for k in ['conn','auth','user','now','APIError','event'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS palette_console_keys(actor_id INTEGER NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key));
        CREATE TABLE IF NOT EXISTS palette_attachments(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,document_id INTEGER NOT NULL REFERENCES ops_documents(id),mime TEXT NOT NULL,content BLOB NOT NULL,note TEXT NOT NULL DEFAULT '',actor_id INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL);
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
        if u['role'] not in ('admin','agent'):raise Error('Console réservée à Admin et aux agents de réception.',403)
    def doc(c,did,ku,u):
        kk=KINDS[ku]
        tbl='partner_palette_meta' if ku=='partner' else 'return_palette_meta'
        cols=('m.partner_reference AS track_ref,m.transport,0 AS lots') if ku=='partner' else ('m.tracking_code AS track_ref,m.transport,m.lots')
        r=c.execute('SELECT d.*,'+cols+' FROM ops_documents d JOIN '+tbl+' m ON m.document_id=d.id WHERE d.id=? AND d.kind=?',(did,kk)).fetchone()
        if not r:raise Error('Palette introuvable.',404)
        r=dict(r)
        if u['role']=='agent' and r['destination_hub_id']!=u['agent_hub_id']:raise Error('Palette hors de votre hub.',404)
        return r
    def lines(c,did):
        return [dict(r) for r in c.execute('SELECT l.*,p.phone,p.status current_status,p.current_hub_id,p.address,p.product,p.amount FROM ops_document_lines l JOIN parcels p ON p.id=l.parcel_id WHERE l.document_id=? ORDER BY l.id',(did,))]
    def audit(c,did,u,action,details):
        c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(did,u['id'],action,json.dumps(details,ensure_ascii=False),now()))
    def replay(c,u,d,did,action):
        key=d.get('request_key')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de confirmation invalide.')
        fp=hashlib.sha256(json.dumps([did,action,d],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        r=c.execute('SELECT * FROM palette_console_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
        if r:
            if r['fingerprint']!=fp:raise Error('Clé déjà utilisée pour une autre saisie.',409)
            return fp,{**json.loads(r['result']),'replayed':True}
        return fp,None
    def memo(c,u,d,fp,r):
        c.execute('INSERT OR REPLACE INTO palette_console_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)',(u['id'],d['request_key'],fp,json.dumps(r)))
        return jsonify(r)
    def d10(v,label):
        v=str(v or '').strip()
        if not v:return None
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v):raise Error(label+' invalide (AAAA-MM-JJ).')
        return v
    def bucket(status,ku):
        closed=PARTNER_CLOSED if ku=='partner' else RETURN_CLOSED
        if 'Partiellement' in status:return 'PARTIEL'
        return 'CLOSED' if status in closed else 'OPEN'
    def days_between(s,ref):
        if not s:return 0
        try:return max(0,(ref-datetime.date.fromisoformat(str(s)[:10])).days)
        except ValueError:return 0

    # ------------------------------------------------------------------- liste
    @app.get('/api/palette-console')
    @auth('admin','agent')
    def console_list():
        u=user();access(u)
        tab=text(request.args,'tab',20) or 'default'
        if tab not in ('default','retours','a-recevoir'):raise Error('Onglet inconnu.')
        status=text(request.args,'status',10).upper()
        if status not in ('','OPEN','PARTIEL','CLOSED'):raise Error('Filtre d\'état invalide.')
        exc=text(request.args,'exc',20)
        if exc not in ('','ecarts','retard'):raise Error('Filtre d\'exceptions invalide.')
        hub_id=text(request.args,'hub_id',10);q=text(request.args,'q',120).lower()
        dfrom=d10(request.args.get('date_from'),'Date de début');dto=d10(request.args.get('date_to'),'Date de fin')
        try:
            page=int(request.args.get('page',1));size=int(request.args.get('size',30))
            if page<1 or size not in (30,50,100):raise ValueError()
        except (ValueError,TypeError):raise Error('Pagination invalide.')
        today=datetime.date.fromisoformat(now()[:10])
        rel=[]
        with conn() as c:
            for ku in (('partner',) if tab=='default' else ('return',) if tab=='retours' else ('partner','return')):
                tbl='partner_palette_meta' if ku=='partner' else 'return_palette_meta'
                cols=('m.partner_reference AS track_ref,m.transport,0 AS lots') if ku=='partner' else ('m.tracking_code AS track_ref,m.transport,m.lots')
                where=['d.kind=?'];args=[KINDS[ku]]
                if u['role']=='agent':where.append('d.destination_hub_id=?');args.append(u['agent_hub_id'])
                elif hub_id.isdigit() and 1<=int(hub_id)<=10**9:where.append('d.destination_hub_id=?');args.append(int(hub_id))
                if dfrom:where.append('substr(d.created_at,1,10)>=?');args.append(dfrom)
                if dto:where.append('substr(d.created_at,1,10)<=?');args.append(dto)
                if tab=='a-recevoir':where.append("d.status IN ('En transit','Partiellement reçu','Partiellement remis')")
                if q:where.append("(instr(lower(d.reference),?)>0 OR instr(lower(d.client_name),?)>0 OR instr(lower(d.source_name),?)>0 OR instr(lower(d.destination_name),?)>0 OR instr(lower(COALESCE(m.partner_reference,m.tracking_code,'')),?)>0 OR EXISTS(SELECT 1 FROM ops_document_lines l WHERE l.document_id=d.id AND instr(lower(l.tracking),?)>0))");args.extend([q]*6)
                for r in c.execute('SELECT d.id,d.kind,d.reference,d.status,d.client_id,d.client_name,d.source_name,d.destination_name,d.note,d.created_at,d.dispatched_at,d.revision,'+cols+' FROM ops_documents d JOIN '+tbl+' m ON m.document_id=d.id WHERE '+' AND '.join(where)+' ORDER BY d.id DESC',args):
                    r=dict(r)
                    cnt=c.execute('SELECT count(*),sum(received_at IS NOT NULL),sum(missing_at IS NOT NULL) FROM ops_document_lines WHERE document_id=?',(r['id'],)).fetchone()
                    count,recv,miss=cnt[0],cnt[1] or 0,cnt[2] or 0
                    wait=days_between(r['dispatched_at'] or r['created_at'],today)
                    r.update(kind=ku,count=count,received=recv,missing=miss,remaining=count-recv-miss,bucket=bucket(r['status'],ku),days=wait,
                             sans_reponse=(ku=='return' and r['status'] in ('En transit','Partiellement remis') and wait>=RELANCE_DAYS),
                             retard_hub=(ku=='partner' and r['status'] in ('En transit','Partiellement reçu') and wait>=RELANCE_DAYS))
                    rel.append(r)
        rel.sort(key=lambda r:(str(r['created_at']),r['id']),reverse=True)
        # relance automatique : 7 jours sans réponse du vendeur -> une notification par jour et par palette
        reminded=0
        pend=[r for r in rel if r['sans_reponse']]
        if pend:
            with conn() as wc:
                wc.execute('BEGIN IMMEDIATE')
                for r in pend:
                    ref='Relance réception retour · '+r['reference']
                    if not wc.execute('SELECT 1 FROM ops_notifications WHERE user_id=? AND title=? AND substr(created_at,1,10)=?',(r['client_id'],ref,now()[:10])).fetchone():
                        wc.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',(r['client_id'],ref,'La palette retour '+r['reference']+' ('+str(r['count'])+' colis) attend votre confirmation depuis '+str(r['days'])+' jours. Scannez-la ou signalez un problème au hub.',now()))
                        audit(wc,r['id'],u,'Relance vendeur envoyée',{'days':r['days'],'count':r['count']})
                        reminded+=1
        if status:rel=[r for r in rel if r['bucket']==status]
        if exc=='ecarts':rel=[r for r in rel if r['missing']>0]
        if exc=='retard':rel=[r for r in rel if r['sans_reponse'] or r['retard_hub']]
        total=len(rel);total_colis=sum(r['count'] for r in rel);total_restants=sum(r['remaining'] for r in rel)
        page=min(page,max(1,(total+size-1)//size))
        return jsonify(tab=tab,rows=rel[(page-1)*size:page*size],total=total,page=page,size=size,
                       total_colis=total_colis,total_restants=total_restants,reminded=reminded,relance_days=RELANCE_DAYS)

    # ------------------------------------------------------------------ détail
    @app.get('/api/palette-console/<kind>/<int:did>')
    @auth('admin','agent')
    def console_detail(kind,did):
        u=user();access(u)
        if kind not in KINDS:raise Error('Type de palette inconnu.',404)
        with conn() as c:
            d=doc(c,did,kind,u);ls=lines(c,did)
            attachments=[dict(r) for r in c.execute('SELECT a.id,a.mime,a.note,a.created_at,u.name actor FROM palette_attachments a JOIN users u ON u.id=a.actor_id WHERE a.kind=? AND a.document_id=? ORDER BY a.id DESC',(KINDS[kind],did))]
            acts=[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT a.*,u.name actor FROM ops_audit a JOIN users u ON u.id=a.actor_id WHERE a.document_id=? ORDER BY a.id DESC LIMIT 40',(did,))]
            recv=sum(bool(l['received_at']) for l in ls);miss=sum(bool(l['missing_at']) for l in ls)
            hid=d['destination_hub_id'] if kind=='partner' else d['source_hub_id']
            hc=c.execute('SELECT ci.name FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=?',(hid,)).fetchone()
            return jsonify({**d,'hub_city':hc[0] if hc else None,'lines':ls,'count':len(ls),'received':recv,'missing':miss,'remaining':len(ls)-recv-miss,'attachments':attachments,'activities':acts})

    @app.get('/api/palette-console/<kind>/<int:did>/colis-csv')
    @auth('admin','agent')
    def console_colis_csv(kind,did):
        u=user();access(u)
        if kind not in KINDS:raise Error('Type de palette inconnu.',404)
        with conn() as c:
            d=doc(c,did,kind,u);ls=lines(c,did)
        def cell(v):
            s=str('' if v is None else (('%g'%round(float(v),2)) if isinstance(v,(int,float)) else v))
            return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s.replace('\r',' ').replace('\n',' ')
        rows=['sep=;','ID de suivi; destinataire; adresse; Ville;Nature de produit;Numero de telephone;COD;Status']
        for l in ls:rows.append(';'.join([cell(l['tracking']),cell(l['recipient']),cell(l['address']),cell(l['city']),cell(l['product']),cell(l['phone']),cell(l['amount']),cell(str(l['current_status'] or '').upper())])+';')
        return Response('\ufeff'+'\n'.join(rows)+'\n',mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="ORIENTAL24-colis-'+str(d['reference'])+'.csv"','Cache-Control':'private, no-store'})

    # --------------------------------------------------- réception par lot (scan)
    @app.post('/api/palette-console/partner/<int:did>/receive-bulk')
    @auth('admin','agent')
    def console_receive(did):
        u=user();access(u);d=body()
        if d.get('confirmed') is not True:raise Error('Confirmez avoir physiquement réceptionné les colis cochés.')
        trks=d.get('trackings')
        if not isinstance(trks,list) or not 1<=len(trks)<=500 or any(not isinstance(t,str) or not t.strip() or len(t)>160 for t in trks):raise Error('Trackings à réceptionner requis (1 à 500).')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc_=doc(c,did,'partner',u);fp,prior=replay(c,u,d,did,'receive-bulk')
            if prior:return jsonify(prior)
            if doc_['status'] not in ('En transit','Partiellement reçu'):raise Error('La société doit confirmer l’envoi avant réception.',409)
            ls=lines(c,did);at=now();done=[];picked=[]
            wanted={t.strip().casefold() for t in trks}
            for l in ls:
                if l['tracking'].casefold() not in wanted:continue
                if l['received_at']:continue  # idempotent : déjà reçu, on l'ignore
                if l['missing_at']:raise Error('Colis '+l['tracking']+' déclaré non réceptionné : clôturez ou utilisez le pack fusion.',409)
                p=c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()
                if p['client_id']!=doc_['client_id'] or p['status']!='Créé' or p['driver_id'] is not None or p['current_hub_id'] is not None or p['invoice_id']:
                    raise Error('Colis '+l['tracking']+' : état incompatible avec la réception (déjà affecté, reçu ou facturé).',409)
                picked.append(l)
            if not picked:raise Error('Aucun colis à réceptionner dans cette sélection.',404)
            for l in picked:
                c.execute("UPDATE parcels SET status='Réceptionné',current_hub_id=?,reason_code=NULL,next_attempt_at=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(doc_['destination_hub_id'],at,l['parcel_id']))
                event(c,l['parcel_id'],'Réceptionné',doc_['reference']+' · réception physique ORIENTAL24 à '+doc_['destination_name'],u)
                c.execute('UPDATE ops_document_lines SET received_at=?,received_by=?,active=0 WHERE id=?',(at,u['id'],l['id']))
                done.append(l['tracking'])
            pend=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NULL AND missing_at IS NULL',(did,)).fetchone()[0]
            c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Reçu' if pend==0 else 'Partiellement reçu',at if pend==0 else None,did))
            audit(c,did,u,'Réception par lots (console Palettes)',{'trackings':done,'count':len(picked)})
            r={'ok':True,'id':did,'received':len(picked),'pending':pend,'reference':doc_['reference']}
            return memo(c,u,d,fp,r)

    # ------------------------------------------- ligne « poubelle » : non réceptionné
    @app.post('/api/palette-console/partner/<int:did>/miss')
    @auth('admin','agent')
    def console_miss(did):
        u=user();access(u);d=body()
        code=tracking_text(d.get('tracking'),Error)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc_=doc(c,did,'partner',u);fp,prior=replay(c,u,d,did,'miss')
            if prior:return jsonify(prior)
            if doc_['status'] not in ('En transit','Partiellement reçu'):raise Error('Marquage possible uniquement pendant la réception.',409)
            l=next((x for x in lines(c,did) if x['tracking'].casefold()==code.casefold()),None)
            if not l:raise Error('Ce tracking ne figure pas dans cette palette.',404)
            if l['received_at']:raise Error('Colis déjà réceptionné : le marquage est impossible.',409)
            if l['missing_at']:return memo(c,u,d,fp,{'ok':True,'id':did,'already':True})
            at=now()
            c.execute('UPDATE ops_document_lines SET missing_at=?,active=0 WHERE id=?',(at,l['id']))
            pend=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NULL AND missing_at IS NULL',(did,)).fetchone()[0]
            if pend==0:
                c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Clôturé (écarts)',at,did))
                missing=[x['tracking'] for x in lines(c,did) if x['missing_at']]
                title='Colis non réceptionné(s) · '+doc_['reference']
                if not c.execute('SELECT 1 FROM ops_notifications WHERE user_id=? AND title=?',(doc_['client_id'],title)).fetchone():
                    c.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',(doc_['client_id'],title,'%d colis n\'ont pas été réceptionnés/remis lors de la clôture console : %s'%(len(missing),' · '.join(missing[:12]))+(' …' if len(missing)>12 else ''),at))
            else:c.execute('UPDATE ops_documents SET revision=revision+1 WHERE id=?',(did,))
            event(c,l['parcel_id'],l['current_status'],doc_['reference']+' · déclaré non réceptionné au hub '+doc_['destination_name'],u)
            audit(c,did,u,'Colis déclaré non réceptionné',{'tracking':l['tracking']})
            return memo(c,u,d,fp,{'ok':True,'id':did,'pending':pend})

    # -------------------------------------- réception tardive d’un colis retrouvé
    @app.post('/api/palette-console/partner/<int:did>/receive-recovered')
    @auth('admin','agent')
    def console_receive_recovered(did):
        u=user();access(u);d=body()
        if d.get('confirmed') is not True:raise Error('Confirmez avoir physiquement retrouvé et réceptionné ce colis au hub.')
        tracking=tracking_text(d.get('tracking'),Error)
        expected=d.get('expected_missing_at')
        if not isinstance(expected,str) or not expected:raise Error('Actualisez la fiche avant de confirmer le colis retrouvé.',409)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc_=doc(c,did,'partner',u);fp,prior=replay(c,u,d,did,'receive-recovered')
            if prior:return jsonify(prior)
            if doc_['status'] not in ('En transit','Partiellement reçu','Clôturé (écarts)'):
                raise Error('Cette palette ne contient plus de réception en attente.',409)
            line=next((l for l in lines(c,did) if l['tracking'].casefold()==tracking.casefold()),None)
            if not line:raise Error('Ce tracking ne figure pas dans cette palette.',404)
            if line['received_at']:
                remaining=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND missing_at IS NOT NULL',(did,)).fetchone()[0]
                return memo(c,u,d,fp,{'ok':True,'id':did,'tracking':line['tracking'],'already_received':True,'remaining_exceptions':remaining})
            if not line['missing_at']:raise Error('Ce colis n’est plus dans la liste des colis non réceptionnés. Actualisez.',409)
            if line['missing_at']!=expected:raise Error('L’état du colis a changé. Actualisez puis recommencez.',409)
            p=c.execute('SELECT * FROM parcels WHERE id=?',(line['parcel_id'],)).fetchone()
            if not p or p['client_id']!=doc_['client_id']:raise Error('Commande introuvable pour cette palette.',404)
            if p['status']!='Créé' or p['driver_id'] is not None or p['current_hub_id'] is not None or p['invoice_id']:
                raise Error('État de la commande modifié depuis sa déclaration : vérifiez-la avant la réception.',409)
            at=now();previous_missing_at=line['missing_at']
            changed=c.execute('''UPDATE ops_document_lines SET received_at=?,received_by=?,active=0,missing_at=NULL,missing_by=NULL
                WHERE id=? AND missing_at=? AND received_at IS NULL''',(at,u['id'],line['id'],expected)).rowcount
            if changed!=1:raise Error('La ligne a changé. Actualisez puis recommencez.',409)
            c.execute("UPDATE parcels SET status='Réceptionné',current_hub_id=?,reason_code=NULL,next_attempt_at=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",
                      (doc_['destination_hub_id'],at,line['parcel_id']))
            event(c,line['parcel_id'],'Réceptionné',doc_['reference']+' · réception tardive au hub '+doc_['destination_name']+' après déclaration non réceptionnée',u)
            received=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NOT NULL',(did,)).fetchone()[0]
            pending=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NULL AND missing_at IS NULL',(did,)).fetchone()[0]
            missing=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND missing_at IS NOT NULL',(did,)).fetchone()[0]
            if pending:
                status='Partiellement reçu' if received else 'En transit';completed=None
            elif missing:
                status='Clôturé (écarts)';completed=doc_['completed_at'] or at
            else:
                status='Reçu';completed=at
            c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',(status,completed,did))
            audit(c,did,u,'Réception tardive confirmée après déclaration non réceptionnée',
                  {'tracking':line['tracking'],'trackings':[line['tracking']],'missing_at':previous_missing_at,'received_at':at,'hub_id':doc_['destination_hub_id']})
            title='Colis retrouvé et réceptionné · '+doc_['reference']
            c.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',
                      (doc_['client_id'],title,'Le colis '+line['tracking']+' déclaré non réceptionné a été retrouvé puis réceptionné au hub '+doc_['destination_name']+'. '+str(missing)+' exception(s) restante(s).',at))
            return memo(c,u,d,fp,{'ok':True,'id':did,'tracking':line['tracking'],'received':True,
                                  'remaining_exceptions':missing,'pending':pending,'status':status,'reference':doc_['reference']})

    # ------------------------------------------------------------------ clôture
    @app.post('/api/palette-console/<kind>/<int:did>/close')
    @auth('admin','agent')
    def console_close(kind,did):
        u=user();access(u)
        if kind not in KINDS:raise Error('Type de palette inconnu.',404)
        d=body()
        if d.get('confirmed') is not True:raise Error('Confirmez explicitement cette opération.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc_=doc(c,did,kind,u);fp,prior=replay(c,u,d,did,'close')
            if prior:return jsonify(prior)
            allow=('En transit','Partiellement reçu') if kind=='partner' else ('En transit','Partiellement remis')
            if doc_['status'] not in allow:raise Error('Palette déjà terminée, annulée ou non expédiée : clôture impossible.',409)
            if type(d.get('expected_remaining')) is not int:raise Error('Compteur de colis restants requis.',400)
            at=now();pend=[l for l in lines(c,did) if not l['received_at'] and not l['missing_at']]
            if d['expected_remaining']!=len(pend):raise Error('La liste a changé entre-temps. Actualisez puis recommencez.',409)
            for l in pend:c.execute('UPDATE ops_document_lines SET missing_at=?,active=0 WHERE id=?',(at,l['id']))
            c.execute('UPDATE ops_documents SET status=?,completed_at=?,revision=revision+1 WHERE id=?',('Clôturé (écarts)',at,did))
            trks=[l['tracking'] for l in pend]
            for l in pend:event(c,l['parcel_id'],l['current_status'],doc_['reference']+' · non réceptionné (clôture console) '+(doc_['destination_name'] if kind=='partner' else '— retour jamais remis au vendeur'),u)
            if trks:
                title=('Colis non réceptionné(s) · ' if kind=='partner' else 'Retour clôturé sans remise · ')+doc_['reference']
                c.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',(doc_['client_id'],title,'%d colis n\'ont pas été réceptionnés/remis lors de la clôture console : %s'%(len(trks),' · '.join(trks[:12]))+(' …' if len(trks)>12 else ''),at))
            audit(c,did,u,'Clôture console : colis non réceptionnés',{'trackings':trks,'count':len(trks)})
            r={'ok':True,'id':did,'missing':len(trks),'notified':bool(trks),'reference':doc_['reference']}
            return memo(c,u,d,fp,r)

    # ------------------------------------------------- envoi de retour (une étape)
    @app.post('/api/palette-console/return-send')
    @auth('admin','agent')
    def console_return_send():
        u=user();access(u);d=body()
        if d.get('confirmed') is not True:raise Error('Confirmez l’envoi physique des colis au vendeur.')
        cid=d.get('client_id')
        if isinstance(cid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(cid)):raise Error('Vendeur invalide.')
        hid=d.get('hub_id')
        if isinstance(hid,bool) or not re.fullmatch(r'[1-9][0-9]{0,9}',str(hid)):raise Error('Hub de départ invalide.')
        lots=d.get('lots',0)
        if isinstance(lots,bool) or not isinstance(lots,(int,float)) or int(lots)!=lots or not 0<=int(lots)<=500:raise Error('Nombre de lots invalide (0 à 500).')
        trks=d.get('trackings')
        if not isinstance(trks,list) or not 1<=len(trks)<=500 or any(not isinstance(t,str) or not t.strip() or len(t.strip())>160 for t in trks):raise Error('Scannez 1 à 500 trackings à retourner.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');fp,prior=replay(c,u,d,None,'return-send')
            if prior:return jsonify(prior)
            cl=c.execute("SELECT * FROM users WHERE id=? AND role='client' AND active=1",(cid,)).fetchone()
            if not cl:raise Error('Vendeur actif requis.')
            h=c.execute('SELECT * FROM ops_hubs WHERE id=? AND active=1',(hid,)).fetchone()
            if not h:raise Error('Choisissez un hub de départ actif.',409)
            if u['role']=='agent' and u['agent_hub_id']!=h['id']:raise Error('Vous ne pouvez expédier des retours que depuis votre hub.',403)
            cl=dict(cl)
            seen=set();ps=[]
            for t in trks:
                code=tracking_text(t,Error)
                if code.casefold() in seen:raise Error('Deux scans identiques : '+code,409)
                seen.add(code.casefold())
                p=c.execute("SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.tracking=? AND p.client_id=?",(code,cl['id'])).fetchone()
                if not p:raise Error('Colis '+code+' introuvable pour ce vendeur.',404)
                p=dict(p)
                if p['status'] not in ('Refusé','Retourné'):raise Error('Colis '+code+' : seuls Refusé/Retourné sont retournables.',409)
                if p['current_hub_id']!=h['id']:raise Error('Colis '+code+' physiquement hors du hub choisi.',409)
                if c.execute('SELECT 1 FROM ops_document_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone():raise Error('Colis '+code+' déjà réservé dans un document actif.',409)
                ps.append(p)
            did=c.execute('INSERT INTO ops_documents(kind,client_id,destination_hub_id,client_name,source_name,destination_name,note,created_by,created_at,status,dispatched_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(RKIND,cl['id'],h['id'],cl['company'] or cl['name'],h['name'],cl['company'] or cl['name'],text(d,'note',600),u['id'],now(),'En transit',now())).lastrowid
            ref='PR-%06d'%did
            c.execute('UPDATE ops_documents SET reference=? WHERE id=?',(ref,did))
            c.execute('INSERT INTO return_palette_meta(document_id,transport,tracking_code,lots) VALUES(?,?,?,?)',(did,text(d,'transport',120),text(d,'tracking_code',80),int(lots)))
            for p in ps:c.execute('INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,?,?,?)',(did,p['id'],p['tracking'],p['recipient'],p['city'],p['status']))
            for p in ps:event(c,p['id'],p['status'],ref+' · retour expédié au vendeur (console Palettes), remise encore attendue',u)
            audit(c,did,u,'Return Pallet sent',{'count':len(ps),'vendor':cl['id'],'hub':h['id'],'transport':text(d,'transport',120),'tracking_code':text(d,'tracking_code',80),'lots':int(lots)})
            r={'ok':True,'id':did,'reference':ref,'count':len(ps),'status':'En transit'}
            return memo(c,u,d,fp,r)

    # --------------------------------------------------------- pièces jointes 📎
    @app.post('/api/palette-console/<kind>/<int:did>/attach')
    @auth('admin','agent')
    def console_attach(kind,did):
        u=user();access(u)
        if kind not in KINDS:raise Error('Type de palette inconnu.',404)
        d=body()
        url=d.get('data_url') or ''
        m=re.fullmatch(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=\s]+)',url)
        if not m:raise Error('Image invalide : JPEG, PNG ou WebP attendu.')
        raw=base64.b64decode(m.group(2),validate=True)
        if not raw or len(raw)>1500000:raise Error('Image trop lourde (1,5 Mo maximum après compression).')
        note=text(d,'note',300)
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');doc(c,did,kind,u)
            aid=c.execute('INSERT INTO palette_attachments(kind,document_id,mime,content,note,actor_id,created_at) VALUES(?,?,?,?,?,?,?)',(KINDS[kind],did,'image/'+m.group(1),raw,note,u['id'],now())).lastrowid
            audit(c,did,u,'Pièce jointe ajoutée',{'attachment_id':aid,'note':note})
            return jsonify(ok=True,id=aid)

    @app.get('/api/palette-console/attach/<int:aid>')
    @auth('admin','agent')
    def console_attach_get(aid):
        u=user();access(u)
        with conn() as c:
            r=c.execute('SELECT a.*,d.destination_hub_id FROM palette_attachments a JOIN ops_documents d ON d.id=a.document_id WHERE a.id=?',(aid,)).fetchone()
            if not r or(u['role']=='agent' and r['destination_hub_id']!=u['agent_hub_id']):raise Error('Pièce jointe introuvable.',404)
            return Response(r['content'],mimetype=r['mime'],headers={'Cache-Control':'private, max-age=3600'})

    @app.get('/api/palette-console/<kind>/<int:did>/summary-csv')
    @auth('admin','agent')
    def console_summary_csv(kind,did):
        u=user();access(u)
        if kind not in KINDS:raise Error('Type de palette inconnu.',404)
        with conn() as c:
            d=doc(c,did,kind,u)
            cnt=c.execute('SELECT count(*),sum(received_at IS NOT NULL),sum(missing_at IS NOT NULL) FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()
            buf=io.StringIO();w=csv.writer(buf)
            w.writerow(['Palette','Vendeur / Société','Source','Destination','État','Nb colis','Reçus','Non réceptionnés','Lots','Transport','Suivi','Créée le','Envoyée le'])
            w.writerow([d['reference'],d['client_name'],d['source_name'],d['destination_name'],d['status'],cnt[0],cnt[1] or 0,cnt[2] or 0,d['lots'],d['transport'],d['track_ref'],d['created_at'],d['dispatched_at'] or ''])
            return Response('\ufeff'+buf.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="ORIENTAL24-'+d['reference']+'.resume.csv"','Cache-Control':'private, no-store'})
