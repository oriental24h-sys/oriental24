import json
import sqlite3
import unittest

from audit_guard import install_audit_log_guards
from audit_log import append_audit_log


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('''CREATE TABLE audit_log(
            id INTEGER PRIMARY KEY, actor_id INTEGER, actor_name TEXT NOT NULL,
            action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
            old_value TEXT NOT NULL, new_value TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
        )''')
        install_audit_log_guards(self.db)

    def tearDown(self):
        self.db.close()

    def test_append_records_actor_old_new_and_redacts_secrets(self):
        audit_id = append_audit_log(
            self.db,
            actor_id=12,
            actor_name='Amina Admin',
            action='hub_manager_created',
            entity_type='hub_manager',
            entity_id=51,
            old_value=None,
            new_value={'name': 'Samir', 'email': 'samir@example.test', 'password': 'never-store-this'},
            metadata={'request_token': 'also-secret'},
            created_at='2026-10-13T12:30:00',
        )
        row = self.db.execute('''SELECT actor_id,actor_name,action,entity_type,entity_id,
                                old_value,new_value,metadata,created_at
                                FROM audit_log WHERE id=?''', (audit_id,)).fetchone()
        self.assertEqual(row[:5], (12, 'Amina Admin', 'hub_manager_created', 'hub_manager', '51'))
        self.assertEqual(json.loads(row[5]), None)
        self.assertEqual(json.loads(row[6])['password'], '[REDACTED]')
        self.assertEqual(json.loads(row[7])['request_token'], '[REDACTED]')
        self.assertEqual(row[8], '2026-10-13T12:30:00')

    def test_audit_rows_cannot_be_updated_or_deleted(self):
        audit_id = append_audit_log(
            self.db, actor_id=None, actor_name='SYSTEM', action='migration',
            entity_type='schema', entity_id='single-hub-city', old_value={},
            new_value={'version': 1}, created_at='2026-10-13T12:30:00',
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
            self.db.execute("UPDATE audit_log SET action='rewritten' WHERE id=?", (audit_id,))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
            self.db.execute('DELETE FROM audit_log WHERE id=?', (audit_id,))

    def test_required_attribution_fields_are_checked(self):
        with self.assertRaises(ValueError):
            append_audit_log(
                self.db, actor_id=1, actor_name='', action='change',
                entity_type='parcel', entity_id='9', old_value={}, new_value={},
                created_at='2026-10-13T12:30:00',
            )


if __name__ == '__main__':
    unittest.main()
