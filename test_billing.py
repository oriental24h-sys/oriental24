"""Unified billing acceptance: real ledger payments, driver-only visibility, scoped files."""
import unittest,secrets,csv,io
from datetime import datetime
from zoneinfo import ZoneInfo
from pypdf import PdfReader
import test_driver_finance as f
S=f.system
class BillingTests(unittest.TestCase):
    def setUp(self):
        f.DriverFinanceTests.setUp(self)
        with S.conn() as c:c.execute("UPDATE parcels SET status='Créé'")
    data=f.DriverFinanceTests.data
    mutate=f.DriverFinanceTests.mutate
    new_parcel=f.DriverFinanceTests.new_parcel
    terms=f.DriverFinanceTests.terms
    closed=f.DriverFinanceTests.closed
    preview=f.DriverFinanceTests.preview
    confirm=f.DriverFinanceTests.confirm
    issue=f.DriverFinanceTests.issue
    pay=f.DriverFinanceTests.pay
    parallel=f.DriverFinanceTests.parallel
    def row(self,kind,iid,cl=None):return (cl or self.admin).get(f'/api/billing/{kind}/{iid}').json['invoice']
    def body(self,kind,iid,action='settle',**kw):
        d=dict(version=self.row(kind,iid)['version'],request_key=secrets.token_hex(16),confirmed=True)
        if action=='settle':d.update(method='Espèces',reference='TEST-'+secrets.token_hex(6),payment_date=datetime.now(ZoneInfo('Africa/Casablanca')).date().isoformat())
        else:d['reason']='Correction de saisie de test'
        d.update(kw);return d
    def action(self,kind,iid,action='settle',data=None,cl=None):return self.mutate(cl or self.admin,f'/api/billing/{kind}/{iid}/{action}',data or self.body(kind,iid,action))
    def ci(self):
        r=self.mutate(self.admin,'/api/invoices',{'client_id':2});self.assertEqual(r.status_code,200,r.json)
        return self.admin.get('/api/invoices').json[0]['id']
    def ids(self,cl):return {p['id'] for p in self.data(cl)['parcels']}
    def test_new_invoices_both_ledgers_appear(self):
        self.terms();p=self.closed();cid=self.ci();sid=self.issue()
        for kind,iid in [('client',cid),('livreur',sid)]:
            result=self.admin.get('/api/billing?kind='+kind).json;self.assertIn(iid,[r['id'] for r in result['rows']]);self.assertEqual(self.row(kind,iid)['state'],'Not Paid')
        self.assertIn(p['id'],self.ids(self.driver))
    def test_paid_hides_driver_parcels_not_client_and_keeps_archives(self):
        self.terms();p=self.closed();cid=self.ci();sid=self.issue();self.assertEqual(self.action('livreur',sid).status_code,200)
        self.assertNotIn(p['id'],self.ids(self.driver));self.assertIn(p['id'],self.ids(self.client));self.assertIn(p['id'],self.ids(self.admin))
        self.assertEqual(self.driver.get('/api/parcels/'+str(p['id'])).status_code,404)
        self.assertEqual(self.driver.get('/api/billing/livreur/'+str(sid)).status_code,200)
        self.assertEqual(self.driver.get('/api/billing?kind=livreur&archive=paid').json['rows'][0]['state'],'Paid')
        self.assertEqual(self.driver.get('/api/billing?kind=livreur&archive=current').json['count'],0)
        self.assertEqual(self.row('client',cid)['state'],'Not Paid')
        self.assertEqual(self.action('client',cid).status_code,200);self.assertEqual(self.row('client',cid,self.client)['state'],'Paid');self.assertIn(p['id'],self.ids(self.client))
        with S.conn() as c:
            row=dict(c.execute('SELECT * FROM parcels WHERE id=?',(p['id'],)).fetchone());self.assertEqual(row['driver_id'],3);self.assertEqual(row['status'],'Livré');self.assertEqual(row['invoice_id'],cid)
    def test_reopen_audited_no_delete_and_visibility_restored(self):
        self.terms();p=self.closed();sid=self.issue();self.action('livreur',sid);r=self.action('livreur',sid,'reopen');self.assertEqual(r.status_code,200);self.assertEqual(r.json['invoice']['state'],'Not Paid');self.assertIn(p['id'],self.ids(self.driver))
        with S.conn() as c:
            t=c.execute('SELECT * FROM driver_transactions WHERE statement_id=?',(sid,)).fetchall();self.assertEqual(len(t),1);self.assertTrue(t[0]['voided_at']);self.assertEqual(c.execute('SELECT active FROM driver_statement_lines WHERE statement_id=?',(sid,)).fetchone()[0],1)
    def test_partial_does_not_hide_and_legacy_full_payment_does(self):
        self.terms();p=self.closed();sid=self.issue();self.pay(sid,'10.00');self.assertEqual(self.row('livreur',sid)['state'],'Partiel');self.assertIn(p['id'],self.ids(self.driver));self.pay(sid,'79.75');self.assertEqual(self.row('livreur',sid)['state'],'Paid');self.assertNotIn(p['id'],self.ids(self.driver))
    def test_gross_two_flows_atomic_and_partial_requires_commission(self):
        self.terms(mode='gross');p=self.closed();sid=self.issue();self.pay(sid,'100.00');self.assertEqual(self.row('livreur',sid)['state'],'Partiel');self.assertIn(p['id'],self.ids(self.driver));self.action('livreur',sid);self.assertEqual(self.row('livreur',sid)['state'],'Paid');self.assertNotIn(p['id'],self.ids(self.driver));self.action('livreur',sid,'reopen');self.assertIn(p['id'],self.ids(self.driver))
    def test_second_flow_error_rolls_back_first(self):
        self.terms(mode='gross');self.closed();sid=self.issue();self.pay(sid,'0.25',kind='commission',reference='DUPLICATE');version=self.row('livreur',sid)['version'];res=self.action('livreur',sid,data=self.body('livreur',sid,reference='DUPLICATE'));self.assertEqual(res.status_code,409)
        self.assertEqual(self.row('livreur',sid)['version'],version)
        with S.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM driver_transactions WHERE statement_id=?',(sid,)).fetchone()[0],1);self.assertEqual(c.execute('SELECT count(*) FROM billing_action_keys').fetchone()[0],0)
    def test_stale_and_idempotent_retries_after_reversal(self):
        self.terms();self.closed();sid=self.issue();old=self.body('livreur',sid);self.pay(sid,'1.00');self.assertEqual(self.action('livreur',sid,data=old).status_code,409)
        d=self.body('livreur',sid);a=self.action('livreur',sid,data=d);b=self.action('livreur',sid,data=d);self.assertEqual(a.status_code,200);self.assertTrue(b.json['already_recorded']);self.action('livreur',sid,'reopen');again=self.action('livreur',sid,data=d);self.assertTrue(again.json['already_recorded']);self.assertEqual(again.json['invoice']['state'],'Not Paid')
    def test_concurrent_settles_one_ledger_write(self):
        self.terms();self.closed();sid=self.issue();url=f'/api/billing/livreur/{sid}/settle';d=self.body('livreur',sid);rs=self.parallel([('post',url,d),('post',url,d)]);self.assertEqual([r.status_code for r in rs],[200,200]);self.assertEqual(sum(r.json['already_recorded'] for r in rs),1)
        with S.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM driver_transactions WHERE statement_id=?',(sid,)).fetchone()[0],1)
    def test_scope_and_csrf(self):
        self.terms();self.closed();sid=self.issue();cid=self.ci();self.terms(5);self.closed(did=5);other=self.issue(5)
        for cl in [self.driver,self.client]:self.assertEqual(self.action('livreur',sid,cl=cl).status_code,403)
        self.assertEqual(self.client.get('/api/billing?kind=livreur').status_code,403);self.assertEqual(self.driver.get('/api/billing?kind=client').status_code,403)
        for fmt in ['pdf','csv']:
            self.assertEqual(self.driver.get(f'/api/billing/livreur/{other}/{fmt}').status_code,404);self.assertEqual(self.client.get(f'/api/billing/livreur/{sid}/{fmt}').status_code,403);self.assertEqual(self.driver.get(f'/api/billing/client/{cid}/{fmt}').status_code,403)
        self.assertEqual(self.admin.post(f'/api/billing/livreur/{sid}/settle',json=self.body('livreur',sid)).status_code,403)
    def test_paid_csv_and_real_pdf_for_both_roles(self):
        self.terms();p=self.closed();cid=self.ci();sid=self.issue();self.action('livreur',sid);self.action('client',cid)
        for kind,iid,cl in [('livreur',sid,self.driver),('client',cid,self.client)]:
            csvres=cl.get(f'/api/billing/{kind}/{iid}/csv');self.assertEqual(csvres.status_code,200);rows=list(csv.reader(io.StringIO(csvres.data.decode('utf-8-sig')),delimiter=';'));self.assertEqual(rows[1][3],'Paid');self.assertEqual(rows[1][5],p['tracking']);self.assertIn('attachment',csvres.headers['Content-Disposition'])
            pdf=cl.get(f'/api/billing/{kind}/{iid}/pdf');self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'));r=PdfReader(io.BytesIO(pdf.data));text='\n'.join(p.extract_text() for p in r.pages);self.assertIn('Paid',text);self.assertIn(p['tracking'],text);self.assertIn('Page : 1 /',text);self.assertIn('non assimilable',text);self.assertAlmostEqual(float(r.pages[0].mediabox.width),595.2756,places=2)
    def test_negative_and_zero_client_totals(self):
        self.closed('Refusé');cid=self.ci();r=self.row('client',cid);self.assertLess(r['net_cents'],0);self.assertGreater(r['incoming_cents'],0);self.assertEqual(r['outgoing_cents'],0);self.assertEqual(self.action('client',cid).json['invoice']['state'],'Paid');self.assertEqual(self.action('client',cid,'reopen').json['invoice']['state'],'Not Paid')
        self.closed(amount='25.00');cid=self.ci();self.assertEqual(self.row('client',cid)['net_cents'],0);self.assertEqual(self.action('client',cid).json['invoice']['state'],'Paid')
        with S.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM client_receipts WHERE invoice_id=?',(cid,)).fetchone()[0],0)
    def test_filters_export_and_validation(self):
        self.terms();self.closed();sid=self.issue();self.action('livreur',sid);r=self.admin.get('/api/billing?kind=livreur&state=Not+Paid').json;self.assertEqual(r['count'],0);r=self.admin.get('/api/billing?kind=livreur&state=Paid&q=DRV-000001').json;self.assertEqual(r['count'],1)
        self.assertEqual(self.admin.get('/api/billing?from=2026-99-00T20:00').status_code,400);self.assertEqual(self.admin.get('/api/billing?size=-2').status_code,400)
        self.assertEqual(self.admin.get('/api/billing/export?kind=livreur&state=Paid').status_code,200)
        self.action('livreur',sid,'reopen')
        for kw in [dict(confirmed=False),dict(payment_date='2099-01-01'),dict(method='Bank automation'),dict(extra='bad')]:self.assertEqual(self.action('livreur',sid,data=self.body('livreur',sid,**kw)).status_code,400)
    def test_closed_recovered_remains_out_of_scope_on_reopen(self):
        self.terms();p=self.closed('Refusé');raw=self.admin.get('/api/parcels/'+str(p['id'])).json['parcel'];self.mutate(self.admin,'/api/drivers-workspace/3/scan',dict(parcel_id=p['id'],revision=raw['ops_revision'],mode='receive',request_key=secrets.token_hex(16),hub_id=None,confirmed=True));sid=self.issue();self.action('livreur',sid);self.action('livreur',sid,'reopen');self.assertNotIn(p['id'],self.ids(self.driver));self.assertIn(p['id'],self.ids(self.client))
    def test_export_safe_strings_and_numeric_negative(self):
        p=self.closed('Refusé');cid=self.ci()
        with S.conn() as c:c.execute("UPDATE users SET company='=BAD(1)' WHERE id=2")
        rows=list(csv.reader(io.StringIO(self.client.get(f'/api/billing/client/{cid}/csv').data.decode('utf-8-sig')),delimiter=';'));self.assertTrue(rows[1][2].startswith("'="));self.assertLess(float(rows[1][-1]),0)
    def test_background_refresh_does_not_extend_idle_session(self):
        import time
        past=int(time.time())-120
        with S.conn() as c:c.execute('UPDATE auth_sessions SET last_seen=? WHERE user_id=1 AND revoked_at IS NULL',(past,))
        self.assertEqual(self.admin.get('/api/billing',headers={'X-Background-Poll':'1'}).status_code,200)
        with S.conn() as c:self.assertEqual(c.execute('SELECT last_seen FROM auth_sessions WHERE user_id=1 AND revoked_at IS NULL').fetchone()[0],past)
        self.assertEqual(self.admin.get('/api/billing').status_code,200)
        with S.conn() as c:
            self.assertGreater(c.execute('SELECT last_seen FROM auth_sessions WHERE user_id=1 AND revoked_at IS NULL').fetchone()[0],past)
            c.execute('UPDATE auth_sessions SET last_seen=? WHERE user_id=1 AND revoked_at IS NULL',(int(time.time())-S.app.config['AUTH_IDLE_SECONDS']-1,))
        self.assertEqual(self.admin.get('/api/billing',headers={'X-Background-Poll':'1'}).status_code,401)
if __name__=='__main__':unittest.main()
