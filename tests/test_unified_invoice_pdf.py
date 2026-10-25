import sqlite3
import json
import unittest
from io import BytesIO
from pypdf import PdfReader
from billing_pdf import invoice_pdf
from invoice_profile import issuer_for_actor


class UnifiedInvoicePDFTests(unittest.TestCase):
    def test_long_invoice_has_all_rows_once_and_numbered_pages(self):
        lines=[dict(tracking=f'TEST-{i:05d}',city='Agadir',phone='0600000000',status='Livré',amount_cents=10000,cod_cents=10000,fees_cents=1500) for i in range(70)]
        d=dict(invoice=dict(kind='livreur',reference='DRV-TEST',name='Recipient Test',email='',state='Not Paid',parcel_count=70,created_at='2026-10-25',cod_cents=700000,fees_cents=105000,net_cents=595000,incoming_cents=700000,outgoing_cents=105000),record=dict(mode='gross',retained_cents=0),issuer=dict(legal_name='Hub Test',ice='TEST-ICE'),recipient={},transactions=[],lines=lines)
        doc=PdfReader(BytesIO(invoice_pdf(d)));text='\n'.join(p.extract_text() for p in doc.pages)
        self.assertGreater(len(doc.pages),1)
        self.assertIn('TEST-00000',doc.pages[0].extract_text())
        for row in lines:self.assertEqual(text.count(row['tracking']),1)
        for i,p in enumerate(doc.pages,1):
            self.assertIn(f'Page : {i} / {len(doc.pages)}',p.extract_text())
            self.assertIn('TEST-ICE',p.extract_text())
        self.assertNotIn('Olivraison',text)

    def test_hub_issuer_never_inherits_company_fiscal_identity(self):
        c=sqlite3.connect(':memory:');c.row_factory=sqlite3.Row
        c.executescript('CREATE TABLE settings(key,value);CREATE TABLE cities(id,name);CREATE TABLE ops_hubs(id,name,address,city_id);INSERT INTO cities VALUES(1,"Agadir");INSERT INTO ops_hubs VALUES(10,"Hub Test","Adresse du Hub",1);')
        c.execute('INSERT INTO settings VALUES(?,?)',('driver_invoice_profile',json.dumps(dict(legal_name='ORIENTAL24',ice='COMPANY-ICE',rc='COMPANY-RC'))))
        hub=issuer_for_actor(c,dict(role='agent',agent_hub_id=10))
        self.assertEqual(hub['legal_name'],'Hub Test');self.assertEqual(hub['city'],'Agadir')
        self.assertNotIn('ice',hub);self.assertNotIn('rc',hub)
        self.assertEqual(issuer_for_actor(c,dict(role='admin'))['ice'],'COMPANY-ICE')
        c.close()
