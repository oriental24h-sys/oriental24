import sqlite3
import unittest
from admin_hub_analytics import admin_analytics
from hub_manager_analytics import period

class AdminHubAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''
        CREATE TABLE ops_hubs(id,name,active);
        CREATE TABLE users(id,name,role,driver_hub_id,active);
        CREATE TABLE parcels(id,tracking);
        CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY,parcel_id,new_driver_id,hub_id,created_at);
        CREATE TABLE ops_attempts(id INTEGER PRIMARY KEY,parcel_id,driver_id,operational_hub_id,outcome,created_at);
        CREATE TABLE events(id INTEGER PRIMARY KEY,parcel_id,actor_id,status,note,created_at);
        CREATE TABLE driver_receipts(parcel_id PRIMARY KEY,driver_id,received_at,hub_id);
        INSERT INTO ops_hubs VALUES(10,'Hub A',1),(20,'Hub B',1),(30,'Inactive',0),(40,'Empty',1);
        INSERT INTO users VALUES(1,'Courier A','livreur',10,1),(2,'Courier B','livreur',20,1),(3,'Courier C','livreur',10,1);
        INSERT INTO parcels VALUES(1,'A'),(2,'B'),(3,'C'),(4,'D');
        INSERT INTO ops_assignments VALUES(1,1,1,10,'2026-01-01T10:00:00+01:00'),(2,2,2,20,'2026-01-01T10:00:00+01:00');
        INSERT INTO ops_attempts VALUES(1,1,1,10,'Livré','2026-01-01T11:00:00+01:00');
        ''')
        self.start,self.end=period({'from':'2026-01-01','to':'2026-01-02'})
    def tearDown(self):self.c.close()
    def data(self,hid=None):return admin_analytics(self.c,self.start,self.end,hid)
    def test_global_weighted_totals_and_hub_rows(self):
        d=self.data();z=d['summary']
        self.assertEqual((z['hubs'],z['assigned'],z['processed'],z['pending'],z['progress'],z['delivery_rate']),(4,2,1,1,50,50))
        self.assertEqual({r['id'] for r in d['rows']},{10,20,30,40})
        self.assertEqual(z['active_hubs'],3)
        self.assertEqual(z['risk'],1)
        self.assertTrue(all('Courier' not in r['name'] for r in d['rows']))
    def test_filter_one_hub_preserves_options_and_excludes_other_parcels(self):
        d=self.data(20)
        self.assertEqual([r['id'] for r in d['rows']],[20])
        self.assertEqual(len(d['hubs']),4)
        self.assertEqual([p['tracking'] for p in d['parcels']],['B'])
        self.assertEqual(d['summary']['progress'],0)
    def test_unknown_hub(self):
        with self.assertRaises(LookupError):self.data(999)
    def test_net_recovery_and_delivered_retention_apply_to_daily_and_cards(self):
        self.c.execute("INSERT INTO driver_receipts VALUES(2,2,'2026-01-01T18:00:00+01:00',20)")
        d=self.data();self.assertEqual(d['summary']['assigned'],1)
        b=next(r for r in d['rows'] if r['id']==20)
        self.assertEqual((b['assigned'],b['pending'],sum(b['daily'].values())),(0,0,0))
        self.assertEqual(d['summary']['delivered'],1)
    def test_latest_cycle_once_per_hub_not_one_row_per_driver(self):
        self.c.execute("INSERT INTO ops_assignments VALUES(3,1,3,10,'2026-01-02T10:00:00+01:00')")
        d=self.data(10)
        self.assertEqual(d['summary']['assigned'],1)
        self.assertEqual(d['summary']['processed'],0)
        self.assertEqual(d['rows'][0]['daily'],{'2026-01-01':0,'2026-01-02':1})
    def test_recovered_latest_cycle_does_not_resurrect_previous_driver_cycle(self):
        self.c.execute("INSERT INTO ops_assignments VALUES(3,1,3,10,'2026-01-02T10:00:00+01:00')")
        self.c.execute("INSERT INTO driver_receipts VALUES(1,3,'2026-01-02T18:00:00+01:00',10)")
        self.assertEqual(self.data(10)['summary']['assigned'],0)
    def test_historical_status_change_counts_without_structured_attempt(self):
        self.c.execute("INSERT INTO events VALUES(1,2,2,'Annulé','Statut mis à jour','2026-01-01T11:00:00+01:00')")
        self.assertEqual(self.data()['summary']['processed'],2)
    def test_empty_network_has_dates_and_safe_denominators(self):
        self.c.execute('DELETE FROM ops_hubs');d=self.data()
        self.assertEqual(d['summary']['progress'],0)
        self.assertEqual(len(d['days']),2)
        self.assertEqual(d['rows'],[])
    def test_no_writes_on_analytics_read(self):
        before=self.c.total_changes;self.data()
        self.assertEqual(self.c.total_changes,before)
