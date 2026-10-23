import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, request

from ramassage_bon import register_ramassage_bon
from hub_access import hub_manager_route_allowed


class APIError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class RamassageBonTests(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix='.sqlite')
        os.close(fd)
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        @contextmanager
        def conn():
            db = sqlite3.connect(self.db_path)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        def auth(*roles):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    actor = getattr(g, 'actor', None)
                    if not actor or (roles and actor['role'] not in roles):
                        raise APIError('Forbidden', 403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate

        @self.app.before_request
        def set_actor():
            hub = request.headers.get('X-Hub')
            g.actor = {
                'id': int(request.headers.get('X-Actor', '2')),
                'name': request.headers.get('X-Name', 'Test'),
                'role': request.headers.get('X-Role', 'client'),
                'agent_hub_id': int(hub) if hub else None,
            }

        @self.app.errorhandler(APIError)
        def api_error(exc):
            return jsonify(error=str(exc)), exc.status

        def now():
            return datetime.now().isoformat(timespec='seconds')

        def text(data, key, required=True, maxlen=255):
            value = data.get(key, '')
            if not isinstance(value, str) or len(value.strip()) > maxlen or (required and not value.strip()):
                raise APIError('Champ invalide : ' + key)
            return value.strip()

        services = {
            'conn': conn,
            'auth': auth,
            'user': lambda: g.actor,
            'now': now,
            'text': text,
            'APIError': APIError,
            'event': lambda *a, **k: None,
        }

        with conn() as c:
            c.executescript('''
                CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT,region TEXT,
                    delivery INTEGER DEFAULT 1,pickup INTEGER DEFAULT 1,fee REAL DEFAULT 30,
                    return_fee REAL DEFAULT 20,hub_id INTEGER);
                CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,password TEXT DEFAULT '',
                    role TEXT,company TEXT DEFAULT '',phone TEXT DEFAULT '',active INTEGER DEFAULT 1,
                    client_type TEXT DEFAULT 'vendeur',agent_hub_id INTEGER,driver_hub_id INTEGER);
                CREATE TABLE parcels(id INTEGER PRIMARY KEY,tracking TEXT UNIQUE,recipient TEXT DEFAULT '',
                    phone TEXT DEFAULT '',address TEXT DEFAULT '',client_id INTEGER,city_id INTEGER,
                    status TEXT,amount REAL,fee REAL,return_fee REAL,note TEXT DEFAULT '',
                    invoice_id INTEGER,current_hub_id INTEGER,created_at TEXT,updated_at TEXT);
                CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT,city_id INTEGER,address TEXT,
                    active INTEGER DEFAULT 1,created_at TEXT);
            ''')
            c.executemany('INSERT INTO cities(id,name,region,pickup) VALUES(?,?,?,1)',
                          [(1, 'Oujda', 'Oriental'), (2, 'Berkane', 'Oriental')])
            c.executemany('INSERT INTO ops_hubs(id,name,city_id,address,active,created_at) VALUES(?,?,?,?,?,?)',
                          [(10, 'Hub Oujda', 1, 'Zone', 1, now()),
                           (20, 'Hub Berkane', 2, 'Zone', 1, now())])
            c.executemany('INSERT INTO users(id,name,email,role,active,agent_hub_id) VALUES(?,?,?,?,1,?)',
                          [(1, 'Admin', 'a@x.test', 'admin', None),
                           (2, 'Yasmine', 'c@x.test', 'client', None),
                           (910, 'Manager Oujda', 'm10@x.test', 'agent', 10),
                           (920, 'Manager Berkane', 'm20@x.test', 'agent', 20)])
            c.executemany(
                'INSERT INTO parcels(id,tracking,client_id,city_id,status,invoice_id,current_hub_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
                [(101, 'O24-101', 2, 1, 'Créé', None, None, now(), now()),
                 (102, 'O24-102', 2, 1, 'Créé', None, None, now(), now()),
                 (103, 'O24-103', 2, 1, 'Ramassé', None, None, now(), now()),
                 (104, 'O24-104', 2, 1, 'Créé', 77, None, now(), now()),
                 (105, 'O24-105', 2, 1, 'Créé', None, None, now(), now())])

        register_ramassage_bon(self.app, services)
        self.conn = conn
        self.client = self.app.test_client()

    def hdr(self, role='client', actor=2, hub=None):
        h = {'X-Role': role, 'X-Actor': str(actor)}
        if hub:
            h['X-Hub'] = str(hub)
        return h

    def status(self, parcel_id):
        with self.conn() as c:
            r = c.execute('SELECT status,current_hub_id FROM parcels WHERE id=?', (parcel_id,)).fetchone()
            return r['status'], r['current_hub_id']

    def create(self, parcels, role='client', actor=2, hub=10):
        return self.client.post('/api/ramassage-bons', headers=self.hdr(role, actor, hub), json={
            'hub_id': hub, 'city_id': 1, 'address': '12 rue Exemple', 'phone': '+212600000000',
            'pickup_date': '2026-11-01', 'parcel_ids': parcels})

    def batch_fixture(self):
        bid=self.create([101,102]).get_json()['id']
        self.client.post(f'/api/ramassage-bons/{bid}/validate',headers=self.hdr())
        d=self.client.get(f'/api/ramassage-bons/{bid}',headers=self.hdr('agent',910,10)).get_json()
        return bid,dict(snapshot=d['snapshot'],parcel_ids=[101,102],confirmed=True,request_key='batch-'+__import__('uuid').uuid4().hex)

    def test_batch_atomic_receipt_and_retry(self):
        bid,d=self.batch_fixture()
        self.assertEqual(self.status(101),('Confirmé',None))
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('agent',910,10),json=d)
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(self.status(101),('Ramassé',10));self.assertEqual(self.status(102),('Ramassé',10))
        retry=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('agent',910,10),json=d)
        self.assertTrue(retry.json['replayed'])
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('agent',910,10),json={**d,'parcel_ids':[101]})
        self.assertEqual(r.status_code,409)
        self.assertTrue(hub_manager_route_allowed('POST',f'/api/ramassage-bons/{bid}/receive-batch'))

    def test_batch_requires_all_scans_confirmation_and_own_hub(self):
        bid,d=self.batch_fixture()
        for headers,change,code in [(self.hdr(),{},403),(self.hdr('agent',920,20),{},404),(self.hdr('agent',910,10),{'parcel_ids':[101]},409),(self.hdr('agent',910,10),{'parcel_ids':[101,101]},400),(self.hdr('agent',910,10),{'confirmed':False},400),(self.hdr('agent',910,10),{'parcel_ids':[101,105]},409)]:
            r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=headers,json={**d,**change})
            self.assertEqual(r.status_code,code,r.data)
            self.assertEqual(self.status(101),('Confirmé',None));self.assertEqual(self.status(102),('Confirmé',None))

    def test_batch_stale_snapshot_does_not_partially_receive(self):
        bid,d=self.batch_fixture()
        with self.conn() as c:c.execute("UPDATE parcels SET recipient='Changed' WHERE id=102")
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.status(101),('Confirmé',None));self.assertEqual(self.status(102),('Confirmé',None))

    def test_batch_blocks_invoice_and_inactive_hub(self):
        bid,d=self.batch_fixture()
        with self.conn() as c:c.execute('UPDATE parcels SET invoice_id=99 WHERE id=102')
        d['snapshot']=self.client.get(f'/api/ramassage-bons/{bid}',headers=self.hdr('admin',1)).json['snapshot']
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(r.status_code,409);self.assertEqual(self.status(101),('Confirmé',None))
        with self.conn() as c:c.execute('UPDATE parcels SET invoice_id=NULL WHERE id=102');c.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(r.status_code,404);self.assertEqual(self.status(101),('Confirmé',None))

    def test_batch_can_finish_partial_receipt_and_admin_allowed(self):
        bid,d=self.batch_fixture()
        self.client.post(f'/api/ramassage-bons/{bid}/receive',headers=self.hdr('agent',910,10),json={'tracking':'O24-101'})
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(r.status_code,409);self.assertEqual(self.status(102),('Confirmé',None))
        detail=self.client.get(f'/api/ramassage-bons/{bid}',headers=self.hdr('admin',1)).json
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json={**d,'snapshot':detail['snapshot'],'parcel_ids':[102]})
        self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.json['received'],1)

    def test_batch_write_failure_rolls_back_whole_lot(self):
        bid,d=self.batch_fixture()
        with self.conn() as c:
            c.execute("CREATE TRIGGER reject_second BEFORE UPDATE ON parcels WHEN NEW.id=102 AND NEW.status='Ramassé' BEGIN SELECT RAISE(ABORT,'test rollback'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(self.status(101),('Confirmé',None));self.assertEqual(self.status(102),('Confirmé',None))
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ramassage_receive_keys').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM ramassage_bon_lines WHERE received_at IS NOT NULL').fetchone()[0],0)

    def test_removed_draft_line_not_required_in_batch(self):
        bid=self.create([101,102]).json['id']
        with self.conn() as c:c.execute('UPDATE ramassage_bon_lines SET active=0 WHERE bon_id=? AND parcel_id=102',(bid,))
        self.client.post(f'/api/ramassage-bons/{bid}/validate',headers=self.hdr())
        detail=self.client.get(f'/api/ramassage-bons/{bid}',headers=self.hdr('admin',1)).json
        self.assertEqual(detail['count'],1)
        d=dict(parcel_ids=[101],snapshot=detail['snapshot'],confirmed=True,request_key='removed-'+__import__('uuid').uuid4().hex)
        r=self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('admin',1),json=d)
        self.assertEqual(r.status_code,200,r.data);self.assertEqual(self.status(102),('Créé',None))

    def collected_setup(self):
        bid,d=self.batch_fixture()
        self.client.post(f'/api/ramassage-bons/{bid}/receive-batch',headers=self.hdr('agent',910,10),json=d)
        return bid

    def test_collected_scope_search_filters_and_pagination(self):
        self.collected_setup();url='/api/ramassage-bons/hub/collected'
        for headers in (self.hdr('admin',1),self.hdr('agent',910,10)):
            r=self.client.get(url+'?size=1',headers=headers)
            self.assertEqual(r.status_code,200,r.data);self.assertEqual(r.json['total'],2);self.assertEqual(len(r.json['rows']),1)
            self.assertEqual(r.json['counts'],{'at_hub':2})
            r=self.client.get(url+'?q=O24-101&state=at_hub',headers=headers)
            self.assertEqual(r.json['total'],1);self.assertEqual(r.json['rows'][0]['parcel_id'],101)
            self.assertEqual(self.client.get(url+'?q=%25',headers=headers).json['total'],0)
        self.assertEqual(self.client.get(url,headers=self.hdr('agent',920,20)).json['total'],0)
        self.assertEqual(self.client.get(url+'?hub_id=20',headers=self.hdr('agent',910,10)).status_code,404)
        self.assertEqual(self.client.get(url,headers=self.hdr()).status_code,403)
        self.assertEqual(self.client.get(url,headers=self.hdr('agent',910)).status_code,404)
        self.assertTrue(hub_manager_route_allowed('GET',url))
        self.assertFalse(hub_manager_route_allowed('POST',url))

    def test_collected_excludes_societe_and_does_not_drop_unexpected_status(self):
        self.collected_setup();url='/api/ramassage-bons/hub/collected';headers=self.hdr('agent',910,10)
        with self.conn() as c:c.execute("UPDATE parcels SET status='Livré',current_hub_id=NULL WHERE id=101")
        r=self.client.get(url,headers=headers)
        self.assertEqual(r.json['total'],2);self.assertEqual(r.json['counts'],{'at_hub':1,'review':1})
        with self.conn() as c:c.execute("UPDATE users SET client_type='societe_livraison' WHERE id=2")
        self.assertEqual(self.client.get(url,headers=headers).json['total'],0)

    def test_collected_rejects_invalid_filters_and_inactive_hub(self):
        url='/api/ramassage-bons/hub/collected';headers=self.hdr('agent',910,10)
        for query in ('page=0','size=-1','state=bad','hub_id=no'):
            self.assertEqual(self.client.get(url+'?'+query,headers=headers).status_code,400)
        with self.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        self.assertEqual(self.client.get(url,headers=headers).status_code,404)

    def test_create_draft_and_eligibility(self):
        r = self.create([101, 102])
        self.assertEqual(r.status_code, 200, r.data)
        bid = r.get_json()['id']
        detail = self.client.get('/api/ramassage-bons/%d' % bid, headers=self.hdr()).get_json()
        self.assertEqual(detail['status'], 'Brouillon')
        self.assertEqual(detail['count'], 2)
        self.assertEqual(detail['hub_id'], 10)
        # Un colis non « Créé » est refusé
        r = self.client.post('/api/ramassage-bons/%d/lines' % bid, headers=self.hdr(), json={'parcel_ids': [103]})
        self.assertEqual(r.status_code, 409)
        # Un colis facturé est refusé
        r = self.client.post('/api/ramassage-bons/%d/lines' % bid, headers=self.hdr(), json={'parcel_ids': [104]})
        self.assertEqual(r.status_code, 409)

    def test_parcel_locked_in_one_active_bon(self):
        self.assertEqual(self.create([101]).status_code, 200)
        r = self.create([101])
        self.assertEqual(r.status_code, 409)

    def test_validate_sets_confirme(self):
        bid = self.create([101, 102]).get_json()['id']
        r = self.client.post('/api/ramassage-bons/%d/validate' % bid, headers=self.hdr())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status(101)[0], 'Confirmé')
        self.assertEqual(self.status(102)[0], 'Confirmé')
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT status FROM ramassage_bons WHERE id=?', (bid,)).fetchone()['status'],
                             'Confirmé')
        # Validation idempotente
        r = self.client.post('/api/ramassage-bons/%d/validate' % bid, headers=self.hdr())
        self.assertEqual(r.get_json().get('already_validated'), True)
        # Bon confirmé non modifiable
        r = self.client.post('/api/ramassage-bons/%d/lines' % bid, headers=self.hdr(), json={'parcel_ids': [105]})
        self.assertEqual(r.status_code, 409)

    def test_hub_reception_flow(self):
        bid = self.create([101, 102]).get_json()['id']
        self.client.post('/api/ramassage-bons/%d/validate' % bid, headers=self.hdr())
        # Mauvais Hub refusé
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('agent', 920, 20),
                             json={'tracking': 'O24-101'})
        self.assertEqual(r.status_code, 404)
        # Tracking inconnu refusé
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('agent', 910, 10),
                             json={'tracking': 'INCONNU'})
        self.assertEqual(r.status_code, 404)
        # Première réception -> En cours, colis Ramassé et localisé au Hub
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('agent', 910, 10),
                             json={'tracking': 'O24-101'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.get_json()['status'], 'En cours')
        st, hub = self.status(101)
        self.assertEqual(st, 'Ramassé')
        self.assertEqual(hub, 10)
        # Idempotence du scan
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('agent', 910, 10),
                             json={'tracking': 'O24-101'})
        self.assertEqual(r.get_json().get('already_received'), True)
        # Dernière réception -> Reçu
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('agent', 910, 10),
                             json={'tracking': 'O24-102'})
        self.assertEqual(r.get_json()['status'], 'Reçu')
        self.assertEqual(self.status(102)[0], 'Ramassé')
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT status FROM ramassage_bons WHERE id=?', (bid,)).fetchone()['status'],
                             'Reçu')
            self.assertEqual(c.execute('SELECT count(*) k FROM ramassage_bon_lines WHERE bon_id=? AND active=1',
                                       (bid,)).fetchone()['k'], 0)

    def test_admin_reception_allowed(self):
        bid = self.create([101]).get_json()['id']
        self.client.post('/api/ramassage-bons/%d/validate' % bid, headers=self.hdr())
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr('admin', 1),
                             json={'tracking': 'O24-101'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.status(101)[0], 'Ramassé')

    def test_client_cannot_receive(self):
        bid = self.create([101]).get_json()['id']
        self.client.post('/api/ramassage-bons/%d/validate' % bid, headers=self.hdr())
        r = self.client.post('/api/ramassage-bons/%d/receive' % bid, headers=self.hdr(),
                             json={'tracking': 'O24-101'})
        self.assertEqual(r.status_code, 403)

    def test_cancel_draft_and_confirmed(self):
        # Annulation d'un brouillon par le client
        bid = self.create([105]).get_json()['id']
        r = self.client.post('/api/ramassage-bons/%d/cancel' % bid, headers=self.hdr(), json={'reason': 'test'})
        self.assertEqual(r.status_code, 200)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT status FROM ramassage_bons WHERE id=?', (bid,)).fetchone()['status'],
                             'Annulé')
        # Le colis redevient éligible
        elig = self.client.get('/api/ramassage-bons/eligible', headers=self.hdr()).get_json()
        self.assertIn(105, [p['id'] for p in elig])
        # Annulation d'un bon confirmé par l'admin -> retour à Créé
        bid2 = self.create([105]).get_json()['id']
        self.client.post('/api/ramassage-bons/%d/validate' % bid2, headers=self.hdr())
        self.assertEqual(self.status(105)[0], 'Confirmé')
        r = self.client.post('/api/ramassage-bons/%d/cancel' % bid2, headers=self.hdr('admin', 1),
                             json={'reason': 'erreur'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.status(105)[0], 'Créé')
        # Le client ne peut pas annuler un bon confirmé
        bid3 = self.create([101, 102]).get_json()['id']
        self.client.post('/api/ramassage-bons/%d/validate' % bid3, headers=self.hdr())
        r = self.client.post('/api/ramassage-bons/%d/cancel' % bid3, headers=self.hdr(), json={})
        self.assertEqual(r.status_code, 403)

    def test_other_client_isolation(self):
        bid = self.create([101]).get_json()['id']
        r = self.client.get('/api/ramassage-bons/%d' % bid, headers=self.hdr('client', 999))
        self.assertEqual(r.status_code, 404)

    def test_hub_allowlist_covers_routes(self):
        self.assertTrue(hub_manager_route_allowed('GET', '/api/ramassage-bons/hub/queue'))
        self.assertTrue(hub_manager_route_allowed('GET', '/api/ramassage-bons/12'))
        self.assertTrue(hub_manager_route_allowed('POST', '/api/ramassage-bons/12/receive'))
        self.assertFalse(hub_manager_route_allowed('POST', '/api/ramassage-bons'))


if __name__ == '__main__':
    unittest.main()
