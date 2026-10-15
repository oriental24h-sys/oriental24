import sqlite3
import unittest

from hub_access import (
    hub_manager_route_allowed,
    hub_manager_requires_active_hub,
    parcel_by_tracking_at_hub,
    parcel_by_manifest_at_hub,
    hub_received_lines,
    hub_parcel_scope,
    resolve_routing_hub,
    central_hub_transfer_allowed,
    parcel_physically_at_hub,
    driver_dispatch_allowed,
    driver_team_member_ids,
    hub_document_lines_at_hub,
    hub_manager_transfer_scope,
    ops_manifest_counts,
    manifest_status_from_counts,
)


class HubManagerRoutePolicyTests(unittest.TestCase):
    def test_reviewed_hub_scoped_routes_are_allowed(self):
        cases = [
            ('GET', '/api/bootstrap'),
            ('GET', '/api/parcels/1'),
            ('POST', '/api/logistics/parcels/1/tickets'),
            ('GET', '/api/logistics/config'),
            ('GET', '/api/logistics/documents'),
            ('GET', '/api/logistics/documents/18'),
            ('GET', '/api/logistics/hub-dashboard'),
            ('GET', '/api/logistics/hub/drivers'),
            ('POST', '/api/logistics/hub/drivers'),
            ('PATCH', '/api/logistics/hub/drivers/17'),
            ('POST', '/api/logistics/hub/assignments'),
            ('GET', '/api/logistics/hub/invoices'),
            ('GET', '/api/logistics/hub/driver-statements'),
            ('GET', '/api/logistics/cod/hub'),
            ('POST', '/api/logistics/cod/hub/handoffs'),
            ('POST', '/api/logistics/documents/18/departure-scan'),
            ('POST', '/api/logistics/documents/18/receive'),
            ('GET', '/api/partner-palettes/18'),
            ('POST', '/api/partner-palettes/18/receive'),
            ('POST', '/api/partner-palettes/18/receive-all'),
            ('POST', '/api/return-palettes/18/receive'),
            ('POST', '/api/return-palettes/18/dispatch'),
            ('POST', '/api/return-palettes/18/cancel'),
            ('GET', '/api/return-palettes/scan-lookup'),
            ('POST', '/api/return-palettes/scan-send'),
            ('GET', '/api/return-palettes/24'),
            ('GET', '/api/partner-palettes/fusion/7'),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assertTrue(hub_manager_route_allowed(method, path))

    def test_unreviewed_or_wrong_method_routes_fail_closed(self):
        cases = [
            ('PATCH', '/api/parcels/1'),
            ('POST', '/api/return-palettes/18/receive-all'),
            ('POST', '/api/partner-palettes/18/mystery'),
            ('GET', '/api/parcels/1/media/3'),
            ('POST', '/api/logistics/parcels/1/attempts'),
            ('GET', '/api/audit'),
            ('POST', '/api/logistics/documents/24'),
            ('POST', '/api/logistics/hub-dashboard'),
            ('POST', '/api/logistics/cod/admin/receipts'),
            ('POST', '/api/logistics/cod/admin/receipts/1/settlements'),
            ('GET', '/api/logistics/cod/admin/handoffs/1/settlement-options'),
            ('POST', '/api/logistics/cod/admin/adjustments'),
            ('GET', '/api/logistics/cod/admin'),
            ('POST', '/api/logistics/hubs/10/manager'),
            ('POST', '/api/logistics/hubs/10/manager/replace'),
            ('PATCH', '/api/logistics/cod/hub'),
            ('POST', '/api/logistics/documents/24/reconcile-departure'),
            ('POST', '/api/logistics/documents/24/dispatch'),
            ('POST', '/api/logistics/documents/24/cancel'),
            ('PATCH', '/api/logistics/central-hub'),
            ('GET', '/api/palette-console'),
            ('GET', '/api/invoices'),
            ('GET', '/api/warehouses'),
            ('GET', '/api/ramassage/board'),
            ('GET', '/api/partner-palettes/candidates'),
            ('POST', '/api/partner-palettes/daily-draft'),
            ('PATCH', '/api/partner-palettes/18'),
            ('POST', '/api/return-palettes/scan-lookup'),
        ]
        for method, path in cases:
            with self.subTest(method=method, path=path):
                self.assertFalse(hub_manager_route_allowed(method, path))

    def test_get_head_is_read_only_alias_but_mutations_are_not(self):
        self.assertTrue(hub_manager_route_allowed('HEAD', '/api/partner-palettes/18'))
        self.assertFalse(hub_manager_route_allowed('PUT', '/api/partner-palettes/18'))

    def test_operational_routes_require_an_active_assigned_hub(self):
        for path in (
            '/api/parcels/123',
            '/api/logistics/parcels/123/tickets',
            '/api/logistics/config',
            '/api/logistics/documents',
            '/api/logistics/documents/123/receive',
            '/api/logistics/hub-dashboard',
            '/api/logistics/hub/drivers',
            '/api/logistics/hub/assignments',
            '/api/logistics/hub/invoices',
            '/api/logistics/cod/hub',
            '/api/logistics/cod/hub/handoffs',
            '/api/logistics/notifications',
            '/api/partner-palettes/18',
            '/api/partner-palette-incidents/3/photo',
            '/api/return-palettes/config',
            '/api/alerts',
        ):
            with self.subTest(path=path):
                self.assertTrue(hub_manager_requires_active_hub(path))
        for path in ('/api/bootstrap', '/api/profile', '/api/security/sessions'):
            with self.subTest(path=path):
                self.assertFalse(hub_manager_requires_active_hub(path))


class HubDocumentLineScopeTests(unittest.TestCase):
    def test_only_lines_physically_at_assigned_hub_are_exposed(self):
        lines=[
            {'tracking':'AT-SOURCE','current_hub_id':10},
            {'tracking':'IN-TRANSIT','current_hub_id':None},
            {'tracking':'AT-DESTINATION','current_hub_id':20},
            {'tracking':'MALFORMED','current_hub_id':True},
        ]
        self.assertEqual([x['tracking'] for x in hub_document_lines_at_hub(lines,10)],['AT-SOURCE'])
        self.assertEqual([x['tracking'] for x in hub_document_lines_at_hub(lines,20)],['AT-DESTINATION'])
        self.assertEqual(hub_document_lines_at_hub(lines,1),[])
        self.assertEqual(hub_document_lines_at_hub(lines,None),[])
        self.assertEqual(hub_document_lines_at_hub(lines,True),[])


class HubManagerTransferScanScopeTests(unittest.TestCase):
    def test_managers_can_scan_only_the_assigned_end_of_a_transfer(self):
        document={'kind':'transfer','source_hub_id':10,'destination_hub_id':20}
        self.assertTrue(hub_manager_transfer_scope(document,10,'departure'))
        self.assertTrue(hub_manager_transfer_scope(document,20,'arrival'))
        self.assertFalse(hub_manager_transfer_scope(document,20,'departure'))
        self.assertFalse(hub_manager_transfer_scope(document,10,'arrival'))
        self.assertFalse(hub_manager_transfer_scope({**document,'kind':'pickup'},10,'departure'))
        self.assertFalse(hub_manager_transfer_scope(document,True,'departure'))
        self.assertFalse(hub_manager_transfer_scope(document,10,'unknown'))


class ManifestReconciliationCountTests(unittest.TestCase):
    def test_reconciled_departure_lines_are_excluded_from_live_manifest_counts(self):
        lines=[
            {'departure_scanned_at':'2026-10-13T09:00:00','received_at':None,'departure_reconciled_at':None},
            {'departure_scanned_at':'2026-10-13T10:00:00','received_at':'2026-10-13T14:00:00','departure_reconciled_at':None},
            {'departure_scanned_at':None,'received_at':None,'departure_reconciled_at':'2026-10-13T11:00:00'},
        ]
        self.assertEqual(ops_manifest_counts(lines),{
            'count':2,'original_count':3,'departure_reconciled_count':1,
            'received':1,'departure_scanned':2,
        })


class ManifestReconciliationStatusTests(unittest.TestCase):
    def test_reconciliation_status_tracks_only_live_manifest_lines(self):
        self.assertEqual(manifest_status_from_counts(7,7,0),'En transit')
        self.assertEqual(manifest_status_from_counts(7,7,2),'Partiellement reçu')
        self.assertEqual(manifest_status_from_counts(7,7,7),'Reçu')
        self.assertEqual(manifest_status_from_counts(8,7,2),'Départ partiel')

    def test_inconsistent_manifest_counts_fail_closed(self):
        for values in ((0,0,0),(2,3,0),(2,0,3),(True,0,0),(-1,0,0)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                manifest_status_from_counts(*values)


class CentralHubTransferPolicyTests(unittest.TestCase):
    def test_central_hub_may_dispatch_to_or_receive_from_another_hub(self):
        self.assertTrue(central_hub_transfer_allowed(90, 10, 90, True))
        self.assertTrue(central_hub_transfer_allowed(10, 90, 90, True))

    def test_secondary_hubs_cannot_transfer_directly_to_each_other(self):
        self.assertFalse(central_hub_transfer_allowed(10, 20, 90, True))

    def test_transfer_requires_a_configured_active_central_and_distinct_hubs(self):
        self.assertFalse(central_hub_transfer_allowed(90, 10, None, True))
        self.assertFalse(central_hub_transfer_allowed(90, 10, 90, False))
        self.assertFalse(central_hub_transfer_allowed(90, 90, 90, True))
        self.assertFalse(central_hub_transfer_allowed(True, 10, 90, True))


class ParcelDepartureLocationTests(unittest.TestCase):
    def test_transfer_requires_parcel_to_be_recorded_at_source_hub(self):
        self.assertTrue(parcel_physically_at_hub(10, 10))
        self.assertFalse(parcel_physically_at_hub(None, 10))
        self.assertFalse(parcel_physically_at_hub(20, 10))
        self.assertFalse(parcel_physically_at_hub(True, 10))


class DriverDispatchHubTests(unittest.TestCase):
    def test_team_scope_excludes_unmapped_cross_hub_and_inactive_members(self):
        db=sqlite3.connect(':memory:')
        db.executescript('''
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,active INTEGER NOT NULL);
            CREATE TABLE users(id INTEGER PRIMARY KEY,role TEXT,active INTEGER,driver_hub_id INTEGER,team_lead_id INTEGER);
            INSERT INTO ops_hubs(id,active) VALUES(10,1),(20,1),(30,0);
            INSERT INTO users(id,role,active,driver_hub_id,team_lead_id) VALUES
                (1,'livreur',1,10,NULL),(2,'livreur',1,10,1),(3,'livreur',1,20,1),
                (4,'livreur',1,NULL,1),(5,'livreur',0,10,1),(6,'livreur',1,30,NULL);
        ''')
        self.assertEqual(driver_team_member_ids(db,1),[2])
        self.assertEqual(driver_team_member_ids(db,6),[])
        self.assertEqual(driver_team_member_ids(db,True),[])
        db.close()

    def test_dispatch_requires_parcel_at_the_same_active_hub(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,active INTEGER NOT NULL)')
        db.executemany('INSERT INTO ops_hubs(id,active) VALUES(?,?)',[(10,1),(20,0)])
        self.assertTrue(driver_dispatch_allowed(db,10,10))
        self.assertFalse(driver_dispatch_allowed(db,None,10))
        self.assertFalse(driver_dispatch_allowed(db,20,10))
        self.assertFalse(driver_dispatch_allowed(db,20,20))
        self.assertFalse(driver_dispatch_allowed(db,10,True))
        self.assertFalse(driver_dispatch_allowed(db,10,None))
        db.close()


class CentralHubRoutingFallbackTests(unittest.TestCase):
    def test_active_city_primary_takes_precedence(self):
        self.assertEqual(resolve_routing_hub(12, 90, True), (12, 'city_primary'))

    def test_admin_designated_central_hub_is_the_only_fallback(self):
        self.assertEqual(resolve_routing_hub(None, 90, True), (90, 'central'))

    def test_missing_or_inactive_central_hub_fails_closed(self):
        self.assertEqual(resolve_routing_hub(None, None, False), (None, None))
        self.assertEqual(resolve_routing_hub(None, 90, False), (None, None))

    def test_invalid_hub_ids_do_not_become_routes(self):
        self.assertEqual(resolve_routing_hub(0, 90, True), (90, 'central'))
        self.assertEqual(resolve_routing_hub(-1, 0, True), (None, None))
        self.assertEqual(resolve_routing_hub(True, 90, True), (90, 'central'))


class PhysicalHubParcelScopeTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE parcels(id INTEGER PRIMARY KEY, tracking TEXT, current_hub_id INTEGER);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1);
            INSERT INTO ops_hubs VALUES(10,1);
            INSERT INTO ops_hubs VALUES(20,1);
            INSERT INTO ops_hubs VALUES(30,0);
            CREATE TABLE ops_documents(id INTEGER PRIMARY KEY, reference TEXT, destination_hub_id INTEGER);
            CREATE TABLE ops_document_lines(id INTEGER PRIMARY KEY, document_id INTEGER, parcel_id INTEGER, active INTEGER);
            INSERT INTO parcels VALUES(1,'TRK-LOCAL',10);
            INSERT INTO parcels VALUES(2,'TRK-REMOTE',20);
            INSERT INTO parcels VALUES(3,'TRK-UNRECEIVED',NULL);
            INSERT INTO ops_documents VALUES(1,'MAN-LOCAL',10);
            INSERT INTO ops_documents VALUES(2,'MAN-REMOTE',20);
            INSERT INTO ops_documents VALUES(3,'MAN-WRONG-LOCATION',10);
            INSERT INTO ops_documents VALUES(4,'MAN-CLOSED-LINE',10);
            INSERT INTO ops_document_lines VALUES(1,1,1,1);
            INSERT INTO ops_document_lines VALUES(2,2,2,1);
            INSERT INTO ops_document_lines VALUES(3,3,2,1);
            INSERT INTO ops_document_lines VALUES(4,4,1,0);
        ''')

    def tearDown(self):
        self.db.close()

    def test_general_parcel_scope_is_active_hub_and_physical_location_only(self):
        for hub_id, expected in ((10, [1]), (20, [2])):
            clause, params = hub_parcel_scope(self.db, 'p', hub_id)
            rows = self.db.execute(f'SELECT p.id FROM parcels p WHERE {clause} ORDER BY p.id', params).fetchall()
            self.assertEqual([row['id'] for row in rows], expected)
        for hub_id in (30, 99, None, True):
            with self.subTest(hub_id=hub_id):
                self.assertEqual(hub_parcel_scope(self.db, 'p', hub_id), ('1=0', []))
        self.assertEqual(hub_parcel_scope(self.db, 'p; DROP TABLE parcels;--', 10), ('1=0', []))
        missing_schema = sqlite3.connect(':memory:')
        try:
            self.assertEqual(hub_parcel_scope(missing_schema, 'p', 10), ('1=0', []))
        finally:
            missing_schema.close()

    def test_tracking_lookup_only_returns_parcels_at_selected_hub(self):
        self.assertEqual(parcel_by_tracking_at_hub(self.db, 'TRK-LOCAL', 10)['id'], 1)
        self.assertIsNone(parcel_by_tracking_at_hub(self.db, 'TRK-REMOTE', 10))
        self.assertIsNone(parcel_by_tracking_at_hub(self.db, 'TRK-UNRECEIVED', 10))
        self.assertIsNone(parcel_by_tracking_at_hub(self.db, 'TRK-LOCAL', 20))
        self.assertIsNone(parcel_by_tracking_at_hub(self.db, 'TRK-LOCAL', True))

    def test_manifest_lookup_requires_matching_destination_and_physical_receipt(self):
        self.assertEqual(parcel_by_manifest_at_hub(self.db, 'MAN-LOCAL', 10)['id'], 1)
        self.assertIsNone(parcel_by_manifest_at_hub(self.db, 'MAN-REMOTE', 10))
        self.assertIsNone(parcel_by_manifest_at_hub(self.db, 'MAN-WRONG-LOCATION', 10))
        self.assertIsNone(parcel_by_manifest_at_hub(self.db, 'MAN-CLOSED-LINE', 10))

    def test_manifest_details_hide_unreceived_and_other_hub_lines(self):
        lines = [
            {'id': 1, 'received_at': '2026-10-13T10:00:00', 'current_hub_id': 10},
            {'id': 2, 'received_at': '2026-10-13T10:01:00', 'current_hub_id': 20},
            {'id': 3, 'received_at': None, 'current_hub_id': None},
            {'id': 4, 'received_at': '2026-10-13T10:02:00', 'current_hub_id': None},
        ]
        self.assertEqual([line['id'] for line in hub_received_lines(lines, 10)], [1])
        self.assertEqual(hub_received_lines(lines, True), [])


if __name__ == '__main__':
    unittest.main()
