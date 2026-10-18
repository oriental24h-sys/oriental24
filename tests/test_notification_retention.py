import sqlite3
import unittest
from notification_retention import purge_read_notifications


class NotificationRetentionTests(unittest.TestCase):
    def test_retention_is_based_on_first_read_not_creation(self):
        with sqlite3.connect(':memory:') as c:
            c.execute('CREATE TABLE ops_notifications(id INTEGER PRIMARY KEY, user_id INTEGER, created_at TEXT, read_at TEXT)')
            rows = [
                (1, 1, '2020-01-01T00:00:00', None),
                (2, 1, '2020-01-01T00:00:00', '2026-10-18T09:59:59'),
                (3, 1, '2020-01-01T00:00:00', '2026-10-18T10:00:00'),
                (4, 1, '2020-01-01T00:00:00', '2026-10-18T11:59:00'),
                (5, 2, '2020-01-01T00:00:00', '2026-10-17T12:00:00'),
                (6, 2, '2020-01-01T00:00:00', None),
            ]
            c.executemany('INSERT INTO ops_notifications VALUES(?,?,?,?)', rows)
            self.assertEqual(purge_read_notifications(c, '2026-10-18T12:00:00'), 2)
            self.assertEqual([r[0] for r in c.execute('SELECT id FROM ops_notifications ORDER BY id')], [1, 3, 4, 6])
            self.assertEqual(purge_read_notifications(c, '2026-10-18T12:00:00'), 0)
            self.assertEqual(purge_read_notifications(c, '2026-10-18T12:00:01'), 1)
