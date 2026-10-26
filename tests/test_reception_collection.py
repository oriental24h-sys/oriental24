import unittest, json, uuid
import test_hub_palette_flow as fixtures
from partner_palettes import register_partner_palettes
from return_palettes import register_return_palettes
from fusion_reception import register_fusion_reception
from reception_collection import register_reception_collection
from palette_console import register_palette_console

class ReceptionCollectionTests(unittest.TestCase):
    def setUp(self):
        self.t=fixtures.HubPaletteFlowTests();self.t.setUp()
        s=self.t.services;a=self.t.app
        with self.t.conn() as c:
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_at TEXT')
            c.execute('ALTER TABLE ops_document_lines ADD COLUMN missing_by INTEGER')
            c.execute("ALTER TABLE parcels ADD COLUMN address TEXT DEFAULT ''")
            c.execute("ALTER TABLE parcels ADD COLUMN product TEXT DEFAULT ''")
        register_partner_palettes(a,s);register_return_palettes(a,s);register_fusion_reception(a,s)
        register_palette_console(a,s)
        register_reception_collection(a,s)
        self.client=self.t.client;self.conn=self.t.conn
        self.admin=self.t.headers('admin');self.central=self.t.headers('agent',90,990);self.other=self.t.headers('agent',20,920)
        with self.conn() as c:
            c.execute("INSERT INTO users(id,name,email,role,client_type) VALUES(2,'Seller','s@test','client','vendeur')")
            c.execute("INSERT INTO users(id,name,email,role,client_type) VALUES(6,'Company','c@test','client','societe_livraison')")
            c.execute('UPDATE parcels SET invoice_id=NULL WHERE id=4')

    def tearDown(self):self.t.tearDown()
    def manifest(self,kind,did,headers=None):
        r=self.client.get(f'/api/reception-collection/{kind}/{did}',headers=headers or self.admin)
        self.assertEqual(r.status_code,200,r.json);return r.json
    def body(self,detail):
        return dict(snapshot=detail['snapshot'],confirmed=True,request_key=uuid.uuid4().hex,line_ids=[x['id'] for x in detail['lines'] if not x['received_at'] and not x['excluded']])
    def commit(self,kind,did,d,headers=None):return self.client.post(f'/api/reception-collection/{kind}/{did}',json=d,headers=headers or self.admin)
    def transfer(self,ids=(3,4),purpose='standard'):
        if purpose!='standard':
            with self.conn() as c:c.execute("UPDATE parcels SET status='Refusé' WHERE id IN (3,4)")
        r=self.t.create_palette('agent',10,purpose,10,90,list(ids),910)
        self.assertEqual(r.status_code,200,r.json);return r.json['id']
    def dispatch(self,did,ids=(3,4)):
        for pid in ids:
            tracking=self.t.parcel_state(pid)['tracking']
            r=self.t.scan_departure(did,tracking,10,910);self.assertEqual(r.status_code,200,r.json)
    def palette(self,kind,ids=(3,4)):
        cid=6 if kind=='partner' else 2
        with self.conn() as c:
            cur=c.execute("INSERT INTO ops_documents(reference,kind,client_id,source_hub_id,destination_hub_id,source_name,destination_name,client_name,status,note,created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",('TEST-'+uuid.uuid4().hex,kind+'_palette',cid,10,90,'Hub A','Central','Client','En transit','',1,'2026-01-01T00:00:00'))
            did=cur.lastrowid
            c.execute('INSERT INTO '+('partner' if kind=='partner' else 'return')+'_palette_meta(document_id) VALUES(?)',(did,))
            for pid in ids:
                c.execute('UPDATE parcels SET client_id=?,status=?,current_hub_id=?,driver_id=NULL WHERE id=?',(cid,'Créé' if kind=='partner' else 'Refusé',None if kind=='partner' else 10,pid))
                p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
                c.execute('INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,?,?,?)',(did,pid,p['tracking'],p['recipient'],'City',p['status']))
            return did

    def test_transfer_atomic_all_scanned_and_replay(self):
        did=self.transfer();self.dispatch(did)
        detail=self.manifest('transfer',did,self.central);d=self.body(detail)
        self.assertTrue(all(not l['recipient'] for l in detail['lines']))
        self.assertEqual(self.t.parcel_state(3)['status'],'Transit')
        first={**d,'line_ids':d['line_ids'][:1]}
        r=self.commit('transfer',did,first,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['received'],1)
        self.assertEqual(self.t.parcel_state(3)['status'],'Réceptionné')
        self.assertEqual(self.t.parcel_state(4)['status'],'Transit')
        self.assertTrue(self.commit('transfer',did,first,self.central).json['replayed'])
        fresh=self.manifest('transfer',did,self.central)
        self.assertEqual(fresh['status'],'Partiellement reçu')
        remaining=self.body(fresh);self.assertEqual(len(remaining['line_ids']),1)
        r=self.commit('transfer',did,remaining,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.manifest('transfer',did,self.central)['status'],'Reçu')
        self.assertEqual(self.client.get(f'/api/reception-collection/transfer/{did}',headers=self.other).status_code,404)
        self.assertEqual(self.client.get(f'/api/reception-collection/transfer/{did}',headers=self.t.headers('client',None,2)).status_code,403)

    def test_received_line_can_be_forwarded_before_old_palette_complete(self):
        did=self.transfer();self.dispatch(did)
        d=self.body(self.manifest('transfer',did,self.central));d['line_ids']=d['line_ids'][:1]
        self.assertEqual(self.commit('transfer',did,d,self.central).status_code,200)
        with self.conn() as c:
            rows=c.execute('SELECT parcel_id,active,received_at FROM ops_document_lines WHERE document_id=? ORDER BY parcel_id',(did,)).fetchall()
            self.assertEqual(rows[0]['active'],0);self.assertIsNotNone(rows[0]['received_at'])
            self.assertEqual(rows[1]['active'],1);self.assertIsNone(rows[1]['received_at'])
            c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        r=self.client.get('/api/logistics/palette-candidates?mode=standard&source_hub_id=90&destination_hub_id=20',headers=self.central)
        self.assertEqual(r.status_code,200,r.json)
        self.assertIn(3,[p['id'] for p in r.json['rows']]);self.assertNotIn(4,[p['id'] for p in r.json['rows']])
        new=self.t.create_palette('agent',90,'standard',90,20,[3],990)
        self.assertEqual(new.status_code,200,new.json)
        # Finish the first palette after its first received parcel was already forwarded.
        rest=self.body(self.manifest('transfer',did,self.central))
        self.assertEqual(self.commit('transfer',did,rest,self.central).status_code,200)
        with self.conn() as c:
            self.assertEqual(c.execute('SELECT active FROM ops_document_lines WHERE document_id=? AND parcel_id=3',(new.json['id'],)).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()[0],2)

    def test_legacy_received_lock_repair_is_idempotent(self):
        from logistics import release_received_transfer_lines
        did=self.transfer();self.dispatch(did)
        d=self.body(self.manifest('transfer',did,self.central));d['line_ids']=d['line_ids'][:1]
        self.assertEqual(self.commit('transfer',did,d,self.central).status_code,200)
        with self.conn() as c:
            c.execute('UPDATE ops_document_lines SET active=1 WHERE id=?',(d['line_ids'][0],))
            self.assertEqual(release_received_transfer_lines(c),1)
            self.assertEqual(release_received_transfer_lines(c),0)
            self.assertEqual(c.execute('SELECT active FROM ops_document_lines WHERE document_id=? AND parcel_id=4',(did,)).fetchone()[0],1)

    def test_partial_departure_blocks_final_validation(self):
        did=self.transfer();self.dispatch(did,(3,))
        detail=self.manifest('transfer',did,self.central)
        self.assertEqual(sum(x['blocked'] for x in detail['lines']),1)
        r=self.commit('transfer',did,self.body(detail),self.central);self.assertEqual(r.status_code,409)
        self.assertEqual(self.t.parcel_state(3)['status'],'Transit')
        d=self.body(detail);d['line_ids']=[l['id'] for l in detail['lines'] if not l['blocked']]
        r=self.commit('transfer',did,d,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(3)['status'],'Réceptionné')
        self.assertNotEqual(self.t.parcel_state(4)['current_hub_id'],90)
        fresh=self.manifest('transfer',did,self.central)
        self.assertEqual(sum(bool(l['received_at']) for l in fresh['lines']),1)

    def test_stale_snapshot_and_rollback_on_second_parcel(self):
        did=self.transfer();self.dispatch(did);d=self.body(self.manifest('transfer',did))
        with self.conn() as c:c.execute("UPDATE parcels SET recipient='Changed' WHERE id=4")
        self.assertEqual(self.commit('transfer',did,d).status_code,409)
        d=self.body(self.manifest('transfer',did))
        with self.conn() as c:c.execute('UPDATE parcels SET invoice_id=123 WHERE id=4')
        # Fresh snapshot, but the second parcel is financially locked: first write must roll back.
        d=self.body(self.manifest('transfer',did))
        self.assertEqual(self.commit('transfer',did,d).status_code,409)
        self.assertEqual(self.t.parcel_state(3)['status'],'Transit')
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND received_at IS NOT NULL',(did,)).fetchone()[0],0)

    def test_partner_agent_batch_and_ownership(self):
        did=self.palette('partner');detail=self.manifest('partner',did,self.central);d=self.body(detail)
        self.assertEqual(self.commit('partner',did,d,self.other).status_code,404)
        r=self.commit('partner',did,d,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(3)['status'],'Réceptionné')
        self.assertTrue(self.commit('partner',did,d,self.central).json['replayed'])

    def test_return_owner_batch_preserves_money(self):
        did=self.palette('return');owner=self.t.headers('client',None,2)
        d=self.body(self.manifest('return',did,owner));before=self.t.parcel_state(3)['amount']
        self.assertEqual(self.commit('return',did,d,self.t.headers('client',None,6)).status_code,404)
        r=self.commit('return',did,d,owner);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(3)['status'],'Retourné');self.assertEqual(self.t.parcel_state(3)['amount'],before)
        self.assertTrue(self.commit('return',did,d,owner).json['replayed'])

    def test_interhub_returns_keep_special_status_rules(self):
        did=self.transfer(purpose='return_to_central');self.dispatch(did)
        # Departure to Central keeps the delivery status and sets the return state.
        self.assertEqual(self.t.parcel_state(3)['status'],'Refusé')
        self.assertEqual(self.t.parcel_state(3)['return_state'],'envoye')
        r=self.commit('transfer',did,self.body(self.manifest('transfer',did,self.central)),self.central)
        self.assertEqual(r.status_code,200,r.json)
        # Central receipt keeps the delivery status and marks the return received.
        self.assertEqual(self.t.parcel_state(3)['status'],'Refusé')
        self.assertEqual(self.t.parcel_state(3)['return_state'],'recu_entrepot')

    def test_fusion_commits_all_child_palettes(self):
        a=self.palette('partner',(3,));b=self.palette('partner',(4,))
        with self.conn() as c:
            bid=c.execute("INSERT INTO fusion_batches(hub_destination_id,created_by,created_at) VALUES(90,1,'2026-01-02')").lastrowid
            c.executemany('INSERT INTO fusion_batch_palettes VALUES(?,?)',[(bid,a),(bid,b)])
        d=self.body(self.manifest('fusion',bid,self.central));r=self.commit('fusion',bid,d,self.central)
        self.assertEqual(r.status_code,200,r.json)
        with self.conn() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM ops_documents WHERE id IN (?,?) AND status='Reçu'",(a,b)).fetchone()[0],2)
        self.assertTrue(self.commit('fusion',bid,d,self.central).json['replayed'])

    def test_duplicates_confirmation_and_inactive_hub(self):
        did=self.palette('partner');d=self.body(self.manifest('partner',did))
        self.assertEqual(self.commit('partner',did,{**d,'confirmed':False}).status_code,400)
        self.assertEqual(self.commit('partner',did,{**d,'line_ids':[d['line_ids'][0]]*2}).status_code,400)
        with self.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=90')
        self.assertEqual(self.commit('partner',did,d,self.central).status_code,403)

    def test_recovered_parcel_uses_same_collection_and_notifies_once(self):
        did=self.palette('partner',(3,))
        with self.conn() as c:
            c.execute("UPDATE ops_document_lines SET missing_at='2026-01-02',active=0 WHERE document_id=?",(did,))
            c.execute("UPDATE ops_documents SET status='Clôturé (écarts)' WHERE id=?",(did,))
            lid=c.execute('SELECT id FROM ops_document_lines WHERE document_id=?',(did,)).fetchone()[0]
        detail=self.manifest('recovered',lid,self.central);d=self.body(detail)
        self.assertEqual(len(d['line_ids']),1)
        r=self.commit('recovered',lid,d,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(3)['status'],'Réceptionné')
        self.assertTrue(self.commit('recovered',lid,d,self.central).json['replayed'])
        with self.conn() as c:
            self.assertIsNone(c.execute('SELECT missing_at FROM ops_document_lines WHERE id=?',(lid,)).fetchone()[0])
            self.assertEqual(c.execute("SELECT count(*) FROM ops_notifications WHERE title LIKE 'Colis retrouvé%'").fetchone()[0],1)

    def test_missing_lines_are_not_silently_received_with_regular_palette(self):
        did=self.palette('partner')
        with self.conn() as c:c.execute("UPDATE ops_document_lines SET missing_at='2026-01-02',active=0 WHERE document_id=? AND parcel_id=4",(did,))
        detail=self.manifest('partner',did,self.central);d=self.body(detail)
        self.assertEqual(len(d['line_ids']),1)
        r=self.commit('partner',did,d,self.central);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.t.parcel_state(4)['status'],'Créé')

    def test_partial_partner_return_and_fusion_resume(self):
        for kind in ('partner','return','fusion'):
            with self.subTest(kind=kind):
                with self.conn() as c:c.execute('DELETE FROM ops_document_lines')
                if kind=='fusion':
                    a=self.palette('partner',(3,));b=self.palette('partner',(4,))
                    with self.conn() as c:
                        did=c.execute("INSERT INTO fusion_batches(hub_destination_id,created_by,created_at) VALUES(90,1,'2026-01-02')").lastrowid
                        c.executemany('INSERT INTO fusion_batch_palettes VALUES(?,?)',[(did,a),(did,b)])
                else:did=self.palette(kind)
                d=self.body(self.manifest(kind,did));d['line_ids']=d['line_ids'][:1]
                r=self.commit(kind,did,d);self.assertEqual(r.status_code,200,r.json)
                self.assertEqual(r.json['received'],1)
                fresh=self.manifest(kind,did)
                self.assertTrue(fresh['available'])
                self.assertEqual(sum(bool(l['received_at']) for l in fresh['lines']),1)
                rest=self.body(fresh);self.assertEqual(len(rest['line_ids']),1)
                r=self.commit(kind,did,rest);self.assertEqual(r.status_code,200,r.json)
                self.assertFalse(self.manifest(kind,did)['available'])

    def test_empty_foreign_and_already_received_rejected(self):
        did=self.palette('partner');d=self.body(self.manifest('partner',did))
        self.assertEqual(self.commit('partner',did,{**d,'line_ids':[]}).status_code,400)
        self.assertEqual(self.commit('partner',did,{**d,'line_ids':[999999]}).status_code,409)
        d['line_ids']=d['line_ids'][:1]
        self.assertEqual(self.commit('partner',did,d).status_code,200)
        fresh=self.body(self.manifest('partner',did));fresh['line_ids']=d['line_ids']
        self.assertEqual(self.commit('partner',did,fresh).status_code,409)

    def test_legacy_single_receipts_still_work_without_batch_count_regression(self):
        for kind in ('partner','return'):
            with self.conn() as c:
                c.execute('DELETE FROM ops_document_lines')
                c.execute("UPDATE parcels SET status='Créé',current_hub_id=NULL WHERE id IN (3,4)")
            did=self.palette(kind)
            d=dict(tracking='TRK-STANDARD',confirmed=True,revision=1,request_key=uuid.uuid4().hex)
            r=self.client.post(f'/{"api/partner-palettes" if kind=="partner" else "api/return-palettes"}/{did}/receive',headers=self.admin,json=d)
            self.assertEqual(r.status_code,200,r.json)
            with self.conn() as c:
                self.assertEqual(c.execute('SELECT status FROM ops_documents WHERE id=?',(did,)).fetchone()[0],'Partiellement reçu' if kind=='partner' else 'Partiellement remis')
