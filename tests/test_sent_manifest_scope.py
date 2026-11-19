import sqlite3
import unittest
from hub_access import hub_read_parcel_scope, hub_tracking_parcel_scope, hub_transfer_manifest_lines


class SentManifestScopeTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:')
        self.c.executescript('''
            CREATE TABLE ops_hubs(id INTEGER PRIMARY KEY,active INTEGER);
            CREATE TABLE parcels(id INTEGER PRIMARY KEY,current_hub_id INTEGER,driver_id INTEGER,status TEXT);
            CREATE TABLE ops_assignments(id INTEGER PRIMARY KEY,parcel_id INTEGER,new_driver_id INTEGER,hub_id INTEGER);
            CREATE TABLE ops_documents(id INTEGER PRIMARY KEY,kind TEXT,source_hub_id INTEGER,destination_hub_id INTEGER,status TEXT,departure_scan_required INTEGER,dispatched_at TEXT);
            CREATE TABLE ops_document_lines(id INTEGER PRIMARY KEY,parcel_id INTEGER,document_id INTEGER,departure_scanned_at TEXT,departure_reconciled_at TEXT);
            INSERT INTO ops_hubs VALUES(10,1),(20,1),(30,1);
            INSERT INTO parcels VALUES(1,NULL,NULL,'Transit'),(2,20,NULL,'Réceptionné'),(3,NULL,NULL,'Transit'),(4,NULL,NULL,'Transit'),(5,NULL,NULL,'Transit'),(6,30,NULL,'Livré');
            INSERT INTO ops_documents VALUES(1,'transfer',10,20,'En transit',1,'sent'),(2,'transfer',10,20,'En transit',0,'legacy'),(3,'transfer',10,20,'Annulé',1,NULL),(4,'transfer',10,20,'Départ partiel',1,NULL);
            INSERT INTO ops_document_lines VALUES(1,1,1,'sent',NULL),(2,2,1,'sent',NULL),(3,3,3,NULL,NULL),(4,4,4,NULL,'reconciled'),(5,5,4,NULL,NULL),(6,6,2,NULL,NULL);
        ''')

    def tearDown(self):self.c.close()

    def ids(self,hub=10,read=True):
        where,args=(hub_read_parcel_scope if read else hub_tracking_parcel_scope)(self.c,'p',hub)
        return {r[0] for r in self.c.execute('SELECT p.id FROM parcels p WHERE '+where,args)}

    def test_a_departed_parcel_belongs_to_its_destination_not_to_the_sender(self):
        # Règle métier : chaque Hub ne voit que les CMD comptées sur lui.
        # 10 a tout expédié -> plus rien ; 20 reçoit le colis 1 en route ; 30 garde le sien.
        self.assertEqual(self.ids(10),set())
        self.assertEqual(self.ids(20),{1,2})
        self.assertEqual(self.ids(30),{6})
        # La lecture large ne change jamais la garde physique (mutations).
        self.assertEqual(self.ids(20,read=False),{2})

    def test_invalid_or_inactive_hub_is_fail_closed(self):
        for hub in (None,True,0,'10',999):self.assertEqual(self.ids(hub),set())
        self.c.execute('UPDATE ops_hubs SET active=0 WHERE id=20')
        self.assertEqual(self.ids(20),set())

    def test_cancellation_reconciliation_and_unscanned_departures_never_reach_a_hub(self):
        # Un départ annulé, réconcilié ou jamais scanné n'attribue la CMD à personne.
        self.assertEqual(self.ids(20),{1,2})
        self.c.execute("UPDATE ops_document_lines SET departure_scanned_at=NULL WHERE parcel_id=1")
        self.assertEqual(self.ids(20),{2})

    def test_manifest_participants_keep_sent_lines_not_other_hub_inventory(self):
        doc=dict(kind='transfer',source_hub_id=10,destination_hub_id=20,departure_scan_required=1,dispatched_at='sent')
        lines=[dict(id=1,current_hub_id=10),dict(id=2,current_hub_id=None,departure_scanned_at='sent'),dict(id=3,current_hub_id=30,received_at='received'),dict(id=4,current_hub_id=10,departure_reconciled_at='reconciled')]
        self.assertEqual(hub_transfer_manifest_lines(lines,doc,10),lines)
        self.assertEqual([l['id'] for l in hub_transfer_manifest_lines(lines,doc,20)],[2,3])
        for hub in (None,True,30):self.assertEqual(hub_transfer_manifest_lines(lines,doc,hub),[])
        legacy={**doc,'departure_scan_required':0}
        self.assertEqual([l['id'] for l in hub_transfer_manifest_lines(lines,legacy,20)],[1,2,3])


if __name__=='__main__':unittest.main()
