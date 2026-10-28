"""Real authenticated requests against an isolated database, never the preview DB."""
import importlib
import os
import tempfile
import unittest
import uuid


class CentralHubPreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werkzeug.security import generate_password_hash
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = {k: os.environ.get(k) for k in ('DB_PATH', 'ORIENTAL24_MODE')}
        os.environ.update(DB_PATH=cls.tmp.name+'/test.sqlite', ORIENTAL24_MODE='demo')
        cls.m = importlib.reload(importlib.import_module('app'))
        cls.m.app.config['TESTING'] = True
        with cls.m.conn() as c:
            cls.city = c.execute('SELECT id FROM cities WHERE delivery=1 LIMIT 1').fetchone()[0]
            cls.client_id = c.execute("SELECT id FROM users WHERE email='client@oriental24.ma'").fetchone()[0]
            cls.central, cls.other = [c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)", (name,cls.city,cls.m.now())).lastrowid for name in ('Central preparation test','Other preparation test')]
            cls.product = c.execute("INSERT INTO products(client_id,name,reference,quantity,created_at) VALUES(?,'Test product','CENTRAL-TEST',100,?)", (cls.client_id,cls.m.now())).lastrowid
            cls.manager_ids = {}
            for name, role, hub in (('central','hub_manager',cls.central),('other','hub_manager',cls.other),('unassigned','hub_manager',None)):
                cls.manager_ids[name] = c.execute('INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,?,?,?)', (name,name+'@prep.test',generate_password_hash('PreparationTest!123'),role,hub,cls.m.now())).lastrowid
        cls.browsers = {}
        cls.headers = {}
        for index, name in enumerate(('client','admin','central','other','unassigned')):
            browser = cls.m.app.test_client()
            email = name+'@oriental24.ma' if name in ('client','admin') else name+'@prep.test'
            password = 'Oriental24!Demo' if name in ('client','admin') else 'PreparationTest!123'
            r = browser.post('/api/login', json={'email':email,'password':password}, environ_overrides={'REMOTE_ADDR':f'10.89.0.{index+1}'})
            assert r.status_code == 200, r.json
            cls.browsers[name] = browser
            cls.headers[name] = {'X-CSRF-Token':browser.get('/api/bootstrap').json['csrf']}

    @classmethod
    def tearDownClass(cls):
        for key,value in cls.env.items():
            if value is None: os.environ.pop(key,None)
            else: os.environ[key]=value
        cls.tmp.cleanup()

    def setUp(self):
        with self.m.conn() as c:
            c.execute('UPDATE ops_hubs SET active=1 WHERE id=?',(self.central,))
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(self.central),))
            c.execute('UPDATE users SET agent_hub_id=? WHERE id=?',(self.central,self.manager_ids['central']))
        self.payload = dict(recipient='Recipient',phone='0612345678',address='Agadir',city_id=self.city,amount=200,note='Fragile',not_allowed_to_open=True,is_exchange=True,request_key=uuid.uuid4().hex,items=[{'product_id':self.product,'quantity':2}])
        r = self.post('client','/api/fulfillment/orders',self.payload)
        self.assertEqual(r.status_code,200,r.json)
        self.oid = r.json['id']
        self.path = f'/api/fulfillment/orders/{self.oid}'

    def post(self,who,path,data):
        return self.browsers[who].post(path,json=data,headers=self.headers[who])

    def ship(self,who='central',**overrides):
        return self.post(who,self.path+'/ship',dict(hub_id=self.central,checked=True,**overrides))

    def test_central_manager_reads_queue_detail_and_configuration(self):
        for role in ('central',):
            r=self.browsers[role].get('/api/fulfillment/orders')
            self.assertEqual(r.status_code,200,r.json)
            self.assertIn(self.oid,[o['id'] for o in r.json])
            detail=self.browsers[role].get(self.path)
            self.assertEqual(detail.status_code,200,detail.json)
            self.assertEqual(detail.json['shipping']['note'],'Fragile')
            self.assertEqual(detail.json['lines'][0]['quantity'],2)
            self.assertTrue(detail.json['city'])
            config=self.browsers[role].get('/api/logistics/config')
            self.assertEqual(config.status_code,200,config.json)
            self.assertEqual(config.json['central_hub_id'],self.central)
            self.assertEqual([h['id'] for h in config.json['hubs']],[self.central])

    def test_central_manager_prepares_once_and_preserves_policies(self):
        with self.m.conn() as c:
            quantity=c.execute('SELECT quantity FROM products WHERE id=?',(self.product,)).fetchone()[0]
        r=self.ship()
        self.assertEqual(r.status_code,200,r.json)
        detail=self.browsers['central'].get(self.path)
        self.assertEqual(detail.status_code,200,detail.json)
        o=detail.json
        self.assertEqual(o['status'],'Préparé')
        self.assertEqual(o['dispatch_hub_id'],self.central)
        self.assertEqual(o['processed_by'],self.manager_ids['central'])
        self.assertTrue(o['stock_deducted_at'])
        self.assertEqual(self.browsers['central'].get(f"/api/parcels/{o['parcel_id']}").status_code,200)
        self.assertEqual(self.ship().status_code,409)
        with self.m.conn() as c:
            parcel=c.execute('SELECT * FROM parcels WHERE id=?',(o['parcel_id'],)).fetchone()
            self.assertEqual((parcel['current_hub_id'],parcel['status']), (self.central,'Ramassé'))
            self.assertEqual((parcel['open_allowed'],parcel['is_exchange']),(0,1))
            self.assertEqual(c.execute('SELECT quantity FROM products WHERE id=?',(self.product,)).fetchone()[0],quantity-2)
            self.assertEqual(c.execute('SELECT count(*) FROM movements WHERE fulfillment_order_id=?',(self.oid,)).fetchone()[0],1)

    def test_legacy_agent_role_is_not_authorized(self):
        # Runtime authorization uses the canonical role. Legacy DB rows are migrated
        # to hub_manager at startup; a manually reintroduced alias must not bypass it.
        with self.m.conn() as c:
            c.execute("UPDATE users SET role='agent' WHERE id=?",(self.manager_ids['central'],))
        try:
            self.assertEqual(self.browsers['central'].get('/api/fulfillment/orders').status_code,403)
            self.assertEqual(self.ship().status_code,403)
        finally:
            with self.m.conn() as c:
                c.execute("UPDATE users SET role='hub_manager' WHERE id=?",(self.manager_ids['central'],))

    def test_other_hub_and_unassigned_manager_denied(self):
        for role in ('other','unassigned'):
            for path in ('/api/fulfillment/orders',self.path):
                self.assertEqual(self.browsers[role].get(path).status_code,403)
            self.assertEqual(self.ship(role).status_code,403)

    def test_inactive_missing_or_changed_central_denied(self):
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.central,))
        for path in ('/api/fulfillment/orders',self.path):
            self.assertEqual(self.browsers['central'].get(path).status_code,403)
        self.assertEqual(self.ship().status_code,403)
        with self.m.conn() as c:
            c.execute('UPDATE ops_hubs SET active=1 WHERE id=?',(self.central,))
            c.execute("DELETE FROM settings WHERE key='central_hub_id'")
        self.assertEqual(self.ship().status_code,403)
        with self.m.conn() as c:
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?)",(str(self.other),))
        self.assertEqual(self.browsers['central'].get('/api/fulfillment/orders').status_code,403)
        self.assertEqual(self.ship().status_code,403)

    def test_reassignment_takes_effect_without_relogin(self):
        with self.m.conn() as c:
            vacant=c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES('Reassigned hub',?,'',?)",(self.city,self.m.now())).lastrowid
            c.execute('UPDATE users SET agent_hub_id=? WHERE id=?',(vacant,self.manager_ids['central']))
        self.assertEqual(self.browsers['central'].get(self.path).status_code,403)
        self.assertEqual(self.ship().status_code,403)

    def test_wrong_hub_or_missing_physical_confirmation_does_not_mutate(self):
        for data,status in (({'hub_id':self.other,'checked':True},409),({'hub_id':self.central,'checked':False},400),({'hub_id':self.central},400),({'hub_id':self.central,'checked':'true'},400)):
            r=self.post('central',self.path+'/ship',data)
            self.assertEqual(r.status_code,status,r.json)
        with self.m.conn() as c:
            order=c.execute('SELECT status,parcel_id,stock_deducted_at FROM fulfillment_orders WHERE id=?',(self.oid,)).fetchone()
            self.assertEqual(tuple(order),('Réservé',None,None))
            self.assertEqual(c.execute('SELECT count(*) FROM movements WHERE fulfillment_order_id=?',(self.oid,)).fetchone()[0],0)

    def test_unrelated_manager_actions_remain_denied(self):
        for path,payload in (('/api/fulfillment/orders',self.payload),(self.path+'/cancel',{'reason':'Not permitted'}),(self.path+'/restock',{'checked':True})):
            self.assertEqual(self.post('central',path,payload).status_code,403)
        self.assertEqual(self.browsers['central'].get('/api/fulfillment/analytics').status_code,403)
        self.assertEqual(self.ship('client').status_code,403)

    def test_cancelled_reservation_not_preparable(self):
        r=self.post('client',self.path+'/cancel',{'reason':'Client cancelled'})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.browsers['central'].get(self.path).status_code,404)
        self.assertEqual(self.ship().status_code,404)
        rows=self.browsers['central'].get('/api/fulfillment/orders').json
        self.assertNotIn(self.oid,[o['id'] for o in rows])


if __name__=='__main__':unittest.main()
