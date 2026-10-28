"""Stock-order parcel policies: reservation, validation and physical preparation.
Run in its own process: python -m unittest discover -s tests -p test_fulfillment_flags.py
"""
import importlib
import itertools
import json
import os
import tempfile
import unittest
import uuid


class FulfillmentFlagsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = {k: os.environ.get(k) for k in ('DB_PATH', 'ORIENTAL24_MODE')}
        os.environ.update(DB_PATH=cls.tmp.name + '/test.sqlite', ORIENTAL24_MODE='demo')
        cls.m = importlib.reload(importlib.import_module('app'))
        cls.m.app.config['TESTING'] = True
        with cls.m.conn() as c:
            cls.client_id = c.execute("SELECT id FROM users WHERE email='client@oriental24.ma'").fetchone()[0]
            cls.city = c.execute('SELECT id FROM cities WHERE delivery=1 LIMIT 1').fetchone()[0]
            cls.hub = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES('Test central',?,'',?)", (cls.city, cls.m.now())).lastrowid
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(cls.hub),))
            cls.product = c.execute("INSERT INTO products(client_id,name,reference,quantity,created_at) VALUES(?,'Policy test','POLICY-TEST',100,?)", (cls.client_id, cls.m.now())).lastrowid
        cls.client, cls.admin = cls.m.app.test_client(), cls.m.app.test_client()
        for browser, email in ((cls.client, 'client@oriental24.ma'), (cls.admin, 'admin@oriental24.ma')):
            response = browser.post('/api/login', json={'email': email, 'password': 'Oriental24!Demo'})
            assert response.status_code == 200, response.json
        cls.client_headers = {'X-CSRF-Token': cls.client.get('/api/bootstrap').json['csrf']}
        cls.admin_headers = {'X-CSRF-Token': cls.admin.get('/api/bootstrap').json['csrf']}

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.tmp.cleanup()

    def payload(self, **flags):
        return dict(recipient='Test Recipient', phone='0612345678', address='Agadir',
                    city_id=self.city, amount=120, note='Keep this note',
                    items=[{'product_id': self.product, 'quantity': 1}],
                    request_key=uuid.uuid4().hex, **flags)

    def reserve(self, payload, admin=False):
        browser, headers = (self.admin, self.admin_headers) if admin else (self.client, self.client_headers)
        r = browser.post('/api/fulfillment/orders', json=payload, headers=headers)
        self.assertEqual(r.status_code, 200, r.json)
        oid = r.json['id']
        detail = browser.get(f'/api/fulfillment/orders/{oid}')
        self.assertEqual(detail.status_code, 200, detail.json)
        return oid, detail.json

    def ship(self, oid, expected):
        r = self.admin.post(f'/api/fulfillment/orders/{oid}/ship',
                            json={'hub_id': self.hub, 'checked': True}, headers=self.admin_headers)
        self.assertEqual(r.status_code, 200, r.json)
        detail = self.client.get(f'/api/fulfillment/orders/{oid}').json
        with self.m.conn() as c:
            parcel = c.execute('SELECT open_allowed,is_exchange,note FROM parcels WHERE id=?', (detail['parcel_id'],)).fetchone()
            self.assertEqual(tuple(parcel), (*expected, 'Keep this note'))
            self.assertEqual(c.execute('SELECT count(*) FROM movements WHERE fulfillment_order_id=? AND delta=-1', (oid,)).fetchone()[0], 1)
        # The same policies are available to the existing label renderer.
        labels = self.client.post('/api/labels', json={'ids': [detail['parcel_id']]}, headers=self.client_headers)
        self.assertEqual(labels.status_code, 200, labels.json)
        self.assertEqual((labels.json[0]['open_allowed'], labels.json[0]['is_exchange']), expected)

    def test_all_flag_combinations_persist_to_parcel(self):
        for no_open, exchange in itertools.product((False, True), repeat=2):
            with self.subTest(no_open=no_open, exchange=exchange):
                payload = self.payload(not_allowed_to_open=no_open, is_exchange=exchange)
                oid, detail = self.reserve(payload)
                expected = (int(not no_open), int(exchange))
                self.assertEqual((detail['shipping']['open_allowed'], detail['shipping']['is_exchange']), expected)
                retry = self.client.post('/api/fulfillment/orders', json=payload, headers=self.client_headers)
                self.assertEqual(retry.status_code, 200, retry.json)
                self.assertTrue(retry.json['already_created'])
                self.assertEqual(retry.json['id'], oid)
                conflict = self.client.post('/api/fulfillment/orders', json={**payload, 'is_exchange': not exchange}, headers=self.client_headers)
                self.assertEqual(conflict.status_code, 409)
                self.ship(oid, expected)

    def test_omitted_flags_keep_existing_defaults(self):
        oid, detail = self.reserve(self.payload())
        self.assertEqual((detail['shipping']['open_allowed'], detail['shipping']['is_exchange']), (1, 0))
        self.ship(oid, (1, 0))

    def test_legacy_reservation_without_flags_can_ship(self):
        oid, detail = self.reserve(self.payload())
        shipping = detail['shipping']
        shipping.pop('open_allowed')
        shipping.pop('is_exchange')
        with self.m.conn() as c:
            c.execute('UPDATE fulfillment_orders SET shipping=? WHERE id=?', (json.dumps(shipping), oid))
        self.ship(oid, (1, 0))

    def test_admin_can_reserve_both_flags(self):
        oid, detail = self.reserve(self.payload(client_id=self.client_id, not_allowed_to_open=True, is_exchange=True), admin=True)
        self.assertEqual((detail['shipping']['open_allowed'], detail['shipping']['is_exchange']), (0, 1))
        self.ship(oid, (0, 1))

    def test_non_boolean_flags_rejected_without_reservation(self):
        for flag in ('not_allowed_to_open', 'is_exchange'):
            for value in ('false', 'true', 'on', 0, 1, None, [], {}):
                with self.subTest(flag=flag, value=value):
                    payload = self.payload(**{flag: value})
                    r = self.client.post('/api/fulfillment/orders', json=payload, headers=self.client_headers)
                    self.assertEqual(r.status_code, 400, r.json)
                    with self.m.conn() as c:
                        self.assertIsNone(c.execute('SELECT id FROM fulfillment_orders WHERE request_key=?', (payload['request_key'],)).fetchone())


if __name__ == '__main__':
    unittest.main()
