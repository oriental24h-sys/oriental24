"""Read-only dispatch scans followed by one atomic, idempotent physical departure."""
import hashlib
import json
import re
from flask import request, jsonify


def register_dispatch_collection(app,s):
    conn,auth,user,Error=(s[k] for k in ('conn','auth','user','APIError'))
    registry=s.setdefault('dispatch_adapters',{})
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS dispatch_collection_keys(
            actor_id INTEGER NOT NULL,request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,
            result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key))''')

    def load(c,kind,did,u):
        a=registry.get(kind)
        if not a:raise Error('Envoi inconnu.',404)
        if u['role']=='hub_manager' and not c.execute('SELECT id FROM ops_hubs WHERE id=? AND active=1',(u.get('agent_hub_id'),)).fetchone():raise Error('Hub actif requis.',403)
        doc,ls=a['load'](c,did,u)
        ps=[dict(c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()) for l in ls]
        snapshot=hashlib.sha256(json.dumps([doc,ls,ps],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return a,doc,ls,snapshot

    def sent(kind,doc,l):
        return (l.get('departure_scanned_at') or l.get('received_at')) if kind=='transfer' else doc.get('dispatched_at')
    def excluded(l):return bool(l.get('departure_reconciled_at') or l.get('missing_at'))
    def available(doc):return doc['status'] in ('Préparé','Départ partiel')

    @app.get('/api/dispatch-collection/<kind>/<int:did>')
    @auth('admin','hub_manager','client')
    def dispatch_collection_get(kind,did):
        u=user()
        with conn() as c:
            a,doc,ls,snapshot=load(c,kind,did,u);rows=[]
            for l in ls:
                reason=''
                if available(doc) and not sent(kind,doc,l) and not excluded(l):
                    try:a['check'](c,doc,l,u)
                    except Error as e:reason=str(e)
                private=u['role']=='hub_manager' and l.get('current_hub_id')!=u.get('agent_hub_id')
                rows.append(dict(id=l['id'],tracking=l['tracking'],received_at=sent(kind,doc,l),excluded=excluded(l),blocked=bool(reason),blocked_reason=reason,
                    recipient='' if private else l.get('recipient',''),city='' if private else l.get('city','')))
            return jsonify(id=did,reference=doc['reference'],status=doc['status'],snapshot=snapshot,lines=rows,available=available(doc),allow_partial_dispatch=bool(a.get('release')),
                route=' → '.join(filter(None,[doc.get('source_name') or doc.get('client_name'),doc.get('destination_name')])),
                confirmation='Je confirme le départ physique de tous les colis scannés. Aucun envoi avant cette validation.')

    @app.get('/api/dispatch-collection/<kind>/<int:did>/check')
    @auth('admin','hub_manager','client')
    def dispatch_collection_check(kind,did):
        u=user();tracking=request.args.get('tracking','').strip().casefold()
        with conn() as c:
            a,doc,ls,snapshot=load(c,kind,did,u)
            if request.args.get('snapshot')!=snapshot:raise Error('Le manifeste, les commandes ou le trajet ont changé. Rouvrez et contrôlez les scans.',409)
            l=next((l for l in ls if l['tracking'].casefold()==tracking),None)
            if not l or excluded(l):raise Error('Commande hors du manifeste de départ.',404)
            if sent(kind,doc,l):return jsonify(ok=True,already_scanned=True)
            if not available(doc):raise Error('Palette indisponible pour envoi.',409)
            a['check'](c,doc,l,u)
            return jsonify(ok=True,line_id=l['id'],already_scanned=False)

    @app.post('/api/dispatch-collection/<kind>/<int:did>')
    @auth('admin','hub_manager','client')
    def dispatch_collection_commit(kind,did):
        d=request.get_json(silent=True);u=user()
        if not isinstance(d,dict) or d.get('confirmed') is not True:raise Error('Confirmez explicitement le départ physique.')
        key=d.get('request_key');ids=d.get('line_ids')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de confirmation invalide.')
        if not isinstance(ids,list) or not 1<=len(ids)<=500 or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(set(ids)):raise Error('Liste de scans invalide ou répétée.')
        fp=hashlib.sha256(json.dumps([kind,did,d],sort_keys=True).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE');a,doc,ls,snapshot=load(c,kind,did,u)
            prior=c.execute('SELECT * FROM dispatch_collection_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
            if prior:
                if prior['fingerprint']!=fp:raise Error('Clé déjà utilisée pour un autre envoi.',409)
                return jsonify(**json.loads(prior['result']),replayed=True)
            if d.get('snapshot')!=snapshot:raise Error('Le manifeste, les commandes ou le trajet ont changé. Rouvrez et contrôlez les scans.',409)
            if not available(doc):raise Error('Palette indisponible pour envoi.',409)
            pending=[l for l in ls if not sent(kind,doc,l) and not excluded(l)]
            if not set(ids).issubset({l['id'] for l in pending}):raise Error('Commande extérieure, exclue ou déjà envoyée.',409)
            selected=[l for l in pending if l['id'] in set(ids)]
            omitted=[l for l in pending if l['id'] not in set(ids)]
            if omitted and not a.get('release'):raise Error('Ce type de document exige encore tous les scans.',409)
            for l in selected:a['check'](c,doc,l,u)
            if omitted:a['release'](c,doc,omitted,u)
            a['apply'](c,doc,selected,u)
            result=dict(ok=True,id=did,dispatched=len(selected),released=len(omitted),reference=doc['reference'])
            c.execute('INSERT INTO dispatch_collection_keys VALUES(?,?,?,?)',(u['id'],key,fp,json.dumps(result)))
            return jsonify(result)
