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
        CREATE TABLE events(id INTEGER PRIMARY KEY,parcel_id,actor_id,status,note,created_at);
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
    def status_event(self,pid,status,actor=1,at='2026-01-01T11:00:00+01:00',note='Statut mis à jour'):
        self.c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',(pid,actor,status,note,at))

    def test_four_parcels_three_status_only_paths_are_all_processed(self):
        for pid in (1,2,3,4):
            self.assignment(pid)
            self.status_event(pid,'En livraison',at='2026-01-01T10:00:00+01:00')
        self.attempt(1,'Livré')
        for pid,status in [(2,'Annulé'),(3,'Intéressé'),(4,'Programmé')]:
            self.status_event(pid,status)
            self.status_event(pid,status,actor=2,at='2026-01-01T18:00:00+01:00',note='Récupéré physiquement à l’agence')
        r=self.data()['rows'][0]
        self.assertEqual((r['assigned'],r['processed'],r['pending'],r['progress'],r['delivered']),(4,4,0,100,1))

    def test_physical_recovery_without_driver_processing_is_not_a_treatment(self):
        self.assignment(1)
        self.status_event(1,'En livraison',at='2026-01-01T10:00:00+01:00')
        self.status_event(1,'Reporté',actor=2,note='Récupéré physiquement à l’agence')
        self.assertEqual(self.data()['summary']['processed'],0)

    def test_legacy_null_attempt_hub_is_proven_by_assignment_not_city(self):
        self.assignment(1);self.attempt(1,'Reporté',hid=None)
        self.assertEqual(self.data()['summary']['processed'],1)
        self.c.execute('UPDATE ops_assignments SET hub_id=NULL')
        self.assertEqual(self.data()['summary']['assigned'],0)

    def test_foreign_attempt_mirror_event_cannot_override_explicit_hub(self):
        self.assignment(1);self.status_event(1,'En livraison',at='2026-01-01T10:00:00+01:00')
        self.attempt(1,'Livré',hid=20);self.status_event(1,'Livré',note='Tentative : livraison déclarée')
        self.assertEqual(self.data()['summary']['processed'],0)

    def test_same_state_note_or_client_interest_is_not_courier_processing(self):
        self.assignment(1);self.assignment(2)
        self.status_event(1,'Reporté',actor=2,at='2026-01-01T09:00:00+01:00')
        self.status_event(1,'Reporté',note='Preuve ajoutée')
        self.status_event(2,'Intéressé',actor=2,note='Le client a marqué la commande')
        self.assertEqual(self.data()['summary']['processed'],0)

    def test_history_treatment_is_bound_to_same_assignment_cycle_and_cutoff(self):
        self.assignment(1);self.assignment(1,did=3,hid=20,at='2026-01-01T12:00:00+01:00')
        self.status_event(1,'Annulé',at='2026-01-01T13:00:00+01:00')
        self.assignment(2);self.status_event(2,'Intéressé',at='2026-01-03T09:00:00+01:00')
        self.assertEqual(self.data()['summary']['processed'],0)

    def test_structured_and_event_mirror_are_not_counted_twice(self):
        self.assignment(1);self.attempt(1,'Livré');self.status_event(1,'Livré',note='Tentative : livraison déclarée')
        r=self.data()['rows'][0]
        self.assertEqual((r['processed'],r['delivered']),(1,1))
        self.assertEqual(self.data()['parcels'][0]['evidence_source'],'attempt')

    def custody_tables(self):
        self.c.executescript("""CREATE TABLE driver_receipts(parcel_id PRIMARY KEY,driver_id,received_at,hub_id);
        CREATE TABLE driver_workspace_audit(id INTEGER PRIMARY KEY,parcel_id,driver_id,action,created_at);""")

    def recovery(self,pid,at='2026-01-01T18:00:00+01:00',did=1):
        self.c.execute('INSERT INTO driver_workspace_audit(parcel_id,driver_id,action,created_at) VALUES(?,?,?,?)',(pid,did,'receive',at))
        self.c.execute('INSERT OR REPLACE INTO driver_receipts VALUES(?,?,?,?)',(pid,did,at,10))

    def test_four_scans_two_recoveries_leave_only_two_deliveries_in_both_views(self):
        self.custody_tables()
        for pid in (1,2,3,4):self.assignment(pid)
        self.attempt(1,'Livré');self.attempt(2,'Livré')
        self.attempt(3,'Reporté');self.attempt(4,'Refusé')
        self.recovery(3);self.recovery(4)
        d=self.data();r=d['rows'][0]
        self.assertEqual((r['assigned'],r['processed'],r['delivered'],r['pending'],r['progress'],r['delivery_rate']),(2,2,2,0,100,100))
        self.assertEqual(r['daily']['2026-01-01'],2)
        self.assertEqual(d['summary']['assigned'],2)
        self.assertEqual({p['parcel_id'] for p in d['parcels']},{1,2})
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ops_assignments').fetchone()[0],4)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ops_attempts').fetchone()[0],4)

    def test_delivery_is_retained_even_if_old_receipt_exists(self):
        self.custody_tables();self.assignment(1);self.attempt(1,'Livré');self.recovery(1)
        self.assertEqual(self.data()['summary']['assigned'],1)
        self.assertEqual(self.data()['rows'][0]['daily']['2026-01-01'],1)

    def test_recovery_after_selected_period_does_not_rewrite_earlier_snapshot(self):
        self.custody_tables();self.assignment(1);self.recovery(1,at='2026-01-03T12:00:00+01:00')
        self.assertEqual(self.data()['summary']['assigned'],1)

    def test_reassignment_after_recovery_starts_a_new_visible_cycle(self):
        self.custody_tables();self.assignment(1);self.recovery(1)
        self.assignment(1,at='2026-01-02T09:00:00+01:00')
        self.c.execute("INSERT INTO driver_workspace_audit(parcel_id,driver_id,action,created_at) VALUES(1,1,'assign','2026-01-02T09:00:00+01:00')")
        d=self.data();self.assertEqual(d['summary']['assigned'],1)
        self.assertEqual(d['rows'][0]['daily'],{'2026-01-01':0,'2026-01-02':1})

    def test_recovery_without_attempt_removes_pending_not_marks_it_processed(self):
        self.custody_tables();self.assignment(1);self.recovery(1)
        z=self.data()['summary']
        self.assertEqual((z['assigned'],z['pending'],z['processed'],z['progress']),(0,0,0,0))

    def test_other_driver_receipt_does_not_remove_local_assignment(self):
        self.custody_tables();self.assignment(1);self.recovery(1,did=3)
        self.assertEqual(self.data()['summary']['assigned'],1)

    def test_same_second_rescan_after_recovery_is_not_removed_by_stale_receipt(self):
        self.custody_tables();self.assignment(1);self.recovery(1,at='2026-01-01T10:00:00+01:00')
        self.c.execute("INSERT INTO driver_workspace_audit(parcel_id,driver_id,action,created_at) VALUES(1,1,'assign','2026-01-01T10:00:00+01:00')")
        self.assertEqual(self.data()['summary']['assigned'],1)

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
