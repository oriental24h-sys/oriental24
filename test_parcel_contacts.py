import unittest
import test_app as f
class ParcelContactTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    def contact(self):
        r=self.mutate(self.admin,'/api/support-contacts',dict(name='Support fictif',phone='+212 600 000 099'));self.assertEqual(r.status_code,200,r.json);return r.json['id']
    def detail(self,p):return self.client.get('/api/parcels/'+str(p['id'])).json['parcel']
    def assign(self,p,cid,rev=0):return self.mutate(self.admin,f'/api/parcels/{p["id"]}/support',dict(contact_id=cid,revision=rev),'patch')
    def test_current_driver_and_phone_follow_assignment_not_snapshot(self):
        p=self.new_parcel()
        with f.system.conn() as c:
            c.execute("UPDATE users SET phone='0600000003' WHERE id=3");c.execute("UPDATE users SET phone='0600000005' WHERE id=5")
        for did in [3,5]:
            self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=did),'patch');r=self.detail(p)
            self.assertEqual(r['driver_id'],did);self.assertEqual(r['driver_phone'],'060000000'+str(did))
        self.assertEqual(self.driver.get('/api/parcels/'+str(p['id'])).status_code,404)
        self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=''),'patch');self.assertIsNone(self.detail(p)['driver_phone'])
    def test_contacts_scoped_no_roster_for_client(self):
        p=self.new_parcel();cid=self.contact();self.assign(p,cid)
        self.assertEqual(self.detail(p)['support_phone'],'+212 600 000 099')
        for c in [self.client,self.driver]:
            self.assertEqual(c.get('/api/support-contacts').status_code,403)
            self.assertEqual(self.mutate(c,f'/api/parcels/{p["id"]}/support',dict(contact_id=cid,revision=1),'patch').status_code,403)
        self.assertEqual(self.data(self.client)['users'],[])
        other=next(x for x in self.data(self.admin)['parcels'] if x['client_id']!=2)
        self.assertEqual(self.client.get('/api/parcels/'+str(other['id'])).status_code,404)
    def test_missing_contact_values_not_fabricated(self):
        p=self.new_parcel();r=self.detail(p);self.assertIsNone(r['driver']);self.assertIsNone(r['driver_phone']);self.assertIsNone(r['support_name']);self.assertEqual(r['support_revision'],0)
        self.assertEqual(self.admin.get('/api/support-contacts').json,[])
    def test_contact_edit_refresh_and_deactivation(self):
        p=self.new_parcel();cid=self.contact();self.assign(p,cid)
        d=dict(name='Support modifié',phone='0600000088',revision=1,active=False)
        self.assertEqual(self.mutate(self.admin,'/api/support-contacts/'+str(cid),d,'patch').status_code,200)
        r=self.detail(p);self.assertEqual(r['support_phone'],'0600000088');self.assertEqual(r['support_active'],0)
        p2=self.new_parcel();self.assertEqual(self.assign(p2,cid).status_code,400)
        self.assertEqual(self.mutate(self.admin,'/api/support-contacts/'+str(cid),d,'patch').status_code,409)
    def test_support_routing_does_not_mutate_closed_parcel_money_or_dates(self):
        p=self.new_parcel();self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(status='Livré'),'patch');self.mutate(self.admin,'/api/invoices',dict(client_id=2))
        before=self.detail(p);cid=self.contact();self.assertEqual(self.assign(p,cid).status_code,200);after=self.detail(p)
        for key in ['amount','fee','return_fee','invoice_id','status','updated_at','ops_revision','driver_id']:self.assertEqual(before[key],after[key])
        self.assertTrue(any('Support affecté' in e['note'] for e in self.client.get('/api/parcels/'+str(p['id'])).json['events']))
    def test_assignment_revision_and_unassignment(self):
        p=self.new_parcel();cid=self.contact();self.assertEqual(self.assign(p,cid).status_code,200)
        self.assertEqual(self.assign(p,None).status_code,409);self.assertEqual(self.assign(p,None,1).status_code,200)
        self.assertIsNone(self.detail(p)['support_phone']);self.assertFalse(self.assign(p,None,2).json['changed'])
    def test_validation_and_csrf(self):
        for phone in ['javascript:alert(1)','12',None]:self.assertEqual(self.mutate(self.admin,'/api/support-contacts',dict(name='Test',phone=phone)).status_code,400)
        self.assertEqual(self.admin.post('/api/support-contacts',json=dict(name='Test',phone='0600000099')).status_code,403)
        p=self.new_parcel();self.assertEqual(self.assign(p,False).status_code,400);self.assertEqual(self.assign(p,None,True).status_code,400)
if __name__=='__main__':unittest.main()
