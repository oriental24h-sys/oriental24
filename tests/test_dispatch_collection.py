import unittest, uuid, sqlite3
import test_reception_collection as base
from dispatch_collection import register_dispatch_collection
from hub_access import hub_manager_route_allowed

class DispatchCollectionTests(unittest.TestCase):
    def setUp(self):
        self.r=base.ReceptionCollectionTests();self.r.setUp();self.t=self.r.t
        register_dispatch_collection(self.t.app,self.t.services)
        self.client=self.t.client;self.conn=self.t.conn
        self.admin=self.t.headers('admin');self.source=self.t.headers('agent',10,910);self.central=self.t.headers('agent',90,990)
    def tearDown(self):self.r.tearDown()
    def manifest(self,kind,did,headers=None):
        r=self.client.get(f'/api/dispatch-collection/{kind}/{did}',headers=headers or self.admin)
        self.assertEqual(r.status_code,200,r.json);return r.json
    def payload(self,d):return dict(snapshot=d['snapshot'],line_ids=[l['id'] for l in d['lines'] if not l['received_at'] and not l['excluded']],confirmed=True,request_key=uuid.uuid4().hex)
    def commit(self,kind,did,d,headers=None):return self.client.post(f'/api/dispatch-collection/{kind}/{did}',headers=headers or self.admin,json=d)
    def check(self,kind,did,d,code,headers=None):return self.client.get(f'/api/dispatch-collection/{kind}/{did}/check',query_string={'tracking':code,'snapshot':d['snapshot']},headers=headers or self.admin)
    def palette(self,kind):
        did=self.r.palette(kind)
        with self.conn() as c:
            c.execute("UPDATE ops_documents SET status='Préparé',dispatched_at=NULL WHERE id=?",(did,))
            if kind=='return':c.execute('UPDATE parcels SET current_hub_id=90 WHERE id IN (3,4)')
        return did

    def test_transfer_reads_do_not_dispatch_then_atomic_commit_replay(self):
        did=self.r.transfer();d=self.manifest('transfer',did,self.source);p=self.payload(d)
        for l in d['lines']:self.assertEqual(self.check('transfer',did,d,l['tracking'],self.source).status_code,200)
        self.assertEqual(self.t.parcel_state(3)['current_hub_id'],10)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE departure_scanned_at IS NOT NULL').fetchone()[0],0)
        self.assertEqual(self.commit('transfer',did,{**p,'line_ids':[999999]},self.source).status_code,409)
        r=self.commit('transfer',did,p,self.source);self.assertEqual(r.status_code,200,r.json)
        self.assertIsNone(self.t.parcel_state(3)['current_hub_id']);self.assertEqual(self.t.parcel_state(3)['status'],'Transit')
        self.assertTrue(self.commit('transfer',did,p,self.source).json['replayed'])
        with self.conn() as c:self.assertEqual(c.execute("SELECT count(*) FROM ops_audit WHERE document_id=? AND action='Départ physique confirmé'",(did,)).fetchone()[0],1)
        self.assertTrue(hub_manager_route_allowed('GET',f'/api/dispatch-collection/transfer/{did}/check'))

    def test_selected_dispatch_releases_unscanned_for_another_palette(self):
        did=self.r.transfer();detail=self.manifest('transfer',did,self.source)
        self.assertTrue(detail['allow_partial_dispatch'])
        p=self.payload(detail);p['line_ids']=p['line_ids'][:1]
        r=self.commit('transfer',did,p,self.source);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual((r.json['dispatched'],r.json['released']),(1,1))
        self.assertTrue(self.commit('transfer',did,p,self.source).json['replayed'])
        self.assertEqual(self.t.parcel_state(3)['status'],'Transit')
        self.assertEqual(self.t.parcel_state(4)['current_hub_id'],10)
        self.assertEqual(self.t.parcel_state(4)['status'],'Réceptionné')
        with self.conn() as c:
            doc=c.execute('SELECT * FROM ops_documents WHERE id=?',(did,)).fetchone()
            self.assertEqual(doc['status'],'En transit')
            ls=[dict(l) for l in c.execute('SELECT * FROM ops_document_lines WHERE document_id=? ORDER BY parcel_id',(did,))]
            self.assertEqual(ls[1]['active'],0);self.assertIsNotNone(ls[1]['departure_reconciled_at'])
            self.assertIsNone(ls[1]['departure_scanned_at'])
            from hub_access import ops_manifest_counts
            self.assertEqual(ops_manifest_counts(ls)['count'],1)
        received=self.r.manifest('transfer',did,self.central)
        self.assertEqual(len([l for l in received['lines'] if not l['excluded']]),1)
        new=self.t.create_palette('agent',10,'standard',10,90,[4],910)
        self.assertEqual(new.status_code,200,new.json)
        self.assertEqual(self.r.commit('transfer',did,self.r.body(received),self.central).status_code,200)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT active FROM ops_document_lines WHERE document_id=?',(new.json['id'],)).fetchone()[0],1)
        self.assertEqual(self.t.parcel_state(4)['current_hub_id'],10)

    def test_selected_dispatch_failure_restores_released_locks(self):
        did=self.r.transfer();p=self.payload(self.manifest('transfer',did));p['line_ids']=p['line_ids'][:1]
        self.assertEqual(self.commit('transfer',did,{**p,'line_ids':[]}).status_code,400)
        with self.conn() as c:
            c.execute("CREATE TRIGGER fail_selected BEFORE UPDATE ON parcels WHEN NEW.id=3 AND NEW.status='Transit' BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.commit('transfer',did,p)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND active=1 AND departure_reconciled_at IS NULL',(did,)).fetchone()[0],2)
            self.assertEqual(c.execute('SELECT count(*) FROM dispatch_collection_keys').fetchone()[0],0)
        self.assertEqual(self.t.parcel_state(3)['current_hub_id'],10)

    def test_transfer_source_scope_only(self):
        did=self.r.transfer();p=self.payload(self.manifest('transfer',did))
        self.assertEqual(self.commit('transfer',did,p,self.central).status_code,404)
        self.assertEqual(self.commit('transfer',did,p,self.t.headers('client',None,2)).status_code,403)
        with self.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        self.assertEqual(self.commit('transfer',did,p,self.source).status_code,403)

    def test_city_mapping_rechecked_without_partial_dispatch(self):
        with self.conn() as c:c.execute('UPDATE parcels SET current_hub_id=90 WHERE id IN (3,4)')
        r=self.t.create_palette('agent',90,'standard',90,10,[3,4],990);self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        d=self.manifest('transfer',did,self.central)
        with self.conn() as c:c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        self.assertEqual(self.check('transfer',did,d,'TRK-STANDARD',self.central).status_code,409)
        self.assertEqual(self.commit('transfer',did,self.payload(d),self.central).status_code,409)
        fresh=self.manifest('transfer',did,self.central);self.assertTrue(all(l['blocked'] for l in fresh['lines']))
        self.assertEqual(self.commit('transfer',did,self.payload(fresh),self.central).status_code,409)
        self.assertEqual(self.t.parcel_state(3)['current_hub_id'],90)

    def test_company_sender_and_destination_agent_permissions(self):
        did=self.palette('partner');owner=self.t.headers('client',None,6);d=self.manifest('partner',did,owner)
        self.assertEqual(self.commit('partner',did,self.payload(d),self.central).status_code,403)
        self.assertEqual(self.commit('partner',did,self.payload(d),self.t.headers('client',None,2)).status_code,404)
        p=self.payload(d);r=self.commit('partner',did,p,owner);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(3)['status'],'Créé');self.assertIsNone(self.t.parcel_state(3)['current_hub_id'])
        self.assertTrue(self.commit('partner',did,p,owner).json['replayed'])

    def test_return_dispatch_keeps_business_status_and_money(self):
        did=self.palette('return');d=self.manifest('return',did,self.central);before=self.t.parcel_state(3)
        self.assertEqual(self.commit('return',did,self.payload(d),self.t.headers('client',None,2)).status_code,403)
        p=self.payload(d);r=self.commit('return',did,p,self.central);self.assertEqual(r.status_code,200,r.json)
        after=self.t.parcel_state(3)
        for k in ('status','amount','invoice_id'):self.assertEqual(after[k],before[k])
        self.assertTrue(self.commit('return',did,p,self.central).json['replayed'])

    def test_legacy_partial_departure_only_requires_remaining(self):
        did=self.r.transfer();self.r.dispatch(did,(3,))
        d=self.manifest('transfer',did,self.source);p=self.payload(d)
        self.assertEqual(len(p['line_ids']),1)
        self.assertTrue(self.check('transfer',did,d,'TRK-STANDARD',self.source).json['already_scanned'])
        self.assertEqual(self.commit('transfer',did,p,self.source).status_code,200)
        with self.conn() as c:self.assertEqual(c.execute('SELECT status FROM ops_documents WHERE id=?',(did,)).fetchone()[0],'En transit')

    def test_trigger_failure_rolls_back_all_writes(self):
        did=self.r.transfer();p=self.payload(self.manifest('transfer',did))
        with self.conn() as c:c.execute("CREATE TRIGGER fail_last BEFORE UPDATE ON parcels WHEN NEW.id=4 AND NEW.status='Transit' BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(sqlite3.IntegrityError):self.commit('transfer',did,p)
        self.assertEqual(self.t.parcel_state(3)['current_hub_id'],10)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM dispatch_collection_keys').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE departure_scanned_at IS NOT NULL').fetchone()[0],0)

    def test_special_return_to_central_preserves_financial_fields(self):
        did=self.r.transfer(purpose='return_to_central');before=self.t.parcel_state(3)
        r=self.commit('transfer',did,self.payload(self.manifest('transfer',did)),self.admin);self.assertEqual(r.status_code,200,r.json)
        # The return departure keeps the delivery status and only sets the return state.
        after=self.t.parcel_state(3);self.assertEqual(after['status'],'Refusé');self.assertEqual(after['return_state'],'envoye')
        self.assertEqual(after['amount'],before['amount']);self.assertEqual(after['invoice_id'],before['invoice_id'])

    def test_duplicate_ids_confirmation_and_stale_parcel(self):
        did=self.palette('partner');d=self.manifest('partner',did);p=self.payload(d)
        self.assertEqual(self.commit('partner',did,{**p,'confirmed':False}).status_code,400)
        self.assertEqual(self.commit('partner',did,{**p,'line_ids':[p['line_ids'][0]]*2}).status_code,400)
        with self.conn() as c:c.execute("UPDATE parcels SET recipient='Changed' WHERE id=4")
        self.assertEqual(self.commit('partner',did,p).status_code,409)
