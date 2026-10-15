import sqlite3
import unittest

from hub_cod import (
    add_adjustment,
    admin_overview,
    admin_settlement_options,
    ensure_hub_cod_schema,
    manager_overview,
    money_cents,
    record_admin_receipt,
    record_admin_driver_settlement,
    record_driver_handoff,
    resolve_cod_hub,
)


class HubCodLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT NOT NULL,hub_id INTEGER);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE ops_attempts(
                id INTEGER PRIMARY KEY,driver_id INTEGER,outcome TEXT,amount_cents INTEGER,
                created_at TEXT NOT NULL,parcel_id INTEGER
            );
            CREATE TABLE driver_statements(
                id INTEGER PRIMARY KEY,driver_id INTEGER NOT NULL,driver_name TEXT NOT NULL,
                mode TEXT NOT NULL,period_from TEXT,period_to TEXT,parcel_count INTEGER NOT NULL,
                cash_due_cents INTEGER NOT NULL,created_at TEXT NOT NULL,cancelled_at TEXT
            );
            CREATE TABLE driver_statement_lines(
                id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL,parcel_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE driver_transactions(
                id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL,amount_cents INTEGER NOT NULL,
                voided_at TEXT,kind TEXT,method TEXT,reference TEXT,request_key TEXT UNIQUE
            );
            INSERT INTO users(id,name,role,active) VALUES(1,'Hub manager','hub_manager',1),(2,'Driver A','livreur',1),(3,'Admin','admin',1);
            INSERT INTO cities(id,name,hub_id) VALUES(1,'Agadir',10),(2,'Oujda',20),(3,'Fallback',NULL);
            INSERT INTO ops_hubs(id,name,city_id,active) VALUES(10,'Hub Agadir',1,1),(20,'Hub Oujda',2,1),(90,'Central',3,1),(30,'Inactive',3,0);
            INSERT INTO settings(key,value) VALUES('central_hub_id','90');
        ''')
        ensure_hub_cod_schema(self.db)
        self.db.executemany('''INSERT INTO ops_attempts(id,driver_id,outcome,amount_cents,created_at,cod_hub_id)
            VALUES(?,?,?,?,?,?)''', [
            (101, 2, 'Livré', 12000, '2026-10-12T10:00:00', 10),
            (102, 2, 'Livré', 8000, '2026-10-12T11:00:00', 10),
            (103, 2, 'Livré', 5000, '2026-10-12T12:00:00', 20),
            (104, 2, 'Refusé', None, '2026-10-12T13:00:00', 10),
            (105, 2, 'Livré', 1100, '2026-10-12T14:00:00', None),
            (106, 2, 'Livré', 0, '2026-10-12T15:00:00', 10),
            (107, 2, 'Livré', 0, '2026-10-12T16:00:00', None),
        ])
        self.db.execute('UPDATE ops_attempts SET parcel_id=id+1000')

    def tearDown(self):
        self.db.close()

    def record_handoff(self, received='200.00', reason='', key='driver-handoff-key-0001'):
        return record_driver_handoff(
            self.db, hub_id=10, driver_id=2, received_cents=money_cents(received), reason=reason,
            actor_id=1, actor_name='Hub manager', request_key=key, created_at='2026-10-13T10:00:00',
        )

    def test_city_route_uses_direct_hub_then_only_admin_central_fallback(self):
        self.assertEqual(resolve_cod_hub(self.db, 1), 10)
        self.assertEqual(resolve_cod_hub(self.db, 3), 90)
        self.db.execute('UPDATE ops_hubs SET active=0 WHERE id=10')
        self.assertEqual(resolve_cod_hub(self.db, 1), 90)
        self.db.execute("UPDATE settings SET value='30' WHERE key='central_hub_id'")
        self.assertIsNone(resolve_cod_hub(self.db, 3))

    def test_unassigned_driver_cod_is_visible_but_not_handoffable(self):
        self.db.execute("INSERT INTO ops_attempts(id,driver_id,outcome,amount_cents,created_at,cod_hub_id) VALUES(108,NULL,'Livré',3000,'2026-10-12T17:00:00',10)")
        overview=manager_overview(self.db,10)
        unassigned=next(row for row in overview['drivers_due'] if row['driver_id'] is None)
        self.assertEqual(unassigned['driver_name'],'Livreur non attribué')
        self.assertEqual(unassigned['expected_cents'],3000)
        admin=admin_overview(self.db)
        hub=next(row for row in admin['hubs'] if row['id']==10)
        self.assertEqual((hub['unassigned_driver_cod_count'],hub['unassigned_driver_cod_cents']),(1,3000))

    def test_money_parser_uses_integer_cents_and_rejects_fractional_centimes(self):
        self.assertEqual(money_cents('12,34'), 1234)
        self.assertEqual(money_cents('-0.25', signed=True), -25)
        with self.assertRaises(ValueError):
            money_cents('1.001')
        with self.assertRaises(ValueError):
            money_cents('-1.00')

    def test_driver_handoff_is_hub_scoped_private_and_idempotent(self):
        with self.assertRaisesRegex(ValueError, 'Motif obligatoire'):
            self.record_handoff('199.00')
        first = self.record_handoff()
        self.assertEqual(first['expected_cents'], 20000)
        self.assertEqual(first['delivery_count'], 2)
        replay = self.record_handoff()
        self.assertTrue(replay['already_recorded'])
        overview = manager_overview(self.db, 10)
        self.assertEqual(overview['expected_due_cents'], 0)
        self.assertEqual(len(overview['handoffs']), 1)
        self.assertEqual(overview['handoffs'][0]['variance_cents'], 0)
        self.assertNotIn('tracking', overview['handoffs'][0])
        self.assertNotIn('lines', overview['handoffs'][0])
        for private_key in ('request_key', 'payload_hash', 'actor_id'):
            self.assertNotIn(private_key, overview['handoffs'][0])
        other_hub = manager_overview(self.db, 20)
        self.assertEqual(other_hub['expected_due_cents'], 5000)
        with self.assertRaisesRegex(ValueError, 'Clé déjà utilisée'):
            self.record_handoff('201.00', 'Autre montant', key='driver-handoff-key-0001')

    def test_admin_receipt_and_manual_adjustment_are_auditable_and_append_only(self):
        self.record_handoff('190.00', 'Écart déclaré lors du comptage')
        handoff_id=self.db.execute('SELECT id FROM hub_cod_handoffs').fetchone()[0]
        adjusted=add_adjustment(
            self.db, record_type='driver_handoff', record_id=handoff_id, delta_cents=1000,
            reason='Correction validée après recomptage', actor_id=3, actor_name='Admin',
            request_key='hub-cod-adjust-key-0001', created_at='2026-10-13T11:00:00',
        )
        self.assertEqual((adjusted['old_amount_cents'], adjusted['new_amount_cents']), (19000, 20000))
        pending_view=admin_overview(self.db)
        self.assertEqual(len(pending_view['pending_handoffs']),1)
        for private_key in ('request_key', 'payload_hash', 'actor_id'):
            self.assertNotIn(private_key,pending_view['pending_handoffs'][0])
        receipt=record_admin_receipt(
            self.db, hub_id=10, handoff_ids=[handoff_id], received_cents=20000, reason='',
            actor_id=3, actor_name='Admin', request_key='hub-admin-receipt-key-0001',
            created_at='2026-10-13T12:00:00',
        )
        self.assertEqual(receipt['expected_cents'], 20000)
        self.assertEqual(receipt['variance_cents'], 0)
        view=admin_overview(self.db)
        self.assertEqual(view['pending_handoffs'], [])
        self.assertEqual(view['admin_receipts'][0]['effective_received_cents'], 20000)
        for private_key in ('request_key', 'payload_hash', 'actor_id'):
            self.assertNotIn(private_key, view['admin_receipts'][0])
        self.assertEqual(view['unassigned_cod_count'], 1)
        self.assertEqual(view['unassigned_cod_cents'], 1100)
        with self.assertRaisesRegex(ValueError, 'déjà été rapprochée'):
            add_adjustment(
                self.db, record_type='driver_handoff', record_id=handoff_id, delta_cents=100,
                reason='Correction tardive', actor_id=3, actor_name='Admin',
                request_key='hub-cod-adjust-key-0002', created_at='2026-10-13T12:10:00',
            )
        adjustment=add_adjustment(
            self.db, record_type='admin_receipt', record_id=receipt['id'], delta_cents=-500,
            reason='Correction après rapprochement bancaire', actor_id=3, actor_name='Admin',
            request_key='hub-cod-adjust-key-0003', created_at='2026-10-13T12:15:00',
        )
        self.assertEqual((adjustment['old_amount_cents'], adjustment['new_amount_cents']), (20000, 19500))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
            self.db.execute("UPDATE hub_cod_admin_receipts SET reason='rewrite' WHERE id=?", (receipt['id'],))
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'append-only'):
            self.db.execute('DELETE FROM hub_cod_adjustments WHERE id=1')

    def settlement_services(self):
        def statement_reader(connection, statement_id, actor):
            row=connection.execute('SELECT * FROM driver_statements WHERE id=?',(statement_id,)).fetchone()
            if not row:raise ValueError('Relevé introuvable.')
            return dict(row)
        def balances_reader(connection, statement):
            received=connection.execute('''SELECT COALESCE(sum(amount_cents),0) FROM driver_transactions
                WHERE statement_id=? AND voided_at IS NULL''',(statement['id'],)).fetchone()[0]
            return {**statement,'cash_remaining_cents':statement['cash_due_cents']-received}
        def add_transaction(connection, statement_id, actor, payload):
            amount_cents=money_cents(payload['amount'])
            cursor=connection.execute('''INSERT INTO driver_transactions(
                statement_id,amount_cents,voided_at,kind,method,reference,request_key)
                VALUES(?,?,NULL,?,?,?,?)''',(statement_id,amount_cents,payload['kind'],payload['method'],
                payload['reference'],payload['request_key']))
            return {'transaction_id':cursor.lastrowid,'already_recorded':False}
        return statement_reader,balances_reader,add_transaction

    def received_handoff_and_receipt(self):
        self.record_handoff()
        handoff_id=self.db.execute('SELECT id FROM hub_cod_handoffs').fetchone()[0]
        receipt=record_admin_receipt(self.db,hub_id=10,handoff_ids=[handoff_id],received_cents=20000,
            reason='',actor_id=3,actor_name='Admin',request_key='hub-admin-receipt-key-settle',
            created_at='2026-10-13T12:00:00')
        return handoff_id,receipt['id']

    def create_statement(self, *, statement_id=1, driver_id=2, cash_due=15000, parcels=(1101,1102)):
        self.db.execute('''INSERT INTO driver_statements(
            id,driver_id,driver_name,mode,period_from,period_to,parcel_count,cash_due_cents,created_at,cancelled_at)
            VALUES(?,?,?,?,?,?,?,?,?,NULL)''',(statement_id,driver_id,'Driver A','gross','2026-10-12',
            '2026-10-12',len(parcels),cash_due,'2026-10-13T13:00:00'))
        self.db.executemany('INSERT INTO driver_statement_lines(statement_id,parcel_id,active) VALUES(?,?,1)',
                            [(statement_id,p) for p in parcels])

    def test_manual_link_is_idempotent_capped_and_excess_remains_visible(self):
        handoff_id,receipt_id=self.received_handoff_and_receipt()
        self.create_statement(cash_due=15000)
        reader,balances,add_tx=self.settlement_services()
        actor={'id':3,'name':'Admin','role':'admin'}
        options=admin_settlement_options(self.db,handoff_id,actor=actor,statement_reader=reader,balances_reader=balances)
        self.assertEqual((options['handoff_remaining_cents'],options['receipt_remaining_cents']),(20000,20000))
        self.assertEqual(len(options['statements']),1)
        self.assertEqual(options['statements'][0]['cash_remaining_cents'],15000)
        self.assertEqual(options['statements'][0]['matched_delivery_count'],2)
        with self.assertRaisesRegex(ValueError,'Motif obligatoire'):
            record_admin_driver_settlement(self.db,receipt_id=receipt_id,handoff_id=handoff_id,
                statement_id=1,amount_cents=15000,reason='',actor=actor,request_key='cod-settlement-partial-key-01',
                paid_on='2026-10-13',created_at='2026-10-13T14:00:00',statement_reader=reader,
                balances_reader=balances,add_transaction_fn=add_tx)
        payload=dict(receipt_id=receipt_id,handoff_id=handoff_id,statement_id=1,amount_cents=15000,
            reason='Affectation limitée au cash dû restant du relevé',actor=actor,
            request_key='cod-settlement-partial-key-01',paid_on='2026-10-13',created_at='2026-10-13T14:00:00',
            statement_reader=reader,balances_reader=balances,add_transaction_fn=add_tx)
        linked=record_admin_driver_settlement(self.db,**payload)
        self.assertFalse(linked['already_recorded'])
        self.assertEqual((linked['old_cash_remaining_cents'],linked['new_cash_remaining_cents']),(15000,0))
        tx=self.db.execute('SELECT kind,method,amount_cents FROM driver_transactions').fetchone()
        self.assertEqual(tuple(tx),('cash','Espèces',15000))
        replay=record_admin_driver_settlement(self.db,**payload)
        self.assertTrue(replay['already_recorded'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM driver_transactions').fetchone()[0],1)
        overview=admin_overview(self.db)
        self.assertEqual(overview['settlement_unlinked_cents'],5000)
        receipt=overview['admin_receipts'][0]
        self.assertEqual((receipt['settlement_allocated_cents'],receipt['settlement_unlinked_cents']),(15000,5000))
        handoff=overview['settlement_handoffs'][0]
        self.assertEqual((handoff['settlement_allocated_cents'],handoff['settlement_unlinked_cents']),(15000,5000))
        with self.assertRaisesRegex(ValueError,'règlements déjà liés'):
            add_adjustment(self.db,record_type='admin_receipt',record_id=receipt_id,delta_cents=-15001,
                reason='Tentative de réduction sous le lien actif',actor_id=3,actor_name='Admin',
                request_key='hub-cod-adjust-under-link-001',created_at='2026-10-13T15:00:00')

    def test_manual_link_rejects_amount_over_cash_due_or_received_cash(self):
        handoff_id,receipt_id=self.received_handoff_and_receipt()
        self.create_statement(cash_due=15000)
        reader,balances,add_tx=self.settlement_services()
        actor={'id':3,'name':'Admin','role':'admin'}
        common=dict(receipt_id=receipt_id,handoff_id=handoff_id,statement_id=1,reason='Motif du test',
            actor=actor,paid_on='2026-10-13',created_at='2026-10-13T14:00:00',statement_reader=reader,
            balances_reader=balances,add_transaction_fn=add_tx)
        with self.assertRaisesRegex(ValueError,'solde COD restant'):
            record_admin_driver_settlement(self.db,amount_cents=15001,request_key='cod-settle-over-statement-01',**common)
        with self.assertRaisesRegex(ValueError,'cash reçu'):
            record_admin_driver_settlement(self.db,amount_cents=20001,request_key='cod-settle-over-receipt-01',**common)
        self.create_statement(statement_id=2,driver_id=3,cash_due=10000,parcels=(1101,))
        with self.assertRaisesRegex(ValueError,'autre livreur'):
            record_admin_driver_settlement(self.db,amount_cents=10000,request_key='cod-settle-wrong-driver-01',
                **{**common,'statement_id':2})
        self.assertEqual(self.db.execute('SELECT count(*) FROM driver_transactions').fetchone()[0],0)

    def test_grouped_receipt_balance_is_shared_across_handoffs(self):
        first_handoff=self.record_handoff()
        first_id=first_handoff['id']
        self.db.execute("INSERT INTO ops_attempts(id,driver_id,outcome,amount_cents,created_at,cod_hub_id,parcel_id) VALUES(109,2,'Livré',5000,'2026-10-13T09:00:00',10,1109)")
        second=self.record_handoff('50.00',key='driver-handoff-key-grouped-0002')
        receipt=record_admin_receipt(self.db,hub_id=10,handoff_ids=[first_id,second['id']],received_cents=22000,
            reason='Écart de comptage sur le reçu groupé',actor_id=3,actor_name='Admin',
            request_key='hub-admin-receipt-key-grouped',created_at='2026-10-13T12:00:00')
        self.create_statement(statement_id=1,cash_due=20000,parcels=(1101,1102))
        self.create_statement(statement_id=2,cash_due=5000,parcels=(1109,))
        reader,balances,add_tx=self.settlement_services();actor={'id':3,'name':'Admin'}
        first_options=admin_settlement_options(self.db,first_id,actor=actor,statement_reader=reader,balances_reader=balances)
        second_options=admin_settlement_options(self.db,second['id'],actor=actor,statement_reader=reader,balances_reader=balances)
        self.assertEqual(first_options['receipt_remaining_cents'],22000)
        self.assertEqual(second_options['receipt_remaining_cents'],22000)
        common=dict(receipt_id=receipt['id'],actor=actor,paid_on='2026-10-13',
            statement_reader=reader,balances_reader=balances,add_transaction_fn=add_tx)
        record_admin_driver_settlement(self.db,handoff_id=first_id,statement_id=1,amount_cents=20000,reason='',
            request_key='cod-settle-group-first-key-01',created_at='2026-10-13T14:00:00',**common)
        with self.assertRaisesRegex(ValueError,'cash reçu'):
            record_admin_driver_settlement(self.db,handoff_id=second['id'],statement_id=2,amount_cents=2001,
                reason='Test de dépassement',request_key='cod-settle-group-over-key-01',
                created_at='2026-10-13T14:01:00',**common)
        options=admin_settlement_options(self.db,second['id'],actor=actor,statement_reader=reader,balances_reader=balances)
        self.assertEqual((options['handoff_remaining_cents'],options['receipt_remaining_cents']),(5000,2000))
        record_admin_driver_settlement(self.db,handoff_id=second['id'],statement_id=2,amount_cents=2000,
            reason='Rapprochement limité au cash reçu par l’Administration',
            request_key='cod-settle-group-second-key-01',created_at='2026-10-13T14:02:00',**common)
        overview=admin_overview(self.db)
        receipt_view=overview['admin_receipts'][0]
        self.assertEqual((receipt_view['settlement_allocated_cents'],receipt_view['settlement_unlinked_cents']),(22000,0))
        second_view=next(h for h in overview['settlement_handoffs'] if h['id']==second['id'])
        self.assertEqual((second_view['settlement_unlinked_cents'],second_view['receipt_unlinked_cents']),(3000,0))

    def test_receipt_excess_and_manual_statement_options_stay_visible(self):
        handoff_id,receipt_id=self.received_handoff_and_receipt()
        self.create_statement(cash_due=0)
        reader,balances,add_tx=self.settlement_services()
        options=admin_settlement_options(self.db,handoff_id,actor={'id':3,'name':'Admin'},
            statement_reader=reader,balances_reader=balances)
        self.assertEqual(options['statements'],[])
        self.assertEqual(options['receipt_remaining_cents'],20000)
        self.assertEqual(admin_overview(self.db)['admin_receipts'][0]['settlement_unlinked_cents'],20000)

    def test_admin_receipt_cannot_mix_hubs_or_reuse_handoff(self):
        self.record_handoff()
        first=self.db.execute('SELECT id FROM hub_cod_handoffs').fetchone()[0]
        second=record_driver_handoff(
            self.db, hub_id=20, driver_id=2, received_cents=5000, reason='', actor_id=1,
            actor_name='Hub manager', request_key='driver-handoff-key-0002', created_at='2026-10-13T10:05:00',
        )
        with self.assertRaisesRegex(ValueError, 'autre Hub'):
            record_admin_receipt(self.db, hub_id=10, handoff_ids=[first,second['id']], received_cents=25000,
                reason='', actor_id=3, actor_name='Admin', request_key='hub-admin-receipt-key-0002',
                created_at='2026-10-13T12:00:00')
        receipt=record_admin_receipt(self.db, hub_id=10, handoff_ids=[first], received_cents=20000,
            reason='', actor_id=3, actor_name='Admin', request_key='hub-admin-receipt-key-0003',
            created_at='2026-10-13T12:01:00')
        with self.assertRaisesRegex(ValueError, 'déjà été rapprochée'):
            record_admin_receipt(self.db, hub_id=10, handoff_ids=[first], received_cents=20000,
                reason='', actor_id=3, actor_name='Admin', request_key='hub-admin-receipt-key-0004',
                created_at='2026-10-13T12:02:00')
        self.assertEqual(receipt['handoff_count'], 1)


if __name__ == '__main__':
    unittest.main()
