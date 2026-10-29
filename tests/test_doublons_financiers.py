"""Doublons financiers : ce que le système protège déjà, et le trou encore ouvert.

Suite issue de la revue du 29/10/2026. Elle fige les protections vérifiées à la main
(facture, échange, palette, réception) **et documente** le seul écart restant :
`POST /api/parcels` n'a pas de clé d'idempotence (deux clients identiques peuvent créer
deux CMD). Ce dernier cas est marqué `expectedFailure` : dès que l'idempotence sera
ajoutée, le test passera et signalera qu'il faut retirer le décorateur.
"""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash


class DoublonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env_backup = {}
        for key, value in (('DB_PATH', cls.tmp.name + '/doublons.sqlite'),
                           ('ORIENTAL24_MODE', 'demo'),
                           ('TZ', 'Africa/Casablanca')):
            import os
            cls.env_backup[key] = os.environ.get(key)
            os.environ[key] = value
        import app as module
        module.app.config['TESTING'] = True
        cls.m = module
        adm = module.app.test_client()
        adm.post('/api/login', json={'email': 'admin@oriental24.ma', 'password': 'Oriental24!Demo'})
        cls.boot = adm.get('/api/bootstrap').json
        cls.T = '2026-02-01T09:00:00'
        with module.conn() as c:
            cls.hub = c.execute("INSERT INTO ops_hubs(name,city_id,address,active,created_at) "
                                "VALUES('HUB TEST',?,'A',1,?)", (cls.boot['cities'][0]['id'], cls.T)).lastrowid
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) "
                      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(cls.hub),))
            c.execute("INSERT OR REPLACE INTO hub_cities(hub_id,city_id,active,is_primary,created_at) "
                      "VALUES(?,?,1,1,?)", (cls.hub, cls.boot['cities'][0]['id'], cls.T))

    @classmethod
    def tearDownClass(cls):
        import os
        for key, value in cls.env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.tmp.cleanup()

    # ---------- utilitaires ----------
    def admin(self):
        cl = self.m.app.test_client()
        cl.post('/api/login', json={'email': 'admin@oriental24.ma', 'password': 'Oriental24!Demo'})
        return cl, {'X-CSRF-Token': cl.get('/api/bootstrap').json['csrf']}

    def make_client(self, tag, kind='vendeur'):
        with self.m.conn() as c:
            uid = c.execute("""INSERT INTO users(name,email,password,role,company,phone,active,client_type,created_at)
                               VALUES(?,?,?,'client',?,'0600000000',1,?,?)""",
                            (tag, tag.lower() + '@t.ma', generate_password_hash('MotDePasse!2026'), tag, kind, self.T)).lastrowid
        cl = self.m.app.test_client()
        cl.post('/api/login', json={'email': tag.lower() + '@t.ma', 'password': 'MotDePasse!2026'})
        return uid, cl, {'X-CSRF-Token': cl.get('/api/bootstrap').json['csrf']}

    def parcel(self, tracking, client_id, status='Livré', **extra):
        with self.m.conn() as c:
            pid = c.execute("""INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,
                               return_fee,status,product,note,open_allowed,is_exchange,is_fragile,created_at,updated_at,
                               current_hub_id,origin_hub_id)
                               VALUES(?,?,'D','0600000000','R',?,250,20,10,?,'','',1,?,0,?,?,?,?)""",
                            (tracking, client_id, self.boot['cities'][0]['id'], status,
                             1 if extra.get('is_exchange') else 0, self.T, self.T,
                             self.hub, self.hub)).lastrowid
            return pid

    # ---------- protection 1 : facture ----------
    def test_facture_double_clic_ne_cree_qu_une_facture(self):
        uid, _cl, _h = self.make_client('FAC1')
        self.parcel('FAC1-1', uid)
        adm, ah = self.admin()
        first = adm.post('/api/invoices', json={'client_id': uid}, headers=ah)
        second = adm.post('/api/invoices', json={'client_id': uid}, headers=ah)
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertGreaterEqual(second.status_code, 400, second.get_json())
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) n FROM invoices WHERE client_id=?', (uid,)).fetchone()['n'], 1)

    def test_facture_concurrente_ne_cree_qu_une_facture(self):
        uid, _cl, _h = self.make_client('FAC2')
        self.parcel('FAC2-1', uid)
        codes = []

        def generate():
            cl, h = self.admin()
            codes.append(cl.post('/api/invoices', json={'client_id': uid}, headers=h).status_code)

        threads = [threading.Thread(target=generate) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) n FROM invoices WHERE client_id=?', (uid,)).fetchone()['n'], 1)
        self.assertIn(200, codes)

    def test_facture_exacte_au_centime_et_detaillee(self):
        uid, _cl, _h = self.make_client('FAC3')
        self.parcel('FAC3-1', uid)
        self.parcel('FAC3-2', uid, status='Refusé')
        adm, ah = self.admin()
        adm.post('/api/invoices', json={'client_id': uid}, headers=ah)
        with self.m.conn() as c:
            invoice = c.execute('SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC LIMIT 1', (uid,)).fetchone()
            # totaux en centimes exacts : 250.00 livré - (20.00 frais + 10.00 retour)
            self.assertEqual(invoice['cod_cents'], 25000)
            self.assertEqual(invoice['fees_cents'], 3000)
            self.assertEqual(invoice['total_cents'], 22000)
            self.assertEqual(round(invoice['cod'] - invoice['fees'], 2), 220.0)
            lines = c.execute('SELECT count(*) n FROM invoice_lines WHERE invoice_id=?', (invoice['id'],)).fetchone()['n']
            self.assertEqual(lines, 2)
            detail = adm.get('/api/invoices/%d' % invoice['id'], headers=ah).json
            self.assertEqual(len(detail['lines']), 2)
            self.assertEqual(detail['lines_total_cents'], 22000)

    # ---------- protection 2 : échange ----------
    def test_echange_livre_deux_fois_ne_cree_qu_une_reprise(self):
        uid, _cl, _h = self.make_client('ECH1')
        pid = self.parcel('ECH1-1', uid, status='Ramassé', is_exchange=True)
        with self.m.conn() as c:
            c.execute("INSERT INTO users(name,email,password,role,company,phone,active,client_type,created_at,driver_hub_id) "
                      "VALUES('L','l1@t.ma',?,'livreur','H','',1,'vendeur',?,?)",
                      (generate_password_hash('MotDePasse!2026'), self.T, self.hub))
            drv = c.execute("SELECT id FROM users WHERE email='l1@t.ma'").fetchone()['id']
            c.execute('UPDATE parcels SET driver_id=? WHERE id=?', (drv, pid))
        cl = self.m.app.test_client()
        cl.post('/api/login', json={'email': 'l1@t.ma', 'password': 'MotDePasse!2026'})
        h = {'X-CSRF-Token': cl.get('/api/bootstrap').json['csrf']}
        self.assertEqual(cl.patch('/api/parcels/%d' % pid, json={'status': 'Livré'}, headers=h).status_code, 200)
        cl.patch('/api/parcels/%d' % pid, json={'status': 'Livré'}, headers=h)
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) n FROM parcels WHERE exchange_of_id=?', (pid,)).fetchone()['n'], 1)

    # ---------- protection 3 : identité de tracking ----------
    def test_meme_tracking_deux_societes_autorise_une_seule_fois_par_societe(self):
        uid_a, cl_a, h_a = self.make_client('SOCI', 'societe_livraison')
        uid_b, _cl_b, _h_b = self.make_client('SOCJ', 'societe_livraison')
        body = {'tracking': 'SHARED-1', 'recipient': 'X', 'phone': '0600000000',
                'city_id': self.boot['cities'][0]['id'], 'amount': 100}
        self.assertEqual(cl_a.post('/api/parcels', json=body, headers=h_a).status_code, 200)
        again = cl_a.post('/api/parcels', json=body, headers=h_a)
        self.assertEqual(again.status_code, 409, again.get_json())
        with self.m.conn() as c:
            self.assertEqual(c.execute("SELECT count(*) n FROM parcels WHERE client_id=?", (uid_a,)).fetchone()['n'], 1)

    def test_index_unique_par_client_existe(self):
        with self.m.conn() as c:
            row = c.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name='parcels_client_tracking_unique'").fetchone()
        self.assertIsNotNone(row, 'index unique (client_id, tracking) attendu')

    # ---------- horloge ----------
    def test_heure_marocaine_est_utilisee(self):
        self.assertEqual(self.m.app.config.get('TIMEZONE'), 'Africa/Casablanca')
        import datetime
        expected = datetime.datetime.now().date().isoformat()
        self.assertTrue(self.m.now().startswith(expected))

    # ---------- écart documenté : idempotence de création de CMD ----------
    @unittest.expectedFailure
    def test_creation_cmd_double_doit_etre_idempotente(self):
        uid, cl, h = self.make_client('DUP1')
        body = {'recipient': 'X', 'phone': '0600000000', 'city_id': self.boot['cities'][0]['id'], 'amount': 100}
        cl.post('/api/parcels', json=body, headers=h)
        cl.post('/api/parcels', json=body, headers=h)
        with self.m.conn() as c:
            count = c.execute('SELECT count(*) n FROM parcels WHERE client_id=?', (uid,)).fetchone()['n']
        # Aujourd'hui : 2 CMD (pas de clé d'idempotence) -> expectedFailure.
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
