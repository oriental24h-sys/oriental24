import unittest,secrets
import test_app as f
import test_logistics as logistics_tests
import test_driver_finance as finance_tests
from parcel_statuses import STATUSES,DRIVER_TRANSITIONS
NEW=['Transit','Reporté','Réceptionné','Reçu par le livreur','Intéressé']
class StatusCatalogueTests(unittest.TestCase):
    setUp=logistics_tests.LogisticsTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    new_parcel=f.PlatformTests.new_parcel
    p=logistics_tests.LogisticsTests.p
    doc=logistics_tests.LogisticsTests.doc
    action=logistics_tests.LogisticsTests.action
    attempt=logistics_tests.LogisticsTests.attempt
    terms=finance_tests.DriverFinanceTests.terms
    preview=finance_tests.DriverFinanceTests.preview
    def get(self,p):return self.admin.get('/api/parcels/'+str(p['id'])).json['parcel']
    def status(self,p,s,client=None,**kw):return self.mutate(client or self.admin,'/api/parcels/'+str(p['id']),dict(status=s,**kw),'patch')
    def test_13_states_and_single_transition_policy(self):
        b=self.data(self.admin);self.assertEqual(len(b['statuses']),13);self.assertEqual(len(set(b['statuses'])),13)
        self.assertEqual(b['status_policy']['driver_transitions'],DRIVER_TRANSITIONS)
        for old in ['Créé','Ramassé','Au hub','En livraison','Programmé','Livré','Retourné','Refusé']:self.assertIn(old,STATUSES)
        for state in NEW:
            p=self.p();before=self.get(p);r=self.status(p,state,revision=before['ops_revision']);self.assertEqual(r.status_code,200,r.json)
            after=self.get(p);self.assertEqual(after['status'],state);self.assertEqual(after['ops_revision'],before['ops_revision']+1)
            for k in ['amount','fee','return_fee','driver_id','invoice_id']:self.assertEqual(before[k],after[k])
            self.assertEqual(self.admin.get('/api/parcels/'+str(p['id'])).json['events'][0]['status'],state)
    def test_new_states_not_financially_closed(self):
        with f.system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
        parcels=[self.p(s) for s in NEW];ids={p['id'] for p in parcels};self.assertEqual(self.terms().status_code,200)
        self.assertNotEqual(self.preview().status_code,200)
        delivered=self.p('Livré');preview=self.preview();self.assertEqual(preview.status_code,200,preview.json)
        self.assertEqual({p['parcel_id'] for p in preview.json['lines']},{delivered['id']});self.assertEqual(preview.json['cod_cents'],19990)
        r=self.mutate(self.admin,'/api/invoices',dict(client_id=2));self.assertEqual(r.status_code,200,r.json)
        with f.system.conn() as c:
            for pid in ids:self.assertIsNone(c.execute('SELECT invoice_id FROM parcels WHERE id=?',(pid,)).fetchone()[0])
    def test_reported_clears_schedule_and_records_retry_once(self):
        p=self.p();self.assertEqual(self.status(p,'Programmé',reason_code='appointment',next_attempt_at='2099-01-01T12:00').status_code,200)
        p=self.get(p);key=secrets.token_hex(16);r=self.attempt(p,'Reporté',reason_code='postponed',request_key=key);self.assertEqual(r.status_code,200,r.json)
        self.assertTrue(self.attempt(p,'Reporté',reason_code='postponed',request_key=key).json['already_recorded'])
        after=self.get(p);self.assertEqual(after['status'],'Reporté');self.assertIsNone(after['next_attempt_at'])
        a=self.admin.get('/api/logistics/parcels/'+str(p['id'])).json['attempts'];self.assertEqual(len(a),1);self.assertIsNone(a[0]['amount_cents'])
        self.assertEqual(self.status(after,'En livraison',client=self.driver,revision=after['ops_revision']).status_code,200)
    def test_receipt_requires_assigned_active_driver(self):
        p=self.new_parcel();self.assertEqual(self.status(p,'Reçu par le livreur').status_code,400)
        self.assertEqual(self.status(p,'Reçu par le livreur',driver_id=3).status_code,200)
        with f.system.conn() as c:c.execute('UPDATE users SET active=0 WHERE id=3')
        self.assertEqual(self.status(p,'Reçu par le livreur').status_code,400)
    def test_driver_scope_and_no_agency_self_validation(self):
        p=self.p('Réceptionné');self.assertEqual(self.status(p,'Reçu par le livreur',client=self.driver).status_code,200)
        self.assertEqual(self.status(p,'Livré',client=self.driver).status_code,400)
        self.assertEqual(self.status(p,'En livraison',client=self.driver).status_code,200)
        for s in ['Transit','Réceptionné']:
            self.assertEqual(self.status(p,s,client=self.driver).status_code,400);self.assertEqual(self.get(p)['status'],'En livraison')
        other=self.p('Réceptionné',5);self.assertEqual(self.status(other,'Reçu par le livreur',client=self.driver).status_code,404)
        self.assertEqual(self.status(p,'Reporté',client=self.client).status_code,403)
    def test_transfer_links_transit_and_agency_receipt(self):
        a,b=self.p('Réceptionné'),self.p('Au hub');did=self.doc([a,b],'transfer').json['id']
        self.assertEqual(self.action(did,'dispatch',revision=1).status_code,200)
        for p in [a,b]:
            q=self.get(p);self.assertEqual(q['status'],'Transit');self.assertIsNone(q['current_hub_id']);self.assertEqual(self.status(q,'Réceptionné').status_code,409)
        self.assertEqual(self.action(did,'receive',tracking=a['tracking']).status_code,200);q=self.get(a);self.assertEqual(q['status'],'Réceptionné');self.assertEqual(q['current_hub_id'],self.hubs[1]);self.assertTrue(q['operations_locked']);self.assertEqual(self.get(b)['status'],'Transit')
        self.assertTrue(self.action(did,'receive',tracking=a['tracking']).json['already_received']);self.assertEqual(self.get(a)['ops_revision'],q['ops_revision'])
        self.action(did,'receive',tracking=b['tracking']);self.assertFalse(self.get(a)['operations_locked'])
        r=self.status(self.get(a),'Reçu par le livreur',client=self.driver);self.assertEqual(r.status_code,200,r.json);self.assertIsNone(self.get(a)['current_hub_id'])
    def test_interest_not_a_delivery_and_stale_locks(self):
        p=self.p('En livraison');old=self.get(p);self.assertEqual(self.status(p,'Intéressé',client=self.driver,revision=old['ops_revision']).status_code,200)
        self.assertEqual(self.status(p,'Reporté',client=self.driver,revision=old['ops_revision']).status_code,409)
        q=self.get(p);self.assertEqual(self.attempt(q).status_code,409);self.assertEqual(self.status(q,'En livraison',client=self.driver).status_code,200)
        self.status(p,'Livré');self.mutate(self.admin,'/api/invoices',dict(client_id=2))
        for state in NEW:self.assertNotEqual(self.status(p,state).status_code,200)
    def test_reassignment_does_not_claim_new_driver_already_received(self):
        p=self.p('Reçu par le livreur')
        url='/api/parcels/'+str(p['id'])
        for did in [5,None]:self.assertEqual(self.mutate(self.admin,url,dict(driver_id=did),'patch').status_code,409)
        self.assertEqual(self.mutate(self.admin,'/api/logistics/assignments/preview',dict(driver_id=5,parcel_ids=[p['id']])).status_code,409)
        self.assertEqual(self.get(p)['driver_id'],3)
        self.assertEqual(self.mutate(self.admin,url,dict(driver_id=5,status='Reporté'),'patch').status_code,200)
        self.assertEqual(self.get(p)['status'],'Reporté')

    def test_manual_state_does_not_complete_document_or_stock(self):
        p=self.p('Au hub');did=self.doc([p],'transfer').json['id'];self.assertEqual(self.status(p,'Transit').status_code,409)
        self.action(did,'cancel',revision=1,reason='Test');self.assertEqual(self.status(p,'Transit').status_code,200);self.assertEqual(self.status(p,'Réceptionné').status_code,200)
        self.assertEqual(self.admin.get('/api/logistics/documents/'+str(did)).json['status'],'Annulé')
        self.assertEqual(self.admin.get('/api/fulfillment/orders').json,[])
if __name__=='__main__':unittest.main()
