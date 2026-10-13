import sqlite3
import unittest

from audit_guard import (
    install_departure_reconciliation_guard,
    install_driver_workspace_audit_guards,
    install_ops_audit_guards,
)


class AppendOnlyAuditTests(unittest.TestCase):
    AUDITS = (
        ('ops_audit', install_ops_audit_guards),
        ('driver_workspace_audit', install_driver_workspace_audit_guards),
    )

    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        for table, install in self.AUDITS:
            self.db.execute(f'CREATE TABLE {table}(id INTEGER PRIMARY KEY, action TEXT NOT NULL)')
            install(self.db)
        self.db.execute('''CREATE TABLE ops_document_lines(
            id INTEGER PRIMARY KEY,active INTEGER NOT NULL DEFAULT 1,
            departure_reconciled_at TEXT,departure_reconciled_by INTEGER,
            departure_reconciliation_reason TEXT)''')
        install_departure_reconciliation_guard(self.db)

    def tearDown(self):
        self.db.close()

    def test_inserts_remain_allowed(self):
        for table, _ in self.AUDITS:
            with self.subTest(table=table):
                self.db.execute(f"INSERT INTO {table}(action) VALUES('event')")
                self.assertEqual(self.db.execute(f'SELECT action FROM {table}').fetchone()[0], 'event')

    def test_updates_and_deletes_are_rejected_without_changing_rows(self):
        for table, _ in self.AUDITS:
            with self.subTest(table=table):
                self.db.execute(f"INSERT INTO {table}(action) VALUES('original')")
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                    self.db.execute(f"UPDATE {table} SET action='rewritten' WHERE id=1")
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                    self.db.execute(f'DELETE FROM {table} WHERE id=1')
                self.assertEqual(self.db.execute(f'SELECT action FROM {table} WHERE id=1').fetchone()[0], 'original')

    def test_reconciliation_marker_can_be_set_once_but_not_rewritten(self):
        self.db.execute('INSERT INTO ops_document_lines(id) VALUES(1)')
        self.db.execute('''UPDATE ops_document_lines SET active=0,departure_reconciled_at=?,
            departure_reconciled_by=?,departure_reconciliation_reason=? WHERE id=1''',
            ('2026-10-13T12:00:00',7,'Colis resté au Hub'))
        self.db.execute('UPDATE ops_document_lines SET active=0 WHERE id=1')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
            self.db.execute("UPDATE ops_document_lines SET departure_reconciliation_reason='rewritten' WHERE id=1")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'immutable'):
            self.db.execute('UPDATE ops_document_lines SET departure_reconciled_at=NULL WHERE id=1')
        row=self.db.execute('SELECT active,departure_reconciliation_reason FROM ops_document_lines WHERE id=1').fetchone()
        self.assertEqual(row,(0,'Colis resté au Hub'))

    def test_guard_installation_is_idempotent(self):
        for table, install in self.AUDITS:
            with self.subTest(table=table):
                install(self.db)
                self.db.execute(f"INSERT INTO {table}(action) VALUES('event')")
                with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
                    self.db.execute(f'DELETE FROM {table} WHERE id=1')
        install_departure_reconciliation_guard(self.db)


if __name__ == '__main__':
    unittest.main()
