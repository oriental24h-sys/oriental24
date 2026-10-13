"""Ramassage live map: saved pickup contacts, geofenced driver assignment and history.

This extends the existing Tour de contrôle and driver_positions tables.  No synthetic GPS
positions are created.  The browser polls the existing WSGI app; no new server/runtime is
required for Railway.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from flask import jsonify, request

from tour_control import GEO, haversine

ONLINE_SECONDS = 90
POSITION_RETENTION_DAYS = 30
DEFAULT_ZONE_RADIUS_KM = 20.0
OPEN_JOB_STATES = ('assigned', 'en_route')
JOB_STATES = ('pending', 'assigned', 'en_route', 'picked_up', 'cancelled')
_GOOGLE_HOSTS = {'google.com', 'maps.google.com', 'maps.app.goo.gl', 'goo.gl'}


def _city_key(value):
    """Accent/case-insensitive city key for matching DB labels to known centroids."""
    text = unicodedata.normalize('NFKD', str(value or '')).casefold()
    return ''.join(ch for ch in text if not unicodedata.combining(ch) and ch.isalnum())


_GEO_BY_CITY_KEY = {_city_key(name): coords for name, coords in GEO.items()}
_GEO_BY_CITY_KEY.update({
    _city_key('Oujda-Angad'): GEO['Oujda'],
    _city_key('Oujda Angad'): GEO['Oujda'],
    _city_key('وجدة'): GEO['Oujda'],
    _city_key('بركان'): GEO['Berkane'],
    _city_key('Barkane'): GEO['Berkane'],
})


def _city_centroid(name):
    return _GEO_BY_CITY_KEY.get(_city_key(name))


def _valid_google_url(value, *, short_only=False):
    """Validate a Google Maps URL before following it (prevents arbitrary URL fetching)."""
    value = str(value or '').strip()
    if not value or len(value) > 2048:
        raise ValueError('Collez un lien Google Maps valide (2 048 caractères maximum).')
    if not re.match(r'^https?://', value, re.I):
        value = 'https://' + value
    try:
        p = urllib.parse.urlsplit(value)
        host = (p.hostname or '').lower().rstrip('.')
        port = p.port
    except ValueError:
        raise ValueError('Lien Google Maps invalide.')
    allowed = host in _GOOGLE_HOSTS or host.endswith('.google.com')
    if not allowed or p.scheme.lower() != 'https' or p.username or p.password or port not in (None, 443):
        raise ValueError('Seuls les liens Google Maps HTTPS sont acceptés.')
    if short_only and host not in {'maps.app.goo.gl', 'goo.gl'}:
        raise ValueError('Lien court Google Maps invalide.')
    return urllib.parse.urlunsplit(('https', p.netloc, p.path, p.query, p.fragment))


class _GoogleRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, limit=5):
        super().__init__()
        self.limit = limit
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > self.limit:
            raise urllib.error.HTTPError(req.full_url, code, 'Too many redirects', headers, fp)
        try:
            safe = _valid_google_url(urllib.parse.urljoin(req.full_url, newurl))
        except ValueError as exc:
            raise urllib.error.HTTPError(req.full_url, code, str(exc), headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, safe)


def _expand_google_url(value):
    url = _valid_google_url(value)
    host = urllib.parse.urlsplit(url).hostname.lower()
    if host not in {'maps.app.goo.gl', 'goo.gl'}:
        return url
    opener = urllib.request.build_opener(_GoogleRedirects())
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (compatible; Oriental24Ramassage/1.0)',
        'Accept': 'text/html,application/xhtml+xml',
    })
    try:
        with opener.open(req, timeout=5) as response:
            final_url = response.geturl()
    except Exception as exc:
        raise ValueError('Impossible de développer ce lien court. Vérifiez le lien puis réessayez.') from exc
    return _valid_google_url(final_url)


def _coordinate_candidates(value):
    text = urllib.parse.unquote(str(value or ''))
    # Google Maps data strings use !3dLAT!4dLNG, while some links use !2dLNG!3dLAT.
    for pattern, swap in ((r'!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)', False),
                          (r'!2d(-?\d+(?:\.\d+)?)!3d(-?\d+(?:\.\d+)?)', True)):
        for m in re.finditer(pattern, text, re.I):
            a, b = map(float, m.groups())
            yield (b, a) if swap else (a, b)
    # The viewport location is the most common long-link format.
    for m in re.finditer(r'@\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)', text):
        yield float(m.group(1)), float(m.group(2))
    # Search/query links and coordinates copied directly into a Maps URL.
    for m in re.finditer(r'(?<![\d.])(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})(?![\d.])', text):
        yield float(m.group(1)), float(m.group(2))


def _extract_google_coordinates(url):
    for lat, lng in _coordinate_candidates(url):
        if -90 <= lat <= 90 and -180 <= lng <= 180:
            return round(lat, 6), round(lng, 6)
    raise ValueError('Aucune coordonnée lisible dans ce lien. Envoyez un lien Google Maps avec une épingle précise.')


def _age_seconds(value):
    try:
        text = str(value or '').replace('Z', '+00:00')
        dt = datetime.fromisoformat(text)
        current = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        return max(0.0, (current - dt).total_seconds())
    except Exception:
        return 10**9


def _row_dict(row):
    return dict(row) if row is not None else None


def register_ramassage_tower(app, s):
    conn, auth, user, now, Error = s['conn'], s['auth'], s['user'], s['now'], s['APIError']

    def ensure_default_zones(c):
        """Seed missing circular geofences for every pickup-enabled city with a known centroid.

        Run this on requests as well as startup: an administrator can enable pickup for a
        city after the process has started, so startup-only seeding leaves the dropdown empty.
        Existing configured zones (including their radius and active flag) are never overwritten.
        """
        stamp = now()
        for city in c.execute('SELECT id,name FROM cities WHERE pickup=1').fetchall():
            center = _city_centroid(city['name'])
            if center:
                c.execute('''INSERT OR IGNORE INTO ramassage_zones
                             (city_id,center_lat,center_lng,radius_km,active,updated_at)
                             VALUES(?,?,?,?,1,?)''',
                          (city['id'], center[0], center[1], DEFAULT_ZONE_RADIUS_KM, stamp))

    with conn() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS ramassage_zones(
          city_id INTEGER PRIMARY KEY REFERENCES cities(id) ON DELETE CASCADE,
          center_lat REAL NOT NULL, center_lng REAL NOT NULL,
          radius_km REAL NOT NULL DEFAULT 20, active INTEGER NOT NULL DEFAULT 1,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ramassage_clients(
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL,
          lat REAL NOT NULL, lng REAL NOT NULL, maps_url TEXT NOT NULL,
          city_id INTEGER NOT NULL REFERENCES cities(id),
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ramassage_clients_name_idx ON ramassage_clients(name COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS ramassage_clients_phone_idx ON ramassage_clients(phone);
        CREATE TABLE IF NOT EXISTS ramassage_jobs(
          id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES ramassage_clients(id),
          city_id INTEGER NOT NULL REFERENCES cities(id),
          parcels_count INTEGER NOT NULL DEFAULT 1 CHECK(parcels_count BETWEEN 1 AND 10000),
          status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','assigned','en_route','picked_up','cancelled')),
          driver_id INTEGER REFERENCES users(id), created_by INTEGER REFERENCES users(id),
          created_at TEXT NOT NULL, assigned_at TEXT, picked_up_at TEXT, updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ramassage_jobs_status_idx ON ramassage_jobs(status,created_at DESC);
        CREATE INDEX IF NOT EXISTS ramassage_jobs_driver_idx ON ramassage_jobs(driver_id,status,updated_at DESC);
        CREATE TABLE IF NOT EXISTS ramassage_driver_state(
          driver_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          availability TEXT NOT NULL DEFAULT 'available' CHECK(availability IN ('available','rest')),
          full_load INTEGER NOT NULL DEFAULT 0 CHECK(full_load IN (0,1)),
          gps_enabled INTEGER NOT NULL DEFAULT 0 CHECK(gps_enabled IN (0,1)),
          battery_pct REAL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ramassage_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ops_notifications(
          id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),
          parcel_id INTEGER REFERENCES parcels(id),title TEXT NOT NULL,body TEXT NOT NULL,
          created_at TEXT NOT NULL,read_at TEXT
        );
        CREATE INDEX IF NOT EXISTS ramassage_notice_user_idx ON ops_notifications(user_id,id);
        ''')
        # The hub table predates the map; keep its existing records and add optional precise pins.
        if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ops_hubs'").fetchone():
            hubcols = {r['name'] for r in c.execute('PRAGMA table_info(ops_hubs)')}
            if 'lat' not in hubcols:
                c.execute('ALTER TABLE ops_hubs ADD COLUMN lat REAL')
            if 'lng' not in hubcols:
                c.execute('ALTER TABLE ops_hubs ADD COLUMN lng REAL')
        # Seed known pickup-city geofences on startup; ensure_default_zones also handles
        # cities switched on later, without changing an existing admin-configured zone.
        ensure_default_zones(c)
        c.execute("INSERT OR IGNORE INTO ramassage_settings(key,value) VALUES('auto_dispatch','0')")

    def zone_for_point(c, lat, lng):
        ensure_default_zones(c)
        hits = []
        for z in c.execute('''SELECT z.city_id,z.center_lat,z.center_lng,z.radius_km,ci.name
                              FROM ramassage_zones z JOIN cities ci ON ci.id=z.city_id
                              WHERE z.active=1 AND ci.pickup=1'''):
            distance = haversine((lat, lng), (z['center_lat'], z['center_lng']))
            if distance <= float(z['radius_km']):
                hits.append((distance, dict(z)))
        return min(hits, key=lambda x: (x[0], x[1]['city_id']))[1] if hits else None

    def zone_by_id(c, city_id):
        if city_id in (None, ''):
            return None
        ensure_default_zones(c)
        return c.execute('''SELECT z.city_id,z.center_lat,z.center_lng,z.radius_km,ci.name
                            FROM ramassage_zones z JOIN cities ci ON ci.id=z.city_id
                            WHERE z.city_id=? AND z.active=1 AND ci.pickup=1''', (int(city_id),)).fetchone()

    def map_driver_rows(c):
        result = []
        base = c.execute("SELECT id,name,phone,driver_city_id FROM users WHERE role='livreur' AND active=1 ORDER BY name").fetchall()
        for d in base:
            p = c.execute('SELECT lat,lng,city_id,created_at FROM driver_positions WHERE driver_id=? ORDER BY id DESC LIMIT 1', (d['id'],)).fetchone()
            state = c.execute('SELECT availability,full_load,gps_enabled,battery_pct,updated_at FROM ramassage_driver_state WHERE driver_id=?', (d['id'],)).fetchone()
            vehicle = c.execute('SELECT id,label,type,plate,battery_pct,state FROM vehicles WHERE driver_id=? AND active=1 ORDER BY id DESC LIMIT 1', (d['id'],)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vehicles'").fetchone() else None
            open_jobs = c.execute("SELECT COUNT(*) FROM ramassage_jobs WHERE driver_id=? AND status IN ('assigned','en_route')", (d['id'],)).fetchone()[0]
            age = _age_seconds(p['created_at']) if p else None
            if age is not None and age > 12 * 3600:
                p, age = None, None
            online = bool(p and age is not None and age <= ONLINE_SECONDS)
            gps_state = 'unknown' if state is None else ('enabled' if state['gps_enabled'] else 'disabled')
            availability = state['availability'] if state else 'available'
            full_load = bool(state['full_load']) if state else False
            vehicle_ok = bool(vehicle and vehicle['state'] not in ('maintenance', 'garage'))
            if not online:
                status = 'offline'
            elif gps_state == 'disabled':
                status = 'gps_off'
            elif availability == 'rest':
                status = 'rest'
            elif open_jobs or (vehicle and vehicle['state'] == 'en_tournee'):
                status = 'busy'
            elif full_load:
                status = 'full'
            else:
                status = 'available'
            zone = zone_for_point(c, p['lat'], p['lng']) if p else None
            result.append({
                'id': d['id'], 'name': d['name'], 'phone': d['phone'] or '',
                'pos': ({'lat': p['lat'], 'lng': p['lng'], 'created_at': p['created_at'],
                         'ago_sec': int(age or 0), 'ago_min': int((age or 0) / 60)} if p else None),
                'online': online, 'gps_state': gps_state, 'battery_pct': state['battery_pct'] if state else None,
                'availability': availability, 'full_load': full_load, 'status': status,
                'zone_id': zone['city_id'] if zone else None, 'zone': zone['name'] if zone else '',
                'zone_distance_km': round(haversine((p['lat'], p['lng']), (zone['center_lat'], zone['center_lng'])), 2) if p and zone else None,
                'vehicle': ({'id': vehicle['id'], 'label': vehicle['label'], 'type': vehicle['type'],
                             'plate': vehicle['plate'] or '', 'battery_pct': vehicle['battery_pct'],
                             'state': vehicle['state']} if vehicle else None),
                'vehicle_ok': vehicle_ok, 'active_jobs': int(open_jobs),
            })
        return result

    def eligible_candidates(c, city_id, client_lat, client_lng):
        drivers = map_driver_rows(c)
        eligible = []
        for d in drivers:
            if (not d['online'] or d['gps_state'] != 'enabled' or d['status'] != 'available'
                    or d['full_load'] or not d['vehicle_ok'] or not d['vehicle']
                    or d['zone_id'] != int(city_id)):
                continue
            distance = haversine((d['pos']['lat'], d['pos']['lng']), (client_lat, client_lng))
            speed = {'velo': 15, 'drone': 45, 'camion': 28}.get(d['vehicle']['type'], 32)
            eta = max(3, round(distance / max(1, speed) * 60 + 4))
            eligible.append({**d, 'distance_km': distance, 'eta_min': eta})
        return sorted(eligible, key=lambda x: (x['distance_km'], x['id']))

    def _notify_driver(c, driver_id, job_id, client, distance_km, eta_min):
        title = 'Nouveau ramassage à effectuer'
        body = (f"Ramassage #{job_id} · {client['name']} · {client['phone']} · "
                f"{distance_km:.1f} km · ETA ~{eta_min} min")
        c.execute('INSERT INTO ops_notifications(user_id,parcel_id,title,body,created_at) VALUES(?,NULL,?,?,?)',
                  (driver_id, title, body, now()))

    def assign_job(c, job_id, driver_id):
        job = c.execute('''SELECT j.*,rc.name client_name,rc.phone client_phone,rc.lat,rc.lng,rc.maps_url,rc.city_id client_city_id
                           FROM ramassage_jobs j JOIN ramassage_clients rc ON rc.id=j.client_id WHERE j.id=?''', (job_id,)).fetchone()
        if not job:
            raise Error('Demande de ramassage introuvable.', 404)
        if job['status'] not in ('pending', 'assigned'):
            raise Error('Cette demande ne peut plus être affectée.', 409)
        if job['status'] == 'assigned' and job['driver_id'] == driver_id:
            return {'already_assigned': True, 'driver_id': driver_id}
        if job['status'] == 'assigned' and job['driver_id'] != driver_id:
            raise Error('Cette demande est déjà affectée à un autre livreur.', 409)
        candidates = eligible_candidates(c, job['city_id'], job['lat'], job['lng'])
        target = next((x for x in candidates if x['id'] == int(driver_id)), None)
        if not target:
            raise Error('Livreur non éligible : vérifiez GPS actif, disponibilité, véhicule, charge et zone.', 409)
        stamp = now()
        c.execute("UPDATE ramassage_jobs SET driver_id=?,status='assigned',assigned_at=?,updated_at=? WHERE id=? AND status='pending'",
                  (driver_id, stamp, stamp, job_id))
        _notify_driver(c, driver_id, job_id,
                       {'name': job['client_name'], 'phone': job['client_phone']},
                       target['distance_km'], target['eta_min'])
        return {'already_assigned': False, 'driver_id': driver_id,
                'driver': target['name'], 'distance_km': target['distance_km'], 'eta_min': target['eta_min']}

    def tower_payload():
        with conn() as c:
            ensure_default_zones(c)
            zones = [dict(r) for r in c.execute('''SELECT z.city_id,ci.name city,z.center_lat,z.center_lng,z.radius_km,z.active
                  FROM ramassage_zones z JOIN cities ci ON ci.id=z.city_id WHERE ci.pickup=1 ORDER BY ci.name''')]
            cities = [dict(r) for r in c.execute('''SELECT id,name FROM cities WHERE pickup=1 ORDER BY name''')]
            for city in cities:
                zone = next((z for z in zones if z['city_id'] == city['id']), None)
                city['zone_ready'] = bool(zone and zone['active'])
                city['zone_center_lat'] = zone['center_lat'] if zone else None
                city['zone_center_lng'] = zone['center_lng'] if zone else None
                city['zone_radius_km'] = zone['radius_km'] if zone else None
            clients = []
            for r in c.execute('''SELECT rc.*,ci.name zone FROM ramassage_clients rc LEFT JOIN cities ci ON ci.id=rc.city_id
                                  ORDER BY rc.updated_at DESC,rc.id DESC LIMIT 300'''):
                clients.append(dict(r))
            jobs = []
            for r in c.execute('''SELECT j.id,j.client_id,j.city_id,j.parcels_count,j.status,j.driver_id,j.created_at,j.assigned_at,j.picked_up_at,j.updated_at,
                                         rc.name client_name,rc.phone,rc.lat,rc.lng,rc.maps_url,ci.name zone,d.name driver_name
                                  FROM ramassage_jobs j JOIN ramassage_clients rc ON rc.id=j.client_id
                                  LEFT JOIN cities ci ON ci.id=j.city_id LEFT JOIN users d ON d.id=j.driver_id
                                  ORDER BY CASE WHEN j.status IN ('pending','assigned','en_route') THEN 0 ELSE 1 END,j.created_at DESC,j.id DESC LIMIT 100'''):
                row = dict(r)
                row['client'] = {'id': row.pop('client_id'), 'name': row.pop('client_name'),
                                 'phone': row.pop('phone'), 'lat': row.pop('lat'), 'lng': row.pop('lng'),
                                 'maps_url': row.pop('maps_url')}
                jobs.append(row)
            hubs = []
            for r in c.execute('''SELECT h.id,h.name,h.city_id,h.address,h.active,h.lat,h.lng,ci.name city
                                  FROM ops_hubs h LEFT JOIN cities ci ON ci.id=h.city_id WHERE h.active=1 ORDER BY h.name'''):
                row = dict(r)
                exact = row['lat'] is not None and row['lng'] is not None
                if not exact:
                    z = zone_by_id(c, row['city_id'])
                    if z:
                        row['lat'], row['lng'] = z['center_lat'], z['center_lng']
                row['exact_location'] = exact
                hubs.append(row)
            setting = c.execute("SELECT value FROM ramassage_settings WHERE key='auto_dispatch'").fetchone()
            auto_dispatch = bool(setting and setting['value'] == '1')
            drivers = map_driver_rows(c)
            gps_alerts = [d for d in drivers if d['gps_state'] == 'disabled' and d['pos'] and d['pos']['ago_sec'] <= 3600]
        return {'map_drivers': drivers, 'ramassage_clients': clients, 'ramassage_jobs': jobs,
                'hubs': hubs, 'zones': zones, 'pickup_cities': cities,
                'auto_dispatch': auto_dispatch, 'gps_alerts': gps_alerts,
                'map_refresh_seconds': 8}

    app.o24_ramassage_tower_payload = tower_payload

    @app.get('/api/control-tower/map-data')
    @auth('admin')
    def ramassage_map_data():
        return jsonify(**tower_payload())

    @app.patch('/api/control-tower/settings')
    @auth('admin')
    def ramassage_settings():
        d = request.get_json(silent=True) or {}
        if 'auto_dispatch' not in d:
            raise Error('Choisissez une valeur pour le mode de répartition automatique.')
        enabled = bool(d.get('auto_dispatch'))
        with conn() as c:
            c.execute('INSERT INTO ramassage_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                      ('auto_dispatch', '1' if enabled else '0'))
        return jsonify(ok=True, auto_dispatch=enabled)

    @app.patch('/api/control-tower/zones/<int:city_id>')
    @auth('admin')
    def ramassage_zone_update(city_id):
        d = request.get_json(silent=True) or {}
        try:
            lat, lng = float(d.get('center_lat')), float(d.get('center_lng'))
            radius = float(d.get('radius_km', DEFAULT_ZONE_RADIUS_KM))
        except (TypeError, ValueError):
            raise Error('Coordonnées et rayon de zone invalides.')
        if not (-90 <= lat <= 90 and -180 <= lng <= 180 and 1 <= radius <= 100):
            raise Error('Rayon entre 1 et 100 km et coordonnées GPS valides requis.')
        with conn() as c:
            city = c.execute('SELECT id FROM cities WHERE id=? AND pickup=1', (city_id,)).fetchone()
            if not city:
                raise Error('Ville de ramassage introuvable.', 404)
            c.execute('''INSERT INTO ramassage_zones(city_id,center_lat,center_lng,radius_km,active,updated_at)
                         VALUES(?,?,?,?,1,?) ON CONFLICT(city_id) DO UPDATE SET center_lat=excluded.center_lat,
                         center_lng=excluded.center_lng,radius_km=excluded.radius_km,active=1,updated_at=excluded.updated_at''',
                      (city_id, lat, lng, radius, now()))
        return jsonify(ok=True)

    @app.patch('/api/control-tower/hubs/<int:hub_id>/location')
    @auth('admin')
    def ramassage_hub_location(hub_id):
        d = request.get_json(silent=True) or {}
        try:
            lat, lng = float(d.get('lat')), float(d.get('lng'))
        except (TypeError, ValueError):
            raise Error('Coordonnées GPS du hub invalides.')
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise Error('Coordonnées GPS du hub hors limites.')
        with conn() as c:
            cur = c.execute('UPDATE ops_hubs SET lat=?,lng=? WHERE id=? AND active=1', (lat, lng, hub_id))
            if cur.rowcount != 1:
                raise Error('Hub actif introuvable.', 404)
        return jsonify(ok=True, lat=lat, lng=lng)

    @app.post('/api/control-tower/ramassage')
    @auth('admin')
    def ramassage_create():
        d = request.get_json(silent=True) or {}
        name = str(d.get('name') or '').strip()[:100]
        phone_raw = str(d.get('phone') or '').strip()[:32]
        phone = re.sub(r'[^0-9+]', '', phone_raw)
        if not name:
            raise Error('Le nom du client est obligatoire.')
        if len(re.sub(r'\D', '', phone)) < 8:
            raise Error('Numéro de téléphone invalide.')
        map_input = str(d.get('maps_url') or d.get('map_url') or '').strip()
        try:
            expanded = _expand_google_url(map_input)
            lat, lng = _extract_google_coordinates(expanded)
        except ValueError as exc:
            raise Error(str(exc))
        try:
            requested_city = int(d.get('city_id')) if d.get('city_id') not in (None, '') else None
            parcels_count = int(d.get('parcels_count') or 1)
        except (TypeError, ValueError):
            raise Error('Zone ou nombre de colis invalide.')
        if not 1 <= parcels_count <= 10000:
            raise Error('Le nombre de colis doit être compris entre 1 et 10 000.')
        normalized_url = 'https://www.google.com/maps/search/?api=1&query=' + urllib.parse.quote(f'{lat},{lng}', safe=',-')
        actor = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            zone = zone_by_id(c, requested_city) if requested_city else zone_for_point(c, lat, lng)
            if not zone:
                raise Error('Zone introuvable pour ces coordonnées. Choisissez une ville avec une zone configurée.')
            distance_to_zone = haversine((lat, lng), (zone['center_lat'], zone['center_lng']))
            if distance_to_zone > float(zone['radius_km']):
                raise Error(f"Le point est hors de la zone {zone['name']} ({distance_to_zone:.1f} km du centre, rayon {zone['radius_km']:.0f} km). Ajustez la zone ou choisissez la bonne ville.")
            city = c.execute('SELECT id,name,pickup FROM cities WHERE id=?', (zone['city_id'],)).fetchone()
            if not city or not city['pickup']:
                raise Error('Cette ville n’accepte pas les ramassages.')
            # Reuse the same saved place for repeated requests from the same phone/location.
            client = c.execute('''SELECT id FROM ramassage_clients WHERE phone=? AND city_id=?
                                  AND abs(lat-?)<0.0002 AND abs(lng-?)<0.0002 ORDER BY id DESC LIMIT 1''',
                               (phone, zone['city_id'], lat, lng)).fetchone()
            if client:
                client_id = client['id']
                c.execute('UPDATE ramassage_clients SET name=?,phone=?,lat=?,lng=?,maps_url=?,city_id=?,updated_at=? WHERE id=?',
                          (name, phone, lat, lng, normalized_url, zone['city_id'], now(), client_id))
            else:
                client_id = c.execute('''INSERT INTO ramassage_clients(name,phone,lat,lng,maps_url,city_id,created_at,updated_at)
                                         VALUES(?,?,?,?,?,?,?,?)''',
                                      (name, phone, lat, lng, normalized_url, zone['city_id'], now(), now())).lastrowid
            job_id = c.execute('''INSERT INTO ramassage_jobs(client_id,city_id,parcels_count,status,created_by,created_at,updated_at)
                                  VALUES(?,?,?,'pending',?,?,?)''',
                               (client_id, zone['city_id'], parcels_count, actor['id'], now(), now())).lastrowid
            setting = c.execute("SELECT value FROM ramassage_settings WHERE key='auto_dispatch'").fetchone()
            auto = bool(setting and setting['value'] == '1')
            assignment = None
            if auto:
                choices = eligible_candidates(c, zone['city_id'], lat, lng)
                if choices:
                    assignment = assign_job(c, job_id, choices[0]['id'])
                # If there is no suitable driver, keep the request pending for manual follow-up.
        return jsonify(ok=True, job_id=job_id, client_id=client_id, city=zone['name'],
                       lat=lat, lng=lng, maps_url=normalized_url,
                       auto_dispatched=bool(assignment), assignment=assignment,
                       warning=None if assignment or not auto else 'Aucun livreur en ligne, disponible et adapté dans cette zone; demande conservée sans affectation.')

    @app.get('/api/control-tower/ramassage/<int:job_id>/candidates')
    @auth('admin')
    def ramassage_candidates(job_id):
        with conn() as c:
            job = c.execute('''SELECT j.id,j.city_id,rc.lat,rc.lng FROM ramassage_jobs j
                               JOIN ramassage_clients rc ON rc.id=j.client_id WHERE j.id=?''', (job_id,)).fetchone()
            if not job:
                raise Error('Demande de ramassage introuvable.', 404)
            rows = eligible_candidates(c, job['city_id'], job['lat'], job['lng'])
        return jsonify(job_id=job_id, candidates=rows)

    @app.post('/api/control-tower/ramassage/<int:job_id>/assign')
    @auth('admin')
    def ramassage_assign(job_id):
        d = request.get_json(silent=True) or {}
        try:
            driver_id = int(d.get('driver_id'))
        except (TypeError, ValueError):
            raise Error('Sélectionnez un livreur valide.')
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            assignment = assign_job(c, job_id, driver_id)
        return jsonify(ok=True, job_id=job_id, assignment=assignment)

    @app.get('/api/driver/tower-status')
    @auth('livreur')
    def driver_tower_status_get():
        u=user()
        with conn() as c:
            row=c.execute('SELECT availability,full_load,gps_enabled,battery_pct,updated_at FROM ramassage_driver_state WHERE driver_id=?',(u['id'],)).fetchone()
        return jsonify(availability=row['availability'] if row else 'available',full_load=bool(row['full_load']) if row else False,
                       gps_enabled=bool(row['gps_enabled']) if row else False,battery_pct=row['battery_pct'] if row else None,
                       updated_at=row['updated_at'] if row else None)

    @app.post('/api/driver/tower-status')
    @auth('livreur')
    def driver_tower_status():
        d = request.get_json(silent=True) or {}
        u = user()
        availability = d.get('availability')
        full_load = d.get('full_load')
        gps_enabled = d.get('gps_enabled')
        battery = d.get('battery_pct')
        if availability not in (None, 'available', 'rest'):
            raise Error('État conducteur invalide : choisissez disponible ou repos.')
        if full_load not in (None, True, False, 0, 1):
            raise Error('Indicateur de chargement invalide.')
        if gps_enabled not in (None, True, False, 0, 1):
            raise Error('État GPS invalide.')
        if battery not in (None, ''):
            try:
                battery = float(battery)
            except (TypeError, ValueError):
                raise Error('Pourcentage de batterie invalide.')
            if not 0 <= battery <= 100:
                raise Error('La batterie doit être entre 0 et 100 %.')
        with conn() as c:
            old = c.execute('SELECT availability,full_load,gps_enabled,battery_pct FROM ramassage_driver_state WHERE driver_id=?', (u['id'],)).fetchone()
            values = {
                'availability': availability if availability is not None else (old['availability'] if old else 'available'),
                'full_load': int(bool(full_load)) if full_load is not None else (old['full_load'] if old else 0),
                'gps_enabled': int(bool(gps_enabled)) if gps_enabled is not None else (old['gps_enabled'] if old else 0),
                'battery_pct': battery if battery not in (None, '') else (old['battery_pct'] if old else None),
            }
            c.execute('''INSERT INTO ramassage_driver_state(driver_id,availability,full_load,gps_enabled,battery_pct,updated_at)
                         VALUES(?,?,?,?,?,?) ON CONFLICT(driver_id) DO UPDATE SET availability=excluded.availability,
                         full_load=excluded.full_load,gps_enabled=excluded.gps_enabled,battery_pct=excluded.battery_pct,updated_at=excluded.updated_at''',
                      (u['id'], values['availability'], values['full_load'], values['gps_enabled'], values['battery_pct'], now()))
        return jsonify(ok=True, **values)

    @app.get('/api/driver/ramassage')
    @auth('livreur')
    def driver_ramassage_list():
        u = user()
        with conn() as c:
            rows = [dict(r) for r in c.execute('''SELECT j.id,j.parcels_count,j.status,j.created_at,j.assigned_at,j.updated_at,
                         rc.name client_name,rc.phone,rc.lat,rc.lng,rc.maps_url,ci.name zone
                  FROM ramassage_jobs j JOIN ramassage_clients rc ON rc.id=j.client_id
                  LEFT JOIN cities ci ON ci.id=j.city_id WHERE j.driver_id=? AND j.status IN ('assigned','en_route')
                  ORDER BY j.assigned_at DESC,j.id DESC LIMIT 50''', (u['id'],))]
        return jsonify(items=rows)

    @app.patch('/api/driver/ramassage/<int:job_id>')
    @auth('livreur')
    def driver_ramassage_update(job_id):
        d = request.get_json(silent=True) or {}
        status = d.get('status')
        if status not in ('en_route', 'picked_up'):
            raise Error('Statut invalide. Choisissez en_route ou picked_up.')
        u = user()
        with conn() as c:
            c.execute('BEGIN IMMEDIATE')
            job = c.execute('SELECT * FROM ramassage_jobs WHERE id=? AND driver_id=?', (job_id, u['id'])).fetchone()
            if not job:
                raise Error('Cette demande ne vous est pas affectée.', 404)
            if job['status'] not in ('assigned', 'en_route'):
                raise Error('Cette demande ne peut plus être modifiée.', 409)
            stamp = now()
            c.execute('UPDATE ramassage_jobs SET status=?,picked_up_at=?,updated_at=? WHERE id=?',
                      (status, stamp if status == 'picked_up' else job['picked_up_at'], stamp, job_id))
        return jsonify(ok=True, status=status)

    @app.get('/api/control-tower/route-history/<int:driver_id>')
    @auth('admin')
    def ramassage_route_history(driver_id):
        day = str(request.args.get('date') or datetime.now().date().isoformat())
        try:
            datetime.strptime(day, '%Y-%m-%d')
        except ValueError:
            raise Error('Date invalide; utilisez AAAA-MM-JJ.')
        with conn() as c:
            if not c.execute("SELECT 1 FROM users WHERE id=? AND role='livreur'", (driver_id,)).fetchone():
                raise Error('Livreur introuvable.', 404)
            rows = [dict(r) for r in c.execute('''SELECT lat,lng,created_at FROM driver_positions
                         WHERE driver_id=? AND substr(created_at,1,10)=? ORDER BY id LIMIT 10000''', (driver_id, day))]
        return jsonify(driver_id=driver_id, date=day, points=rows, count=len(rows), retention_days=POSITION_RETENTION_DAYS)

    @app.after_request
    def _ramassage_no_cache(response):
        # Live locations and phone numbers must never be cached by a proxy/browser.
        if request.path.startswith('/api/control-tower') or request.path.startswith('/api/driver/ramassage'):
            response.headers['Cache-Control'] = 'no-store, private'
        return response
