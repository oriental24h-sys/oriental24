import unittest,secrets
import test_app as f
import test_driver_finance as finance
import test_logistics as logistics
W='/api/drivers-workspace/'
class DriverWorkspaceTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    parallel=finance.DriverFinanceTests.parallel
    terms=finance.DriverFinanceTests.terms
    preview=finance.DriverFinanceTests.preview
    confirm=finance.DriverFinanceTests.confirm
    issue=finance.DriverFinanceTests.issue
    def p(self,p):return self.admin.get('/api/parcels/'+str(p['id'])).json['parcel']
    def dr(self,uid=3):return self.admin.get(W+str(uid)).json['driver']
    def scan(self,p,mode='assign',uid=3,**kw):
        d=dict(parcel_id=p['id'],revision=self.p(p)['ops_revision'],mode=mode,request_key=secrets.token_hex(16),hub_id=None,confirmed=True);d.update(kw);return self.mutate(self.admin,W+str(uid)+'/scan',d)
    def access(self,action,uid=3,**kw):
        d=dict(action=action,reason='Motif de test',revision=self.dr(uid)['driver_revision']);d.update(kw);return self.mutate(self.admin,W+str(uid)+'/access',d)
    def info(self,**kw):
        d=dict(name='Livreur modifié',phone='0611223344',city_id=2,address='Adresse fictive',password='',revision=self.dr()['driver_revision']);d.update(kw);return self.mutate(self.admin,W+'3',d,'patch')
    def test_morning_evening_cycle_and_second_dispatch(self):
        p=self.new_parcel();before=self.p(p);self.assertEqual(self.scan(p).status_code,200);morning=self.p(p);self.assertEqual((morning['driver_id'],morning['status']),(3,'Reçu par le livreur'));self.assertEqual(self.driver.get('/api/parcels/'+str(p['id'])).status_code,200)
        self.assertEqual(self.scan(p,'receive').status_code,200);night=self.p(p);self.assertEqual((night['driver_id'],night['status']),(None,'Réceptionné'));self.assertEqual(self.driver.get('/api/parcels/'+str(p['id'])).status_code,404)
        for k in ['amount','fee','return_fee','recipient','address','phone','product']:self.assertEqual(before[k],night[k])
        self.assertEqual(self.scan(p,uid=5).status_code,200);self.assertEqual(self.p(p)['driver_id'],5)
    def test_delivered_stays_with_driver_and_cannot_be_recovered(self):
        p=self.new_parcel();self.scan(p);self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Livré'),'patch');before=self.p(p);self.assertEqual(self.scan(p,'receive').status_code,409);self.assertEqual(self.p(p),before);self.assertEqual(self.scan(p).status_code,409)
    def test_refusal_receipt_preserves_pending_commission_and_contact_truth(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        p=self.new_parcel();self.scan(p);self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Refusé'),'patch');self.terms();before=self.preview().json;old=self.p(p)
        self.assertEqual(self.scan(p,'receive').status_code,200);after=self.preview().json;new=self.p(p)
        for k in ['driver_id','status','amount','fee','return_fee','updated_at']:self.assertEqual(new[k],old[k])
        self.assertEqual(before['lines'],after['lines']);self.assertEqual(before['commission_cents'],after['commission_cents']);self.assertTrue(new['driver_returned']);self.assertIsNone(new['driver_phone']);self.assertEqual(self.driver.get('/api/parcels/'+str(p['id'])).status_code,404)
        self.assertNotIn(p['id'],[x['id'] for x in self.admin.get(W+'3').json['parcels']])
    def test_already_issued_financial_lines_unchanged_by_physical_receipt(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        p=self.new_parcel();self.scan(p);self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Retourné'),'patch');self.terms();sid=self.issue()
        with f.system.conn() as c:before=[tuple(r) for r in c.execute('SELECT * FROM driver_statement_lines')]
        self.assertEqual(self.scan(p,'receive').status_code,200)
        with f.system.conn() as c:self.assertEqual(before,[tuple(r) for r in c.execute('SELECT * FROM driver_statement_lines')])
    def test_scope_csrf_and_wrong_driver(self):
        p=self.new_parcel();self.scan(p)
        for cl in [self.client,self.driver]:self.assertEqual(cl.get(W.rstrip('/')).status_code,403);self.assertEqual(self.mutate(cl,W+'3/access',{}).status_code,403)
        self.assertEqual(self.admin.post(W+'3/scan',json={}).status_code,403);self.assertEqual(self.scan(p,'receive',uid=5).status_code,409);self.assertEqual(self.scan(p,'assign',uid=5).status_code,409)
    def test_duplicate_and_concurrent_scan_are_idempotent(self):
        p=self.new_parcel();d=dict(parcel_id=p['id'],revision=0,mode='assign',request_key=secrets.token_hex(16),hub_id=None,confirmed=True);responses=self.parallel([('post',W+'3/scan',d),('post',W+'3/scan',d)]);self.assertEqual([r.status_code for r in responses],[200,200]);self.assertEqual(self.p(p)['ops_revision'],1)
        self.assertEqual(self.mutate(self.admin,W+'5/scan',d).status_code,409);self.assertTrue(self.scan(p).json['already']);self.assertEqual(self.p(p)['ops_revision'],1)
        self.scan(p,'receive');n=self.p(p)['ops_revision'];self.assertTrue(self.scan(p,'receive').json['already']);self.assertEqual(self.p(p)['ops_revision'],n)
    def test_versions_revalidation_and_confirmation(self):
        p=self.new_parcel();self.assertEqual(self.scan(p,revision=99).status_code,409);self.assertEqual(self.scan(p,confirmed=False).status_code,400);self.assertEqual(self.scan(p,hub_id=True).status_code,400)
        self.access('block');self.assertEqual(self.scan(p).status_code,409);self.assertEqual(self.p(p)['driver_id'],None)
    def test_block_revokes_session_and_still_allows_recovery(self):
        p=self.new_parcel();self.scan(p);self.assertEqual(self.access('block').status_code,200);self.assertEqual(self.driver.get('/api/bootstrap').status_code,401);self.assertEqual(self.driver.post('/api/login',json=dict(email='livreur@oriental24.ma',password='Oriental24!Demo')).status_code,401);self.assertEqual(self.scan(p,'receive').status_code,200);self.access('unblock');self.assertEqual(self.driver.get('/api/bootstrap').status_code,401)
    def test_archive_restore_and_legacy_bypass_protection(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        p=self.new_parcel();self.scan(p);self.assertEqual(self.access('archive').status_code,409);self.scan(p,'receive');self.access('block');self.assertEqual(self.access('archive').status_code,200);self.assertTrue(self.dr()['driver_archived'])
        self.assertEqual(self.mutate(self.admin,'/api/users/3',dict(name='Test',phone='0600000000',company='',active=True),'patch').status_code,409);self.access('restore');self.assertFalse(self.dr()['active']);self.access('unblock');self.assertTrue(self.dr()['active'])
    def test_information_validation_revision_and_password_reset(self):
        original=self.dr();self.assertEqual(self.info().status_code,200);self.assertEqual(self.dr()['email'],original['email']);self.assertEqual(self.dr()['driver_city_id'],2);self.assertEqual(self.info(revision=1).status_code,409);self.assertEqual(self.info(phone='bad').status_code,400);self.assertEqual(self.info(city_id=99999).status_code,400)
        self.assertEqual(self.info(password='NouveauMotDePasse!12').status_code,200);self.assertEqual(self.driver.get('/api/bootstrap').status_code,401);self.assertEqual(self.driver.post('/api/login',json=dict(email='livreur@oriental24.ma',password='NouveauMotDePasse!12')).status_code,200)
        with f.system.conn() as c:self.assertNotIn('NouveauMotDePasse',str([dict(r) for r in c.execute('SELECT * FROM driver_workspace_audit')]))
    def test_document_lock_cannot_be_bypassed_by_scan(self):
        p=self.new_parcel();h=self.mutate(self.admin,'/api/logistics/hubs',dict(name='Agence test',city_id=1,address='Adresse')).json['id'];r=self.mutate(self.admin,'/api/logistics/documents',dict(kind='pickup',parcel_ids=[p['id']],client_id=2,driver_id=3,source_hub_id=h,destination_hub_id=h,note='Test'));self.assertEqual(r.status_code,200,r.json);self.assertEqual(self.scan(p).status_code,409)
    def test_archived_account_historical_settlement_still_possible(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        p=self.new_parcel();self.scan(p);self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Livré'),'patch');self.terms();self.assertEqual(self.access('archive').status_code,200);self.assertEqual(self.preview().status_code,200)

if __name__=='__main__':unittest.main()
