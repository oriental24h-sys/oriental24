"""Authenticated partner intake: company + Central Hub => Ramassé, not Réceptionné."""
import base64
import io
import unittest
import uuid
import test_fulfillment_flags as fixture


class CompanyCentralIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werkzeug.security import generate_password_hash
        fixture.FulfillmentFlagsTests.setUpClass()
        cls.t=fixture.FulfillmentFlagsTests();cls.m=cls.t.m
        cls.admin=cls.t.admin;cls.admin_headers=cls.t.admin_headers
        with cls.m.conn() as c:
            cls.company=c.execute("INSERT INTO users(name,email,password,role,client_type,company,created_at) VALUES('Company','intake-company@test.invalid','unused','client','societe_livraison','Company',?)",(cls.m.now(),)).lastrowid
            cls.other=c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES('Other intake hub',?,'',?)",(cls.t.city,cls.m.now())).lastrowid
            c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES('Manager','intake-manager@test.invalid',?,'hub_manager',?,?)",(generate_password_hash('IntakeTest!123'),cls.t.hub,cls.m.now()))
        cls.manager=cls.m.app.test_client()
        r=cls.manager.post('/api/login',json={'email':'intake-manager@test.invalid','password':'IntakeTest!123'})
        assert r.status_code==200,r.json
        cls.manager_headers={'X-CSRF-Token':cls.manager.get('/api/bootstrap').json['csrf']}

    @classmethod
    def tearDownClass(cls):fixture.FulfillmentFlagsTests.tearDownClass()

    def post(self,path,data,manager=False):
        return (self.manager if manager else self.admin).post(path,json=data,headers=self.manager_headers if manager else self.admin_headers)

    def palette(self,owner=None,hub=None,count=1):
        owner=owner or self.company;hub=hub or self.t.hub;ids=[];trackings=[]
        with self.m.conn() as c:
            for _ in range(count):
                trk='INTAKE-'+uuid.uuid4().hex;trackings.append(trk)
                ids.append(c.execute("""INSERT INTO parcels(tracking,client_id,recipient,phone,address,city_id,amount,fee,return_fee,status,created_at,updated_at)
                    VALUES(?,?,'Recipient','0612345678','Test address',?,120,25,10,'Créé',?,?)""",(trk,owner,self.t.city,self.m.now(),self.m.now())).lastrowid)
        r=self.post('/api/partner-palettes',dict(client_id=owner,destination_hub_id=hub,parcel_ids=ids,request_key=uuid.uuid4().hex))
        self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        r=self.post(f'/api/partner-palettes/{did}/dispatch',dict(revision=r.json['revision'],confirmed=True,request_key=uuid.uuid4().hex))
        self.assertEqual(r.status_code,200,r.json)
        return did,ids,trackings,r.json['revision']

    def check_parcel(self,pid,status='Ramassé',hub=None):
        with self.m.conn() as c:
            row=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual(row['status'],status)
            self.assertEqual(row['current_hub_id'],hub or self.t.hub)
            self.assertEqual((row['amount'],row['fee'],row['return_fee']),(120,25,10))
            self.assertIsNone(row['driver_id'])
            self.assertIsNone(row['invoice_id'])
            event=c.execute('SELECT status FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
            self.assertEqual(event['status'],status)
        return self.admin.get(f'/api/parcels/{pid}').json

    def collect(self,kind,did,manager=True):
        browser=self.manager if manager else self.admin
        r=browser.get(f'/api/reception-collection/{kind}/{did}')
        self.assertEqual(r.status_code,200,r.json)
        d=dict(snapshot=r.json['snapshot'],confirmed=True,request_key=uuid.uuid4().hex,line_ids=[l['id'] for l in r.json['lines'] if not l['received_at'] and not l['excluded']])
        r=self.post(f'/api/reception-collection/{kind}/{did}',d,manager)
        self.assertEqual(r.status_code,200,r.json)
        retry=self.post(f'/api/reception-collection/{kind}/{did}',d,manager)
        self.assertEqual(retry.status_code,200,retry.json);self.assertTrue(retry.json['replayed'])

    def test_manager_individual_scan_sets_status_and_history_once(self):
        did,ids,trks,revision=self.palette()
        d=dict(tracking=trks[0],revision=revision,confirmed=True,request_key=uuid.uuid4().hex)
        r=self.post(f'/api/partner-palettes/{did}/receive',d,True)
        self.assertEqual(r.status_code,200,r.json)
        self.check_parcel(ids[0])
        self.assertEqual(self.post(f'/api/partner-palettes/{did}/receive',d,True).status_code,200)
        with self.m.conn() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM events WHERE parcel_id=? AND status='Ramassé'",(ids[0],)).fetchone()[0],1)
            line=c.execute('SELECT * FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()
            self.assertTrue(line['received_at']);self.assertEqual(line['active'],0)
        self.assertEqual(self.manager.get(f'/api/partner-palettes/{did}').json['status'],'Reçu')

    def test_admin_receive_all_and_console_bulk_use_same_rule(self):
        for mode in ('all','console'):
            with self.subTest(mode=mode):
                did,ids,trks,revision=self.palette(count=2)
                path=f'/api/partner-palettes/{did}/receive-all' if mode=='all' else f'/api/palette-console/partner/{did}/receive-bulk'
                data=dict(revision=revision,confirmed=True,request_key=uuid.uuid4().hex,expected_remaining=2,trackings=trks)
                r=self.post(path,data);self.assertEqual(r.status_code,200,r.json)
                for pid in ids:self.check_parcel(pid)

    def test_partner_collection_and_fusion_collection(self):
        did,ids,_,_=self.palette(count=2)
        self.collect('partner',did)
        for pid in ids:self.check_parcel(pid)
        first,a,_,_=self.palette();second,b,_,_=self.palette()
        r=self.post('/api/partner-palettes/fusion',{'palette_ids':[first,second]},True)
        self.assertEqual(r.status_code,200,r.json)
        self.collect('fusion',r.json['id'])
        for pid in a+b:self.check_parcel(pid)

    def test_fusion_individual_scan_uses_matching_history_status(self):
        first,a,trks,_=self.palette();second,b,_,_=self.palette()
        r=self.post('/api/partner-palettes/fusion',{'palette_ids':[first,second]},True)
        self.assertEqual(r.status_code,200,r.json);bid=r.json['id']
        r=self.post(f'/api/partner-palettes/fusion/{bid}/scan',{'tracking':trks[0]},True)
        self.assertEqual(r.status_code,200,r.json)
        self.check_parcel(a[0])
        with self.m.conn() as c:self.assertEqual(c.execute('SELECT status FROM parcels WHERE id=?',(b[0],)).fetchone()[0],'Créé')

    def test_seller_and_secondary_hub_intake_unchanged(self):
        for owner,hub in ((self.t.client_id,self.t.hub),(self.company,self.other)):
            with self.subTest(owner=owner,hub=hub):
                did,ids,trks,rev=self.palette(owner,hub)
                r=self.post(f'/api/partner-palettes/{did}/receive',dict(tracking=trks[0],revision=rev,confirmed=True,request_key=uuid.uuid4().hex))
                self.assertEqual(r.status_code,200,r.json)
                self.check_parcel(ids[0],'Réceptionné',hub)

    def test_recovered_missing_company_parcel_becomes_collected(self):
        did,ids,trks,_=self.palette()
        r=self.post(f'/api/palette-console/partner/{did}/miss',dict(tracking=trks[0],request_key=uuid.uuid4().hex))
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:lid=c.execute('SELECT id FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()[0]
        self.collect('recovered',lid)
        self.check_parcel(ids[0])

    def test_damaged_receipt_and_release_keep_ramasse_and_hold(self):
        from PIL import Image
        did,ids,trks,revision=self.palette()
        buf=io.BytesIO();Image.new('RGB',(2,2),'white').save(buf,format='PNG')
        data=dict(kind='damaged',tracking=trks[0],note='Emballage endommagé',revision=revision,confirmed=True,request_key=uuid.uuid4().hex,
                  photo={'name':'test.png','content':base64.b64encode(buf.getvalue()).decode()})
        r=self.post(f'/api/partner-palettes/{did}/incidents',data,True)
        self.assertEqual(r.status_code,200,r.json);iid=r.json['incident_id']
        self.check_parcel(ids[0])
        with self.m.conn() as c:self.assertTrue(self.m.damage_hold_open(c,ids[0]))
        r=self.post(f'/api/partner-palettes/{did}/incidents/{iid}/resolve',dict(action='release',note='Contrôle terminé'),True)
        self.assertEqual(r.status_code,200,r.json)
        self.check_parcel(ids[0])
        with self.m.conn() as c:self.assertFalse(self.m.damage_hold_open(c,ids[0]))

    def test_onward_inter_hub_transfer_still_becomes_receptionne(self):
        did,ids,trks,_=self.palette()
        self.collect('partner',did)
        self.check_parcel(ids[0])
        with self.m.conn() as c:
            old=c.execute('SELECT hub_id FROM cities WHERE id=?',(self.t.city,)).fetchone()[0]
            c.execute('UPDATE cities SET hub_id=? WHERE id=?',(self.other,self.t.city))
        try:
            candidates=self.manager.get('/api/logistics/palette-candidates',query_string=dict(mode='standard',source_hub_id=self.t.hub,destination_hub_id=self.other))
            self.assertEqual(candidates.status_code,200,candidates.json)
            self.assertIn(ids[0],[p['id'] for p in candidates.json['rows']])
            r=self.post('/api/logistics/documents',dict(kind='transfer',palette_purpose='standard',source_hub_id=self.t.hub,destination_hub_id=self.other,parcel_ids=ids,note=''))
            self.assertEqual(r.status_code,200,r.json);transfer=r.json['id']
            r=self.post(f'/api/logistics/documents/{transfer}/departure-scan',{'tracking':trks[0]},True)
            self.assertEqual(r.status_code,200,r.json)
            r=self.post(f'/api/logistics/documents/{transfer}/receive',{'tracking':trks[0]})
            self.assertEqual(r.status_code,200,r.json)
            self.check_parcel(ids[0],'Réceptionné',self.other)
        finally:
            with self.m.conn() as c:c.execute('UPDATE cities SET hub_id=? WHERE id=?',(old,self.t.city))

    def test_wrong_hub_receipt_remains_denied(self):
        did,ids,trks,rev=self.palette(hub=self.other)
        r=self.post(f'/api/partner-palettes/{did}/receive',dict(tracking=trks[0],revision=rev,confirmed=True,request_key=uuid.uuid4().hex),True)
        self.assertEqual(r.status_code,404,r.json)
        with self.m.conn() as c:
            row=c.execute('SELECT status,current_hub_id FROM parcels WHERE id=?',(ids[0],)).fetchone()
            self.assertEqual(tuple(row),('Créé',None))


if __name__=='__main__':unittest.main()
