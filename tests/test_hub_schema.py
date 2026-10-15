import sqlite3
import unittest

from hub_schema import (
    migrate_city_hub_id,
    assign_cities_to_hub,
    install_one_active_hub_manager_guards,
    ensure_hub_manager_can_leave,
    migrate_driver_hub_id,
)


class CityHubMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT NOT NULL,delivery INTEGER NOT NULL DEFAULT 1,pickup INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL);
            CREATE TABLE hub_cities(
                hub_id INTEGER NOT NULL, city_id INTEGER NOT NULL,
                active INTEGER NOT NULL, is_primary INTEGER NOT NULL,
                created_by INTEGER,created_at TEXT,
                PRIMARY KEY(hub_id,city_id)
            );
            INSERT INTO cities(id,name) VALUES
                (1,'Explicit primary'),(2,'Secondary only'),(3,'Inactive primary'),
                (4,'Ambiguous legacy'),(5,'Keep direct assignment');
            INSERT INTO ops_hubs(id,name,active) VALUES
                (10,'Older active Hub',1),(20,'Explicit active Hub',1),(30,'Inactive Hub',0);
            INSERT INTO hub_cities(hub_id,city_id,active,is_primary) VALUES
                (10,1,1,0),(20,1,1,1),
                (10,2,1,0),
                (30,3,1,1),
                (10,4,1,1),(20,4,1,1);
        ''')
        # Simulate an explicitly assigned city that must never be overwritten.
        self.db.execute('ALTER TABLE cities ADD COLUMN hub_id INTEGER REFERENCES ops_hubs(id)')
        self.db.execute('UPDATE cities SET hub_id=10 WHERE id=5')

    def tearDown(self):
        self.db.close()

    def test_migration_adds_the_direct_column_to_a_legacy_city_table(self):
        legacy = sqlite3.connect(':memory:')
        legacy.executescript('''
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT NOT NULL);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,active INTEGER NOT NULL);
            INSERT INTO cities(id,name) VALUES(1,'City');
            INSERT INTO ops_hubs(id,name,active) VALUES(1,'Hub',1);
        ''')
        self.assertEqual(migrate_city_hub_id(legacy), 0)
        self.assertIn('hub_id', {row[1] for row in legacy.execute('PRAGMA table_info(cities)')})
        legacy.close()

    def test_only_unique_active_primary_is_backfilled(self):
        changed = migrate_city_hub_id(self.db)
        self.assertEqual(changed, 1)
        values = dict(self.db.execute('SELECT id,hub_id FROM cities'))
        self.assertEqual(values[1], 20)  # explicit primary, not the older secondary Hub
        self.assertIsNone(values[2])     # secondary coverage is not city ownership
        self.assertIsNone(values[3])     # inactive Hub is not promoted
        self.assertIsNone(values[4])     # corrupt/ambiguous legacy row is left for review
        self.assertEqual(values[5], 10)  # an existing direct assignment is preserved

    def test_migration_is_idempotent_and_does_not_overwrite_direct_assignments(self):
        migrate_city_hub_id(self.db)
        self.db.execute('UPDATE cities SET hub_id=10 WHERE id=2')
        self.db.execute('UPDATE hub_cities SET is_primary=0 WHERE city_id=1 AND hub_id=20')
        self.db.execute('UPDATE hub_cities SET is_primary=1 WHERE city_id=1 AND hub_id=10')
        self.assertEqual(migrate_city_hub_id(self.db), 0)
        self.assertEqual(self.db.execute('SELECT hub_id FROM cities WHERE id=1').fetchone()[0], 20)
        self.assertEqual(self.db.execute('SELECT hub_id FROM cities WHERE id=2').fetchone()[0], 10)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\'index\' AND name=\'idx_cities_hub_id\'').fetchone()[0], 1)


    def test_city_assignment_transfers_one_owner_and_preserves_service_flags(self):
        migrate_city_hub_id(self.db)
        self.db.execute('UPDATE cities SET delivery=0,pickup=1 WHERE id=1')
        assign_cities_to_hub(self.db, 10, [1, 2], actor_id=99, created_at='2026-10-13T13:00:00')
        self.assertEqual(self.db.execute('SELECT hub_id,delivery,pickup FROM cities WHERE id=1').fetchone(), (10, 0, 1))
        self.assertEqual(self.db.execute('SELECT hub_id FROM cities WHERE id=2').fetchone()[0], 10)
        rows = self.db.execute('SELECT hub_id,active,is_primary FROM hub_cities WHERE city_id=1').fetchall()
        self.assertEqual(rows, [(10, 1, 1)])
        # Removing a city unassigns it without opening the city or changing its service flags.
        assign_cities_to_hub(self.db, 10, [2], actor_id=99, created_at='2026-10-13T13:01:00')
        self.assertEqual(self.db.execute('SELECT hub_id,delivery,pickup FROM cities WHERE id=1').fetchone(), (None, 0, 1))
        self.assertEqual(self.db.execute('SELECT active,is_primary FROM hub_cities WHERE hub_id=10 AND city_id=1').fetchone(), (0, 0))


class DriverHubMigrationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT,role TEXT,active INTEGER NOT NULL DEFAULT 1,driver_hub_id INTEGER REFERENCES ops_hubs(id));
            CREATE TABLE cities(id INTEGER PRIMARY KEY,hub_id INTEGER REFERENCES ops_hubs(id));
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,active INTEGER NOT NULL);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,driver_id INTEGER,city_id INTEGER,current_hub_id INTEGER,status TEXT);
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE audit_log(id INTEGER PRIMARY KEY,actor_id INTEGER,actor_name TEXT,action TEXT,
                entity_type TEXT,entity_id TEXT,old_value TEXT,new_value TEXT,metadata TEXT,created_at TEXT);
            INSERT INTO ops_hubs(id,active) VALUES(10,1),(20,1),(30,0);
            INSERT INTO cities(id,hub_id) VALUES(1,10),(2,20),(3,NULL),(4,30);
            INSERT INTO users(id,name,role) VALUES
                (1,'One Hub','livreur'),(2,'Conflicting','livreur'),(3,'No open work','livreur'),
                (4,'Physical Hub Wins','livreur'),(5,'No city route','livreur'),(6,'Already mapped','livreur'),
                (7,'Missing City Evidence','livreur');
            UPDATE users SET driver_hub_id=10 WHERE id=6;
            INSERT INTO parcels(id,driver_id,city_id,current_hub_id,status) VALUES
                (101,1,1,NULL,'En livraison'),(102,1,1,NULL,'Programmé'),
                (201,2,1,NULL,'En livraison'),(202,2,2,NULL,'En livraison'),
                (301,3,1,NULL,'Livré'),
                (401,4,1,20,'En livraison'),
                (501,5,3,NULL,'En livraison'),(601,1,4,NULL,'Livré'),
                (701,7,1,NULL,'En livraison'),(702,7,999,NULL,'En livraison');
        ''')
        self.audit=[]
    def tearDown(self):self.db.close()
    def append_audit(self,connection,**entry):self.audit.append(entry)
    def test_infers_only_one_unambiguous_active_assigned_hub_and_audits_it(self):
        result=migrate_driver_hub_id(self.db,created_at='2026-10-14T12:00:00',append_audit=self.append_audit)
        self.assertEqual(result,{'inferred':2,'unmapped':4,'already_migrated':False})
        hubs=dict(self.db.execute("SELECT id,driver_hub_id FROM users WHERE role='livreur'"))
        self.assertEqual(hubs,{1:10,2:None,3:None,4:20,5:None,6:10,7:None})
        self.assertEqual(len(self.audit),2)
        self.assertEqual({row['new_value']['driver_hub_id'] for row in self.audit},{10,20})
        replay=migrate_driver_hub_id(self.db,created_at='2026-10-15T12:00:00',append_audit=self.append_audit)
        self.assertTrue(replay['already_migrated'])
        self.assertEqual(len(self.audit),2)
    def test_non_driver_cannot_be_given_driver_hub(self):
        migrate_driver_hub_id(self.db,created_at='2026-10-14T12:00:00',append_audit=self.append_audit)
        with self.assertRaisesRegex(sqlite3.IntegrityError,'Only couriers'):
            self.db.execute("INSERT INTO users(id,name,role,driver_hub_id) VALUES(8,'Admin insert','admin',10)")
        self.db.execute("INSERT INTO users(id,name,role) VALUES(9,'Admin','admin')")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'Only couriers'):
            self.db.execute('UPDATE users SET driver_hub_id=10 WHERE id=9')


class OneActiveManagerGuardTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,active INTEGER NOT NULL);
            INSERT INTO ops_hubs(id,active) VALUES(7,1),(8,1),(9,0);
            CREATE TABLE users(
                id INTEGER PRIMARY KEY, role TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                agent_hub_id INTEGER
            );
        ''')

    def tearDown(self):
        self.db.close()

    def test_only_one_active_manager_per_hub_and_inactive_replacement_is_allowed(self):
        install_one_active_hub_manager_guards(self.db)
        self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(1,'hub_manager',1,7)")
        self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(2,'hub_manager',1,8)")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'already has an active manager'):
            self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(3,'hub_manager',1,7)")
        self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(3,'hub_manager',0,7)")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'already has an active manager'):
            self.db.execute('UPDATE users SET active=1 WHERE id=3')
        self.db.execute('UPDATE users SET active=0 WHERE id=1')
        self.db.execute('UPDATE users SET active=1 WHERE id=3')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'already has an active manager'):
            self.db.execute('UPDATE users SET agent_hub_id=8 WHERE id=3')
        # Legacy role alias is guarded too.
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'already has an active manager'):
            self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(4,'agent',1,8)")

    def test_active_hub_manager_cannot_be_removed_without_a_replacement(self):
        self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(1,'hub_manager',1,7)")
        with self.assertRaisesRegex(ValueError, 'doit conserver un responsable actif'):
            ensure_hub_manager_can_leave(self.db, 1, 7)
        self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(2,'hub_manager',1,7)")
        self.assertTrue(ensure_hub_manager_can_leave(self.db, 1, 7))
        self.assertTrue(ensure_hub_manager_can_leave(self.db, 1, 9))

    def test_guard_install_is_safe_with_existing_duplicates_and_is_idempotent(self):
        self.db.executemany(
            'INSERT INTO users(id,role,active,agent_hub_id) VALUES(?,?,?,?)',
            [(1, 'hub_manager', 1, 4), (2, 'hub_manager', 1, 4)],
        )
        install_one_active_hub_manager_guards(self.db)
        install_one_active_hub_manager_guards(self.db)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM users WHERE agent_hub_id=4 AND active=1').fetchone()[0], 2)
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'already has an active manager'):
            self.db.execute("INSERT INTO users(id,role,active,agent_hub_id) VALUES(3,'hub_manager',1,4)")


if __name__ == '__main__':
    unittest.main()
