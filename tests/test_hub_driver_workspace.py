"""Real HTTP regression tests on an isolated demo database, never a live DB."""
import importlib
import os
import tempfile
import unittest
import uuid


class HubDriverWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = {k: os.environ.get(k) for k in ('DB_PATH', 'ORIENTAL24_MODE')}
        os.environ['DB_PATH'] = cls.tmp.name + '/test.sqlite'
        os.environ['ORIENTAL24_MODE'] = 'demo'
        cls.m = importlib.import_module('app')
        cls.m.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        for k,v in cls.env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        cls.tmp.cleanup()

    def setUp(self):
        from werkzeug.security import generate_password_hash
        m = self.m
        unique = uuid.uuid4().hex
        with m.conn() as c:
            city = c.execute('SELECT id FROM cities LIMIT 1').fetchone()[0]
            self.city = city
            self.hub = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)", ('Local '+unique,city,m.now())).lastrowid
            self.foreign = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)", ('Other '+unique,city,m.now())).lastrowid
            self.email = unique+'@example.test'
            self.manager = c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,'hub_manager',?,?)",('Manager',self.email,generate_password_hash('TestPassword!123'),self.hub,m.now())).lastrowid
            self.driver = c.execute("INSERT INTO users(name,email,password,role,driver_hub_id,created_at) VALUES(?,?,'unused','livreur',?,?)",('Local Driver','driver'+self.email,self.hub,m.now())).lastrowid
            self.other_driver = c.execute("INSERT INTO users(name,email,password,role,driver_hub_id,created_at) VALUES(?,?,'unused','livreur',?,?)",('Foreign Driver','other'+self.email,self.foreign,m.now())).lastrowid
            self.client_id=c.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()[0]
            c.execute("INSERT INTO driver_terms VALUES(?,'gross',1500,500,500,1,1,?)",(self.driver,m.now()))
        self.client=m.app.test_client()
        r=self.client.post('/api/login',json={'email':self.email,'password':'TestPassword!123'})
        self.assertEqual(r.status_code,200,r.json)
        r=self.client.get('/api/bootstrap')
        self.assertEqual(r.status_code,200,r.json)
        self.headers={'X-CSRF-Token':r.json['csrf']}

    def post(self,path,data):
        return self.client.post('/api/'+path,json=data,headers=self.headers)

    def parcel(self,hub=None,status='Réceptionné',driver=None,assignment=None):
        m=self.m;tracking='TEST-'+uuid.uuid4().hex
        with m.conn() as c:
            pid=c.execute('''INSERT INTO parcels(tracking,client_id,driver_id,recipient,phone,address,city_id,amount,fee,return_fee,status,product,note,created_at,updated_at,current_hub_id)
                VALUES(?,?,?,'Recipient','0600000000','Test address',?,100,25,10,?,'','',?,?,?)''',
                (tracking,self.client_id,driver,self.city,status,m.now(),m.now(),hub)).lastrowid
            if assignment:
                c.execute('INSERT INTO ops_assignments(parcel_id,new_driver_id,actor_id,created_at,hub_id) VALUES(?,?,?,?,?)',(pid,driver,self.manager,m.now(),assignment))
        return pid,tracking

    def scan(self,mode,items,hub=None,key=None,driver=None):
        return self.post(f'drivers-workspace/{driver or self.driver}/scan-batch',dict(mode=mode,scans=[dict(parcel_id=p,revision=r) for p,r in items],hub_id=hub,request_key=key or uuid.uuid4().hex,confirmed=True))

    def test_assign_receive_and_replay(self):
        pid,tracking=self.parcel(self.hub)
        preview=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='assign'))
        self.assertEqual(preview.status_code,200,preview.json)
        key=uuid.uuid4().hex
        r=self.scan('assign',[(pid,0)],key=key);self.assertEqual(r.status_code,200,r.json)
        r=self.scan('assign',[(pid,0)],key=key);self.assertTrue(r.json['replayed'])
        r=self.client.get(f'/api/drivers-workspace/{self.driver}');self.assertEqual([p['id'] for p in r.json['parcels']],[pid])
        r=self.client.get('/api/logistics/hub/drivers');self.assertEqual(r.json['drivers'][0]['outstanding'],1)
        r=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='receive'));self.assertEqual(r.status_code,200,r.json)
        r=self.scan('receive',[(pid,1)]);self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['current_hub_id'],p['driver_id'],p['status']),(self.hub,None,'Réceptionné'))

    def test_cross_hub_driver_and_parcel_denied_atomic_batch(self):
        pid,_=self.parcel(self.hub);foreign,tracking=self.parcel(self.foreign)
        r=self.scan('assign',[(pid,0),(foreign,0)]);self.assertEqual(r.status_code,404,r.json)
        with self.m.conn() as c:self.assertIsNone(c.execute('SELECT driver_id FROM parcels WHERE id=?',(pid,)).fetchone()[0])
        r=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='assign'));self.assertEqual(r.status_code,404)
        r=self.scan('assign',[(pid,0)],driver=self.other_driver);self.assertEqual(r.status_code,404)
        self.assertEqual(self.client.get(f'/api/drivers-workspace/{self.other_driver}').status_code,404)

    def test_return_hub_tampering_and_stale_revision(self):
        pid,_=self.parcel(None,'Reçu par le livreur',self.driver,self.hub)
        self.assertEqual(self.scan('receive',[(pid,0)],self.foreign).status_code,403)
        self.assertEqual(self.scan('receive',[(pid,99)],self.hub).status_code,409)

    def test_closed_recovery_keeps_financial_attribution(self):
        pid,_=self.parcel(None,'Refusé',self.driver,self.hub)
        r=self.scan('receive',[(pid,0)]);self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['status'],p['driver_id'],p['current_hub_id']),('Refusé',self.driver,self.hub))
        pid,_=self.parcel(None,'Livré',self.driver,self.hub)
        self.assertEqual(self.scan('receive',[(pid,0)]).status_code,409)

    def test_invoice_scope_confirm_and_no_payment_permissions(self):
        local,_=self.parcel(None,'Livré',self.driver,self.hub)
        self.parcel(None,'Livré',self.driver,self.foreign)
        self.parcel(None,'Livré',self.driver) # unknown legacy evidence: Admin only
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        self.assertEqual([p['parcel_id'] for p in r.json['lines']],[local]);token=r.json['token']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertEqual(r.status_code,200,r.json);sid=r.json['statement_id']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertTrue(r.json['already_created'])
        r=self.client.get(f'/api/driver-finance/statements/{sid}');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['statement']['hub_id'],self.hub)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/transactions',{}).status_code,403)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/cancel',{}).status_code,403)
        self.assertEqual(self.post('driver-finance/preview',dict(driver_id=self.other_driver)).status_code,404)
        with self.m.conn() as c:c.execute('UPDATE driver_statements SET hub_id=? WHERE id=?',(self.foreign,sid))
        self.assertEqual(self.client.get(f'/api/driver-finance/statements/{sid}').status_code,404)

    def test_inactive_hub_and_csrf(self):
        pid,_=self.parcel(self.hub)
        r=self.client.post(f'/api/drivers-workspace/{self.driver}/scan-preview',json={'tracking':'anything','mode':'assign'});self.assertEqual(r.status_code,403)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,403)
        self.assertEqual(self.post('driver-finance/preview',dict(driver_id=self.driver)).status_code,403)

    def test_preassigned_physical_dispatch_records_hub(self):
        pid,_=self.parcel(self.hub,driver=self.driver)
        r=self.scan('assign',[(pid,0)]);self.assertEqual(r.status_code,200,r.json)
        r=self.scan('receive',[(pid,1)]);self.assertEqual(r.status_code,200,r.json)

    def status_patch(self,pid,status,revision=0,**fields):
        return self.client.patch(f'/api/parcels/{pid}',json={'status':status,'revision':revision,**fields},headers=self.headers)

    def test_manager_status_change_and_audit(self):
        pid,_=self.parcel(self.hub)
        r=self.status_patch(pid,'Reporté',note='Client indisponible')
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['status'],p['ops_revision'],p['current_hub_id']),('Reporté',1,self.hub))
            e=c.execute('SELECT * FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
            self.assertEqual((e['actor_id'],e['status']),(self.manager,'Reporté'))
        self.assertEqual(self.status_patch(pid,'Intéressé',revision=1).status_code,200)

    def test_delivered_and_returned_are_immutable_for_manager(self):
        for final in ('Livré','Retourné'):
            with self.subTest(final=final):
                pid,_=self.parcel(self.hub,final,self.driver,self.hub)
                for target in ('Réceptionné','Reporté',final):
                    r=self.status_patch(pid,target)
                    self.assertEqual(r.status_code,409,r.json)
                with self.m.conn() as c:
                    p=c.execute('SELECT status,ops_revision FROM parcels WHERE id=?',(pid,)).fetchone()
                    self.assertEqual(tuple(p),(final,0))

    def test_manager_can_close_open_parcel_but_not_reopen(self):
        for target in ('Livré','Retourné'):
            with self.subTest(target=target):
                pid,_=self.parcel(self.hub,'En livraison',self.driver,self.hub)
                r=self.status_patch(pid,target)
                self.assertEqual(r.status_code,200,r.json)
                self.assertEqual(self.status_patch(pid,'En livraison',revision=1).status_code,409)
        # Refusé is not one of the two immutable statuses requested.
        pid,_=self.parcel(self.hub,'Refusé',self.driver,self.hub)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,200)

    def test_status_scope_fields_revision_csrf_and_inactive_hub(self):
        pid,_=self.parcel(self.hub)
        foreign,_=self.parcel(self.foreign)
        self.assertEqual(self.status_patch(foreign,'Reporté').status_code,404)
        self.assertEqual(self.status_patch(pid,'Reporté',driver_id=self.other_driver).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',amount=1).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',revision=True).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',revision=99).status_code,409)
        self.assertEqual(self.status_patch(pid,'Unknown').status_code,400)
        self.assertEqual(self.status_patch(pid,'Vers Hub Central').status_code,409)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}',json={'status':'Reporté','revision':0}).status_code,403)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}',json={'status':'Reporté'},headers=self.headers).status_code,403)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,403)

    def test_status_keeps_invoice_and_document_locks(self):
        pid,_=self.parcel(self.hub)
        with self.m.conn() as c:
            invoice=c.execute('INSERT INTO invoices(client_id,created_at) VALUES(?,?)',(self.client_id,self.m.now())).lastrowid
            c.execute('UPDATE parcels SET invoice_id=? WHERE id=?',(invoice,pid))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)
        pid,tracking=self.parcel(self.hub)
        with self.m.conn() as c:
            doc=c.execute("INSERT INTO ops_documents(reference,kind,note,created_by,created_at,source_hub_id) VALUES(?,'transfer','',?,?,?)",('DOC-'+uuid.uuid4().hex,self.manager,self.m.now(),self.hub)).lastrowid
            c.execute("INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,'Test','Test','Réceptionné')",(doc,pid,tracking))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)
        # Financial line guard still applies to non-final source statuses too.
        pid,_=self.parcel(self.hub,'Refusé',self.driver,self.hub)
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        r=self.post(f"driver-finance/preview/{r.json['token']}/confirm",{});self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)

    def test_manager_scheduling_and_otp_checks_preserved(self):
        from datetime import datetime,timedelta
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.status_patch(pid,'Programmé').status_code,400)
        with self.m.conn() as c:
            reason=c.execute('SELECT code FROM ops_reasons WHERE active=1 LIMIT 1').fetchone()[0]
        future=(datetime.now()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        r=self.status_patch(pid,'Programmé',reason_code=reason,next_attempt_at=future)
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:c.execute("UPDATE parcels SET otp_required=1,otp_code='1234' WHERE id=?",(pid,))
        self.assertEqual(self.status_patch(pid,'Livré',revision=1).status_code,400)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='9999').status_code,400)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='1234').status_code,200)

    def test_admin_can_still_correct_final_status(self):
        pid,_=self.parcel(self.hub,'Livré',self.driver,self.hub)
        admin=self.m.app.test_client()
        r=admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'})
        self.assertEqual(r.status_code,200,r.json)
        csrf=admin.get('/api/bootstrap').json['csrf']
        r=admin.patch(f'/api/parcels/{pid}',json={'status':'Reporté','revision':0,'note':'Correction administrative'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200,r.json)

if __name__=='__main__': unittest.main()
