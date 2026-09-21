import unittest
import test_app as f
import test_logistics as l
import test_driver_finance as finance

class ParcelCityTests(unittest.TestCase):
    setUp=l.LogisticsTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    doc=l.LogisticsTests.doc
    action=l.LogisticsTests.action
    terms=finance.DriverFinanceTests.terms
    preview=finance.DriverFinanceTests.preview
    confirm=finance.DriverFinanceTests.confirm
    issue=finance.DriverFinanceTests.issue
    parallel=finance.DriverFinanceTests.parallel
    def detail(self,p):return self.admin.get('/api/parcels/'+str(p['id'])).json
    def city(self,p,cid=2,revision=None,client=None):
        if revision is None:revision=self.detail(p)['parcel']['ops_revision']
        return self.mutate(client or self.admin,f'/api/parcels/{p["id"]}/city',dict(city_id=cid,revision=revision),'patch')
    def test_city_only_and_immutable_parcel_fees(self):
        p=self.new_parcel(note='Consigne à garder');self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=3,status='Programmé',reason_code='appointment',next_attempt_at='2099-01-01T12:00'),'patch')
        before=self.detail(p)['parcel']
        with f.system.conn() as c:c.execute('UPDATE cities SET fee=99,return_fee=44 WHERE id=2')
        r=self.city(p);self.assertEqual(r.status_code,200,r.json);after=self.detail(p)['parcel'];self.assertEqual(after['city_id'],2);self.assertNotEqual(after['city'],before['city']);self.assertEqual(after['ops_revision'],before['ops_revision']+1)
        for key in ['amount','fee','return_fee','status','note','driver_id','address','product','phone','created_at','reason_code','next_attempt_at','current_hub_id','support_revision']:
            self.assertEqual(before[key],after[key],key)
        event=self.detail(p)['events'][0];self.assertIn(before['city']+' → '+after['city'],event['note']);self.assertEqual(event['actor'],'Administrateur');self.assertEqual(event['status'],'Programmé')
        for client in [self.client,self.driver]:
            fresh=client.get('/api/parcels/'+str(p['id'])).json['parcel'];self.assertEqual(fresh['city_id'],2)
    def test_admin_only_and_csrf(self):
        p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=3),'patch')
        for client in [self.client,self.driver]:self.assertEqual(self.city(p,client=client).status_code,403)
        url=f'/api/parcels/{p["id"]}/city';self.assertEqual(self.admin.patch(url,json=dict(city_id=2,revision=1)).status_code,403)
        self.assertEqual(f.system.app.test_client().patch(url,json=dict(city_id=2,revision=1)).status_code,401)
        self.assertEqual(self.detail(p)['parcel']['city_id'],1)
    def test_revision_noop_and_payload_validation(self):
        p=self.new_parcel();before=self.detail(p);self.assertFalse(self.city(p,1,0).json['changed']);self.assertEqual(self.detail(p),before)
        self.assertEqual(self.city(p,2,0).status_code,200);self.assertEqual(self.city(p,1,0).status_code,409)
        for cid in [True,False,None,'2',2.0,0,-1,2**80,[],{},99999]:self.assertEqual(self.city(p,cid).status_code,400)
        for rev in [True,'1',-1,2.0]:self.assertEqual(self.city(p,1,rev).status_code,409)
        for body in [None,[],{},dict(city_id=1,revision=1,amount=0)]:self.assertEqual(self.mutate(self.admin,f'/api/parcels/{p["id"]}/city',body,'patch').status_code,400)
        self.assertEqual(self.city({'id':99999},2,0).status_code,404)
    def test_city_disabled_after_open_is_revalidated(self):
        p=self.new_parcel()
        with f.system.conn() as c:c.execute('UPDATE cities SET delivery=0 WHERE id=2')
        self.assertEqual(self.city(p,2).status_code,400);self.assertEqual(self.detail(p)['parcel']['ops_revision'],0)
    def test_closed_and_invoice_locks(self):
        for status in ['Livré','Retourné','Refusé']:
            p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status=status),'patch');before=self.detail(p);self.assertEqual(self.city(p).status_code,409);self.assertEqual(self.detail(p),before)
        self.mutate(self.admin,'/api/invoices',dict(client_id=2));self.assertEqual(self.city(p).status_code,409)
    def test_active_document_lock(self):
        p=self.new_parcel();r=self.doc([p]);self.assertEqual(r.status_code,200,r.json);before=self.detail(p)
        self.assertEqual(self.city(p).status_code,409);self.assertEqual(self.detail(p),before)
        self.action(r.json['id'],'cancel',revision=1,reason='Erreur de sélection');self.assertEqual(self.city(p).status_code,200)
    def test_driver_financial_snapshot_lock(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=3,status='Livré'),'patch');self.terms();self.issue()
        # Retain the active immutable financial line even if a legacy import has an open status.
        with f.system.conn() as c:c.execute("UPDATE parcels SET status='En livraison' WHERE id=?",(p['id'],))
        before=self.detail(p);self.assertTrue(before['parcel']['financial_locked']);self.assertEqual(self.city(p).status_code,409);self.assertEqual(self.detail(p),before)
    def test_concurrent_changes_commit_once(self):
        p=self.new_parcel();url=f'/api/parcels/{p["id"]}/city';results=self.parallel([('patch',url,dict(city_id=city,revision=0)) for city in [2,3]])
        self.assertEqual(sorted(r.status_code for r in results),[200,409]);after=self.detail(p);self.assertEqual(after['parcel']['ops_revision'],1);self.assertEqual(len(after['events']),2)

if __name__=='__main__':unittest.main()
