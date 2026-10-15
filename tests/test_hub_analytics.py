import sqlite3
import unittest

from hub_analytics import (
    hub_daily_metrics,
    hub_operational_metrics,
    install_hub_analytics_schema,
)


class HubAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL);
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,current_hub_id INTEGER,created_at TEXT);
            CREATE TABLE ops_documents(id INTEGER PRIMARY KEY,destination_hub_id INTEGER);
            CREATE TABLE ops_document_lines(id INTEGER PRIMARY KEY,document_id INTEGER,parcel_id INTEGER,
                received_at TEXT,received_by INTEGER);
            CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER,old_driver_id INTEGER,
                new_driver_id INTEGER,actor_id INTEGER,created_at TEXT);
            CREATE TABLE ops_attempts(id INTEGER PRIMARY KEY,parcel_id INTEGER,outcome TEXT,created_at TEXT);
            INSERT INTO ops_hubs(id,name) VALUES(1,'Hub A'),(2,'Hub B');
        ''')
        install_hub_analytics_schema(self.db, '2026-10-14T00:00:00')

    def tearDown(self):
        self.db.close()

    def test_document_receipt_snapshots_physical_hub_and_is_append_only(self):
        self.db.execute("INSERT INTO parcels(id,current_hub_id,created_at) VALUES(10,NULL,'2026-10-13T12:00:00')")
        self.db.execute("INSERT INTO users(id,name) VALUES(7,'Manager')")
        self.db.execute('INSERT INTO ops_documents(id,destination_hub_id) VALUES(4,1)')
        self.db.execute("INSERT INTO ops_document_lines(id,document_id,parcel_id) VALUES(21,4,10)")
        self.db.execute("UPDATE ops_document_lines SET received_at='2026-10-14T08:15:00',received_by=7 WHERE id=21")
        row = self.db.execute('SELECT * FROM ops_hub_arrivals').fetchone()
        self.assertEqual((row['parcel_id'], row['hub_id'], row['arrived_at'], row['source_type']),
                         (10, 1, '2026-10-14T08:15:00', 'document_line'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE ops_hub_arrivals SET hub_id=2 WHERE id=?", (row['id'],))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM ops_hub_arrivals WHERE id=?', (row['id'],))

    def test_schema_install_is_idempotent_and_does_not_duplicate_live_arrivals(self):
        self.db.execute("INSERT INTO parcels(id,created_at) VALUES(30,'2026-10-10T07:00:00'),(31,'2026-10-14T08:00:00')")
        self.db.execute('INSERT INTO ops_documents(id,destination_hub_id) VALUES(5,1),(6,1)')
        self.db.execute("INSERT INTO ops_document_lines(id,document_id,parcel_id,received_at) VALUES(51,5,30,'2026-10-10T08:00:00')")
        self.db.execute("INSERT INTO ops_document_lines(id,document_id,parcel_id) VALUES(61,6,31)")
        self.db.execute("UPDATE ops_document_lines SET received_at='2026-10-14T09:00:00' WHERE id=61")
        install_hub_analytics_schema(self.db, '2026-10-15T00:00:00')
        rows = self.db.execute('SELECT source_type,count(*) count FROM ops_hub_arrivals GROUP BY source_type ORDER BY source_type').fetchall()
        self.assertEqual({row['source_type']:row['count'] for row in rows},
                         {'document_line':1,'document_line_legacy':1})

    def test_attempt_and_return_metrics_use_hub_snapshots_and_first_recorded_attempt(self):
        rows = [
            (1, 101, 'Livré', '2026-10-14T09:00:00', 1),
            (2, 101, 'Retourné', '2026-10-14T11:00:00', 1),
            (3, 102, 'Refusé', '2026-10-14T09:30:00', 1),
            (4, 103, 'Livré', '2026-10-14T10:00:00', 2),
            (5, 103, 'Livré', '2026-10-14T12:00:00', 1),
        ]
        self.db.executemany('''INSERT INTO ops_attempts(id,parcel_id,outcome,created_at,operational_hub_id)
            VALUES(?,?,?,?,?)''', rows)
        metrics = hub_operational_metrics(self.db, 1, '2026-10-14', '2026-10-14')
        self.assertEqual(metrics['first_attempts'], 2)
        self.assertEqual(metrics['first_attempt_delivered'], 1)
        self.assertEqual(metrics['first_attempt_rate_pct'], 50.0)
        self.assertEqual(metrics['attempts'], 4)
        self.assertEqual(metrics['returned_parcels'], 1)
        self.assertEqual(metrics['return_attempts'], 1)
        self.assertEqual(metrics['return_rate_pct'], 33.3)
        self.assertNotIn('score', metrics)
        self.assertNotIn('rank', metrics)

    def test_processing_speed_is_physical_arrival_to_first_local_assignment(self):
        self.db.execute("INSERT INTO parcels(id,created_at) VALUES(101,'2026-10-14T07:00:00'),(102,'2026-10-14T09:00:00')")
        self.db.executemany('''INSERT INTO ops_hub_arrivals(parcel_id,hub_id,arrived_at,source_type,source_id,created_at)
            VALUES(?,1,?,'test',?,?)''', [
                (101, '2026-10-14T08:00:00', 'a101', '2026-10-14T08:00:00'),
                (102, '2026-10-14T10:00:00', 'a102', '2026-10-14T10:00:00'),
            ])
        self.db.executemany('''INSERT INTO ops_assignments(id,parcel_id,new_driver_id,created_at,hub_id)
            VALUES(?,?,?,?,?)''', [
                (1, 101, 8, '2026-10-14T09:30:00', 1),
                (2, 102, 9, '2026-10-14T10:15:00', 1),
                (3, 102, 9, '2026-10-14T10:05:00', 2),
            ])
        metrics = hub_operational_metrics(self.db, 1, '2026-10-14', '2026-10-14')
        self.assertEqual(metrics['processing_sample_size'], 2)
        self.assertEqual(metrics['processing_average_minutes'], 52.5)
        self.assertEqual(metrics['processing_median_minutes'], 52.5)
        daily = hub_daily_metrics(self.db, 1, '2026-10-14', '2026-10-14')
        self.assertEqual(daily[0]['assignments'], 2)
        self.assertEqual(daily[0]['arrivals'], 2)


if __name__ == '__main__':
    unittest.main()
