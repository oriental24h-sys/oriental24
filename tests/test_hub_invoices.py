import sqlite3
import unittest

from hub_cod import add_adjustment, ensure_hub_cod_schema
from hub_invoices import (
    adjust_hub_invoice,
    cancel_hub_invoice_draft,
    create_hub_invoice_draft,
    ensure_hub_invoice_schema,
    get_hub_admin_invoice_detail,
    hub_manager_invoice_list,
    issue_hub_invoice,
    link_existing_admin_receipt,
    record_hub_invoice_receipt,
)


class HubInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE users(id INTEGER PRIMARY KEY,name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT NOT NULL,hub_id INTEGER);
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,name TEXT NOT NULL,city_id INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,tracking TEXT NOT NULL,city_id INTEGER NOT NULL,status TEXT);
            CREATE TABLE ops_attempts(id INTEGER PRIMARY KEY,parcel_id INTEGER,driver_id INTEGER,outcome TEXT,
                amount_cents INTEGER,created_at TEXT NOT NULL,cod_hub_id INTEGER);
            CREATE TABLE driver_statements(id INTEGER PRIMARY KEY,driver_id INTEGER NOT NULL);
            CREATE TABLE driver_statement_lines(id INTEGER PRIMARY KEY,statement_id INTEGER NOT NULL,parcel_id INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE driver_transactions(id INTEGER PRIMARY KEY,statement_id INTEGER,amount_cents INTEGER,
                voided_at TEXT,kind TEXT,method TEXT,reference TEXT,request_key TEXT UNIQUE);
            INSERT INTO users(id,name,role) VALUES(1,'Admin','admin'),(2,'Manager A','hub_manager'),(3,'Driver','livreur');
            INSERT INTO cities(id,name,hub_id) VALUES(1,'Agadir',10),(2,'Oujda',20);
            INSERT INTO ops_hubs(id,name,city_id,active) VALUES(10,'Hub Agadir',1,1),(20,'Hub Oujda',2,1);
            INSERT INTO parcels(id,tracking,city_id,status) VALUES
                (1001,'TRACK-1001',1,'Livré'),(1002,'TRACK-1002',1,'Livré'),
                (2001,'TRACK-2001',2,'Livré'),(1003,'TRACK-1003',1,'Refusé');
            INSERT INTO ops_attempts(id,parcel_id,driver_id,outcome,amount_cents,created_at,cod_hub_id) VALUES
                (101,1001,3,'Livré',12000,'2026-10-12T10:00:00',10),
                (102,1002,3,'Livré',8000,'2026-10-13T11:00:00',10),
                (103,2001,3,'Livré',5000,'2026-10-12T12:00:00',20),
                (104,1003,3,'Refusé',7000,'2026-10-12T13:00:00',10),
                (105,1001,3,'Livré',3000,'2026-10-14T13:00:00',NULL);
        ''')
        ensure_hub_cod_schema(self.db)
        ensure_hub_invoice_schema(self.db)

    def tearDown(self):
        self.db.close()

    def make_draft(self,key='hub-invoice-draft-key-0001',start='2026-10-12',end='2026-10-13'):
        return create_hub_invoice_draft(self.db,hub_id=10,period_from=start,period_to=end,
            actor_id=1,request_key=key,created_at='2026-10-14T09:00:00')

    def issue(self,invoice_id):
        return issue_hub_invoice(self.db,invoice_id=invoice_id,actor_id=1,issued_at='2026-10-14T10:00:00')

    def test_draft_snapshots_full_hub_attributed_cod_and_requires_admin_issue(self):
        draft=self.make_draft()
        self.assertEqual((draft['delivery_count'],draft['total_cents'],draft['status']),(2,20000,'draft'))
        self.assertEqual(self.make_draft()['id'],draft['id'])
        with self.assertRaisesRegex(ValueError,'Aucun COD'):
            self.make_draft('hub-invoice-draft-key-0002')
        with self.assertRaisesRegex(ValueError,'Période invalide'):
            self.make_draft('hub-invoice-draft-key-0003','2026-10-14','2026-10-12')
        issued=self.issue(draft['id'])
        self.assertEqual((issued['status'],issued['remaining_cents'],issued['settlement_status']),
                         ('issued',20000,'Émise'))
        self.assertTrue(self.issue(draft['id'])['already_issued'])
        manager=hub_manager_invoice_list(self.db,10)
        self.assertEqual((manager['count'],manager['invoices'][0]['total_cents']),(1,20000))
        self.assertEqual(manager['read_only'],True)
        self.assertEqual(hub_manager_invoice_list(self.db,20)['count'],0)
        with self.assertRaisesRegex(sqlite3.IntegrityError,'transition'):
            self.db.execute('UPDATE hub_invoices SET total_cents=1 WHERE id=?',(draft['id'],))

    def test_cancelled_draft_is_audited_and_lines_can_be_reissued(self):
        draft=self.make_draft()
        with self.assertRaisesRegex(ValueError,'Motif obligatoire'):
            cancel_hub_invoice_draft(self.db,invoice_id=draft['id'],actor_id=1,
                cancelled_at='2026-10-14T09:30:00',reason='')
        cancelled=cancel_hub_invoice_draft(self.db,invoice_id=draft['id'],actor_id=1,
            cancelled_at='2026-10-14T09:30:00',reason='Période à corriger')
        self.assertEqual(cancelled['status'],'cancelled')
        replacement=self.make_draft('hub-invoice-draft-key-0004')
        self.assertEqual((replacement['delivery_count'],replacement['total_cents']),(2,20000))
        self.issue(replacement['id'])
        with self.assertRaisesRegex(ValueError,'Seul un brouillon'):
            cancel_hub_invoice_draft(self.db,invoice_id=replacement['id'],actor_id=1,
                cancelled_at='2026-10-14T09:40:00',reason='test')

    def test_existing_admin_receipt_is_manually_linked_with_caps_and_excess_visible(self):
        draft=self.make_draft();self.issue(draft['id'])
        receipt=self.db.execute('''INSERT INTO hub_cod_admin_receipts(
            hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
            request_key,payload_hash,created_at)
            VALUES(10,20000,25000,5000,'Surplus',1,'Admin','admin-receipt-key-0001','hash','2026-10-14T11:00:00')''').lastrowid
        linked=link_existing_admin_receipt(self.db,invoice_id=draft['id'],receipt_id=receipt,
            amount_cents=20000,reason='Rapprochement facture',actor_id=1,actor_name='Admin',
            request_key='hub-invoice-settle-key-0001',created_at='2026-10-14T12:00:00')
        self.assertEqual((linked['invoice']['remaining_cents'],linked['receipt_remaining_cents']), (0,5000))
        with self.assertRaisesRegex(ValueError,'dépasse'):
            link_existing_admin_receipt(self.db,invoice_id=draft['id'],receipt_id=receipt,
                amount_cents=1,reason='Trop',actor_id=1,actor_name='Admin',
                request_key='hub-invoice-settle-key-0002',created_at='2026-10-14T12:01:00')
        detail=get_hub_admin_invoice_detail(self.db,draft['id'])
        self.assertEqual(detail['receipts'][0]['invoice_unlinked_cents'],5000)
        with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):
            self.db.execute('UPDATE hub_invoice_settlement_links SET amount_cents=1 WHERE id=1')

    def test_invoice_adjustments_are_reasoned_audited_append_only_and_capped_at_paid(self):
        draft=self.make_draft();self.issue(draft['id'])
        with self.assertRaisesRegex(ValueError,'Motif obligatoire'):
            adjust_hub_invoice(self.db,invoice_id=draft['id'],delta_cents=1000,reason='',actor_id=1,
                actor_name='Admin',request_key='invoice-adjust-key-reason-001',created_at='2026-10-14T11:00:00')
        adjusted=adjust_hub_invoice(self.db,invoice_id=draft['id'],delta_cents=1000,
            reason='Correction COD justifiée',actor_id=1,actor_name='Admin',
            request_key='invoice-adjust-key-reason-002',created_at='2026-10-14T11:01:00')
        self.assertEqual((adjusted['old_total_cents'],adjusted['new_total_cents'],
                          adjusted['invoice']['adjustments_cents']),(20000,21000,1000))
        receipt=self.db.execute('''INSERT INTO hub_cod_admin_receipts(
            hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
            request_key,payload_hash,created_at) VALUES(10,20000,20000,0,'',1,'Admin',
            'admin-receipt-adjust-cap','hash','2026-10-14T11:30:00')''').lastrowid
        link_existing_admin_receipt(self.db,invoice_id=draft['id'],receipt_id=receipt,
            amount_cents=20000,reason='',actor_id=1,actor_name='Admin',
            request_key='invoice-adjust-cap-link-0001',created_at='2026-10-14T11:31:00')
        with self.assertRaisesRegex(ValueError,'sous les reçus'):
            adjust_hub_invoice(self.db,invoice_id=draft['id'],delta_cents=-1001,
                reason='Ajustement trop important',actor_id=1,actor_name='Admin',
                request_key='invoice-adjust-key-reason-003',created_at='2026-10-14T11:40:00')
        reduced=adjust_hub_invoice(self.db,invoice_id=draft['id'],delta_cents=-1000,
            reason='Correction validée',actor_id=1,actor_name='Admin',
            request_key='invoice-adjust-key-reason-004',created_at='2026-10-14T11:41:00')
        self.assertEqual((reduced['invoice']['total_cents'],reduced['invoice']['remaining_cents']),(20000,0))
        with self.assertRaisesRegex(sqlite3.IntegrityError,'append-only'):
            self.db.execute("UPDATE hub_invoice_adjustments SET reason='changed' WHERE id=1")

    def test_one_physical_receipt_can_cover_both_cod_ledgers_without_double_counting(self):
        draft=self.make_draft();self.issue(draft['id'])
        receipt=self.db.execute('''INSERT INTO hub_cod_admin_receipts(
            hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
            request_key,payload_hash,created_at) VALUES(10,20000,25000,5000,'Surplus',1,'Admin',
            'admin-receipt-key-mirrored','hash','2026-10-14T11:00:00')''').lastrowid
        link_existing_admin_receipt(self.db,invoice_id=draft['id'],receipt_id=receipt,
            amount_cents=20000,reason='',actor_id=1,actor_name='Admin',
            request_key='hub-invoice-settle-mirrored',created_at='2026-10-14T12:00:00')
        self.db.execute("INSERT INTO driver_statements(id,driver_id) VALUES(1,3)")
        self.db.execute("INSERT INTO hub_cod_handoffs(id,hub_id,driver_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,request_key,payload_hash,created_at) VALUES(1,10,3,20000,20000,0,'',1,'Admin','handoff-mirrored','hash','2026-10-14T10:00:00')")
        self.db.execute("INSERT INTO driver_transactions(id,statement_id,amount_cents,kind,method,reference,request_key) VALUES(1,1,20000,'cash','Espèces','ref','transaction-mirrored')")
        self.db.execute("INSERT INTO hub_cod_settlement_links(id,receipt_id,handoff_id,statement_id,driver_transaction_id,amount_cents,old_cash_remaining_cents,new_cash_remaining_cents,reason,actor_id,actor_name,request_key,payload_hash,created_at) VALUES(1,?,1,1,1,20000,40000,20000,'',1,'Admin','statement-link-mirrored','hash','2026-10-14T12:05:00')",(receipt,))
        corrected=add_adjustment(self.db,record_type='admin_receipt',record_id=receipt,delta_cents=-1,
            reason='Correction de saisie',actor_id=1,actor_name='Admin',
            request_key='invoice-adjust-safe-floor-01',created_at='2026-10-14T13:00:00')
        self.assertEqual(corrected['new_amount_cents'],24999)
        with self.assertRaisesRegex(ValueError,'sous les règlements'):
            add_adjustment(self.db,record_type='admin_receipt',record_id=receipt,delta_cents=-5000,
                reason='Correction sous le rapprochement',actor_id=1,actor_name='Admin',
                request_key='invoice-adjust-safe-floor-02',created_at='2026-10-14T13:01:00')

    def test_new_invoice_receipt_is_admin_confirmed_idempotent_and_not_duplicated(self):
        draft=self.make_draft();self.issue(draft['id'])
        kwargs=dict(invoice_id=draft['id'],received_cents=10000,applied_cents=10000,
            reason='Remise partielle',actor_id=1,actor_name='Admin',
            request_key='hub-invoice-new-receipt-key-01',created_at='2026-10-14T12:00:00',
            not_recorded_before=True)
        result=record_hub_invoice_receipt(self.db,**kwargs)
        self.assertEqual((result['invoice']['remaining_cents'],result['unlinked_cents']),(10000,0))
        receipt=self.db.execute('SELECT source_type,invoice_id FROM hub_cod_admin_receipts WHERE id=?',(result['receipt_id'],)).fetchone()
        self.assertEqual(tuple(receipt),('hub_invoice',draft['id']))
        self.assertTrue(record_hub_invoice_receipt(self.db,**kwargs)['already_recorded'])
        self.db.execute('''INSERT INTO hub_cod_admin_receipts(
            hub_id,expected_cents,received_cents,variance_cents,reason,actor_id,actor_name,
            request_key,payload_hash,created_at) VALUES(10,1000,1000,0,'',1,'Admin',
            'old-unlinked-admin-receipt-0001','hash','2026-10-14T12:30:00')''')
        kwargs.update(received_cents=10000,applied_cents=10000,request_key='hub-invoice-new-receipt-key-02')
        with self.assertRaisesRegex(ValueError,'déjà un reçu Admin non relié'):
            record_hub_invoice_receipt(self.db,**kwargs)

    def test_new_invoice_receipt_is_blocked_until_pending_driver_handoff_is_reconciled(self):
        draft=self.make_draft();self.issue(draft['id'])
        self.db.execute('''INSERT INTO hub_cod_handoffs(id,hub_id,driver_id,expected_cents,received_cents,
            variance_cents,reason,actor_id,actor_name,request_key,payload_hash,created_at)
            VALUES(1,10,3,12000,12000,0,'',1,'Admin','pending-invoice-handoff-001','hash','2026-10-14T11:00:00')''')
        self.db.execute('INSERT INTO hub_cod_handoff_lines(handoff_id,attempt_id,amount_cents) VALUES(1,101,12000)')
        detail=get_hub_admin_invoice_detail(self.db,draft['id'])
        self.assertEqual(detail['pending_handoff_count'],1)
        with self.assertRaisesRegex(ValueError,'attendent encore la réception Admin'):
            record_hub_invoice_receipt(self.db,invoice_id=draft['id'],received_cents=12000,
                applied_cents=12000,reason='',actor_id=1,actor_name='Admin',
                request_key='hub-invoice-pending-handoff-key',created_at='2026-10-14T12:00:00',
                not_recorded_before=True)


if __name__=='__main__':
    unittest.main()
