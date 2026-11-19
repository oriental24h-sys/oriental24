"""Chaque Hub ne voit que les CMD « comptées » sur lui.

Règle demandée : « kola hub ibanu lih ghir les cmd li mahsobin 3lih ».
Un Hub voit :
  - les colis physiquement chez lui (ou chez un de ses livreurs) ;
  - les colis réellement en route vers lui (palette partie / ville de livraison) ;
  - ses propres retours en cours de route (il devra les remettre au client).
Il ne voit jamais : les colis d'un autre Hub, ni ceux qu'il a déjà expédiés.

Les mutations, l'inventaire, le dispatch et la finance gardent la garde physique.
"""
import importlib
import os
import sqlite3
import sys
import tempfile
import unittest
import uuid

from hub_access import hub_inbound_parcel_scope, hub_parcel_scope, hub_read_parcel_scope, hub_tracking_parcel_scope


class HubVisibilityScopeUnitTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.row_factory = sqlite3.Row
        self.c.executescript('''
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY, active INTEGER);
            CREATE TABLE cities(id INTEGER PRIMARY KEY, hub_id INTEGER);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY, tracking TEXT, city_id INTEGER, current_hub_id INTEGER,
                origin_hub_id INTEGER, driver_id INTEGER, status TEXT, return_state TEXT);
            CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY, parcel_id INTEGER, new_driver_id INTEGER, hub_id INTEGER);
            CREATE TABLE ops_documents(id INTEGER PRIMARY KEY, kind TEXT, source_hub_id INTEGER, destination_hub_id INTEGER,
                status TEXT, departure_scan_required INTEGER, dispatched_at TEXT);
            CREATE TABLE ops_document_lines(id INTEGER PRIMARY KEY, parcel_id INTEGER, document_id INTEGER,
                active INTEGER, departure_scanned_at TEXT, departure_reconciled_at TEXT, received_at TEXT);
            INSERT INTO ops_hubs VALUES(10,1),(20,1),(30,1);
            INSERT INTO cities VALUES(1,10),(2,20);
            INSERT INTO parcels VALUES
                (1,'P-A-CHEZ-A',1,10,NULL,NULL,'Au hub',NULL),
                (2,'P-B-CHEZ-B',2,20,NULL,NULL,'Au hub',NULL),
                (3,'P-A-TRANSIT',1,NULL,NULL,NULL,'Transit',NULL),
                (4,'P-B-TRANSIT',2,NULL,NULL,NULL,'Transit',NULL),
                (5,'P-A-CREE',1,NULL,NULL,NULL,'Créé',NULL),
                (6,'P-A-RETOUR',1,NULL,10,NULL,'Retourné','envoye'),
                (7,'P-B-RETOUR',2,NULL,20,NULL,'Retourné','envoye'),
                (8,'P-PALETTE-VERS-A',2,NULL,NULL,NULL,'Transit',NULL),
                (9,'P-PALETTE-NON-PARTIE',1,NULL,NULL,NULL,'Transit',NULL),
                (11,'P-A-LIVRE-CHEZ-B',1,20,NULL,NULL,'Livré',NULL),
                (12,'P-A-CHEZ-LIVREUR',1,NULL,NULL,50,'En livraison',NULL);
            INSERT INTO ops_assignments VALUES(1,12,50,10);
            INSERT INTO ops_documents VALUES
                (1,'transfer',20,10,'En transit',1,'sent'),
                (2,'transfer',10,20,'En transit',1,NULL);
            INSERT INTO ops_document_lines VALUES
                (1,8,1,1,'sent',NULL,NULL),
                (2,9,2,1,NULL,NULL,NULL);
        ''')

    def tearDown(self):
        self.c.close()

    def ids(self, hub, reader=hub_read_parcel_scope):
        where, args = reader(self.c, 'p', hub)
        return {r[0] for r in self.c.execute('SELECT p.id FROM parcels p WHERE ' + where, args)}

    def test_a_hub_only_sees_the_commands_counted_on_it(self):
        self.assertEqual(self.ids(10), {1, 3, 6, 8, 12})
        self.assertEqual(self.ids(20), {2, 4, 7, 11})
        self.assertEqual(self.ids(30), set())

    def test_a_departed_command_never_stays_on_the_sender(self):
        # 8 est dans une palette 20 -> 10 : il appartient à 10, plus à 20 malgré sa ville.
        self.assertNotIn(8, self.ids(20))
        # 11 a été expédié par 10 puis livré chez 20 : il n'est plus compté sur 10.
        self.assertNotIn(11, self.ids(10))
        self.assertIn(11, self.ids(20))

    def test_commands_not_yet_dispatched_stay_invisible(self):
        self.assertNotIn(5, self.ids(10))   # Créé : pas encore parti du client.
        self.assertNotIn(9, self.ids(20))   # Palette pas encore scannée au départ.

    def test_returns_stay_with_their_origin_hub(self):
        self.assertIn(6, self.ids(10))
        self.assertNotIn(6, self.ids(20))
        self.assertIn(7, self.ids(20))

    def test_mutation_scope_remains_physical_custody_only(self):
        self.assertEqual(self.ids(10, hub_parcel_scope), {1})
        self.assertEqual(self.ids(20, hub_parcel_scope), {2, 11})
        self.assertEqual(self.ids(10, hub_tracking_parcel_scope), {1, 12})

    def test_invalid_or_inactive_hub_is_fail_closed(self):
        for hub in (None, True, 0, '10', 999, -3):
            self.assertEqual(self.ids(hub), set())
            self.assertEqual(self.ids(hub, hub_inbound_parcel_scope), set())
        self.c.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        self.assertEqual(self.ids(10), set())

    def test_scope_is_never_built_on_missing_tables(self):
        empty = sqlite3.connect(':memory:')
        try:
            self.assertEqual(hub_read_parcel_scope(empty, 'p', 10), ('1=0', []))
            self.assertEqual(hub_inbound_parcel_scope(empty, 'p', 10), ('1=0', []))
        finally:
            empty.close()


class HubVisibilityApiTests(unittest.TestCase):
    """Le filtre est appliqué par le serveur, pas par le navigateur."""

    @classmethod
    def setUpClass(cls):
        from appfixture import acquire
        cls.m, cls.own_module = acquire('hub-visibility')

    def setUp(self):
        from werkzeug.security import generate_password_hash
        m = self.m
        unique = uuid.uuid4().hex
        with m.conn() as c:
            city_a = c.execute('SELECT id FROM cities ORDER BY id LIMIT 1').fetchone()[0]
            city_b = c.execute('SELECT id FROM cities WHERE id<>? ORDER BY id LIMIT 1', (city_a,)).fetchone()[0]
            self.hub_a = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)",
                                   ('Hub A ' + unique, city_a, m.now())).lastrowid
            self.hub_b = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)",
                                   ('Hub B ' + unique, city_b, m.now())).lastrowid
            c.execute('UPDATE cities SET hub_id=? WHERE id=?', (self.hub_a, city_a))
            c.execute('UPDATE cities SET hub_id=? WHERE id=?', (self.hub_b, city_b))
            self.city_a, self.city_b = city_a, city_b
            client_id = c.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()[0]
            self.client_id = client_id
            email = unique + '@example.test'
            self.manager_id = c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,'hub_manager',?,?)",
                      ('Manager A', email, generate_password_hash('HubScopeTest!123'), self.hub_a, m.now())).lastrowid
        self.email = email
        self.browser = m.app.test_client()
        login = self.browser.post('/api/login', json={'email': email, 'password': 'HubScopeTest!123'},
                                  environ_overrides={'REMOTE_ADDR': '10.90.0.1'})
        self.assertEqual(login.status_code, 200, login.json)
        self.headers = {'X-CSRF-Token': self.browser.get('/api/bootstrap').json['csrf']}
    def setUp(self):
        from werkzeug.security import generate_password_hash
        m = self.m
        unique = uuid.uuid4().hex
        with m.conn() as c:
            city_a = c.execute('SELECT id FROM cities ORDER BY id LIMIT 1').fetchone()[0]
            city_b = c.execute('SELECT id FROM cities WHERE id<>? ORDER BY id LIMIT 1', (city_a,)).fetchone()[0]
            self.hub_a = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)",
                                   ('Hub A ' + unique, city_a, m.now())).lastrowid
            self.hub_b = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)",
                                   ('Hub B ' + unique, city_b, m.now())).lastrowid
            c.execute('UPDATE cities SET hub_id=? WHERE id=?', (self.hub_a, city_a))
            c.execute('UPDATE cities SET hub_id=? WHERE id=?', (self.hub_b, city_b))
            self.city_a, self.city_b = city_a, city_b
            client_id = c.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()[0]
            self.client_id = client_id
            email = unique + '@example.test'
            self.manager_id = c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,'hub_manager',?,?)",
                      ('Manager A', email, generate_password_hash('HubScopeTest!123'), self.hub_a, m.now())).lastrowid
        self.email = email
        self.browser = m.app.test_client()
        login = self.browser.post('/api/login', json={'email': email, 'password': 'HubScopeTest!123'},
                                  environ_overrides={'REMOTE_ADDR': '10.90.0.1'})
        self.assertEqual(login.status_code, 200, login.json)
        self.headers = {'X-CSRF-Token': self.browser.get('/api/bootstrap').json['csrf']}

    def parcel(self, tracking, city_id, current_hub_id=None, status='Au hub', origin_hub_id=None, return_state=None):
        with self.m.conn() as c:
            pid = c.execute('''INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,
                    status,created_at,updated_at,current_hub_id,origin_hub_id,return_state)
                VALUES(?,?,'Destinataire','0600000000','Adresse',?,100,20,10,?,?,?,?,?,?)''',
                (tracking, self.client_id, city_id, status, self.m.now(), self.m.now(),
                 current_hub_id, origin_hub_id, return_state)).lastrowid
        return pid

    def bootstrap_ids(self):
        return {p['id'] for p in self.browser.get('/api/bootstrap').json['parcels']}

    def test_bootstrap_and_detail_only_expose_own_hub_commands(self):
        mine = self.parcel('SCOPE-A-' + uuid.uuid4().hex[:8].upper(), self.city_a, self.hub_a)
        transit = self.parcel('SCOPE-A-TRANSIT-' + uuid.uuid4().hex[:8].upper(), self.city_a, None, status='Transit')
        foreign = self.parcel('SCOPE-B-' + uuid.uuid4().hex[:8].upper(), self.city_b, self.hub_b)
        created = self.parcel('SCOPE-A-CREE-' + uuid.uuid4().hex[:8].upper(), self.city_a, None, status='Créé')
        ids = self.bootstrap_ids()
        self.assertIn(mine, ids)
        self.assertIn(transit, ids)          # en route vers lui : déjà comptée sur lui
        self.assertNotIn(foreign, ids)       # CMD d'un autre Hub : invisible
        self.assertNotIn(created, ids)       # pas encore partie du client
        self.assertEqual(self.browser.get(f'/api/parcels/{foreign}').status_code, 404)
        self.assertEqual(self.browser.get(f'/api/parcels/{mine}').status_code, 200)

    def test_departed_command_leaves_the_sender_list_and_counter(self):
        tracking = 'SCOPE-SENT-' + uuid.uuid4().hex[:8].upper()
        pid = self.parcel(tracking, self.city_b, self.hub_a)  # chez A, destinée à la ville de B
        self.assertIn(pid, self.bootstrap_ids())
        before = self.browser.get('/api/sidebar-counts').json['counts']['parcels']
        with self.m.conn() as c:
            # Départ réel vers B : le colis n'est plus compté sur A.
            c.execute('UPDATE parcels SET current_hub_id=NULL,status=? WHERE id=?', ('Transit', pid))
            doc = c.execute('''INSERT INTO ops_documents(kind,palette_purpose,source_hub_id,destination_hub_id,status,note,
                    departure_scan_required,dispatched_at,created_by,created_at) VALUES('transfer','standard',?,?,'En transit','',1,?,?,?)''',
                    (self.hub_a, self.hub_b, self.m.now(), self.manager_id, self.m.now())).lastrowid
            c.execute('''INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status,active,departure_scanned_at)
                    VALUES(?,?,?,'Destinataire','Ville','Transit',1,?)''', (doc, pid, tracking, self.m.now()))
        self.assertNotIn(pid, self.bootstrap_ids())
        self.assertEqual(self.browser.get(f'/api/parcels/{pid}').status_code, 404)
        after = self.browser.get('/api/sidebar-counts').json['counts']['parcels']
        self.assertEqual(after, before - 1)


if __name__ == '__main__':
    unittest.main()
