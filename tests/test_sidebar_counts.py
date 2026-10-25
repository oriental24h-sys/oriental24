import sqlite3
import unittest
from sidebar_counts import sidebar_counts


class SidebarCountsTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(':memory:')
        self.c.executescript('''
        CREATE TABLE ops_hubs(id,active);
        CREATE TABLE parcels(id,client_id,current_hub_id,support_id,driver_id,status);
        CREATE TABLE tickets(user_id,status);
        CREATE TABLE requests(user_id,status);
        CREATE TABLE recipient_change_requests(client_id,status);
        CREATE TABLE invoices(client_id,status);
        CREATE TABLE stock_requests(client_id,status);
        CREATE TABLE fulfillment_orders(client_id,status);
        CREATE TABLE ramassage_bons(client_id,hub_id,status);
        CREATE TABLE ops_documents(id,client_id,source_hub_id,destination_hub_id,driver_id,kind,status);
        CREATE TABLE ops_notifications(user_id,read_at);
        CREATE TABLE driver_statements(id,driver_id,hub_id,cancelled_at,cash_due_cents,commission_due_cents);
        CREATE TABLE driver_transactions(statement_id,kind,amount_cents,voided_at);
        INSERT INTO ops_hubs VALUES(10,1),(20,1),(30,0);
        INSERT INTO ops_documents VALUES
          (1,101,NULL,10,NULL,'partner_palette','En transit'),
          (2,101,NULL,10,NULL,'partner_palette','Partiellement reçu'),
          (3,202,NULL,20,NULL,'partner_palette','En transit'),
          (4,101,NULL,10,NULL,'partner_palette','Préparé'),
          (5,101,NULL,10,NULL,'partner_palette','Reçu'),
          (6,101,20,10,NULL,'transfer','En transit');
        ''')

    def tearDown(self):
        self.c.close()

    @staticmethod
    def scope(u, c=None):
        if u['role']=='admin': return '1=1', []
        field = {'client':'client_id','agent':'current_hub_id','support':'support_id','livreur':'driver_id'}[u['role']]
        return f'p.{field}=?', [u.get('agent_hub_id') if u['role']=='agent' else u['id']]

    def counts(self, role='agent', uid=1, hub=10):
        return sidebar_counts(self.c, dict(id=uid,role=role,agent_hub_id=hub), self.scope)

    def test_reception_decrements_not_visits(self):
        self.assertEqual(self.counts()['partner-palettes'], 2)
        self.assertEqual(self.counts()['partner-palettes'], 2)  # visiting is read-only
        self.c.execute("UPDATE ops_documents SET status='Reçu' WHERE id=1")
        self.assertEqual(self.counts()['partner-palettes'], 1)
        self.c.execute("UPDATE ops_documents SET status='Clôturé (écarts)' WHERE id=2")
        self.assertEqual(self.counts()['partner-palettes'], 0)

    def test_hub_scope_and_transfer_is_separate(self):
        self.assertEqual(self.counts(hub=20)['partner-palettes'], 1)
        self.assertEqual(self.counts()['palette-hub'], 1)
        self.assertEqual(self.counts(hub=20)['palette-hub'], 0)
        self.assertEqual(self.counts('admin')['partner-palettes'], 3)

    def test_inactive_and_missing_hub_fail_closed(self):
        self.assertEqual(self.counts(hub=30), {})
        self.assertEqual(self.counts(hub=None), {})

    def test_client_drafts_count_as_pending_not_lines(self):
        self.assertEqual(self.counts('client',101)['partner-palettes'], 3)
        self.assertEqual(self.counts('client',202)['partner-palettes'], 1)
        self.assertNotIn('palette-hub', self.counts('client',101))

    def test_support_only_own_open_orders(self):
        self.c.executescript("INSERT INTO parcels VALUES(1,101,10,7,NULL,'Créé'),(2,101,10,8,NULL,'Créé'),(3,101,10,7,NULL,'Livré')")
        self.assertEqual(self.counts('support',7), {'support-orders':1})

    def test_no_page_limit_and_finance_paid_disappears(self):
        self.c.executemany("INSERT INTO ops_documents VALUES(?,101,NULL,10,NULL,'partner_palette','En transit')", [(i,) for i in range(100,650)])
        self.assertEqual(self.counts()['partner-palettes'], 552)
        self.c.execute('INSERT INTO driver_statements VALUES(1,8,10,NULL,1000,0)')
        self.assertEqual(self.counts('livreur',8)['driver-finance'], 1)
        self.c.execute("INSERT INTO driver_transactions VALUES(1,'cash',1000,NULL)")
        self.assertEqual(self.counts('livreur',8)['driver-finance'], 0)


if __name__ == '__main__':
    unittest.main()
