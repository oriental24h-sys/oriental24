"""v1.22.0 « Envoi de palette retour au scan » — l'agent scanne les colis à retourner, un par un.

Le scan COLLECTE (aucune écriture avant la fin) puis, quand tout est scanné, un seul bouton
« Valider et envoyer le retour » crée la palette retour et l'expédie au vendeur.

Règles de contrôle, à chaque scan (verdict renvoyé par `scan-lookup` — le son et le message de
l'application en découlent). Elles s'appliquent aux **Hubs secondaires** qui renvoient des colis,
jamais au Hub Central qui ne s'envoie pas de retour à lui-même :

  ok            passe DIRECTEMENT, sans alerte : Annulé, Refusé, Retourné, Échange (tracking EC…).
  double        colis déjà « Livré » scanné : il passe quand même (double scanné par erreur).
  needs_confirm Reporté / Programmé avec un rendez-vous FUTUR → alerte + question
                « Reporter à la date X : OUI (part en retour) / NON (reste à l'agence) ».
                Tout autre état → il faut « une semaine au Hub » ET « plus d'un passage de
                livreur » ; sinon même question OUI / NON avec le motif exact.
  other_client  code d'un colis appartenant à un autre vendeur → refus + nom du vrai vendeur.
  reserved      colis déjà réservé dans une autre palette active → refus.
  not_found     code inconnu → refus.

Le nombre de jours d'une semaine est réglable par le paramètre `return_week_days` (défaut 7).
Les passages de livreur sont vérifiés dans les affectations et tentatives du Hub (chronologie).
"""
import datetime
import hashlib
import json
import re
from flask import request, jsonify
from hub_access import parcel_by_tracking_at_hub, parcel_by_manifest_at_hub

KIND = 'return_palette'
DEFAULT_WEEK_DAYS = 7
MIN_HANDOVERS = 2
CLOSED_STATUSES = ('Livré',)
# Départ direct, sans confirmation : retour déclaré, refus, annulation, reprise échange.
DIRECT_STATUSES = ('Annulé', 'Refusé', 'Retourné')
APPOINTMENT_STATUSES = ('Reporté', 'Programmé')
EXCHANGE_PREFIX = 'EC'


def week_days_of(c, fallback=DEFAULT_WEEK_DAYS):
    """Jours exigés au Hub (paramètre `return_week_days`, défaut 7)."""
    try:
        row = c.execute("SELECT value FROM settings WHERE key='return_week_days'").fetchone()
        if row and str(row['value']).strip().isdigit() and 1 <= int(row['value']) <= 90:
            return int(row['value'])
    except Exception:
        pass
    return fallback


def _day(value):
    if not value:
        return None
    for parser in (lambda v: datetime.datetime.fromisoformat(str(v).replace('Z', '+00:00')).date(),
                   lambda v: datetime.date.fromisoformat(str(v)[:10])):
        try:
            return parser(value)
        except ValueError:
            continue
    return None


def arrived_at_hub(c, pid, hub_id):
    """Dernière arrivée physique connue de ce colis dans ce Hub."""
    stamps = []
    row = c.execute('''SELECT max(l.received_at) received FROM ops_document_lines l
                       JOIN ops_documents d ON d.id=l.document_id
                       WHERE l.parcel_id=? AND l.received_at IS NOT NULL AND d.destination_hub_id=?''',
                    (pid, hub_id)).fetchone()
    if row and row['received']:
        stamps.append(row['received'])
    try:
        row = c.execute('SELECT max(received_at) received FROM driver_receipts WHERE parcel_id=? AND hub_id=?',
                        (pid, hub_id)).fetchone()
        if row and row['received']:
            stamps.append(row['received'])
    except Exception:
        pass
    row = c.execute('SELECT created_at,status_updated_at FROM parcels WHERE id=?', (pid,)).fetchone()
    if row:
        stamps.append(row['status_updated_at'] or row['created_at'])
    valid = [x for x in stamps if x]
    return max(valid) if valid else None


def handovers(c, pid, hub_id):
    """Passages de livreur sur ce colis depuis ce Hub (remises + tentatives)."""
    counts = []
    for sql, args in (('SELECT count(*) FROM ops_assignments WHERE parcel_id=? AND hub_id=?', (pid, hub_id)),
                      ('SELECT count(*) FROM ops_attempts WHERE parcel_id=? AND operational_hub_id=?', (pid, hub_id))):
        try:
            counts.append(int(c.execute(sql, args).fetchone()[0] or 0))
        except Exception:
            counts.append(0)
    return max(counts) if counts else 0


def decide_policy(c, p, hub_id, now, week_days=None):
    """Règle unique d'un colis pour un retour : accept | confirm | blocked | double.

    Utilisée par ce module (scan de palette retour) et par le scan de palette vers le
    Hub Central, pour une seule et même politique.
    """
    status = str(p.get('status') or '')
    is_exchange = bool(p.get('exchange_of_id')) or str(p.get('tracking') or '').upper().startswith(EXCHANGE_PREFIX)
    required = week_days if week_days is not None else week_days_of(c)
    details = {'status': status, 'is_exchange': is_exchange, 'hub_id': hub_id, 'required_days': required}
    if is_exchange or status in DIRECT_STATUSES:
        return {'code': 'accept', 'status': status, 'requires_confirmation': False, 'details': details,
                'message': 'Colis %s : ajouté directement au retour, sans confirmation.' % (
                    'échange' if is_exchange else status.lower())}
    if status in CLOSED_STATUSES:
        return {'code': 'double', 'status': status, 'requires_confirmation': False, 'details': details,
                'message': 'Colis déjà Livré : double scan accepté, aucun blocage.'}
    today = _day(now() if callable(now) else now) or datetime.date.today()
    appointment = _day(p.get('next_attempt_at'))
    if status in APPOINTMENT_STATUSES and appointment and appointment > today:
        details.update(appointment=appointment.isoformat(), appointment_future=True)
        return {'code': 'confirm', 'status': status, 'requires_confirmation': True, 'details': details,
                'message': 'Colis %s au %s : OUI pour l’envoyer en retour, NON pour le laisser à l’agence.' % (
                    status.lower(), appointment.strftime('%d/%m/%Y'))}
    arrived = arrived_at_hub(c, p['id'], hub_id)
    days = (today - _day(arrived)).days if _day(arrived) else 0
    passes = handovers(c, p['id'], hub_id)
    details.update(days_at_hub=days, arrived_at=arrived, handovers=passes,
                   appointment=appointment.isoformat() if appointment else None)
    if days >= required and passes >= MIN_HANDOVERS:
        return {'code': 'accept', 'status': status, 'requires_confirmation': False, 'details': details,
                'message': 'Colis %s : %d jours au Hub et %d passages de livreur — retour autorisé.' % (
                    status.lower(), days, passes)}
    reasons = []
    if days < required:
        reasons.append('seulement %d jour(s) au Hub sur les %d exigés' % (max(days, 0), required))
    if passes < MIN_HANDOVERS:
        reasons.append('les livreurs ne sont passés que %d fois (%d exigées)' % (passes, MIN_HANDOVERS))
    extra = (' Rendez-vous : %s.' % appointment.isoformat()) if appointment else ''
    return {'code': 'blocked', 'status': status, 'requires_confirmation': True, 'details': details,
            'message': 'Statut « %s » : %s.%s OUI pour l’envoyer en retour, NON pour le laisser à l’agence.' % (
                status, ' et '.join(reasons), extra)}


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
            if u['role'] == 'agent':
                raise Error('Hub introuvable.', 404)
            raise Error('Hub de départ invalide.')
        h = c.execute('SELECT h.*,ci.name city FROM ops_hubs h JOIN cities ci ON ci.id=h.city_id WHERE h.id=? AND h.active=1', (hid,)).fetchone()
        if not h:
            if u['role'] == 'agent':
                raise Error('Hub introuvable.', 404)
            raise Error('Choisissez un hub de départ actif.', 409)
        if u['role'] == 'agent' and u['agent_hub_id'] != h['id']:
            raise Error('Hub introuvable.', 404)
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

    def verdict_for(c, p, cid, u, hub_id):
        """Décide quoi faire du code sans révéler les colis d'un autre hub."""
        if p is None:
            return 'not_found', 'Code inconnu : aucun colis avec ce tracking.', None
        if p['current_hub_id']!=hub_id:
            return 'other_hub', 'Colis non réceptionné physiquement dans le Hub choisi.', None
        info = dict(p)
        age = c.execute("SELECT CAST(julianday('now','localtime')-julianday(?) AS INTEGER) d", (p['created_at'],)).fetchone()['d']
        info['days'] = int(age or 0)
        if p['client_id'] != cid:
            other = c.execute('SELECT name,company FROM users WHERE id=?', (p['client_id'],)).fetchone()
            info['client_name'] = (other['company'] or other['name']) if other else ''
            return 'other_client', 'Ce colis appartient à <b>%s</b> — pas au vendeur choisi.' % (info['client_name'] or 'un autre vendeur'), info
        busy = reserved_by(c, p['id'])
        if busy:
            info['reserved_in'] = busy['reference']
            return 'reserved', 'Colis <b>%s</b> déjà réservé dans <b>%s</b>.' % (p['tracking'], busy['reference']), info
        # Politique commune : départ direct / double / confirmation OUI-NON.
        decision = decide_policy(c, dict(p), hub_id, now, week_days=week_days(c))
        info['decision'] = decision
        info.update(decision.get('details') or {})
        if decision['code'] == 'double':
            return 'double', '⚠ Colis <b>%s</b> déjà <b>Livré</b> : double scanné par erreur — il passe quand même.' % p['tracking'], info
        if decision['code'] in ('confirm', 'blocked'):
            return 'needs_confirm', '<b>%s</b> · %s' % (p['tracking'], decision['message']), info
        return 'ok', '✓ <b>%s</b> · %s' % (p['tracking'], decision['message']), info

    def find_tracking(c, code, u, hub_id):
        """Recherche uniquement parmi les colis physiquement présents au Hub choisi."""
        code = str(code or '').strip()
        if not code or len(code) > 160:
            raise Error('Code invalide.')
        p = parcel_by_tracking_at_hub(c, code, hub_id)
        if p:
            return p
        return parcel_by_manifest_at_hub(c, code, hub_id)

    @app.get('/api/return-palettes/scan-lookup')
    @auth('admin', 'agent')
    def return_scan_lookup():
        u = user()
        staff(u)
        with conn() as c:
            cid = clean_client(c, request.args.get('client_id'))['id']
            hub = clean_hub(c, request.args.get('hub_id'), u)
            p = find_tracking(c, request.args.get('tracking'), u, hub['id'])
            verdict, message, info = verdict_for(c, p, cid, u, hub['id'])
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
            decision = (info or {}).get('decision') or {}
            return jsonify(verdict=verdict, message=message, parcel=payload, week_days=week_days(c),
                           decision={'code': decision.get('code'), 'message': decision.get('message'),
                                     'requires_confirmation': bool(decision.get('requires_confirmation')),
                                     'details': decision.get('details') or {}} if decision else None,
                           requires_confirmation=verdict == 'needs_confirm',
                           appointment=(decision.get('details') or {}).get('appointment') if decision else None,
                           days_at_hub=(decision.get('details') or {}).get('days_at_hub') if decision else None,
                           handovers=(decision.get('details') or {}).get('handovers') if decision else None)

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
                verdict, message, info = verdict_for(c, p, cl['id'], u, hub['id'])
                if verdict == 'needs_confirm' and pid not in confirmed:
                    raise Error('Colis %s : confirmez son envoi en retour (OUI) ou laissez-le à l’agence.' % p['tracking'], 409)
                if verdict not in ('ok', 'double', 'needs_confirm'):
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
                                   'week_days': week_days(c), 'confirmed': [i for i in ids if i in confirmed],
                                   'decisions': {str(x['id']): (verdict_for(c, x, cl['id'], u, hub['id'])[2].get('decision') or {}).get('code')
                                                 for x in ps}},
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
                raise Error('Palette retour introuvable.', 404)
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


def assert_allowed(c, p, hub_id, now, confirmed=False, overridden=False):
    """Contrôle serveur avant d'ajouter le colis à la palette de retour."""
    decision = decide_policy(c, p, hub_id, now)
    if decision['code'] in ('accept', 'double'):
        return decision
    if decision['code'] == 'confirm' and confirmed:
        decision['validated'] = 'confirmed_appointment'
        return decision
    if decision['code'] == 'blocked' and overridden:
        decision['validated'] = 'overridden_by_hub'
        return decision
    raise_decision = decision['message']
    raise_decision = raise_decision.replace(' Envoyer quand même en retour ou laisser à l’agence ?', '')
    raise_decision = raise_decision.replace(' : confirmez-vous son envoi en retour ?', ' : confirmation requise.')
    error = _Blocked(raise_decision, getattr(p, 'get', lambda *_: None) and p.get('tracking'))
    raise error


class _Blocked(Exception):
    def __init__(self, message, tracking=None):
        super().__init__(message)
        self.message = message
        self.tracking = tracking
