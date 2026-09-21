"""Vendeur vs société de livraison: tracking policy, imports, scopes and invariants."""
import concurrent.futures
import secrets
import sqlite3
import threading
import unittest
import test_app as fixtures
import test_operations as imports
import client_types

system = fixtures.system

class ClientTypesTests(unittest.TestCase):
    data = fixtures.PlatformTests.data
    mutate = fixtures.PlatformTests.mutate
    rows = imports.OperationsTests.rows
    preview = imports.OperationsTests.preview
    commit = imports.OperationsTests.commit

    def setUp(self):
        fixtures.PlatformTests.setUp(self)
        self.company = self.make_account('societe_livraison')
        self.company_user = system.app.test_client()
        r=self.company_user.post('/api/login',json={'email':self.company['email'],'password':'Oriental24!Demo'})
        self.assertEqual(r.status_code,200)

    def make_account(self,kind='vendeur'):
        email=secrets.token_hex(8)+'@example.test'
        d=dict(name='Compte fictif',email=email,password='Oriental24!Demo',phone='0600000000',company='Entreprise fictive',role='client',client_type=kind)
        r=self.mutate(self.admin,'/api/users',d)
        self.assertEqual(r.status_code,200,r.json)
        return next(u for u in self.data(self.admin)['users'] if u['id']==r.json['id'])

    def shipment(self,**kw):
        d=dict(recipient='Destinataire fictif',phone='0600000000',address='Adresse fictive',city_id=1,amount='199.90',tracking='Soc-000012/Ab.c_1')
        d.update(kw);return d

    def create(self,user=None,**kw):
        return self.mutate(user or self.company_user,'/api/parcels',self.shipment(**kw))

    def parcel_by_tracking(self,tracking):
        return next(p for p in self.data(self.admin)['parcels'] if p['tracking']==tracking)

    def test_defaults_and_repeat_migration_preserve_business_records(self):
        self.assertEqual(self.data(self.client)['user']['client_type'],'vendeur')
        with system.conn() as c:
            before=[tuple(r) for r in c.execute('SELECT * FROM parcels')]
            client_types.migrate(c);client_types.migrate(c)
            self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM parcels')])
            self.assertEqual(c.execute('SELECT client_type FROM users WHERE id=?',(self.company['id'],)).fetchone()[0],'societe_livraison')

    def test_type_validation_and_nonclient_no_partner_type(self):
        for kind in [None,123,'livreur','societe','<script>']:
            r=self.mutate(self.admin,'/api/users',dict(name='Test',email='bad@example.test',password='Oriental24!Demo',phone='0600000000',role='client',client_type=kind))
            self.assertEqual(r.status_code,400,r.json)
        r=self.mutate(self.admin,'/api/users',dict(name='Test',email='bad@example.test',password='Oriental24!Demo',phone='0600000000',role='livreur',client_type='societe_livraison'))
        self.assertEqual(r.status_code,400)

    def test_vendor_automatic_company_keeps_tracking_and_tariffs(self):
        seller=self.create(self.client,tracking=None,client_type='societe_livraison')
        self.assertEqual(seller.status_code,200,seller.json);self.assertRegex(seller.json['tracking'],r'^O24-[A-F0-9]+$')
        company=self.create();self.assertEqual(company.status_code,200,company.json)
        self.assertEqual(company.json['tracking'],'Soc-000012/Ab.c_1')
        a=self.parcel_by_tracking(seller.json['tracking']);b=self.parcel_by_tracking(company.json['tracking'])
        for field in ['status','amount','fee','return_fee','driver_id','invoice_id']:
            self.assertEqual(a[field],b[field],field)
        self.assertEqual(self.create(self.client,tracking='OTHER').status_code,400)

    def test_company_tracking_required_text_and_safe_format(self):
        for invalid in [None,'',123,'a'*81,'<script>','a b','a\nb','=1+1','@foo','-start','https://x','تتبع']:
            r=self.create(tracking=invalid);self.assertEqual(r.status_code,400,(invalid,r.json))
        self.assertEqual(self.create(tracking='00001234').json['tracking'],'00001234')
        self.assertEqual(self.create(tracking='A'*80).status_code,200)

    def test_client_cannot_spoof_type_owner_or_modify_tracking(self):
        r=self.create(client_id=2,client_type='vendeur');self.assertEqual(r.status_code,200)
        p=self.parcel_by_tracking(r.json['tracking']);self.assertEqual(p['client_id'],self.company['id'])
        self.assertEqual(self.client.get('/api/parcels/'+str(p['id'])).status_code,404)
        self.assertEqual(self.create(self.driver).status_code,403)
        self.assertEqual(self.mutate(self.company_user,'/api/profile',{**self.company,'client_type':'vendeur'},'patch').status_code,403)
        self.assertEqual(self.mutate(self.company_user,'/api/parcels/'+str(p['id']),{'tracking':'CHANGED'},'patch').status_code,403)
        self.assertEqual(self.parcel_by_tracking(r.json['tracking'])['tracking'],r.json['tracking'])

    def test_admin_uses_selected_client_policy_and_active_check(self):
        r=self.create(self.admin,client_id=self.company['id']);self.assertEqual(r.status_code,200)
        self.assertEqual(self.create(self.admin,client_id=2,tracking='SUPPLIED').status_code,400)
        self.assertEqual(self.create(self.admin,client_id=2,tracking=None).status_code,200)
        self.assertEqual(self.mutate(self.admin,'/api/users/'+str(self.company['id']),{**self.company,'active':False},'patch').status_code,200)
        self.assertEqual(self.create(self.admin,client_id=self.company['id'],tracking='NEW').status_code,400)

    def test_tracking_unique_per_company_shared_across_companies(self):
        self.assertEqual(self.create(tracking='Mix-0001').status_code,200)
        self.assertEqual(self.create(tracking='mIX-0001').status_code,409)  # même société : jamais deux fois
        second=self.make_account('societe_livraison')
        # Une autre société peut légitimement utiliser le même code.
        second_user=system.app.test_client()
        self.assertEqual(second_user.post('/api/login',json={'email':second['email'],'password':'Oriental24!Demo'}).status_code,200)
        r=self.create(second_user,tracking='mIX-0001');self.assertEqual(r.status_code,200,r.json)
        with system.conn() as c:self.assertEqual(c.execute("SELECT count(*) FROM parcels WHERE tracking=? COLLATE NOCASE",('Mix-0001',)).fetchone()[0],2)
        # Scan ambigu : on doit préciser la société ; avec client_id, la résolution fonctionne.
        scan=self.mutate(self.admin,'/api/scan',{'tracking':'mix-0001'});self.assertEqual(scan.status_code,409)
        scan=self.mutate(self.admin,'/api/scan',{'tracking':'mix-0001','client_id':second['id']});self.assertEqual(scan.status_code,200,scan.json)
        self.assertEqual(self.mutate(self.admin,'/api/scan',{'tracking':'mix-0001','client_id':999}).status_code,409)

    def test_concurrent_duplicate_is_one_creation_one_event(self):
        h={'X-CSRF-Token':self.data(self.company_user)['csrf']};h2={'X-CSRF-Token':self.data(self.admin)['csrf']};barrier=threading.Barrier(2)
        def run(args):
            user,headers=args;barrier.wait();return user.post('/api/parcels',json=self.shipment(client_id=self.company['id'],tracking='RACE-0001'),headers=headers).status_code
        with concurrent.futures.ThreadPoolExecutor(2) as pool:codes=list(pool.map(run,[(self.company_user,h),(self.admin,h2)]))
        self.assertEqual(sorted(codes),[200,409])
        with system.conn() as c:self.assertEqual(c.execute("SELECT count(*) FROM events WHERE parcel_id=(SELECT id FROM parcels WHERE tracking='RACE-0001')").fetchone()[0],1)

    def test_scan_labels_export_and_driver_scope_keep_exact_code(self):
        r=self.create();code=r.json['tracking'];p=self.parcel_by_tracking(code)
        for actor in [self.admin,self.company_user]:
            scan=self.mutate(actor,'/api/scan',{'tracking':code.lower()});self.assertEqual(scan.status_code,200,scan.json);self.assertEqual(scan.json['tracking'],code)
        for actor in [self.client,self.driver]:self.assertEqual(self.mutate(actor,'/api/scan',{'tracking':code}).status_code,404)
        self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(p['id']),{'driver_id':3},'patch').status_code,200)
        self.assertEqual(self.mutate(self.driver,'/api/scan',{'tracking':code}).json['tracking'],code)
        labels=self.mutate(self.company_user,'/api/labels',{'ids':[p['id']]}).json
        self.assertEqual(labels[0]['tracking'],code);self.assertIn('data:image/',labels[0]['qr']);self.assertIn('data:image/',labels[0]['barcode'])
        self.assertIn(code,self.company_user.get('/api/export').data.decode('utf-8-sig'))
        self.assertNotIn(code,self.client.get('/api/export').data.decode('utf-8-sig'))

    def test_import_company_exact_codes_and_retry_idempotency(self):
        rows=[self.rows('0000042'),self.rows('MiXeD-02')]
        b=self.preview(rows,self.company_user).json
        self.assertEqual(b['client_type'],'societe_livraison');self.assertEqual(b['invalid'],0,b)
        self.assertEqual([r['tracking'] for r in b['rows']],['0000042','MiXeD-02'])
        result=self.commit(b,self.company_user);self.assertEqual(result.status_code,200,result.json)
        self.assertEqual([p['tracking'] for p in result.json['parcels']],['0000042','MiXeD-02'])
        replay=self.commit(b,self.company_user);self.assertTrue(replay.json['already_imported']);self.assertEqual(replay.json['parcels'],result.json['parcels'])
        seller=self.preview([self.rows('SELLER-REF')]).json
        result=self.commit(seller);self.assertTrue(result.json['parcels'][0]['tracking'].startswith('O24-'))

    def test_import_xlsx_requires_text_tracking_and_preserves_zero(self):
        b=self.preview([self.rows(123)],self.company_user,fmt='xlsx').json
        self.assertEqual(b['invalid'],1);self.assertIn('cellule texte',' '.join(b['rows'][0]['errors']))
        b=self.preview([self.rows('000123')],self.company_user,fmt='xlsx').json
        self.assertEqual(b['invalid'],0,b);self.assertEqual(self.commit(b,self.company_user).json['parcels'][0]['tracking'],'000123')

    def test_import_conflicts_atomic_and_commit_rechecks_new_duplicate(self):
        b=self.preview([self.rows('FIRST-OK'),self.rows('COLLISION')],self.company_user).json
        self.assertEqual(b['invalid'],0)
        self.create(tracking='collision')
        self.assertEqual(self.commit(b,self.company_user).status_code,409)
        with system.conn() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM parcels WHERE tracking='FIRST-OK'").fetchone())
            self.assertIsNone(c.execute("SELECT 1 FROM parcel_external_refs WHERE reference='first-ok'").fetchone())
        self.assertEqual(self.preview([self.rows('COLLISION')],self.company_user).json['invalid'],1)
        self.assertEqual(self.preview([self.rows('AAA'),self.rows('aaa')],self.company_user).json['invalid'],1)

    def test_type_change_before_first_order_is_audited_and_stales_import(self):
        b=self.preview([self.rows('WILL-NOT-IMPORT')],self.company_user).json
        r=self.mutate(self.admin,'/api/users/'+str(self.company['id']),{**self.company,'client_type':'vendeur'},'patch');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.commit(b,self.company_user).status_code,409)
        self.assertEqual(self.data(self.company_user)['user']['client_type'],'vendeur')
        with system.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM client_type_audit WHERE user_id=?',(self.company['id'],)).fetchone()[0],2)

    def test_type_locked_after_parcel_and_edit_retains_type(self):
        self.create();d={**self.company,'name':'Nouveau nom'};d.pop('client_type')
        self.assertEqual(self.mutate(self.admin,'/api/users/'+str(self.company['id']),d,'patch').status_code,200)
        self.assertEqual(self.data(self.company_user)['user']['client_type'],'societe_livraison')
        self.assertEqual(self.mutate(self.admin,'/api/users/'+str(self.company['id']),{**d,'client_type':'vendeur'},'patch').status_code,409)

    def test_public_registration_kind_is_client_not_privileged(self):
        c=system.app.test_client();r=c.post('/api/register',json=dict(name='Société fictive',email='inscription@example.test',company='Test',phone='0600000000',password='Oriental24!Demo',client_type='societe_livraison',role='admin'))
        self.assertEqual(r.status_code,200,r.json);u=self.data(c)['user'];self.assertEqual(u['role'],'client');self.assertEqual(u['client_type'],'societe_livraison')
        self.assertEqual(self.mutate(c,'/api/users',{}).status_code,403)

    def test_fulfillment_reserves_company_code_and_never_generates_other_code(self):
        with system.conn() as c:
            pid=c.execute('INSERT INTO products(client_id,name,reference,quantity,created_at) VALUES(?,?,?,?,?)',(self.company['id'],'Produit fictif','SKU-TEST',10,system.now())).lastrowid
        d=self.shipment(items=[dict(product_id=pid,quantity=2)],request_key=secrets.token_hex(16),tracking=None)
        self.assertEqual(self.mutate(self.company_user,'/api/fulfillment/orders',d).status_code,400)
        d['tracking']='Reserved-0002';r=self.mutate(self.company_user,'/api/fulfillment/orders',d);self.assertEqual(r.status_code,200,r.json);oid=r.json['id']
        self.assertEqual(self.create(tracking='reserved-0002').status_code,409)
        self.assertEqual(self.mutate(self.admin,'/api/users/'+str(self.company['id']),{**self.company,'client_type':'vendeur'},'patch').status_code,409)
        hub=self.mutate(self.admin,'/api/logistics/hubs',dict(name='Hub fictif',city_id=1,address='Adresse test')).json['id']
        r=self.mutate(self.admin,f'/api/fulfillment/orders/{oid}/ship',dict(hub_id=hub,checked=True));self.assertEqual(r.status_code,200,r.json)
        order=self.company_user.get(f'/api/fulfillment/orders/{oid}').json
        self.assertEqual(order['tracking'],'Reserved-0002')
        self.assertEqual(next(p for p in self.company_user.get('/api/products').json if p['id']==pid)['quantity'],8)

    def test_client_invoice_preserves_company_tracking_and_normal_fees(self):
        r=self.create();p=self.parcel_by_tracking(r.json['tracking'])
        with system.conn() as c:c.execute("UPDATE parcels SET status='Livré' WHERE id=?",(p['id'],))
        self.assertEqual(self.mutate(self.admin,'/api/invoices',{'client_id':self.company['id']}).status_code,200)
        inv=self.company_user.get('/api/invoices').json[0]
        data=self.company_user.get('/api/billing/client/'+str(inv['id'])).json
        self.assertEqual(data['lines'][0]['tracking'],r.json['tracking'])
        self.assertEqual(data['invoice']['cod_cents'],19990)
        self.assertEqual(data['invoice']['fees_cents'],2500)
        self.assertEqual(data['invoice']['net_cents'],17490)
        self.assertEqual(self.company_user.get('/api/billing/client/'+str(inv['id'])+'/pdf').status_code,200)

if __name__=='__main__':unittest.main(verbosity=2)
