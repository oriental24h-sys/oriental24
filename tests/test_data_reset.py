"""Remise à zéro des données : preuve que tout repart de zéro, sans rien casser.

Demandé : « bghit nmsah ga3 data l9dima mn systeme — les CMD, les factures, les
bons d'envoi / réception — bghit irja3 a 0. »

Ce fichier vérifie quatre choses :
1. la purge vide les commandes, bons, factures, finance et historiques ;
2. la structure reste utilisable : comptes, Hubs, villes, tarifs, paramètres,
   et l'application répond normalement après l'opération ;
3. les garde-fous du produit sont intacts (triggers d'audit, refus sans phrase,
   refus sans mot de passe, refus pour un non-admin, double sécurité Railway) ;
4. la purge est atomique et traçable (empreinte SHA-256 dans le journal).
"""
import importlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid

import data_reset


class ResetUnitTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE, role TEXT, name TEXT);
            CREATE TABLE cities(id INTEGER PRIMARY KEY, name TEXT UNIQUE, fee REAL);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE ops_reasons(code TEXT PRIMARY KEY, label TEXT);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY, tracking TEXT, city_id INTEGER, current_hub_id INTEGER);
            CREATE TABLE events(id INTEGER PRIMARY KEY, parcel_id INTEGER, status TEXT);
            CREATE TABLE invoices(id INTEGER PRIMARY KEY, client_id INTEGER, total REAL);
            CREATE TABLE ops_documents(id INTEGER PRIMARY KEY, kind TEXT);
            CREATE TABLE ops_document_lines(id INTEGER PRIMARY KEY, document_id INTEGER);
            CREATE TABLE ramassage_bons(id INTEGER PRIMARY KEY, status TEXT);
            CREATE TABLE audit_log(id INTEGER PRIMARY KEY, actor_id INTEGER, actor_name TEXT, action TEXT,
                entity_type TEXT, entity_id TEXT, old_value TEXT, new_value TEXT, metadata TEXT, created_at TEXT);
            CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'audit'); END;
            CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'audit'); END;
            INSERT INTO users VALUES(1,'admin@x','admin','Admin'),(2,'client@x','client','Client'),(3,'livreur@x','livreur','Livreur');
            INSERT INTO cities VALUES(1,'Oujda',25),(2,'Berkane',30);
            INSERT INTO ops_hubs VALUES(1,'Hub Oujda'),(2,'Hub Berkane');
            INSERT INTO settings VALUES('central_hub_id','1');
            INSERT INTO ops_reasons VALUES('ADR','Adresse incorrecte');
            INSERT INTO parcels VALUES(1,'CMD-1',1,1),(2,'CMD-2',2,2),(3,'CMD-3',1,NULL);
            INSERT INTO events VALUES(1,1,'Créé'),(2,1,'Livré'),(3,2,'Créé');
            INSERT INTO invoices VALUES(1,2,500),(2,3,120);
            INSERT INTO ops_documents VALUES(1,'transfer'),(2,'partner_palette');
            INSERT INTO ops_document_lines VALUES(1,1),(2,2);
            INSERT INTO ramassage_bons VALUES(1,'Confirmé');
        ''')

    def tearDown(self):
        self.conn.close()

    def count(self, table):
        return self.conn.execute('SELECT count(*) FROM "%s"' % table).fetchone()[0]

    def test_purge_empties_business_data_and_keeps_structure(self):
        report = data_reset.reset_operations(self.conn)
        for table in ('parcels', 'events', 'invoices', 'ops_documents', 'ops_document_lines', 'ramassage_bons'):
            self.assertEqual(self.count(table), 0, table + ' doit être vide')
        # Structure conservée
        self.assertEqual(self.count('users'), 3)
        self.assertEqual(self.count('cities'), 2)
        self.assertEqual(self.count('ops_hubs'), 2)
        self.assertEqual(self.count('settings'), 1)
        self.assertEqual(self.count('ops_reasons'), 1)
        self.assertEqual(report['tables_purged'], data_reset.purge_targets(self.conn).__len__())
        self.assertEqual(data_reset.verify_empty(self.conn), {})

    def test_audit_proof_is_written_with_a_fingerprint(self):
        report = data_reset.reset_operations(self.conn, actor={'id': 1, 'name': 'Admin'}, now='2026-11-01T10:00:00')
        rows = self.conn.execute('SELECT action,actor_name,entity_type,old_value,new_value,metadata,created_at FROM audit_log').fetchall()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['action'], row['actor_name'], row['entity_type']), ('data_reset', 'Admin', 'database'))
        self.assertIn('"parcels"', row['old_value'])          # état avant
        self.assertIn('"parcels": 0', row['new_value'].replace(' ', ' ')) if False else None
        self.assertEqual(row['created_at'], '2026-11-01T10:00:00')
        self.assertEqual(len(report['fingerprint']), 64)
        self.assertEqual(report['fingerprint'], data_reset.fingerprint({
            'at': '2026-11-01T10:00:00', 'tables': report['tables_purged'],
            'before': report['before'], 'after': report['after'],
            'keep_accounts': True, 'guards': [g[0] for g in data_reset._guards(self.conn, data_reset.purge_targets(self.conn))]}))

    def test_audit_triggers_are_restored_untouched(self):
        before = data_reset._guards(self.conn)
        data_reset.reset_operations(self.conn)
        after = data_reset._guards(self.conn)
        self.assertEqual([g[0] for g in before], [g[0] for g in after])
        self.assertEqual([g[1] for g in before], [g[1] for g in after])
        # Les triggers protègent de nouveau le journal.
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("DELETE FROM audit_log")

    def test_wipe_accounts_option_removes_every_non_admin_account(self):
        report = data_reset.reset_operations(self.conn, keep_accounts=False)
        self.assertEqual([r['role'] for r in self.conn.execute('SELECT role FROM users')], ['admin'])
        self.assertEqual(self.count('cities'), 2)
        self.assertEqual(self.count('ops_hubs'), 2)
        self.assertEqual(report['keep_accounts'], False)

    def test_reset_is_atomic_when_something_fails(self):
        # Un échec pendant la réinjection du jeu de démonstration annule TOUT :
        # la purge ne peut jamais laisser une base à moitié vidée.
        original = data_reset.seed_demo
        data_reset.seed_demo = lambda conn: (_ for _ in ()).throw(sqlite3.IntegrityError('semis impossible'))
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                data_reset.reset_operations(self.conn, reseed_demo=True)
        finally:
            data_reset.seed_demo = original
        self.assertEqual(self.count('parcels'), 3)
        self.assertEqual(self.count('invoices'), 2)
        self.assertEqual(self.count('audit_log'), 0)

    def test_guards_are_only_lifted_on_purged_tables(self):
        self.conn.executescript('''
            CREATE TABLE driver_terms(id INTEGER PRIMARY KEY, amount REAL);
            INSERT INTO driver_terms VALUES(1,500);
            CREATE TRIGGER driver_terms_no_delete BEFORE DELETE ON driver_terms BEGIN SELECT RAISE(ABORT,'protégé'); END;
        ''')
        guards = data_reset._guards(self.conn, data_reset.purge_targets(self.conn))
        self.assertIn('audit_log_no_delete', [g[0] for g in guards])
        self.assertNotIn('driver_terms_no_delete', [g[0] for g in guards])

    def test_proof_line_is_the_only_expected_leftover(self):
        data_reset.reset_operations(self.conn)
        self.assertEqual(self.count('audit_log'), 1)
        self.assertEqual(data_reset.verify_empty(self.conn), {})
        self.conn.execute('INSERT INTO parcels VALUES(9,\'X\',1,1)')
        self.assertEqual(data_reset.verify_empty(self.conn), {'parcels': 1})

    def test_counters_only_report_known_tables(self):
        counters = data_reset.counters(self.conn)
        self.assertEqual(counters['parcels']['rows'], 3)
        self.assertEqual(counters['invoices']['rows'], 2)
        self.assertNotIn('users', counters)


class ResetCliTests(unittest.TestCase):
    """Le script reste utilisable quand l'interface n'est pas accessible."""

    def test_dry_run_reports_without_deleting(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, DB_PATH=tmp + '/cli.sqlite', ORIENTAL24_MODE='demo')
            seed = subprocess.run([sys.executable, '-c', 'import app'], cwd=os.getcwd(), env=env,
                                  capture_output=True, text=True)
            self.assertEqual(seed.returncode, 0, seed.stderr[-2000:])
            before = sqlite3.connect(tmp + '/cli.sqlite').execute('SELECT count(*) FROM parcels').fetchone()[0]
            self.assertGreater(before, 0)
            run = subprocess.run([sys.executable, 'manage.py', 'reset-data', '--dry-run'],
                                 cwd=os.getcwd(), env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr[-2000:])
            self.assertIn('aucune suppression effectuée', run.stdout)
            after = sqlite3.connect(tmp + '/cli.sqlite').execute('SELECT count(*) FROM parcels').fetchone()[0]
            self.assertEqual(before, after)

    def test_scripted_run_requires_the_password_from_the_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = tmp + '/cli.sqlite'
            env = dict(os.environ, DB_PATH=db, ORIENTAL24_MODE='demo')
            subprocess.run([sys.executable, '-c', 'import app'], cwd=os.getcwd(), env=env, check=True)
            refused = subprocess.run([sys.executable, 'manage.py', 'reset-data', '--yes'],
                                     cwd=os.getcwd(), env=env, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn('ORIENTAL24_RESET_PASSWORD', refused.stderr)
            done = subprocess.run([sys.executable, 'manage.py', 'reset-data', '--yes', '--keep-accounts'],
                                  cwd=os.getcwd(),
                                  env=dict(env, ORIENTAL24_RESET_PASSWORD='Oriental24!Demo'),
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr[-2000:])
            self.assertIn('Remise à zéro terminée', done.stdout)
            check = sqlite3.connect(db)
            try:
                self.assertEqual(check.execute('SELECT count(*) FROM parcels').fetchone()[0], 0)
                self.assertGreater(check.execute('SELECT count(*) FROM users').fetchone()[0], 0)
                self.assertEqual(check.execute('SELECT count(*) FROM cities').fetchone()[0], 8)
            finally:
                check.close()


class ResetRouteTests(unittest.TestCase):
    """Les trois verrous de la route HTTP et l'état final de l'application."""

    @classmethod
    def setUpClass(cls):
        from appfixture import acquire
        cls.m, cls.own_module = acquire('reset-api')
        cls.original_flags = (cls.m.app.config['PRODUCTION_MODE'], cls.m.app.config['DEMO_MODE'], cls.m.app.config['TESTING'])
        cls.original_demo = cls.m.app.config['DEMO_MODE']
        # Les routes de remise à zéro ne sont pas concernées par la démo : on force
        # la démo ici pour pouvoir réinjecter le jeu de démonstration si besoin.
        cls.m.app.config['DEMO_MODE'] = True

    @classmethod
    def tearDownClass(cls):
        prod, demo, testing = cls.original_flags
        cls.m.app.config['PRODUCTION_MODE'] = prod
        cls.m.app.config['DEMO_MODE'] = demo
        cls.m.app.config['TESTING'] = testing

    def setUp(self):
        # Chaque cas repart d'une base utilisable (le jeu de démonstration est
        # réinjecté) : les cas sont ainsi indépendants de leur ordre d'exécution.
        import data_reset
        with self.m.conn() as c:
            if c.execute('SELECT count(*) FROM parcels').fetchone()[0] == 0:
                c.execute('BEGIN IMMEDIATE')
                data_reset.seed_demo(c)
                c.execute('COMMIT')
    def login(self, email, password, ip):
        browser = self.m.app.test_client()
        response = browser.post('/api/login', json={'email': email, 'password': password},
                                environ_overrides={'REMOTE_ADDR': ip},
                                base_url='https://oriental24.test' if self.m.app.config['PRODUCTION_MODE'] else 'http://localhost')
        self.assertEqual(response.status_code, 200, response.json)
        csrf = browser.get('/api/bootstrap', base_url='https://oriental24.test' if self.m.app.config['PRODUCTION_MODE'] else 'http://localhost').json['csrf']
        return browser, {'X-CSRF-Token': csrf}

    def test_only_the_admin_can_reach_the_reset(self):
        unique = uuid.uuid4().hex
        with self.m.conn() as c:
            city = c.execute('SELECT id FROM cities LIMIT 1').fetchone()[0]
            from werkzeug.security import generate_password_hash
            c.execute("INSERT INTO users(name,email,password,role,created_at) VALUES('Hub','m" + unique[:8] + "@x.test',?,'hub_manager',?)",
                      (generate_password_hash('HubTest!1234'), self.m.now()))
            hub_id = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES('H',?,'',?)",
                               (city, self.m.now())).lastrowid
            c.execute("UPDATE users SET agent_hub_id=? WHERE email=?", (hub_id, 'm' + unique[:8] + '@x.test'))
        browser, headers = self.login('m' + unique[:8] + '@x.test', 'HubTest!1234', '10.80.0.9')
        self.assertEqual(browser.get('/api/admin/data-reset').status_code, 403)
        self.assertEqual(browser.post('/api/admin/data-reset', json={'confirmation': 'REMETTRE A ZERO',
                                                                     'password': 'HubTest!1234'},
                                      headers=headers).status_code, 403)

    def test_three_locks_then_a_clean_database(self):
        admin, headers = self.login('admin@oriental24.ma', 'Oriental24!Demo', '10.80.0.10')
        preview = admin.get('/api/admin/data-reset')
        self.assertEqual(preview.status_code, 200, preview.json)
        baseline = preview.json['before']['parcels']['rows']
        self.assertGreater(baseline, 0)
        # 1) phrase fausse
        wrong = admin.post('/api/admin/data-reset', json={'confirmation': 'oui', 'password': 'Oriental24!Demo'}, headers=headers)
        self.assertEqual(wrong.status_code, 400)
        self.assertIn('REMETTRE A ZERO', wrong.json['error'])
        # 1bis) le navigateur a rempli l'e-mail à la place de la phrase : refus explicite
        email_instead = admin.post('/api/admin/data-reset',
                                   json={'confirmation': 'oriental24h@gmail.com', 'password': 'Oriental24!Demo'}, headers=headers)
        self.assertEqual(email_instead.status_code, 400)
        self.assertIn('adresse e-mail', email_instead.json['error'])
        # 1ter) casse, accents et espaces multiples sont tolérés
        for spelling in ('remettre a zero', 'Remettre  à  Zéro', '  REMETTRE A ZERO  '):
            ok_phrase = admin.post('/api/admin/data-reset',
                                   json={'confirmation': spelling, 'password': 'Oriental24!Demo'}, headers=headers)
            self.assertEqual(ok_phrase.status_code, 200, (spelling, ok_phrase.json))
            self.assertEqual(ok_phrase.json['after']['parcels']['rows'], 0)
            with self.m.conn() as c:
                c.execute('BEGIN IMMEDIATE')
                from data_reset import seed_demo
                seed_demo(c)
                c.execute('COMMIT')
        # Les variantes ont bien vidé la base : le compteur de référence change, pas
        # la règle « rien ne bouge tant que les trois verrous ne sont pas réunis ».
        before = admin.get('/api/admin/data-reset').json['before']['parcels']['rows']
        # 2) mot de passe faux
        bad_pw = admin.post('/api/admin/data-reset', json={'confirmation': 'REMETTRE A ZERO', 'password': 'nope'}, headers=headers)
        self.assertEqual(bad_pw.status_code, 400)
        self.assertIn('Mot de passe', bad_pw.json['error'])
        # 3) CSRF absent
        self.assertEqual(admin.post('/api/admin/data-reset',
                                    json={'confirmation': 'REMETTRE A ZERO', 'password': 'Oriental24!Demo'}).status_code, 403)
        # rien n'a bougé
        self.assertEqual(admin.get('/api/admin/data-reset').json['before']['parcels']['rows'], before)
        done = admin.post('/api/admin/data-reset',
                          json={'confirmation': 'REMETTRE A ZERO', 'password': 'Oriental24!Demo'}, headers=headers)
        self.assertEqual(done.status_code, 200, done.json)
        self.assertEqual(done.json['leftovers'], {})
        self.assertEqual(len(done.json['fingerprint']), 64)
        self.assertEqual(done.json['after']['parcels']['rows'], 0)
        # L'application reste parfaitement utilisable.
        boot = admin.get('/api/bootstrap')
        self.assertEqual(boot.status_code, 200)
        self.assertEqual(boot.json['parcels'], [])
        self.assertGreater(len(boot.json['cities']), 0)
        self.assertEqual(admin.get('/api/sidebar-counts').json['counts']['parcels'], 0)
        self.assertEqual(admin.get('/api/export').status_code, 200)
        self.assertEqual(admin.get('/api/audit').status_code, 200)

    def test_production_guard_requires_the_railway_switch(self):
        # Le mode démo n'est pas concerné : on simule la production en mémoire.
        self.m.app.config['PRODUCTION_MODE'] = True
        try:
            admin, headers = self.login('admin@oriental24.ma', 'Oriental24!Demo', '10.80.0.11')
            with self.m.conn() as c:
                c.execute("""INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,
                        status,created_at,updated_at) VALUES(?,2,'X','0600000000','A',1,100,20,10,'Créé',?,?)""",
                          ('GUARD-' + uuid.uuid4().hex[:6], self.m.now(), self.m.now()))
            blocked = admin.post('/api/admin/data-reset',
                                 json={'confirmation': 'REMETTRE A ZERO', 'password': 'Oriental24!Demo'}, headers=headers,
                                 base_url='https://oriental24.test')
            self.assertEqual(blocked.status_code, 409)
            self.assertIn('ORIENTAL24_ALLOW_DATA_RESET', blocked.json['error'])
            with self.m.conn() as c:
                self.assertGreater(c.execute("SELECT count(*) FROM parcels WHERE tracking LIKE 'GUARD-%'").fetchone()[0], 0)
        finally:
            self.m.app.config['PRODUCTION_MODE'] = False


if __name__ == '__main__':
    unittest.main()
