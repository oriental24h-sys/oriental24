import sqlite3
import tempfile
import unittest
from contextlib import contextmanager

import exchange_flow
from parcel_statuses import (STATUSES, DRIVER_TRANSITIONS, EXCHANGE_TO_RECOVER,
                             EXCHANGE_RECEIVED, policy)


class ExchangeFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = self.tmp.name + '/db.sqlite'

        @contextmanager
        def conn():
            c = sqlite3.connect(self.db)
            c.row_factory = sqlite3.Row
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise
            finally:
                c.close()

        self.conn = conn
        with conn() as c:
            c.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,role TEXT,active INTEGER,driver_hub_id INTEGER);
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT,active INTEGER);
            CREATE TABLE events(id INTEGER PRIMARY KEY,parcel_id INTEGER,actor_id INTEGER,status TEXT,note TEXT,created_at TEXT);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,tracking TEXT,client_id INTEGER,driver_id INTEGER,
                recipient TEXT,phone TEXT,address TEXT,city_id INTEGER,amount REAL,fee REAL,return_fee REAL,
                status TEXT,product TEXT,note TEXT,created_at TEXT,updated_at TEXT,current_hub_id INTEGER,
                open_allowed INTEGER NOT NULL DEFAULT 1,is_exchange INTEGER NOT NULL DEFAULT 0,
                exchange_of_id INTEGER,exchange_received_at TEXT,invoice_id INTEGER);
            INSERT INTO users VALUES(1,'Admin','admin',1,NULL),(2,'Hub A','agent',1,NULL),
                                    (3,'Livreur','livreur',1,10);
            INSERT INTO ops_hubs VALUES(10,'Hub A',1);
            INSERT INTO cities VALUES(1,'Agadir');
            ''')
            exchange_flow.migrate(c)

    def tearDown(self):
        self.tmp.cleanup()

    def log(self, store):
        def event(c, pid, status, note, actor):
            store.append((pid, status, note))
            c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',
                      (pid, actor['id'], status, note, '2026-10-28T10:00:00'))
        return event

    def seed(self, c, tracking='CMD100', is_exchange=1, status='Livré', driver=3):
        return c.execute('''INSERT INTO parcels(tracking,client_id,driver_id,recipient,phone,address,city_id,amount,
            fee,return_fee,status,product,note,created_at,updated_at,current_hub_id,open_allowed,is_exchange)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (tracking, 5, driver, 'Sara', '0611223344', 'Rue 1', 1, 150.0, 25.0, 10.0,
             status, 'Pull', 'note', '2026-10-27T09:00:00', '2026-10-27T09:00:00', 10, 1, is_exchange)).lastrowid

    def test_delivery_with_exchange_creates_recovery_order(self):
        events = self.log([])
        with self.conn() as c:
            pid = self.seed(c)
            created = exchange_flow.create_for_delivery(c, pid, {'id': 3, 'name': 'Livreur', 'role': 'livreur'},
                                                        events, lambda: '2026-10-28T11:00:00')
            self.assertEqual(created['tracking'], 'ECCMD100')
            row = c.execute('SELECT * FROM parcels WHERE id=?', (created['id'],)).fetchone()
            self.assertEqual(row['status'], EXCHANGE_TO_RECOVER)
            self.assertEqual(row['exchange_of_id'], pid)
            self.assertEqual(row['driver_id'], 3)
            self.assertEqual(row['current_hub_id'], 10)
            self.assertEqual(row['recipient'], 'Sara')
            self.assertEqual(row['amount'], 150.0)
            self.assertEqual(row['is_exchange'], 1)
            self.assertFalse(row['exchange_received_at'])
            self.assertEqual(len(c.execute('SELECT 1 FROM events WHERE parcel_id=?', (created['id'],)).fetchall()), 1)

    def test_creation_is_idempotent(self):
        events = self.log([])
        with self.conn() as c:
            pid = self.seed(c)
            first = exchange_flow.create_for_delivery(c, pid, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                      events, lambda: '2026-10-28T11:00:00')
            second = exchange_flow.create_for_delivery(c, pid, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                       events, lambda: '2026-10-28T11:05:00')
            self.assertEqual(first['id'], second['id'])
            self.assertEqual(c.execute('SELECT count(*) FROM parcels WHERE exchange_of_id=?', (pid,)).fetchone()[0], 1)

    def test_no_recovery_without_exchange_flag_or_without_delivery(self):
        events = self.log([])
        with self.conn() as c:
            plain = self.seed(c, tracking='CMD200', is_exchange=0)
            self.assertIsNone(exchange_flow.create_for_delivery(c, plain, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                                events, lambda: '2026-10-28T11:00:00'))
            not_delivered = self.seed(c, tracking='CMD201', status='En livraison')
            self.assertIsNone(exchange_flow.create_for_delivery(c, not_delivered, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                                events, lambda: '2026-10-28T11:00:00'))
            self.assertEqual(c.execute('SELECT count(*) FROM parcels').fetchone()[0], 2)

    def test_recovery_order_never_generates_another_one(self):
        events = self.log([])
        with self.conn() as c:
            pid = self.seed(c)
            created = exchange_flow.create_for_delivery(c, pid, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                        events, lambda: '2026-10-28T11:00:00')
            c.execute("UPDATE parcels SET status='Livré' WHERE id=?", (created['id'],))
            self.assertIsNone(exchange_flow.create_for_delivery(c, created['id'],
                                                                {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                                events, lambda: '2026-10-28T11:00:00'))
            self.assertEqual(c.execute('SELECT count(*) FROM parcels').fetchone()[0], 2)

    def test_hub_reception_releases_the_courier(self):
        events = self.log([])
        with self.conn() as c:
            pid = self.seed(c)
            created = exchange_flow.create_for_delivery(c, pid, {'id': 3, 'name': 'L', 'role': 'livreur'},
                                                        events, lambda: '2026-10-28T11:00:00')
            c.execute("UPDATE parcels SET status=? WHERE id=?", (EXCHANGE_RECEIVED, created['id']))
            result = exchange_flow.mark_received(c, created['id'], {'id': 2, 'name': 'Hub', 'role': 'agent',
                                                                    'agent_hub_id': 10}, events,
                                                 lambda: '2026-10-28T12:00:00')
            self.assertEqual(result['hub_id'], 10)
            row = c.execute('SELECT * FROM parcels WHERE id=?', (created['id'],)).fetchone()
            self.assertIsNone(row['driver_id'])
            self.assertEqual(row['current_hub_id'], 10)
            self.assertEqual(row['exchange_received_at'], '2026-10-28T12:00:00')

    def test_mark_received_ignores_plain_parcels(self):
        events = self.log([])
        with self.conn() as c:
            pid = self.seed(c, tracking='CMD300', is_exchange=0, status=EXCHANGE_RECEIVED)
            self.assertIsNone(exchange_flow.mark_received(c, pid, {'id': 2, 'role': 'agent', 'agent_hub_id': 10},
                                                          events, lambda: '2026-10-28T12:00:00'))

    def test_tracking_stays_unique(self):
        with self.conn() as c:
            self.seed(c, tracking='ECCMD400', is_exchange=0, status='Créé')
            self.assertEqual(exchange_flow.exchange_tracking(c, 'CMD400'), 'ECCMD400-2')
            self.assertEqual(exchange_flow.exchange_tracking(c, 'cmd 500'), 'ECCMD500')

    def test_new_statuses_are_never_courier_targets(self):
        for status in (EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED):
            self.assertIn(status, STATUSES)
            self.assertEqual(DRIVER_TRANSITIONS[status], [])
            self.assertNotIn(status, DRIVER_TRANSITIONS['En livraison'])
        self.assertEqual(DRIVER_TRANSITIONS['Livré'], [])
        self.assertEqual(policy()['rank'][EXCHANGE_RECEIVED], 5)


class ExchangeLockTests(unittest.TestCase):
    """L'état « Échange à récupérer » est verrouillé : seule la réception au Hub avance."""

    def test_courier_targets_are_empty_for_both_exchange_states(self):
        for status in (EXCHANGE_TO_RECOVER, EXCHANGE_RECEIVED):
            self.assertEqual(DRIVER_TRANSITIONS[status], [])

    def test_source_states_cannot_reach_exchange_statuses(self):
        for source, targets in DRIVER_TRANSITIONS.items():
            self.assertNotIn(EXCHANGE_TO_RECOVER, targets)
            self.assertNotIn(EXCHANGE_RECEIVED, targets)

    def test_exchange_statuses_are_out_of_courier_vocabulary(self):
        self.assertNotIn(EXCHANGE_TO_RECOVER, DRIVER_TRANSITIONS['En livraison'])
        self.assertNotIn(EXCHANGE_RECEIVED, DRIVER_TRANSITIONS['En livraison'])


if __name__ == '__main__':
    unittest.main()
