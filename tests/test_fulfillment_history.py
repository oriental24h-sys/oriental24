"""Stock chronology: persisted new stages and read-only legacy reconstruction."""
import unittest
from datetime import datetime, timedelta
import test_fulfillment_flags as fixture


class FulfillmentHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.FulfillmentFlagsTests.setUpClass()
        cls.t = fixture.FulfillmentFlagsTests()
        cls.m = cls.t.m

    @classmethod
    def tearDownClass(cls):
        fixture.FulfillmentFlagsTests.tearDownClass()

    def prepare(self):
        oid, _ = self.t.reserve(self.t.payload())
        with self.m.conn() as c:
            c.execute("UPDATE fulfillment_orders SET created_at='2026-10-01T08:00:00' WHERE id=?", (oid,))
        self.t.ship(oid, (1, 0))
        detail = self.t.client.get(f'/api/fulfillment/orders/{oid}').json
        return oid, detail['parcel_id'], detail

    def timeline(self, pid):
        response = self.t.client.get(f'/api/parcels/{pid}')
        self.assertEqual(response.status_code, 200, response.json)
        events = sorted(response.json['events'], key=lambda e: (e['created_at'], e.get('timeline_order', 0), e.get('id') or 0))
        return response.json['parcel'], events

    def snapshot(self, pid, oid):
        with self.m.conn() as c:
            return (
                [tuple(r) for r in c.execute('SELECT * FROM events WHERE parcel_id=? ORDER BY id', (pid,))],
                tuple(c.execute('SELECT * FROM parcels WHERE id=?', (pid,)).fetchone()),
                tuple(c.execute('SELECT * FROM fulfillment_orders WHERE id=?', (oid,)).fetchone()),
                [tuple(r) for r in c.execute('SELECT * FROM movements WHERE fulfillment_order_id=? ORDER BY id', (oid,))],
                [tuple(r) for r in c.execute('SELECT * FROM ops_notifications ORDER BY id')],
            )

    def test_new_stock_order_records_created_confirmed_then_collected(self):
        oid, pid, order = self.prepare()
        parcel, events = self.timeline(pid)
        self.assertEqual([e['status'] for e in events], ['Créé', 'Confirmé', 'Ramassé'])
        self.assertEqual(events[0]['actor_id'], self.t.client_id)
        self.assertEqual(events[0]['created_at'], '2026-10-01T08:00:00')
        self.assertEqual(events[1]['actor_id'], order['processed_by'])
        self.assertEqual(events[1]['created_at'], order['processed_at'])
        self.assertEqual(events[2]['actor_id'], order['processed_by'])
        self.assertTrue(all(e['id'] is not None for e in events))
        self.assertFalse(any(e.get('history_reconstructed') for e in events))
        self.assertEqual(parcel['status'], 'Ramassé')
        with self.m.conn() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT status FROM events WHERE parcel_id=? ORDER BY id', (pid,))], ['Créé','Confirmé','Ramassé'])

    def test_legacy_received_order_keeps_real_events_and_state_unchanged(self):
        oid, pid, order = self.prepare()
        with self.m.conn() as c:
            c.execute("DELETE FROM events WHERE parcel_id=? AND status IN ('Créé','Confirmé')", (pid,))
            start = datetime.fromisoformat(order['processed_at'])
            for minutes, status in ((10, 'Transit'), (60, 'Réceptionné')):
                c.execute('INSERT INTO events(parcel_id,actor_id,status,note,created_at) VALUES(?,?,?,?,?)',
                          (pid, order['processed_by'], status, 'TRF-000028 · scan', (start+timedelta(minutes=minutes)).isoformat(timespec='seconds')))
            c.execute("UPDATE parcels SET status='Réceptionné' WHERE id=?", (pid,))
        before = self.snapshot(pid, oid)
        parcel, events = self.timeline(pid)
        self.assertEqual([e['status'] for e in events], ['Créé','Confirmé','Ramassé','Transit','Réceptionné'])
        self.assertEqual(parcel['status'], 'Réceptionné')
        self.assertEqual([e['status'] for e in events if e.get('history_reconstructed')], ['Créé','Confirmé'])
        self.assertTrue(all('Historique reconstitué' in e['note'] for e in events[:2]))
        self.assertEqual(self.timeline(pid)[1], events)
        self.assertEqual(self.snapshot(pid, oid), before)

    def test_existing_stage_is_preserved_and_same_second_is_ordered(self):
        oid, pid, order = self.prepare()
        with self.m.conn() as c:
            t = c.execute("SELECT created_at FROM events WHERE parcel_id=? AND status='Ramassé'", (pid,)).fetchone()[0]
            c.execute('UPDATE fulfillment_orders SET created_at=?,processed_at=? WHERE id=?', (t,t,oid))
            c.execute("UPDATE events SET created_at=? WHERE parcel_id=? AND status='Créé'", (t,pid))
            c.execute("DELETE FROM events WHERE parcel_id=? AND status='Confirmé'", (pid,))
        _, events = self.timeline(pid)
        self.assertEqual([e['status'] for e in events], ['Créé','Confirmé','Ramassé'])
        self.assertIsNotNone(events[0]['id'])
        self.assertFalse(events[0].get('history_reconstructed', False))
        self.assertTrue(events[1]['history_reconstructed'])

    def test_missing_legacy_preparation_evidence_does_not_invent_confirmation(self):
        oid, pid, _ = self.prepare()
        with self.m.conn() as c:
            c.execute("DELETE FROM events WHERE parcel_id=? AND status IN ('Créé','Confirmé')", (pid,))
            c.execute('UPDATE fulfillment_orders SET processed_at=NULL,processed_by=NULL WHERE id=?', (oid,))
        self.assertEqual([e['status'] for e in self.timeline(pid)[1]], ['Ramassé'])

    def test_regular_parcel_history_is_unchanged(self):
        response = self.t.client.post('/api/parcels', json=self.t.payload(), headers=self.t.client_headers)
        self.assertEqual(response.status_code,200,response.json)
        with self.m.conn() as c:
            pid = c.execute('SELECT id FROM parcels WHERE client_id=? ORDER BY id DESC LIMIT 1', (self.t.client_id,)).fetchone()[0]
        events = self.timeline(pid)[1]
        self.assertEqual([e['status'] for e in events], ['Créé'])
        self.assertFalse(any(e.get('history_reconstructed') for e in events))

    def test_repeat_preparation_does_not_duplicate_events_or_deduct_twice(self):
        oid, pid, _ = self.prepare()
        before = self.snapshot(pid, oid)
        response = self.t.admin.post(f'/api/fulfillment/orders/{oid}/ship', json={'hub_id': self.t.hub, 'checked': True}, headers=self.t.admin_headers)
        self.assertEqual(response.status_code, 409, response.json)
        self.assertEqual(self.snapshot(pid, oid), before)

    def test_missing_physical_check_creates_no_parcel_or_history(self):
        oid, _ = self.t.reserve(self.t.payload())
        response = self.t.admin.post(f'/api/fulfillment/orders/{oid}/ship', json={'hub_id': self.t.hub, 'checked': False}, headers=self.t.admin_headers)
        self.assertEqual(response.status_code, 400, response.json)
        order = self.t.client.get(f'/api/fulfillment/orders/{oid}').json
        self.assertIsNone(order['parcel_id'])
        self.assertEqual(order['status'], 'Réservé')


if __name__ == '__main__':
    unittest.main()
