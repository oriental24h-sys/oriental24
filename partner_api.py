"""API REST pour les sociétés de livraison partenaires.
Authentification par clé (Bearer O24K-…), sans session ni cookie : le jeton CSRF ne
s'applique pas. Chaque clé est révocable par Admin et limitée à sa propre société.
Aucune donnée d'autres clients, aucun accès financier.
"""
import hashlib, json, re, secrets, threading, time
from flask import request, jsonify
from client_types import tracking_for

RATE_LIMIT = 120
_rate = {}
_rate_lock = threading.Lock()


def register_partner_api(app, s):
    conn, auth, user, now, Error = (s[k] for k in ['conn', 'auth', 'user', 'now', 'APIError'])
    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS partner_api_keys(
            id INTEGER PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES users(id),
            label TEXT NOT NULL,
            key_hash TEXT NOT NULL UNIQUE,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            last_used_at TEXT,
            revoked_at TEXT, revoked_by INTEGER REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS partner_api_idem(
            key_id INTEGER NOT NULL REFERENCES partner_api_keys(id),
            idem_key TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(key_id, idem_key));
        ''')

    def check_rate(key_id):
        with _rate_lock:
            window = _rate.setdefault(key_id, [])
            cutoff = time.time() - 60
            while window and window[0] < cutoff:
                window.pop(0)
            if len(window) >= RATE_LIMIT:
                return False
            window.append(time.time())
            return True

    def company_from_token():
        header = request.headers.get('Authorization', '')
        m = re.fullmatch(r'Bearer (O24K-[0-9a-f]{32})', header)
        if not m:
            raise Error('Clé API absente ou mal formée : utilisez « Authorization: Bearer O24K-… ».', 401)
        digest = hashlib.sha256(m.group(1).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            k = c.execute('''SELECT k.*,u.active uactive,u.client_type,u.name uname,u.company ucompany
                FROM partner_api_keys k JOIN users u ON u.id=k.client_id WHERE k.key_hash=?''', (digest,)).fetchone()
            if not k or k['revoked_at'] or not k['uactive']:
                raise Error('Clé API inconnue ou révoquée.', 401)
            if k['client_type'] != 'societe_livraison' or not check_rate(k['id']):
                raise Error('Accès API indisponible pour cette clé.', 403)
            c.execute('UPDATE partner_api_keys SET last_used_at=? WHERE id=?', (now(), k['id']))
            return dict(k)

    # ---------- Gestion des clés (session Admin) ----------

    @app.route('/api/partner-api-keys', methods=['GET', 'POST'])
    @auth('admin')
    def api_keys():
        u = user()
        with conn() as c:
            if request.method == 'GET':
                rows = c.execute('''SELECT k.id,k.client_id,k.label,k.created_at,k.last_used_at,k.revoked_at,
                    u.name client,u.company,u.client_type,creator.name creator
                    FROM partner_api_keys k JOIN users u ON u.id=k.client_id JOIN users creator ON creator.id=k.created_by
                    ORDER BY k.id DESC''').fetchall()
                return jsonify(rows=[dict(r) for r in rows])
            c.execute('BEGIN IMMEDIATE')
            d = request.get_json(silent=True)
            if not isinstance(d, dict) or not set(d) <= {'client_id', 'label'}:
                raise Error('Société et libellé requis.')
            cid = d.get('client_id')
            label = d.get('label', '')
            if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80:
                raise Error('Libellé obligatoire (80 caractères maximum).')
            cl = c.execute("SELECT * FROM users WHERE id=? AND role='client' AND client_type='societe_livraison' AND active=1", (cid,)).fetchone()
            if not cl:
                raise Error('Choisissez une société de livraison active.', 404)
            if c.execute('SELECT 1 FROM partner_api_keys WHERE client_id=? AND revoked_at IS NULL', (cid,)).fetchone():
                raise Error('Cette société possède déjà une clé active : révoquez-la avant d’en créer une nouvelle.', 409)
            plain = 'O24K-' + secrets.token_hex(16)
            kid = c.execute('INSERT INTO partner_api_keys(client_id,label,key_hash,created_by,created_at) VALUES(?,?,?,?,?)',
                            (cid, label.strip(), hashlib.sha256(plain.encode()).hexdigest(), u['id'], now())).lastrowid
            # La clé complète n'est jamais stockée en clair : elle ne sera affichée qu'une fois.
            return jsonify(ok=True, id=kid, key=plain, company=cl['company'] or cl['name'])

    @app.post('/api/partner-api-keys/<int:kid>/revoke')
    @auth('admin')
    def api_key_revoke(kid):
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            k = c.execute('SELECT * FROM partner_api_keys WHERE id=?', (kid,)).fetchone()
            if not k:
                raise Error('Clé introuvable.', 404)
            if k['revoked_at']:
                return jsonify(ok=True, changed=False)
            c.execute('UPDATE partner_api_keys SET revoked_at=?,revoked_by=? WHERE id=?', (now(), u['id'], kid))
            return jsonify(ok=True, changed=True)

    # ---------- Endpoints société ----------

    def text(d, k, required=True, maxlen=300):
        v = d.get(k, '')
        if v is None:
            v = ''
        if not isinstance(v, str):
            raise Error('Champ invalide : ' + k)
        v = v.strip()
        if required and not v:
            raise Error('Champ obligatoire : ' + k)
        if len(v) > maxlen:
            raise Error('Champ trop long : ' + k)
        return v

    def amount(d):
        try:
            v = float(d.get('amount', ''))
            if not 0 <= v <= 1000000:
                raise ValueError()
            return round(v, 2)
        except (ValueError, TypeError, OverflowError):
            raise Error('Montant COD invalide : nombre entre 0 et 1 000 000 MAD.')

    def parcel_json(p, city, with_events=None):
        out = dict(tracking=p['tracking'], status=p['status'], recipient=p['recipient'], city=city,
                   amount=p['amount'], fee=p['fee'], return_fee=p['return_fee'],
                   created_at=p['created_at'], updated_at=p['updated_at'])
        if with_events is not None:
            out['events'] = with_events
        return out

    @app.get('/api/partner/v1/cities')
    def partner_cities():
        k = company_from_token()
        with conn() as c:
            rows = []
            for ci in c.execute('SELECT * FROM cities WHERE delivery=1 ORDER BY name'):
                row = dict(ci)
                row['fee'], row['return_fee'] = s['tariff_fees_for'](c, k['client_id'], row)
                rows.append(row)
            return jsonify(cities=rows)

    @app.post('/api/partner/v1/parcels')
    def partner_parcel_create():
        k = company_from_token()
        idem = request.headers.get('Idempotency-Key', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', idem):
            raise Error('En-tête Idempotency-Key obligatoire (20 à 80 caractères [A-Za-z0-9_-]).')
        d = request.get_json(silent=True)
        if not isinstance(d, dict):
            raise Error('Objet JSON requis.')
        payload = dict(tracking=d.get('tracking'), recipient=d.get('recipient'), phone=d.get('phone'),
                       address=d.get('address'), city=d.get('city'), amount=d.get('amount'),
                       product=d.get('product'), note=d.get('note'))
        fp = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT fingerprint,result FROM partner_api_idem WHERE key_id=? AND idem_key=?', (k['id'], idem)).fetchone()
            if prior:
                if prior['fingerprint'] != fp:
                    raise Error('Cette Idempotency-Key a déjà servi pour un autre colis.', 409)
                return jsonify(**json.loads(prior['result']), replayed=True), 201
            tracking = tracking_for(c, k['client_id'], payload['tracking'], Error)
            phone = text(payload, 'phone')
            if not re.fullmatch(r'\+?[\d\s-]{9,18}', phone):
                raise Error('Numéro de téléphone invalide.')
            city_name = text(payload, 'city', True, 120)
            city = c.execute('SELECT * FROM cities WHERE name=? COLLATE NOCASE AND delivery=1', (city_name,)).fetchone()
            if not city:
                raise Error('Ville inconnue ou fermée à la livraison. Consultez GET /api/partner/v1/cities.', 404)
            city = dict(city)
            fee, ret = s['tariff_fees_for'](c, k['client_id'], city)
            t = now()
            pid = c.execute('INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,product,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (tracking, k['client_id'], text(payload, 'recipient'), phone, text(payload, 'address'), city['id'],
                             amount(payload), fee, ret, text(payload, 'product', False), text(payload, 'note', False), t, t)).lastrowid
            s['event'](c, pid, 'Créé', 'Colis créé via API partenaire · clé «' + k['label'] + '»', {'id': k['client_id']})
            result = dict(ok=True, id=pid, tracking=tracking, status='Créé', fee=fee, return_fee=ret, city=city['name'])
            c.execute('INSERT INTO partner_api_idem(key_id,idem_key,fingerprint,result,created_at) VALUES(?,?,?,?,?)',
                      (k['id'], idem, fp, json.dumps(result), t))
            return jsonify(result), 201

    @app.get('/api/partner/v1/parcels/<tracking>')
    def partner_parcel_get(tracking):
        k = company_from_token()
        with conn() as c:
            p = c.execute('SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE p.tracking=? COLLATE NOCASE AND p.client_id=?', (tracking, k['client_id'])).fetchone()
            if not p:
                raise Error('Colis introuvable pour votre société.', 404)
            ev = [ {k2: r[k2] for k2 in ['status', 'note', 'created_at']} | {'actor': r['actor']}
                   for r in c.execute('SELECT e.status,e.note,e.created_at,u.name actor FROM events e JOIN users u ON u.id=e.actor_id WHERE e.parcel_id=? ORDER BY e.id DESC LIMIT 50', (p['id'],))]
            return jsonify(parcel_json(dict(p), p['city'], ev))

    @app.get('/api/partner/v1/parcels')
    def partner_parcel_list():
        k = company_from_token()
        since = request.args.get('updated_since', '')
        if since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}[T ][0-9:.+-]{5,11}', since):
            raise Error('updated_since invalide : utilisez ISO 8601, ex. 2026-09-20T21:00:00.')
        try:
            page = int(request.args.get('page', 1))
            size = int(request.args.get('size', 50))
            if page < 1 or size not in (50, 100):
                raise ValueError()
        except (ValueError, TypeError):
            raise Error('Pagination invalide : page ≥ 1, size 50 ou 100.')
        with conn() as c:
            where = 'p.client_id=?'
            args = [k['client_id']]
            if since:
                where += ' AND p.updated_at>?'
                args.append(since.replace(' ', 'T'))
            total = c.execute('SELECT count(*) FROM parcels p WHERE ' + where, args).fetchone()[0]
            page = min(page, max(1, (total + size - 1) // size))
            rows = [parcel_json(dict(r), r['city']) for r in c.execute(
                'SELECT p.*,ci.name city FROM parcels p JOIN cities ci ON ci.id=p.city_id WHERE ' + where +
                ' ORDER BY p.updated_at DESC,p.id DESC LIMIT ? OFFSET ?', args + [size, (page - 1) * size])]
            return jsonify(rows=rows, total=total, page=page, size=size), 200, {'Cache-Control': 'private, no-store'}
