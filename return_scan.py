"""v1.22.0 « Envoi de palette retour au scan » — l'agent scanne les colis à retourner, un par un.

Le scan COLLECTE (aucune écriture avant la fin) puis, quand tout est scanné, un seul bouton
« Valider et envoyer le retour » crée la palette retour et l'expédie au vendeur.

Règles de contrôle, à chaque scan (verdict renvoyé par `scan-lookup` — le son et le message de
l'application en découlent) :

  ok            colis du vendeur choisi, resté plus d'une semaine chez nous (état ≠ « Livré »)
                → ajouté au lot + son « validé » (aigu).
  too_recent    colis du vendeur mais pas encore resté une semaine (état ≠ « Livré »)
                → son « refusé » (grave) + question « l'ajouter quand même ? OUI / NON ».
  delivered     colis déjà « Livré » → refus définitif (aucun retour possible).
  other_client  code d'un colis appartenant à un autre vendeur → refus + nom du vrai vendeur.
  reserved      colis déjà réservé dans une autre palette active → refus.
  not_found     code inconnu → refus.

Le nombre de jours d'une semaine est réglable par le paramètre `return_week_days` (défaut 7).
"""
import hashlib
import json
import re
from flask import request, jsonify

KIND = 'return_palette'
DEFAULT_WEEK_DAYS = 7
CLOSED_STATUSES = ('Livré',)


def register_return_scan(app, s):
    conn, auth, user, now, Error = (s[k] for k in ['conn', 'auth', 'user', 'now', 'APIError'])
    event = s.get('event')

    def week_days(c):
        try:
            r = c.execute("SELECT value FROM settings WHERE key='return_week_days'").fetchone()
            if r and str(r['value']).strip().isdigit() and 1 <= int(r['value']) <= 90:
                return int(r['value'])
        except Exception:
            pass
        return DEFAULT_WEEK_DAYS

    def staff(u):
        if u['role'] not in ('admin', 'agent'):
            raise Error('Préparation et envoi des retours réservés à Admin et aux agents de réception.', 403)

    def clean_hub(c, hid, u):
        if isinstance(hid, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}', str(hid)):
            raise Error('Hub de départ invalide.')
        h = c.execute('SELECT h.*,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1', (hid,)).fetchone()
        if not h:
            raise Error('Choisissez un hub de départ actif.', 409)
        if u['role'] == 'agent' and u['agent_hub_id'] != h['id']:
            raise Error('Vous ne pouvez expédier des retours que depuis votre hub.', 403)
        return dict(h)

    def clean_client(c, cid):
        if isinstance(cid, bool) or not re.fullmatch(r'[1-9][0-9]{0,9}', str(cid)):
            raise Error('Vendeur invalide.')
        r = c.execute("SELECT * FROM users WHERE id=? AND role='client' AND active=1", (cid,)).fetchone()
        if not r:
            raise Error('Vendeur actif requis.')
        return dict(r)

    def reserved_by(c, pid):
        r = c.execute('''SELECT d.reference,d.kind FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
            WHERE l.parcel_id=? AND l.active=1 AND l.received_at IS NULL AND l.missing_at IS NULL LIMIT 1''', (pid,)).fetchone()
        return dict(r) if r else None

    def verdict_for(c, p, cid, u):
        """Décide ce que l'application doit faire du code scanné."""
        if p is None:
            return 'not_found', 'Code inconnu : aucun colis avec ce tracking.', None
        info = dict(p)
        age = c.execute("SELECT CAST(julianday('now','localtime')-julianday(?) AS INTEGER) d", (p['created_at'],)).fetchone()['d']
        info['days'] = int(age or 0)
        if p['client_id'] != cid:
            other = c.execute('SELECT name,company FROM users WHERE id=?', (p['client_id'],)).fetchone()
            info['client_name'] = (other['company'] or other['name']) if other else ''
            return 'other_client', 'Ce colis appartient à <b>%s</b> — pas au vendeur choisi.' % (info['client_name'] or 'un autre vendeur'), info
        if p['status'] in CLOSED_STATUSES:
            return 'delivered', 'Colis <b>%s</b> déjà <b>Livré</b> : aucun retour possible.' % p['tracking'], info
        busy = reserved_by(c, p['id'])
        if busy:
            info['reserved_in'] = busy['reference']
            return 'reserved', 'Colis <b>%s</b> déjà réservé dans <b>%s</b>.' % (p['tracking'], busy['reference']), info
        if info['days'] < week_days(c):
            return 'too_recent', 'Colis <b>%s</b> : seulement <b>%d jour(s)</b> chez nous — la semaine n’est pas encore passée (état : %s).' % (
                p['tracking'], info['days'], p['status']), info
        return 'ok', 'Colis <b>%s</b> · %d jours · état %s.' % (p['tracking'], info['days'], p['status']), info

    def find_tracking(c, code, u):
        """Recherche par tracking, puis par référence de palette (une palette = ses colis)."""
        code = str(code or '').strip()
        if not code or len(code) > 160:
            raise Error('Code invalide.')
        p = c.execute('SELECT * FROM parcels WHERE upper(tracking)=upper(?)', (code,)).fetchone()
        if p:
            return p
        p = c.execute('''SELECT p.* FROM ops_document_lines l JOIN ops_documents d ON d.id=l.document_id
            JOIN parcels p ON p.id=l.parcel_id WHERE d.reference=? AND l.active=1 ORDER BY l.id LIMIT 1''', (code,)).fetchone()
        return p

    @app.get('/api/return-palettes/scan-lookup')
    @auth('admin', 'agent')
    def return_scan_lookup():
        u = user()
        staff(u)
        with conn() as c:
            cid = clean_client(c, request.args.get('client_id'))['id']
            clean_hub(c, request.args.get('hub_id'), u)
            p = find_tracking(c, request.args.get('tracking'), u)
            verdict, message, info = verdict_for(c, p, cid, u)
            payload = {k: info[k] for k in ('id', 'tracking', 'recipient', 'city', 'status', 'days') if k in info} if info else {}
            if info and 'client_name' in info:
                payload['client_name'] = info['client_name']
            if info and 'reserved_in' in info:
                payload['reserved_in'] = info['reserved_in']
            if info:
                city = c.execute('SELECT name FROM cities WHERE id=?', (info.get('city_id'),)).fetchone()
                payload['city'] = city['name'] if city else ''
                hub = c.execute('SELECT name FROM ops_hubs WHERE id=?', (info.get('current_hub_id'),)).fetchone() if info.get('current_hub_id') else None
                payload['hub'] = hub['name'] if hub else ''
            return jsonify(verdict=verdict, message=message, parcel=payload, week_days=week_days(c))

    def replay(c, u, d, action):
        key = d.get('request_key')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', key):
            raise Error('Clé de confirmation invalide.')
        fp = hashlib.sha256(json.dumps([action, d], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        r = c.execute('SELECT * FROM return_palette_keys WHERE actor_id=? AND request_key=?', (u['id'], key)).fetchone()
        if r:
            if r['fingerprint'] != fp:
                raise Error('Clé déjà utilisée pour une autre saisie.', 409)
            return fp, {**json.loads(r['result']), 'replayed': True}
        return fp, None

    @app.post('/api/return-palettes/scan-send')
    @auth('admin', 'agent')
    def return_scan_send():
        """Crée la palette retour avec les colis scannés ET l'expédie — un seul geste."""
        u = user()
        staff(u)
        d = request.get_json(silent=True) or {}
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            fp, prior = replay(c, u, d, 'scan-send')
            if prior:
                return jsonify(prior)
            cl = clean_client(c, d.get('client_id'))
            hub = clean_hub(c, d.get('hub_id'), u)
            ids = d.get('parcel_ids')
            if not isinstance(ids, list) or not 1 <= len(ids) <= 500 or any(type(i) is not int or i <= 0 for i in ids) or len(ids) != len(set(ids)):
                raise Error('Scannez 1 à 500 colis distincts avant de valider.')
            confirmed = d.get('confirmed') or []
            if not isinstance(confirmed, list) or any(type(i) is not int for i in confirmed):
                raise Error('Liste de confirmation invalide.')
            ps = []
            for pid in ids:
                p = c.execute('SELECT * FROM parcels WHERE id=? AND client_id=?', (pid, cl['id'])).fetchone()
                if not p:
                    raise Error('Colis inaccessible pour ce vendeur.', 404)
                verdict, message, info = verdict_for(c, p, cl['id'], u)
                if verdict == 'too_recent' and pid not in confirmed:
                    raise Error('Colis %s : la semaine n’est pas encore passée — confirmez son ajout.' % p['tracking'], 409)
                if verdict not in ('ok', 'too_recent'):
                    raise Error(re.sub('<[^>]+>', '', message), 409)
                ps.append(p)
            transport = str(d.get('transport') or '').strip()[:120]
            tracking_code = str(d.get('tracking_code') or '').strip()[:80]
            lots = d.get('lots', 0)
            if isinstance(lots, bool) or lots is None or isinstance(lots, str) or not isinstance(lots, (int, float)) or int(lots) != lots or not 0 <= int(lots) <= 500:
                raise Error('Nombre de lots invalide (0 à 500).')
            at = now()
            did = c.execute('''INSERT INTO ops_documents(kind,client_id,destination_hub_id,client_name,source_name,destination_name,note,created_by,created_at,status,dispatched_at)
                VALUES(?,?,?,?,?,?,?,?,?,'En transit',?)''',
                            (KIND, cl['id'], hub['id'], cl['company'] or cl['name'], hub['name'], cl['company'] or cl['name'],
                             str(d.get('note') or '').strip()[:600], u['id'], at, at)).lastrowid
            ref = 'PR-%06d' % did
            c.execute('UPDATE ops_documents SET reference=? WHERE id=?', (ref, did))
            c.execute('INSERT INTO return_palette_meta(document_id,transport,tracking_code,lots) VALUES(?,?,?,?)',
                      (did, transport, tracking_code, int(lots)))
            for p in ps:
                c.execute('''INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status)
                    VALUES(?,?,?,?,?,?)''', (did, p['id'], p['tracking'], p['recipient'],
                                             c.execute('SELECT name FROM cities WHERE id=?', (p['city_id'],)).fetchone()['name'],
                                             p['status']))
            c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',
                      (did, u['id'], 'Palette retour scannée puis expédiée',
                       json.dumps({'count': len(ps), 'hub_id': hub['id'], 'vendor_id': cl['id'],
                                   'week_days': week_days(c), 'confirmed': [i for i in ids if i in confirmed]},
                                  ensure_ascii=False), at))
            for p in ps:
                if event:
                    event(c, p['id'], p['status'], ref + ' · retour expédié au vendeur (scan à l’agence)', u)
            result = {'ok': True, 'id': did, 'reference': ref, 'count': len(ps), 'status': 'En transit',
                      'vendor': cl['company'] or cl['name'], 'hub': hub['name'], 'week_days': week_days(c),
                      'confirmed': len([i for i in ids if i in confirmed])}
            c.execute('INSERT INTO return_palette_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)',
                      (u['id'], d['request_key'], fp, json.dumps(result)))
        return jsonify(result)

    @app.post('/api/return-palettes/<int:did>/refuse')
    @auth('admin', 'agent', 'client')
    def return_palette_refuse(did):
        """Palette retour refusée (par le vendeur ou l'agence) : les colis redeviennent disponibles."""
        u = user()
        d = request.get_json(silent=True) or {}
        reason = str(d.get('reason') or '').strip()
        if not 3 <= len(reason) <= 600:
            raise Error('Motif du refus obligatoire (3 à 600 caractères).')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            fp, prior = replay(c, u, d, 'refuse-%d' % did)
            if prior:
                return jsonify(prior)
            doc = c.execute('SELECT * FROM ops_documents WHERE id=? AND kind=?', (did, KIND)).fetchone()
            if not doc:
                raise Error('Palette retour introuvable.', 404)
            if u['role'] == 'agent' and doc['destination_hub_id'] != u['agent_hub_id']:
                raise Error('Palette retour introuvable pour votre hub.', 404)
            if u['role'] == 'client' and doc['client_id'] != u['id']:
                raise Error('Palette retour introuvable.', 404)
            if doc['status'] not in ('Préparé', 'En transit', 'Partiellement remis'):
                raise Error('Cette palette est déjà clôturée : elle ne peut plus être refusée.', 409)
            rev = d.get('revision')
            if type(rev) is not int or rev != doc['revision']:
                raise Error('Palette modifiée. Actualisez avant de confirmer.', 409)
            ls = [dict(r) for r in c.execute('SELECT * FROM ops_document_lines WHERE document_id=?', (did,))]
            pending = [l for l in ls if l['active'] and not l['received_at']]
            at = now()
            for l in pending:
                c.execute('UPDATE ops_document_lines SET active=0 WHERE id=?', (l['id'],))
            c.execute("UPDATE ops_documents SET status='Annulé',cancel_reason=?,revision=revision+1 WHERE id=?", (reason, did))
            c.execute('INSERT INTO ops_audit(document_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)',
                      (did, u['id'], 'Palette retour refusée — colis libérés',
                       json.dumps({'reason': reason, 'released': [l['tracking'] for l in pending], 'role': u['role']}, ensure_ascii=False), at))
            for l in pending:
                if event:
                    event(c, l['parcel_id'], l['initial_status'],
                          '%s · retour refusé (%s) — colis de nouveau disponible pour une nouvelle palette' % (doc['reference'], reason), u)
            result = {'ok': True, 'id': did, 'reference': doc['reference'], 'status': 'Annulé', 'released': len(pending)}
            c.execute('INSERT INTO return_palette_keys(actor_id,request_key,fingerprint,result) VALUES(?,?,?,?)',
                      (u['id'], d['request_key'], fp, json.dumps(result)))
        return jsonify(result)
