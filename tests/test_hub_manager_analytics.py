import sqlite3
import unittest
from datetime import datetime
from hub_manager_analytics import analytics, period, TZ, stamp

class HubManagerAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:');self.c.row_factory=sqlite3.Row
        self.c.executescript('''CREATE TABLE users(id,name,role,driver_hub_id,active);
        CREATE TABLE parcels(id,tracking);
        CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY,parcel_id,new_driver_id,hub_id,created_at);
        CREATE TABLE ops_attempts(id INTEGER PRIMARY KEY,parcel_id,driver_id,operational_hub_id,outcome,created_at);
        INSERT INTO users VALUES(1,'Driver A','livreur',10,1),(2,'Driver B','livreur',10,1),(3,'Foreign','livreur',20,1),(4,'Inactive','livreur',10,0);
        INSERT INTO parcels VALUES(1,'A'),(2,'B'),(3,'C'),(4,'D');''')
        self.start,self.end=period({'from':'2026-01-01','to':'2026-01-02'})
    def tearDown(self):self.c.close()
    def assignment(self,pid,did=1,hid=10,at='2026-01-01T10:00:00+01:00'):
        self.c.execute('INSERT INTO ops_assignments(parcel_id,new_driver_id,hub_id,created_at) VALUES(?,?,?,?)',(pid,did,hid,at))
    def attempt(self,pid,status='Reporté',did=1,hid=10,at='2026-01-01T11:00:00+01:00'):
        self.c.execute('INSERT INTO ops_attempts(parcel_id,driver_id,operational_hub_id,outcome,created_at) VALUES(?,?,?,?,?)',(pid,did,hid,status,at))
    def data(self):return analytics(self.c,10,self.start,self.end)
    def test_own_hub_only_no_unknown_inference_and_all_roster_zero_days(self):
        self.assignment(1);self.assignment(2,hid=20);self.assignment(3,hid=None);self.assignment(4,did=3,hid=20)
        d=self.data();self.assertEqual(d['summary']['assigned'],1)
        self.assertEqual({r['id'] for r in d['rows']},{1,2,4})
        self.assertEqual(d['summary']['never_worked'],1)
        self.assertEqual(d['summary']['inactive_driver_days'],3)
        with self.assertRaises(LookupError):analytics(self.c,10,self.start,self.end,3)
    def test_any_attempt_processed_but_reported_is_not_delivery(self):
        for pid in (1,2,3,4):self.assignment(pid)
        self.attempt(1,'Reporté');self.attempt(2,'Injoignable');self.attempt(3,'Livré');self.attempt(4,'Retourné')
        r=self.data()['rows'][0]
        self.assertEqual((r['assigned'],r['processed'],r['pending'],r['delivered'],r['returned']),(4,4,0,1,1))
        self.assertEqual((r['progress'],r['delivery_rate']),(100,25))
    def test_duplicate_assignments_daily_distinct_and_latest_cycle(self):
        self.assignment(1);self.assignment(1,at='2026-01-01T12:00:00+01:00');self.attempt(1,at='2026-01-01T11:00:00+01:00')
        r=self.data()['rows'][0];self.assertEqual((r['assigned'],r['processed'],r['daily']['2026-01-01']),(1,0,1))
    def test_next_foreign_assignment_stops_local_attempt_attribution(self):
        self.assignment(1);self.assignment(1,did=3,hid=20,at='2026-01-01T12:00:00+01:00')
        self.attempt(1,at='2026-01-01T13:00:00+01:00')
        self.assertEqual(self.data()['summary']['processed'],0)
    def test_attempt_outside_cutoff_or_foreign_hub_does_not_process(self):
        self.assignment(1);self.assignment(2);self.assignment(3)
        self.attempt(1,hid=20);self.attempt(2,at='2026-01-03T01:00:00+01:00');self.attempt(3,at='2025-12-31T23:00:00+01:00')
        self.assertEqual(self.data()['summary']['pending'],3)
    def test_latest_outcome_counted_once_no_attempt_inflation(self):
        self.assignment(1);self.attempt(1,'Reporté');self.attempt(1,'Livré',at='2026-01-01T12:00:00+01:00')
        r=self.data()['rows'][0];self.assertEqual((r['assigned'],r['processed'],r['delivered']),(1,1,1))
    def test_period_limit_order_and_last_minute_inclusive(self):
        for args in [{'from':'bad'},{'from':'2026-01-02','to':'2026-01-01'},{'from':'2026-01-01','to':'2026-02-01'}]:
            with self.assertRaises(ValueError):period(args)
        a,b=period({'from':'2026-01-01T00:00','to':'2026-01-01T23:59'})
        self.assertEqual(b.second,59)
    def test_daily_uses_morocco_day_and_zero_assignment_denominators(self):
        self.assignment(1,at='2026-01-01T23:30:00+00:00')
        r=self.data()['rows'][0];self.assertEqual(r['daily']['2026-01-02'],1)
        self.c.execute('DELETE FROM ops_assignments');d=self.data()
        self.assertEqual((d['summary']['progress'],d['summary']['delivery_rate']),(0,0))
        self.assertEqual(d['summary']['never_worked'],2)
    def test_cohort_attempt_boundary_equal_end_and_reassignment_later(self):
        self.assignment(1);self.assignment(1,did=3,hid=20,at='2026-01-04T00:00:00+01:00')
        self.attempt(1,at=self.end.isoformat())
        self.assertEqual(self.data()['summary']['processed'],1)
