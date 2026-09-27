"""Fusion reception: merge several in-transit partner palettes into a single scanning batch.
Single source of truth stays the partner palette lines; the batch only references palettes,
so scanned/closed states are re-derivable and reopenable. Un-scanned lines are declared
non-received (missing_at) and the sending company is notified.
"""
import json,re
from flask import request,jsonify

KIND='partner_palette'

def register_fusion_reception(app,s):
    conn,auth,user,now,Error,event=(s[k] for k in ['conn','auth','user','now','APIError','event'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS fusion_batches(id INTEGER PRIMARY KEY,hub_destination_id INTEGER NOT NULL REFERENCES ops_hubs(id),created_by INTEGER NOT NULL REFERENCES users(id),created_at TEXT NOT NULL,closed_at TEXT);
        CREATE TABLE IF NOT EXISTS fusion_batch_palettes(batch_id INTEGER NOT NULL REFERENCES fusion_batches(id),palette_id INTEGER NOT NULL REFERENCES ops_documents(id),PRIMARY KEY(batch_id,palette_id));
        ''')
    def body():
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        return d
    def access(u):
        if u['role'] not in ('admin','agent'):raise Error('Fusion des réceptions réservée à Admin et aux agents de réception.',403)
    def palettes(c,u,ids):
        if not isinstance(ids,list) or not 2<=len(ids)<=30 or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(set(ids)):
            raise Error('Sélectionnez 2 à 30 palettes distinctes en attente de réception.')
        rows=[]
        for pid in ids:
            r=c.execute('SELECT d.*,m.partner_reference,m.transport FROM ops_documents d JOIN partner_palette_meta m ON m.document_id=d.id WHERE d.id=? AND d.kind=?',(pid,KIND)).fetchone()
            if not r:raise Error('Palette introuvable.',404)
            if r['status'] not in ('En transit','Partiellement reçu'):raise Error(r['reference']+' : déjà réceptionnée ou non expédiée — fusion impossible.',409)
            if u['role']=='agent' and r['destination_hub_id']!=u['agent_hub_id']:raise Error(r['reference']+' : elle attend d\'un autre hub.',404)
            rows.append(dict(r))
        hubs={r['destination_hub_id'] for r in rows}
        if len(hubs)>1:raise Error('Toutes les palettes doivent arriver au même hub.',409)
        return rows,hubs.pop()
    def lines(c,ids):
        return [dict(r) for r in c.execute('SELECT l.id,l.document_id palette_id,l.tracking,l.recipient,l.city,l.received_at,l.missing_at,l.parcel_id,d.reference,d.client_id,d.client_name FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id WHERE l.document_id IN (%s) AND (l.active=1 OR l.received_at IS NOT NULL OR l.missing_at IS NOT NULL) ORDER BY d.id,l.id' % (','.join('?'*len(ids))),ids)]
    def payload(c,bid,u):
        b=c.execute('SELECT * FROM fusion_batches WHERE id=?',(bid,)).fetchone()
        if not b:raise Error('Aucun pack de fusion.',404)
        ids=[r['palette_id'] for r in c.execute('SELECT palette_id FROM fusion_batch_palettes WHERE batch_id=?',(bid,))]
        pl=[dict(j) for j in c.execute('SELECT id,reference,client_id,client_name,status FROM ops_documents WHERE id IN (%s)' % (','.join('?'*len(ids))),ids)]
        ls=lines(c,ids)
        if u['role']=='agent':
            h=c.execute('SELECT hub_destination_id FROM fusion_batches WHERE id=?',(bid,)).fetchone()
            if h and h['hub_destination_id']!=u['agent_hub_id']:raise Error('Pack introuvable pour votre hub.',404)
        received=sum(bool(l['received_at']) for l in ls);missing=sum(bool(l['missing_at']) for l in ls)
        return {'id':bid,'reference':f'FUS-{bid:05d}','palettes':pl,'lines':ls,'count':len(ls),'received':received,'missing':missing,'remaining':len(ls)-received-missing,'closed':bool(b['closed_at'])}

    @app.post('/api/partner-palettes/fusion')
    @auth('admin','agent')
    def fusion_create():
        u=user();access(u);d=body()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            rows,hid=palettes(c,u,d.get('palette_ids'))
            bid=c.execute('INSERT INTO fusion_batches(hub_destination_id,created_by,created_at) VALUES(?,?,?)',(hid,u['id'],now())).lastrowid
            for r in rows:c.execute('INSERT INTO fusion_batch_palettes(batch_id,palette_id) VALUES(?,?)',(bid,r['id']))
            for r in rows:
                c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(r['id'],u['id'],'Palette ajoutée au pack FUS-%05d' % bid,json.dumps({'batch_id':bid},ensure_ascii=False),now()))
            return jsonify(payload(c,bid,u))

    @app.get('/api/partner-palettes/fusion/<int:bid>')
    @auth('admin','agent')
    def fusion_get(bid):
        u=user();access(u)
        with conn() as c:return jsonify(payload(c,bid,u))

    @app.post('/api/partner-palettes/fusion/<int:bid>/scan')
    @auth('admin','agent')
    def fusion_scan(bid):
        u=user();access(u);d=body()
        trk=str(d.get('tracking','')).strip()
        if not trk or len(trk)>160:raise Error('Tracking à scanner requis.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            b=c.execute('SELECT * FROM fusion_batches WHERE id=?',(bid,)).fetchone()
            if not b:raise Error('Aucun pack de fusion.',404)
            if b['closed_at']:raise Error('Pack déjà clôturé.',409)
            if u['role']=='agent' and b['hub_destination_id']!=u['agent_hub_id']:raise Error('Pack introuvable pour votre hub.',404)
            ids=[r['palette_id'] for r in c.execute('SELECT palette_id FROM fusion_batch_palettes WHERE batch_id=?',(bid,))]
            ls=lines(c,ids)
            l=next((x for x in ls if x['tracking']==trk),None)
            if not l:raise Error('Ce tracking ne figure dans aucune palette du pack.',404)
            if l['received_at']:
                p=json.dumps(payload(c,bid,u))
                return app.response_class(p,mimetype='application/json',status=200,headers={'X-Already-Received':'1'})
            if l['missing_at']:raise Error('Ce colis est déjà déclaré non réceptionné.',409)
            at=now()
            c.execute('UPDATE ops_document_lines SET received_at=?,received_by=?,active=0 WHERE id=?',(at,u['id'],l['id']))
            c.execute("UPDATE parcels SET status='Réceptionné',current_hub_id=?,reason_code=NULL,next_attempt_at=NULL,ops_revision=ops_revision+1,updated_at=? WHERE id=?",(b['hub_destination_id'],at,l['parcel_id']))
            dline=c.execute('SELECT d.reference,d.status FROM ops_documents d WHERE d.id=?',(l['palette_id'],)).fetchone()
            c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(l['palette_id'],u['id'],'Colis scanné reçu (fusion FUS-%05d)' % bid,json.dumps({'parcel_ids':[l['parcel_id']],'trackings':[trk],'batch_id':bid},ensure_ascii=False),at))
            pend=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND active=1 AND received_at IS NULL AND missing_at IS NULL',(l['palette_id'],)).fetchone()[0]
            c.execute('UPDATE ops_documents SET status=?,completed_at=CASE WHEN ?=0 THEN ? ELSE completed_at END,revision=revision+1 WHERE id=?',('Reçu' if pend==0 else 'Partiellement reçu',pend,at,l['palette_id']))
            event(c,l['parcel_id'],'En transit',dline['reference']+' · reçu au pack de fusion FUS-%05d' % bid,u)
            return jsonify(payload(c,bid,u))

    @app.post('/api/partner-palettes/fusion/<int:bid>/close')
    @auth('admin','agent')
    def fusion_close(bid):
        u=user();access(u);d=body()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            b=c.execute('SELECT * FROM fusion_batches WHERE id=?',(bid,)).fetchone()
            if not b:raise Error('Aucun pack de fusion.',404)
            if u['role']=='agent' and b['hub_destination_id']!=u['agent_hub_id']:raise Error('Pack introuvable pour votre hub.',404)
            ids=[r['palette_id'] for r in c.execute('SELECT palette_id FROM fusion_batch_palettes WHERE batch_id=?',(bid,))]
            paly=payload(c,bid,u)
            if paly['closed']:
                r=dict(paly);r['replayed']=True
                return jsonify(r)
            pending=[l for l in payload(c,bid,u)['lines'] if not l['received_at'] and not l['missing_at']]
            if type(d.get('expected_remaining')) is not int or d['expected_remaining']!=len(pending):
                raise Error('Le lot a changé entre-temps. Actualisez puis recommencez.',409)
            at=now()
            per={}
            for l in pending:
                c.execute('UPDATE ops_document_lines SET missing_at=?,active=0 WHERE id=?',(at,l['id']))
                per.setdefault((l['palette_id'],l['reference'],l['client_id']),[]).append(l['tracking'])
                event(c,l['parcel_id'],'En transit',l['reference']+' · non réceptionné au pack de fusion FUS-%05d' % bid,u)
            for (pid,ref,cid),trks in per.items():
                pend=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND active=1 AND received_at IS NULL AND missing_at IS NULL',(pid,)).fetchone()[0]
                c.execute("UPDATE ops_documents SET status='Clôturé (écarts)',completed_at=?,revision=revision+1 WHERE id=?",(at,pid))
                c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(pid,u['id'],'Fusion clôturée : colis non réceptionnés',json.dumps({'batch_id':bid,'trackings':trks,'count':len(trks)},ensure_ascii=False),at))
                c.execute('INSERT INTO ops_notifications(user_id,title,body,created_at) VALUES(?,?,?,?)',
                    (cid,'Colis non réceptionné(s) · '+ref,'Fusion FUS-%05d — %d colis envoyé(s) n\'ont pas été réceptionnés au hub : %s' % (bid,len(trks),' · '.join(trks[:12]))+(' …' if len(trks)>12 else ''),at))
            received=sum(bool(l['received_at']) for l in payload(c,bid,u)['lines'])
            for r in c.execute('SELECT palette_id FROM fusion_batch_palettes WHERE batch_id=?',(bid,)):
                pid=r['palette_id']
                pend=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NULL AND missing_at IS NULL',(pid,)).fetchone()[0]
                miss=c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND missing_at IS NOT NULL',(pid,)).fetchone()[0]
                cur=c.execute('SELECT status FROM ops_documents WHERE id=?',(pid,)).fetchone()['status']
                if pend==0 and miss==0 and cur!='Reçu':c.execute("UPDATE ops_documents SET status='Reçu',completed_at=?,revision=revision+1 WHERE id=?",(at,pid))
            c.execute('UPDATE fusion_batches SET closed_at=? WHERE id=?',(at,bid))
            out=payload(c,bid,u);out['notified']=len(per)
            return jsonify(out)
