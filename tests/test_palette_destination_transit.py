import unittest
import test_hub_palette_flow as fixture
from parcel_transit import annotate_parcel_transit

class PaletteDestinationTransitTests(unittest.TestCase):
    def setUp(self):
        self.t=fixture.HubPaletteFlowTests();self.t.setUp();self.client=self.t.client;self.conn=self.t.conn
        with self.conn() as c:
            c.execute("INSERT INTO cities(id,name,region,hub_id) VALUES(4,'Other city covered by A','Region',10)")
            c.execute('UPDATE parcels SET current_hub_id=90 WHERE id=3')
            for pid,city,loc in [(6,4,90),(7,3,90),(8,1,90),(9,2,10)]:
                c.execute("INSERT INTO parcels(id,tracking,recipient,status,amount,city_id,current_hub_id,created_at,updated_at) VALUES(?,?,?,'Réceptionné',20,?,?,?,?)",(pid,'CAND-'+str(pid),'Test',city,loc,'2026-01-01','2026-01-01'))
    def tearDown(self):self.t.tearDown()
    def candidates(self,dest,role='admin'):
        return self.client.get('/api/logistics/palette-candidates',query_string={'source_hub_id':90,'destination_hub_id':dest,'mode':'standard'},headers=self.t.headers(role,90,990) if role=='agent' else self.t.headers('admin'))
    def annotations(self):
        with self.conn() as c:return {p['id']:p for p in annotate_parcel_transit(c,[dict(r) for r in c.execute('SELECT * FROM parcels')])}
    def test_central_filters_all_cities_covered_by_selected_hub(self):
        for role in ('admin','agent'):
            r=self.candidates(10,role);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual({p['id'] for p in r.json['rows']},{3,6})
            self.assertEqual(r.json['destination_hub_id'],10)
            r=self.candidates(20,role);self.assertEqual({p['id'] for p in r.json['rows']},{7})
    def test_mapping_change_and_unassigned_city_remove_candidates(self):
        with self.conn() as c:c.execute('UPDATE cities SET hub_id=NULL WHERE id=4');c.execute('UPDATE cities SET hub_id=20 WHERE id=2')
        self.assertEqual(self.candidates(10).json['rows'],[])
        self.assertEqual({p['id'] for p in self.candidates(20).json['rows']},{3,7})
    def test_wrong_destination_rejected_at_creation(self):
        r=self.t.create_palette('admin',None,'standard',90,10,[3,7],1)
        self.assertEqual(r.status_code,409,r.json)
        with self.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM ops_documents').fetchone()[0],0)
    def test_invalid_destination_and_secondary_route_rejected(self):
        self.assertEqual(self.candidates(90).status_code,409)
        self.assertEqual(self.candidates(999).status_code,400)
        r=self.client.get('/api/logistics/palette-candidates?source_hub_id=10&destination_hub_id=20',headers=self.t.headers('admin'))
        self.assertEqual(r.status_code,409)
    def test_inbound_central_does_not_filter_by_delivery_city(self):
        with self.conn() as c:c.execute('UPDATE parcels SET current_hub_id=10 WHERE id IN (3,6,7)')
        r=self.client.get('/api/logistics/palette-candidates?source_hub_id=10&destination_hub_id=90',headers=self.t.headers('agent',10,910))
        self.assertEqual(r.status_code,200,r.json);self.assertEqual({p['id'] for p in r.json['rows']},{3,6,7,9})
    def test_outbound_badge_uses_actual_transfer_not_parcel_city(self):
        r=self.t.create_palette('agent',90,'standard',90,10,[3],990);self.assertEqual(r.status_code,200,r.json);did=r.json['id']
        self.assertIsNone(self.annotations()[3]['transit_direction'])
        self.assertEqual(self.t.scan_departure(did,'TRK-STANDARD',90,990).status_code,200)
        p=self.annotations()[3];self.assertEqual(p['transit_direction'],'destination');self.assertEqual(p['transit_destination'],'Hub A')
        with self.conn() as c:c.execute('UPDATE parcels SET city_id=3 WHERE id=3')
        self.assertEqual(self.annotations()[3]['transit_destination'],'Hub A')
        self.assertEqual(self.t.receive(did,'TRK-STANDARD',10,910).status_code,200)
        self.assertIsNone(self.annotations()[3]['transit_direction'])
    def test_partial_inbound_badge_only_for_physically_departed_line(self):
        with self.conn() as c:c.execute('UPDATE parcels SET current_hub_id=10 WHERE id IN (3,6)')
        r=self.t.create_palette('agent',10,'standard',10,90,[3,6],910);did=r.json['id']
        self.assertEqual(self.t.scan_departure(did,'TRK-STANDARD',10,910).status_code,200)
        ps=self.annotations();self.assertEqual(ps[3]['transit_direction'],'central');self.assertIsNone(ps[6]['transit_direction'])
        self.assertEqual(self.t.receive(did,'TRK-STANDARD',90,990).status_code,200)
        self.assertIsNone(self.annotations()[3]['transit_direction'])
    def test_status_alone_never_invents_direction(self):
        with self.conn() as c:c.execute("UPDATE parcels SET status='Transit',current_hub_id=NULL WHERE id=3")
        self.assertIsNone(self.annotations()[3]['transit_direction'])
