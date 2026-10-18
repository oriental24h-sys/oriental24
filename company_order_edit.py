"""Company-owned, pre-dispatch order edits and logical deletions with draft sync."""
import json
import re
from flask import request, jsonify
from client_types import tracking_text, check_available


def company_order_block(c, p):
    if p['status'] != 'Créé' or p['driver_id'] is not None or p['current_hub_id'] is not None or p['invoice_id'] or p.get('financial_locked'):
        return 'Commande envoyée, prise en charge ou verrouillée : modification et suppression interdites.'
    if c.execute('SELECT 1 FROM company_deleted_orders WHERE parcel_id=?',(p['id'],)).fetchone():
        return 'Commande supprimée.'
    if c.execute('''SELECT 1 FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
        WHERE l.parcel_id=? AND (d.dispatched_at IS NOT NULL OR l.received_at IS NOT NULL
        OR (l.active=1 AND (d.kind!='partner_palette' OR d.status!='Préparé' OR d.client_id!=?)))''',(p['id'],p['client_id'])).fetchone():
        return 'Palette déjà envoyée ou document verrouillé : modification et suppression interdites.'
    return None


def company_order_flags(c, rows, u):
    if u['role']=='client' and u.get('client_type')=='societe_livraison':
        for p in rows:
            reason=company_order_block(c,p)
            p['company_order_editable']=reason is None
            p['company_order_lock_reason']=reason or ''
    return rows


def register_company_order_edit(app,s):
    conn,auth,user,Error,now=(s[k] for k in ('conn','auth','user','APIError','now'))
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS company_deleted_orders(
            parcel_id INTEGER PRIMARY KEY REFERENCES parcels(id),actor_id INTEGER NOT NULL REFERENCES users(id),deleted_at TEXT NOT NULL)''')

    @app.route('/api/parcels/<int:pid>/company-edit',methods=['PATCH','DELETE'])
    @auth('client')
    def company_order_edit(pid):
        u=user()
        if u.get('client_type')!='societe_livraison':raise Error('Action réservée aux sociétés de livraison.',403)
        d=request.get_json(silent=True)
        if not isinstance(d,dict):raise Error('Objet JSON requis.')
        allowed={'revision','confirmed'} if request.method=='DELETE' else {'revision','tracking','recipient','phone','address','city_id','amount','product','note','not_allowed_to_open','is_exchange'}
        if set(d)-allowed:raise Error('Champ non modifiable.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            p=s['parcel'](c,pid,u)
            reason=company_order_block(c,p)
            if reason:raise Error(reason,409)
            if type(d.get('revision')) is not int or d['revision']!=p['ops_revision']:raise Error('Commande modifiée. Actualisez avant de confirmer.',409)
            docs=[dict(r) for r in c.execute('''SELECT d.id,d.reference FROM ops_documents d JOIN ops_document_lines l ON l.document_id=d.id
                WHERE l.parcel_id=? AND l.active=1 AND d.kind='partner_palette' AND d.status='Préparé' ''',(pid,))]
            t=now()
            if request.method=='DELETE':
                if d.get('confirmed') is not True:raise Error('Confirmez la suppression de cette commande.')
                for doc in docs:
                    c.execute('DELETE FROM ops_document_lines WHERE document_id=? AND parcel_id=?',(doc['id'],pid))
                    c.execute('UPDATE ops_documents SET revision=revision+1 WHERE id=?',(doc['id'],))
                    if not c.execute('SELECT 1 FROM ops_document_lines WHERE document_id=?',(doc['id'],)).fetchone():
                        c.execute("UPDATE ops_documents SET status='Annulé',cancel_reason='Brouillon vide après suppression de sa dernière commande' WHERE id=?",(doc['id'],))
                        c.execute('UPDATE partner_palette_meta SET deleted_at=? WHERE document_id=?',(t,doc['id']))
                    c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(doc['id'],u['id'],'Commande retirée du brouillon avant envoi',json.dumps({'parcel_id':pid,'tracking':p['tracking']},ensure_ascii=False),t))
                c.execute('INSERT INTO company_deleted_orders VALUES(?,?,?)',(pid,u['id'],t))
                c.execute("UPDATE parcels SET status='Annulé',ops_revision=ops_revision+1,updated_at=? WHERE id=?",(t,pid))
                s['event'](c,pid,'Annulé','Commande supprimée par la société avant envoi ; historique conservé.',u)
                s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='company_order_deleted',entity_type='parcel',entity_id=pid,old_value={'tracking':p['tracking'],'status':p['status']},new_value={'deleted':True},metadata={'draft_ids':[x['id'] for x in docs]},created_at=t)
                return jsonify(ok=True,deleted=True)
            # Full edit form; strict types prevent accidental nulls and forged ownership/fees.
            fields={}
            for k in ('recipient','phone','address','product','note'):
                if not isinstance(d.get(k),str):raise Error('Champ texte requis : '+k)
                fields[k]=s['text'](d,k,k not in ('product','note'))
            if not re.fullmatch(r'\+?[\d\s-]{9,18}',fields['phone']):raise Error('Numéro de téléphone invalide.')
            tracking=tracking_text(d.get('tracking'),Error)
            if tracking.casefold()!=p['tracking'].casefold():
                check_available(c,tracking,Error,client_id=u['id'])
            for k in ('not_allowed_to_open','is_exchange'):
                if type(d.get(k)) is not bool:raise Error('Option invalide : '+k)
            if type(d.get('city_id')) is not int:raise Error('Ville invalide.')
            city=c.execute('SELECT * FROM cities WHERE id=?',(d['city_id'],)).fetchone()
            if not city or (city['id']!=p['city_id'] and not city['delivery']):raise Error('Choisissez une ville ouverte à la livraison.')
            if isinstance(d.get('amount'),bool):raise Error('Montant invalide.')
            amount=s['number'](d,'amount')
            fee,ret=p['fee'],p['return_fee']
            if city['id']!=p['city_id']:
                fee,ret=s['tariff_fees_for'](c,u['id'],dict(city)) if 'tariff_fees_for' in s else (city['fee'],city['return_fee'])
            c.execute('''UPDATE parcels SET tracking=?,recipient=?,phone=?,address=?,city_id=?,amount=?,fee=?,return_fee=?,product=?,note=?,open_allowed=?,is_exchange=?,ops_revision=ops_revision+1,updated_at=? WHERE id=?''',
                (tracking,fields['recipient'],fields['phone'],fields['address'],city['id'],amount,fee,ret,fields['product'],fields['note'],int(not d['not_allowed_to_open']),int(d['is_exchange']),t,pid))
            for doc in docs:
                c.execute('UPDATE ops_document_lines SET tracking=?,recipient=?,city=? WHERE document_id=? AND parcel_id=?',(tracking,fields['recipient'],city['name'],doc['id'],pid))
                c.execute('UPDATE ops_documents SET revision=revision+1 WHERE id=?',(doc['id'],))
                c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',(doc['id'],u['id'],'Commande du brouillon modifiée avant envoi',json.dumps({'parcel_id':pid,'tracking':tracking},ensure_ascii=False),t))
            s['event'](c,pid,p['status'],'Informations modifiées par la société avant envoi.',u)
            after=dict(fields,tracking=tracking,city_id=city['id'],amount=amount,fee=fee,return_fee=ret,open_allowed=int(not d['not_allowed_to_open']),is_exchange=int(d['is_exchange']))
            s['append_audit_log'](c,actor_id=u['id'],actor_name=u['name'],action='company_order_edited',entity_type='parcel',entity_id=pid,old_value={k:p[k] for k in after},new_value=after,metadata={'draft_ids':[x['id'] for x in docs]},created_at=t)
            return jsonify(ok=True,revision=p['ops_revision']+1)
