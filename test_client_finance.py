import unittest,secrets
from datetime import datetime
from zoneinfo import ZoneInfo
import test_app as f
import test_driver_finance as df
class ClientFinanceTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    parallel=df.DriverFinanceTests.parallel
    def invoice(self,total=100):
        with f.system.conn() as c:
            return c.execute('INSERT INTO invoices(client_id,cod,fees,total,created_at) VALUES(2,?,?,?,?)',(max(total,0),abs(min(total,0)),total,f.system.now())).lastrowid
    def read(self,iid):return self.admin.get('/api/invoices/'+str(iid)).json
    def d(self,amount=40):return dict(amount=amount,method='Virement',reference='TEST-'+secrets.token_hex(4),payment_date=datetime.now(ZoneInfo('Africa/Casablanca')).date().isoformat(),request_key=secrets.token_hex(16))
    def pay(self,iid,d):return self.mutate(self.admin,f'/api/client-finance/invoices/{iid}/receipts',d)
    def test_partial_total_and_immutable_cents(self):
        iid=self.invoice(100.01);self.assertEqual(self.pay(iid,self.d('40.01')).status_code,200)
        i=self.read(iid)['invoice'];self.assertEqual((i['paid_cents'],i['remaining_cents'],i['status']),(4001,6000,'Partiellement réglée'))
        self.assertEqual(self.pay(iid,self.d(60)).status_code,200);self.assertEqual(self.read(iid)['invoice']['status'],'Réglée')
        self.assertEqual(self.pay(iid,self.d(1)).status_code,409)
    def test_receipt_replay_payload_mismatch_and_precision(self):
        iid=self.invoice();d=self.d();a=self.pay(iid,d);b=self.pay(iid,d);self.assertEqual(a.json['id'],b.json['id']);self.assertTrue(b.json['already_recorded'])
        d['amount']=41;self.assertEqual(self.pay(iid,d).status_code,409)
        for amt in ['NaN','Infinity','0','-1','1.001']:self.assertEqual(self.pay(iid,self.d(amt)).status_code,400)
    def test_negative_invoice_direction(self):
        iid=self.invoice(-75);self.pay(iid,self.d(25));i=self.read(iid)['invoice'];self.assertEqual(i['direction'],'Dû par le client');self.assertEqual(i['remaining_cents'],5000)
    def test_zero_closure_no_fake_cash(self):
        iid=self.invoice(0);self.mutate(self.admin,'/api/invoices/'+str(iid),{},'patch');d=self.read(iid)
        self.assertEqual(d['invoice']['status'],'Réglée');self.assertEqual(d['receipts'],[]);self.assertEqual(d['payment_audit'][0]['action'],'clôture sans flux')
    def test_legacy_settlement_after_partial_idempotent(self):
        iid=self.invoice();self.pay(iid,self.d(40));self.mutate(self.admin,'/api/invoices/'+str(iid),{},'patch');self.mutate(self.admin,'/api/invoices/'+str(iid),{},'patch')
        d=self.read(iid);self.assertEqual(d['invoice']['paid_cents'],10000);self.assertEqual(len(d['receipts']),2)
    def test_void_reopens_balance_and_preserves_audit(self):
        iid=self.invoice();r=self.pay(iid,self.d(100));rid=r.json['id'];url=f'/api/client-finance/receipts/{rid}/void'
        self.assertEqual(self.mutate(self.admin,url,dict(reason='Erreur de saisie')).status_code,200)
        self.assertTrue(self.mutate(self.admin,url,dict(reason='Erreur de saisie')).json['already_voided'])
        d=self.read(iid);self.assertEqual(d['invoice']['remaining_cents'],10000);self.assertEqual(d['receipts'][0]['amount_cents'],10000);self.assertTrue(d['receipts'][0]['voided_at']);self.assertEqual(len(d['payment_audit']),2)
    def test_parallel_payments_no_overpay(self):
        iid=self.invoice();url=f'/api/client-finance/invoices/{iid}/receipts';rs=self.parallel([('post',url,self.d(70)),('post',url,self.d(70))]);self.assertEqual(sorted(r.status_code for r in rs),[200,409]);self.assertEqual(self.read(iid)['invoice']['paid_cents'],7000)
    def test_roles_and_effective_date(self):
        iid=self.invoice();url=f'/api/client-finance/invoices/{iid}/receipts'
        for cl in [self.client,self.driver]:self.assertEqual(self.mutate(cl,url,self.d()).status_code,403)
        self.assertEqual(self.client.get('/api/invoices/'+str(iid)).status_code,200)
        d=self.d();d['payment_date']='2099-01-01';self.assertEqual(self.pay(iid,d).status_code,400)
    def test_historical_paid_not_claimed_verified(self):
        iid=self.invoice()
        with f.system.conn() as c:c.execute("UPDATE invoices SET status='Réglée',paid_at=NULL WHERE id=?",(iid,))
        d=self.read(iid);self.assertEqual(d['invoice']['paid_cents'],10000);self.assertEqual(d['receipts'][0]['method'],'Historique importé');self.assertIsNone(d['receipts'][0]['payment_date'])

    def test_duplicate_active_reference_blocked_even_with_new_request_key(self):
        iid=self.invoice();d=self.d(20);self.assertEqual(self.pay(iid,d).status_code,200)
        d['request_key']=secrets.token_hex(16);self.assertEqual(self.pay(iid,d).status_code,409)
        self.assertEqual(self.read(iid)['invoice']['paid_cents'],2000)

if __name__=='__main__':unittest.main()
