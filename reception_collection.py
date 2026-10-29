"""Shared scan collection API. No mutation on scan; one atomic, replay-safe commit."""
import hashlib
import json
import logging
import re
from flask import request, jsonify

log = logging.getLogger('oriental24')


def register_reception_collection(app, s):
    conn, auth, user, Error = (s[k] for k in ('conn','auth','user','APIError'))
    registry = s.setdefault('reception_adapters', {})
    with conn() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS reception_collection_keys(
            actor_id INTEGER NOT NULL,request_key TEXT NOT NULL,fingerprint TEXT NOT NULL,
            result TEXT NOT NULL,PRIMARY KEY(actor_id,request_key))''')

    def load(c, kind, did, u):
        adapter = registry.get(kind)
        if not adapter:raise Error('Réception inconnue.',404)
        if u['role']=='agent':
            h=c.execute('SELECT id FROM ops_hubs WHERE id=? AND active=1',(u.get('agent_hub_id'),)).fetchone()
            if not h:raise Error('Hub actif requis.',403)
        doc, lines = adapter['load'](c,did,u)
        parcels = [dict(c.execute('SELECT * FROM parcels WHERE id=?',(l['parcel_id'],)).fetchone()) for l in lines]
        snapshot = hashlib.sha256(json.dumps([doc,lines,parcels],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return adapter,doc,lines,snapshot

    @app.get('/api/reception-collection/<kind>/<int:did>')
    @auth('admin','agent','client')
    def reception_collection_get(kind,did):
        u=user()
        with conn() as c:
            _,doc,lines,snapshot=load(c,kind,did,u)
            rows=[]
            for l in lines:
                excluded=bool(l.get('missing_at') or l.get('departure_reconciled_at'))
                blocked=bool(doc.get('departure_scan_required') and not l.get('departure_scanned_at') and not excluded and not l.get('received_at'))
                private=u['role']=='agent' and (not l.get('received_at') or l.get('current_hub_id')!=u.get('agent_hub_id'))
                rows.append(dict(id=l['id'],tracking=l['tracking'],received_at=l.get('received_at'),excluded=excluded,
                    blocked=blocked,recipient='' if private else l.get('recipient',''),city='' if private else l.get('city','')))
            return jsonify(id=did,reference=doc['reference'],status=doc['status'],palette_purpose=doc.get('palette_purpose'),snapshot=snapshot,lines=rows,
                route=doc.get('route') or ' → '.join(filter(None,[doc.get('source_name') or doc.get('client_name'),doc.get('destination_name')])),
                available=doc.get('status') in ('En transit','Partiellement reçu','Départ partiel','Partiellement remis'),
                confirmation='Je confirme la remise physique au vendeur de tous les colis scannés.' if kind=='return' else 'Je confirme la réception physique de tous les colis scannés.')

    @app.post('/api/reception-collection/<kind>/<int:did>')
    @auth('admin','agent','client')
    def reception_collection_commit(kind,did):
        u=user();d=request.get_json(silent=True)
        if not isinstance(d,dict) or d.get('confirmed') is not True:raise Error('Confirmation physique requise.')
        key=d.get('request_key');ids=d.get('line_ids')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}',key):raise Error('Clé de confirmation invalide.')
        if not isinstance(ids,list) or not 1<=len(ids)<=15000 or any(type(i) is not int or i<=0 for i in ids) or len(ids)!=len(set(ids)):raise Error('Scans invalides ou répétés.')
        fp=hashlib.sha256(json.dumps([kind,did,d],sort_keys=True).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            adapter,doc,lines,snapshot=load(c,kind,did,u)
            prior=c.execute('SELECT * FROM reception_collection_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
            if prior:
                if prior['fingerprint']!=fp:raise Error('Clé utilisée pour une autre validation.',409)
                return jsonify(**json.loads(prior['result']),replayed=True)
            if d.get('snapshot')!=snapshot:raise Error('Le manifeste ou une commande a changé. Rouvrez la réception et contrôlez les scans.',409)
            if doc['status'] not in ('En transit','Partiellement reçu','Départ partiel','Partiellement remis'):raise Error('Document indisponible pour réception.',409)
            pending=[l for l in lines if not l.get('received_at') and not l.get('missing_at') and not l.get('departure_reconciled_at')]
            if not set(ids).issubset({l['id'] for l in pending}):raise Error('Un colis est extérieur au bon, déjà réceptionné ou exclu.',409)
            selected=[l for l in pending if l['id'] in set(ids)]
            if doc.get('departure_scan_required') and any(not l.get('departure_scanned_at') for l in selected):raise Error('Des colis n’ont pas encore été scannés au départ. Actualisez après leur départ.',409)
            extra=adapter['apply'](c,doc,selected,u) or {}
            result=dict(ok=True,id=did,received=len(selected),**extra)
            c.execute('INSERT INTO reception_collection_keys VALUES(?,?,?,?)',(u['id'],key,fp,json.dumps(result)))
            return jsonify(result)

    @app.post('/api/reception-collection/bulk')
    @auth('admin','agent','client')
    def reception_collection_bulk():
        """Réception de PLUSIEURS palettes en une seule validation.

        Chaque palette est réceptionnée **en entier** (tous ses colis restants), dans sa
        propre sauvegarde : une palette en erreur (déjà reçue, départ non scanné, hors
        périmètre) n'annule pas les autres et son motif est renvoyé dans la réponse.
        Rejouable : la même `request_key` ne réceptionne jamais deux fois.
        """
        u=user();d=request.get_json(silent=True)
        if not isinstance(d,dict) or d.get('confirmed') is not True:raise Error('Confirmation physique requise.')
        base=d.get('request_key')
        if not isinstance(base,str) or not re.fullmatch(r'[A-Za-z0-9_-]{12,60}',base):raise Error('Clé de confirmation invalide.')
        items=d.get('documents')
        if not isinstance(items,list) or not 1<=len(items)<=30:raise Error('Choisissez entre 1 et 30 palettes à réceptionner.')
        clean=[]
        for it in items:
            if not isinstance(it,dict):raise Error('Sélection invalide.')
            kind=it.get('kind') or 'transfer';did=it.get('id')
            if kind not in ('transfer','partner'):raise Error('Type de palette non autorisé en réception groupée.',403)
            if kind not in registry:raise Error('Type de palette inconnu.',404)
            if type(did) is not int or did<=0:raise Error('Palette invalide.')
            if kind=='partner' and u['role']!='admin':
                raise Error('Le responsable du Hub doit scanner individuellement les colis d’une palette société.',403)
            if (kind,did) not in clean:clean.append((kind,did))
        results=[]
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            for kind,did in clean:
                c.execute('SAVEPOINT bulk_doc')
                try:
                    adapter,doc,lines,snapshot=load(c,kind,did,u)
                    key=(base+'-'+str(did))[:80]
                    fp=hashlib.sha256(json.dumps([kind,did,base],sort_keys=True).encode()).hexdigest()
                    reference=doc.get('reference') or str(did)
                    prior=c.execute('SELECT * FROM reception_collection_keys WHERE actor_id=? AND request_key=?',(u['id'],key)).fetchone()
                    if prior:
                        if prior['fingerprint']!=fp:raise Error('Clé utilisée pour une autre validation.',409)
                        results.append(dict(json.loads(prior['result']),reference=reference,replayed=True))
                    else:
                        if doc['status'] not in ('En transit','Partiellement reçu','Départ partiel','Partiellement remis'):
                            raise Error('Palette non réceptionnable : déjà reçue ou pas encore expédiée.',409)
                        pending=[l for l in lines if not l.get('received_at') and not l.get('missing_at') and not l.get('departure_reconciled_at')]
                        if not pending:raise Error('Aucun colis restant dans cette palette.',409)
                        if doc.get('departure_scan_required'):
                            missing=[l for l in pending if not l.get('departure_scanned_at')]
                            if missing:raise Error(str(len(missing))+' colis ne sont pas scannés au départ. Terminez le départ puis recommencez.',409)
                        extra=adapter['apply'](c,doc,pending,u) or {}
                        result=dict(ok=True,id=did,kind=kind,reference=reference,received=len(pending),**extra)
                        c.execute('INSERT INTO reception_collection_keys VALUES(?,?,?,?)',(u['id'],key,fp,json.dumps(result)))
                        results.append(result)
                    c.execute('RELEASE bulk_doc')
                except Error as exc:
                    c.execute('ROLLBACK TO bulk_doc');c.execute('RELEASE bulk_doc')
                    results.append(dict(ok=False,id=did,kind=kind,error=getattr(exc,'msg',str(exc))))
                except Exception:
                    c.execute('ROLLBACK TO bulk_doc');c.execute('RELEASE bulk_doc')
                    log.warning('Réception groupée : palette %s annulée', did, exc_info=True)
                    results.append(dict(ok=False,id=did,kind=kind,error='Réception impossible sur cette palette. Faites-la à l’unité.'))
            done=[r for r in results if r.get('ok')]
            return jsonify(ok=bool(done),palettes=len(results),received_palettes=len(done),
                           received_parcels=sum(int(r.get('received') or 0) for r in done),results=results)
