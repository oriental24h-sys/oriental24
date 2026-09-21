"""Partner intake on real API: ownership, locks, physical receipt and financial invariants."""
import unittest,secrets,json
import test_client_types as types
import test_driver_finance as concurrency
system=types.system
P='/api/partner-palettes'

class PartnerPaletteTests(unittest.TestCase):
    data=types.ClientTypesTests.data
    mutate=types.ClientTypesTests.mutate
    make_account=types.ClientTypesTests.make_account
    shipment=types.ClientTypesTests.shipment
    create=types.ClientTypesTests.create
    parcel_by_tracking=types.ClientTypesTests.parcel_by_tracking
    parallel=concurrency.DriverFinanceTests.parallel
    def setUp(self):
        types.ClientTypesTests.setUp(self)
        self.hub=self.mutate(self.admin,'/api/logistics/hubs',dict(name='Hub Réception test',city_id=1,address='Adresse fictive')).json['id']
        self.ps=[]
        for n in range(3):
            r=self.create(tracking=f'Soc-0000{n}/Ab');self.assertEqual(r.status_code,200,r.json);self.ps.append(self.parcel_by_tracking(r.json['tracking']))
    def draft_data(self,**kw):
        d=dict(client_id=self.company['id'],destination_hub_id=self.hub,partner_reference='Palette-Soc-007',transport='Transport fictif',note='Test',parcel_ids=[p['id'] for p in self.ps],request_key=secrets.token_hex(16));d.update(kw);return d
    def draft(self,actor=None,**kw):
        r=self.mutate(actor or self.company_user,P,self.draft_data(**kw));self.assertEqual(r.status_code,200,r.json);return r.json['id']
    def detail(self,did):return self.admin.get(P+'/'+str(did)).json
    def action(self,did,action,actor=None,**kw):
        d=dict(revision=self.detail(did)['revision'],request_key=secrets.token_hex(16),confirmed=True);d.update(kw);return self.mutate(actor or self.admin,f'{P}/{did}/{action}',d)
    def dispatch(self,did):
        r=self.action(did,'dispatch',self.company_user);self.assertEqual(r.status_code,200,r.json)
    def state(self,pid):return self.admin.get('/api/parcels/'+str(pid)).json['parcel']

    def test_roles_owner_scope_and_company_cannot_receive(self):
        did=self.draft();other=self.make_account('societe_livraison');c=system.app.test_client();c.post('/api/login',json=dict(email=other['email'],password='Oriental24!Demo'))
        for route in [P,P+'/config',P+'/candidates',P+f'/{did}',P+f'/{did}/csv']:
            self.assertEqual(self.client.get(route).status_code,403);self.assertEqual(self.driver.get(route).status_code,403)
        for route in [P+f'/{did}',P+f'/{did}/csv','/api/logistics/documents/'+str(did)]:self.assertEqual(c.get(route).status_code,404)
        self.assertEqual(c.get(P).json['total'],0)
        self.assertEqual(self.action(did,'dispatch',c).status_code,404)
        self.assertEqual(self.action(did,'receive',self.company_user,tracking=self.ps[0]['tracking']).status_code,403)
        self.assertEqual(self.action(did,'receive-all',self.company_user,expected_remaining=3).status_code,403)
        self.assertEqual(self.company_user.post(P,json=self.draft_data()).status_code,403)

    def test_forced_owner_and_mixed_manifest_rejected_atomically(self):
        foreign=next(p for p in self.data(self.admin)['parcels'] if p['client_id']==2)
        d=self.draft_data(client_id=2,parcel_ids=[self.ps[0]['id'],foreign['id']]);r=self.mutate(self.company_user,P,d);self.assertEqual(r.status_code,404)
        self.assertFalse(self.state(self.ps[0]['id'])['operations_locked']);self.assertEqual(self.admin.get(P).json['total'],0)
        did=self.draft(client_id=2);self.assertEqual(self.detail(did)['client_id'],self.company['id'])

    def test_prepare_locks_no_receipt_or_tracking_money_change(self):
        before=[dict(p) for p in self.ps];did=self.draft();doc=self.detail(did)
        self.assertEqual((doc['status'],doc['received'],doc['remaining']),('Préparé',0,3));self.assertTrue(doc['reference'].startswith('PP-'))
        for p in before:
            fresh=self.state(p['id']);self.assertTrue(fresh['operations_locked'])
            for field in ['tracking','client_id','status','amount','fee','return_fee','invoice_id','driver_id','current_hub_id','ops_revision']:self.assertEqual(fresh[field],p[field],field)
        self.assertEqual(self.company_user.get(P+'/candidates').json['rows'],[])
        self.assertEqual(self.mutate(self.company_user,P,self.draft_data()).status_code,409)

    def test_input_validation_hubs_and_seller_client(self):
        for patch in [dict(parcel_ids=[]),dict(parcel_ids=[True]),dict(parcel_ids=[self.ps[0]['id']]*2),dict(parcel_ids=list(range(1,502))),dict(request_key='x'),dict(partner_reference='x'*81),dict(destination_hub_id=99999),dict(destination_hub_id=True),dict(destination_hub_id=[])]:
            r=self.mutate(self.company_user,P,self.draft_data(**patch));self.assertIn(r.status_code,[400,409],r.json)
        self.assertEqual(self.mutate(self.admin,P,self.draft_data(client_id=2)).status_code,400)
        self.assertEqual(self.admin.get(P).json['total'],0)

    def test_existing_operational_locks_and_creation_eligibility(self):
        for fields in [{'driver_id':3},{'status':'Réceptionné'},{'current_hub_id':self.hub}]:
            with system.conn() as c:
                c.execute('UPDATE parcels SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',list(fields.values())+[self.ps[0]['id']])
            self.assertEqual(self.mutate(self.company_user,P,self.draft_data()).status_code,409)
            with system.conn() as c:c.execute("UPDATE parcels SET status='Créé',driver_id=NULL,current_hub_id=NULL WHERE id=?",(self.ps[0]['id'],))
        r=self.mutate(self.admin,'/api/logistics/documents',dict(kind='pickup',client_id=self.company['id'],destination_hub_id=self.hub,parcel_ids=[self.ps[0]['id']]))
        self.assertEqual(r.status_code,200,r.json);self.assertEqual(self.mutate(self.company_user,P,self.draft_data()).status_code,409)

    def test_idempotent_create_dispatch_receipt_payload_bound(self):
        d=self.draft_data();a=self.mutate(self.company_user,P,d);b=self.mutate(self.company_user,P,d);self.assertEqual(a.json['id'],b.json['id']);self.assertTrue(b.json['replayed'])
        self.assertEqual(self.mutate(self.company_user,P,{**d,'note':'Changed'}).status_code,409)
        did=a.json['id'];payload=dict(revision=1,confirmed=True,request_key=secrets.token_hex(16));url=f'{P}/{did}/dispatch'
        self.assertEqual(self.mutate(self.company_user,url,payload).status_code,200);self.assertTrue(self.mutate(self.company_user,url,payload).json['replayed'])
        payload=dict(revision=2,confirmed=True,request_key=secrets.token_hex(16),tracking=self.ps[0]['tracking']);url=f'{P}/{did}/receive'
        self.assertEqual(self.mutate(self.admin,url,payload).status_code,200);self.assertTrue(self.mutate(self.admin,url,payload).json['replayed'])
        self.assertEqual(self.mutate(self.admin,url,{**payload,'tracking':self.ps[1]['tracking']}).status_code,409)
        self.assertEqual(self.detail(did)['received'],1)

    def test_dispatch_keeps_parcel_created_and_requires_physical_confirmation(self):
        did=self.draft();self.assertEqual(self.action(did,'dispatch',self.company_user,confirmed=False).status_code,400)
        self.assertEqual(self.action(did,'receive',tracking=self.ps[0]['tracking']).status_code,409)
        self.dispatch(did);self.assertEqual(self.detail(did)['status'],'En transit')
        for p in self.ps:self.assertEqual(self.state(p['id'])['status'],'Créé');self.assertIsNone(self.state(p['id'])['current_hub_id'])
        self.assertEqual(self.action(did,'cancel',reason='Ne pas effacer un envoi').status_code,409)

    def test_partial_receipt_releases_only_arrived_parcel_preserves_money(self):
        did=self.draft();self.dispatch(did);before=[self.state(p['id']) for p in self.ps]
        r=self.action(did,'receive',tracking=self.ps[0]['tracking'].lower());self.assertEqual(r.status_code,200,r.json)
        doc=self.detail(did);self.assertEqual((doc['status'],doc['received'],doc['remaining']),('Partiellement reçu',1,2))
        for i,p in enumerate(before):
            fresh=self.state(p['id'])
            for k in ['tracking','client_id','amount','fee','return_fee','invoice_id','driver_id']:self.assertEqual(fresh[k],p[k],k)
            self.assertEqual(fresh['status'],'Réceptionné' if i==0 else 'Créé');self.assertEqual(bool(fresh['operations_locked']),i!=0)
            self.assertEqual(fresh['current_hub_id'],self.hub if i==0 else None)
        self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(self.ps[0]['id']),{'driver_id':3},'patch').status_code,200)
        self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(self.ps[1]['id']),{'driver_id':3},'patch').status_code,409)
        self.assertEqual(self.company_user.get(P+f'/{did}').json['remaining'],2)

    def test_duplicate_scan_never_resets_subsequent_driver_assignment(self):
        did=self.draft();self.dispatch(did);self.action(did,'receive',tracking=self.ps[0]['tracking'])
        self.mutate(self.admin,'/api/parcels/'+str(self.ps[0]['id']),{'driver_id':3,'status':'En livraison'},'patch')
        before=self.state(self.ps[0]['id']);r=self.action(did,'receive',tracking=self.ps[0]['tracking'],revision=1)
        self.assertEqual(r.status_code,200);self.assertTrue(r.json['already_received']);self.assertEqual(self.state(self.ps[0]['id']),before)
        self.assertEqual(self.detail(did)['received'],1)

    def test_receive_all_requires_current_count_and_revision_and_confirmation(self):
        did=self.draft();self.dispatch(did)
        for patch in [dict(expected_remaining=2),dict(expected_remaining=3,revision=1),dict(expected_remaining=3,confirmed=False)]:self.assertIn(self.action(did,'receive-all',**patch).status_code,[400,409])
        self.assertEqual(self.detail(did)['received'],0)
        self.action(did,'receive',tracking=self.ps[0]['tracking'])
        r=self.action(did,'receive-all',expected_remaining=2);self.assertEqual(r.status_code,200,r.json)
        d=self.detail(did);self.assertEqual((d['status'],d['received'],d['remaining']),('Reçu',3,0));self.assertTrue(d['completed_at'])
        for p in self.ps:self.assertFalse(self.state(p['id'])['operations_locked']);self.assertEqual(self.state(p['id'])['status'],'Réceptionné')

    def test_bulk_receipt_revalidation_atomic_rollback(self):
        did=self.draft();self.dispatch(did)
        with system.conn() as c:c.execute("UPDATE parcels SET status='Livré' WHERE id=?",(self.ps[2]['id'],))
        self.assertEqual(self.action(did,'receive-all',expected_remaining=3).status_code,409)
        d=self.detail(did);self.assertEqual(d['received'],0);self.assertEqual(d['revision'],2)
        self.assertEqual(self.state(self.ps[0]['id'])['status'],'Créé')

    def test_inactive_hub_prevents_dispatch_receipt_inactive_company_admin_can_receive(self):
        did=self.draft()
        with system.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.action(did,'dispatch',self.company_user).status_code,409)
        with system.conn() as c:c.execute('UPDATE ops_hubs SET active=1 WHERE id=?',(self.hub,))
        self.dispatch(did)
        with system.conn() as c:c.execute('UPDATE users SET active=0 WHERE id=?',(self.company['id'],));c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.action(did,'receive-all',expected_remaining=3).status_code,409)
        with system.conn() as c:c.execute('UPDATE ops_hubs SET active=1 WHERE id=?',(self.hub,))
        self.assertEqual(self.action(did,'receive-all',expected_remaining=3).status_code,200)

    def test_draft_cancellation_releases_without_deletion(self):
        did=self.draft();r=self.action(did,'cancel',self.company_user,reason='Correction du manifeste');self.assertEqual(r.status_code,200,r.json)
        d=self.detail(did);self.assertEqual(d['status'],'Annulé');self.assertEqual(len(d['lines']),3);self.assertEqual(len(d['audit']),2)
        for p in self.ps:self.assertFalse(self.state(p['id'])['operations_locked']);self.assertEqual(self.state(p['id'])['status'],'Créé')
        self.assertNotEqual(self.draft(),did)

    def test_old_endpoints_cannot_bypass_partner_receipt(self):
        did=self.draft();pid=self.ps[0]['id']
        for action in ['dispatch','cancel','receive']:
            r=self.mutate(self.admin,f'/api/logistics/documents/{did}/{action}',dict(revision=1,tracking=self.ps[0]['tracking'],reason='Legacy'))
            self.assertEqual(r.status_code,409,r.json)
        for data in [{'status':'Réceptionné'},{'driver_id':3}]:self.assertEqual(self.mutate(self.admin,'/api/parcels/'+str(pid),data,'patch').status_code,409)
        self.assertEqual(self.mutate(self.admin,'/api/drivers-workspace/3/scan-preview',dict(mode='assign',tracking=self.ps[0]['tracking'])).status_code,409)
        self.assertEqual(self.mutate(self.admin,'/api/logistics/assignments/preview',dict(driver_id=3,parcel_ids=[pid])).status_code,409)
        self.assertEqual(self.detail(did)['received'],0)

    def test_list_search_csv_scope_and_no_financial_entries(self):
        did=self.draft();self.dispatch(did);self.action(did,'receive',tracking=self.ps[0]['tracking'])
        self.assertEqual(self.company_user.get(P+'?q=00000%2FAb').json['total'],1)
        self.assertEqual(self.company_user.get(P+'?state=Partiellement%20re%C3%A7u').json['total'],1)
        self.assertEqual(self.company_user.get(P+'?page=99&size=20').json['page'],1)
        self.assertEqual(self.company_user.get(P+'?size=500').status_code,400)
        csv=self.company_user.get(P+f'/{did}/csv');self.assertEqual(csv.status_code,200)
        for p in self.ps:self.assertIn(p['tracking'],csv.data.decode('utf-8-sig'))
        with system.conn() as c:
            for table in ['invoices','driver_statements','client_receipts','driver_transactions']:
                self.assertEqual(c.execute('SELECT count(*) FROM '+table).fetchone()[0],0,table)

    def test_concurrent_creation_shares_one_active_document_lock(self):
        tasks=[('post',P,self.draft_data()),('post',P,self.draft_data())]
        rs=self.parallel(tasks);self.assertEqual(sorted(r.status_code for r in rs),[200,409]);self.assertEqual(self.admin.get(P).json['total'],1)

    def test_concurrent_receive_same_key_exactly_once(self):
        did=self.draft();self.dispatch(did);d=dict(revision=2,confirmed=True,request_key=secrets.token_hex(16),tracking=self.ps[0]['tracking'])
        rs=self.parallel([('post',f'{P}/{did}/receive',d)]*2);self.assertEqual([r.status_code for r in rs],[200,200]);self.assertEqual(self.detail(did)['received'],1)
        with system.conn() as c:self.assertEqual(c.execute("SELECT count(*) FROM events WHERE parcel_id=? AND status='Réceptionné'",(self.ps[0]['id'],)).fetchone()[0],1)

    def test_wrong_tracking_and_financial_guard_preserve_missing(self):
        did=self.draft();self.dispatch(did);self.assertEqual(self.action(did,'receive',tracking='NOT-IN-MANIFEST').status_code,404)
        self.assertEqual(self.detail(did)['remaining'],3)
        # Completed intake cannot be repeated even after a manual status reset.
        self.action(did,'receive',tracking=self.ps[0]['tracking'])
        with system.conn() as c:c.execute("UPDATE parcels SET status='Créé',current_hub_id=NULL WHERE id=?",(self.ps[0]['id'],))
        self.assertEqual(self.mutate(self.company_user,P,self.draft_data(parcel_ids=[self.ps[0]['id']])).status_code,409)

if __name__=='__main__':unittest.main(verbosity=2)
