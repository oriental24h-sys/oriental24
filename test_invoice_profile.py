"""Invoice formatting metadata cannot rewrite issued money or historical identities."""
import json,unittest
import test_driver_finance as f
from invoice_profile import FIELDS
system=f.system
class InvoiceProfileTests(unittest.TestCase):
    setUp=f.DriverFinanceTests.setUp
    data=f.DriverFinanceTests.data
    mutate=f.DriverFinanceTests.mutate
    new_parcel=f.DriverFinanceTests.new_parcel
    terms=f.DriverFinanceTests.terms
    closed=f.DriverFinanceTests.closed
    preview=f.DriverFinanceTests.preview
    confirm=f.DriverFinanceTests.confirm
    issue=f.DriverFinanceTests.issue
    detail=f.DriverFinanceTests.detail
    def get_profile(self):return self.admin.get('/api/driver-finance/invoice-profile').json
    def save(self,**kw):
        d=self.get_profile();d.update(kw)
        return self.mutate(self.admin,'/api/driver-finance/invoice-profile',d,'put')
    def test_profile_empty_and_scoped(self):
        p=self.get_profile();self.assertEqual(set(p),set(FIELDS)|{'revision'});self.assertTrue(all(not p[k] for k in FIELDS))
        for cl in (self.client,self.driver):
            self.assertEqual(cl.get('/api/driver-finance/invoice-profile').status_code,403)
            self.assertEqual(self.mutate(cl,'/api/driver-finance/invoice-profile',p,'put').status_code,403)
        self.assertEqual(self.admin.put('/api/driver-finance/invoice-profile',json=p).status_code,403)
    def test_profile_validation_version_and_audit(self):
        self.assertEqual(self.save(email='bad').status_code,400)
        self.assertEqual(self.save(address='x'*301).status_code,400)
        self.assertEqual(self.save(rc='bad\x00').status_code,400)
        self.assertEqual(self.save(revision=True).status_code,400)
        old=self.get_profile();self.assertEqual(self.save(legal_name='ORIENTAL24 test').status_code,200)
        self.assertEqual(self.mutate(self.admin,'/api/driver-finance/invoice-profile',old,'put').status_code,409)
        with system.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM driver_invoice_profile_audit').fetchone()[0],1)
    def test_frozen_contacts_face_cod_and_issuer(self):
        self.terms();delivered=self.closed();returned=self.closed('Retourné',amount='333.25')
        self.save(legal_name='Raison de test',ice='TEST-ONLY',payment_terms='Texte de test')
        with system.conn() as c:c.execute("UPDATE users SET driver_address='Ancienne adresse',driver_city_id=1 WHERE id=3")
        sid=self.issue(3);original=self.detail(sid);snapshot=original['print_snapshot'];self.assertEqual(snapshot['issuer']['ice'],'TEST-ONLY');self.assertEqual(snapshot['driver']['driver_address'],'Ancienne adresse')
        meta=next(p for p in snapshot['parcels'] if p['parcel_id']==returned['id']);self.assertEqual(meta['amount'],'333.25');self.assertEqual(meta['phone'],'0600000000')
        self.assertEqual(next(p for p in original['lines'] if p['parcel_id']==returned['id'])['cod_cents'],0)
        self.save(legal_name='Nouvelle raison',ice='NEW')
        with system.conn() as c:
            c.execute("UPDATE users SET phone='0611111111',driver_address='Nouvelle adresse' WHERE id=3")
            c.execute("UPDATE parcels SET phone='0622222222' WHERE id=?",(returned['id'],))
        after=self.detail(sid);self.assertEqual(snapshot,after['print_snapshot']);self.assertEqual(original['statement'],after['statement']);self.assertEqual(original['lines'],after['lines'])
        self.assertEqual(self.driver.get(f'/api/driver-finance/statements/{sid}').json['print_snapshot'],snapshot)
        self.assertEqual(self.client.get(f'/api/driver-finance/statements/{sid}').status_code,403)
        self.assertNotIn('print_snapshot',self.admin.get('/api/driver-finance').json['statements'][0])
    def test_profile_or_phone_change_invalidates_preview(self):
        self.terms();p=self.closed();draft=self.preview().json;self.save(city='Oujda')
        self.assertEqual(self.confirm(draft['token']).status_code,409)
        draft=self.preview().json
        with system.conn() as c:c.execute("UPDATE parcels SET phone='0611111111' WHERE id=?",(p['id'],))
        self.assertEqual(self.confirm(draft['token']).status_code,409)
        with system.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM driver_statements').fetchone()[0],0)
    def test_legacy_no_backfill(self):
        self.terms();self.closed();sid=self.issue()
        with system.conn() as c:c.execute('UPDATE driver_statements SET print_snapshot=NULL WHERE id=?',(sid,))
        self.save(legal_name='Future only');d=self.detail(sid);self.assertIsNone(d['print_snapshot']);self.assertEqual(d['statement']['cod_cents'],10000)
    def test_same_token_replay_after_profile_change(self):
        self.terms();self.closed();draft=self.preview().json;a=self.confirm(draft['token']);self.save(city='Autre ville');b=self.confirm(draft['token']);self.assertEqual(a.json['statement_id'],b.json['statement_id']);self.assertTrue(b.json['already_created'])
if __name__=='__main__':unittest.main()
