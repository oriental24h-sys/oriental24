"""Driver finance API tests, isolated from the live database. Tariffs are test fixtures only."""
import unittest, secrets, csv, io
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
import test_app as fixtures
system=fixtures.system
BASE='/api/driver-finance'

class DriverFinanceTests(unittest.TestCase):
    data=fixtures.PlatformTests.data
    mutate=fixtures.PlatformTests.mutate
    new_parcel=fixtures.PlatformTests.new_parcel
    def setUp(self):
        fixtures.PlatformTests.setUp(self)
        with system.conn() as c:c.execute('UPDATE parcels SET driver_id=NULL')
    def terms(self,did=3,**kw):
        d=dict(revision=0,mode='net',delivered='10.25',returned='4.50',refused='2.00',overrides=[]);d.update(kw)
        return self.mutate(self.admin,BASE+'/terms/'+str(did),d,'put')
    def closed(self,status='Livré',amount='100.00',did=3,city=1):
        p=self.new_parcel(amount=amount,city_id=city)
        r=self.mutate(self.admin,'/api/parcels/'+str(p['id']),dict(driver_id=did,status=status),'patch')
        self.assertEqual(r.status_code,200,r.json);return p
    def preview(self,did=3,**kw):return self.mutate(self.admin,BASE+'/preview',dict(driver_id=did,**kw))
    def confirm(self,token):return self.mutate(self.admin,BASE+'/preview/'+token+'/confirm',{})
    def issue(self,did=3):
        p=self.preview(did);self.assertEqual(p.status_code,200,p.json)
        r=self.confirm(p.json['token']);self.assertEqual(r.status_code,200,r.json);return r.json['statement_id']
    def detail(self,sid):return self.admin.get(BASE+'/statements/'+str(sid)).json
    def pay(self,sid,amount='1.00',kind='cash',**kw):
        d=dict(kind=kind,amount=amount,method='Espèces',reference=secrets.token_hex(8),paid_on=datetime.now(ZoneInfo('Africa/Casablanca')).date().isoformat(),request_key=secrets.token_hex(16));d.update(kw)
        return self.mutate(self.admin,BASE+f'/statements/{sid}/transactions',d)
    def parallel(self,tasks):
        clients=[system.app.test_client() for _ in tasks]
        headers=[]
        for cl in clients:
            cl.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'})
            headers.append({'X-CSRF-Token':self.data(cl)['csrf']})
        def run(item):
            i,(method,url,data)=item
            return getattr(clients[i],method)(url,json=data,headers=headers[i])
        with ThreadPoolExecutor(max_workers=len(tasks)) as pool:return list(pool.map(run,enumerate(tasks)))
    def test_explicit_setup_and_validation(self):
        self.closed();self.assertEqual(self.preview().status_code,409)
        self.assertTrue(all(d['terms'] is None for d in self.admin.get(BASE+'/terms').json))
        for value in [-1,'NaN','Infinity',True,None,'1.001','10000.01']:
            self.assertEqual(self.terms(delivered=value).status_code,400,str(value))
        self.assertEqual(self.terms(revision=True).status_code,400)
        self.assertEqual(self.terms(mode='unknown').status_code,400)
        self.assertEqual(self.terms(delivered='0',returned='0',refused='0').status_code,200)
        self.assertEqual(self.preview().json['commission_cents'],0)
    def test_overrides_precision_and_status_accounting(self):
        self.closed(amount='100.10');self.closed('Retourné',amount='999.99',city=2);self.closed('Refusé',city=2)
        self.terms(overrides=[dict(city_id=1,delivered='12,35',returned='6',refused='3')])
        p=self.preview().json
        self.assertEqual((p['cod_cents'],p['commission_cents'],p['cash_due_cents'],p['commission_due_cents']),(10010,1885,8125,0))
        self.assertEqual([r['rate_source'] for r in p['lines']],['Ville','Défaut livreur','Défaut livreur'])
        sid=self.issue();self.assertEqual(self.detail(sid)['statement']['commission_cents'],1885)
    def test_invalid_overrides_are_atomic(self):
        row=dict(city_id=1,delivered=1,returned=1,refused=1)
        for rates in [[row,row],[dict(row,city_id=999)],[dict(row,returned='bad')],['bad'],{}]:
            self.assertEqual(self.terms(overrides=rates).status_code,400)
        self.assertIsNone(self.admin.get(BASE+'/terms').json[0]['terms'])
    def test_revision_and_immutable_issued_terms(self):
        self.closed();self.terms();sid=self.issue()
        self.assertEqual(self.terms().status_code,409)
        self.assertEqual(self.terms(revision=1,delivered=30).status_code,200)
        self.assertEqual(self.detail(sid)['statement']['commission_cents'],1025)
        log=self.admin.get(BASE+'/terms/3/history').json
        self.assertEqual(len(log),2);self.assertEqual(log[0]['details']['before']['delivered_cents'],1025)
        self.closed();self.assertEqual(self.preview().json['commission_cents'],3000)
    def test_preview_stale_expired_and_replay(self):
        p=self.closed();self.terms();draft=self.preview().json
        self.terms(revision=1,delivered=20)
        self.assertEqual(self.confirm(draft['token']).status_code,409)
        draft=self.preview().json
        with system.conn() as c:c.execute('UPDATE driver_statement_previews SET created_at=? WHERE id=?',('2000-01-01T00:00:00',draft['token']))
        self.assertEqual(self.confirm(draft['token']).status_code,409)
        token=self.preview().json['token'];a=self.confirm(token);b=self.confirm(token)
        self.assertEqual(a.json['statement_id'],b.json['statement_id']);self.assertTrue(b.json['already_created'])
        self.assertEqual(len(self.detail(a.json['statement_id'])['lines']),1)
    def test_preview_changed_parcel_and_city(self):
        p=self.closed();self.terms();token=self.preview().json['token']
        self.mutate(self.admin,'/api/parcels/'+str(p['id']),{'status':'Refusé'},'patch')
        self.assertEqual(self.confirm(token).status_code,409)
        token=self.preview().json['token']
        with system.conn() as c:c.execute("UPDATE cities SET name='Ville renommée' WHERE id=1")
        self.assertEqual(self.confirm(token).status_code,409)
    def test_financial_lock_and_independent_client_invoice(self):
        p=self.closed();self.terms();sid=self.issue();url='/api/parcels/'+str(p['id'])
        for data in [dict(status='Créé'),dict(driver_id=5),dict(status='Refusé',note='Correction')]:
            self.assertEqual(self.mutate(self.admin,url,data,'patch').status_code,409)
        self.assertTrue(self.admin.get(url).json['parcel']['financial_locked'])
        self.assertTrue(next(x for x in self.data(self.client)['parcels'] if x['id']==p['id'])['financial_locked'])
        self.assertEqual(self.mutate(self.admin,'/api/invoices',dict(client_id=2)).status_code,200)
        self.assertEqual(self.detail(sid)['statement']['cod_cents'],10000)
        self.mutate(self.admin,BASE+f'/statements/{sid}/cancel',dict(reason='Correction test'))
        self.assertEqual(self.mutate(self.admin,url,dict(driver_id=5),'patch').status_code,400) # Still client-invoiced.
    def test_gross_partial_and_independent_balances(self):
        self.closed();self.terms(mode='gross');sid=self.issue()
        self.assertEqual(self.pay(sid,'30.10').status_code,200)
        self.assertEqual(self.pay(sid,'4.25','commission').status_code,200)
        s=self.detail(sid)['statement'];self.assertEqual((s['cash_remaining_cents'],s['commission_remaining_cents'],s['status']),(6990,600,'Partiel'))
        self.assertEqual(self.pay(sid,'69.91').status_code,409)
        self.assertEqual(self.pay(sid,'6.01','commission').status_code,409)
        self.pay(sid,'69.90');self.pay(sid,'6.00','commission')
        self.assertEqual(self.detail(sid)['statement']['status'],'Soldé')
    def test_net_commission_exceeds_cod_and_returns_only(self):
        self.closed(amount='0.10');self.terms(delivered='0.20');sid=self.issue();s=self.detail(sid)['statement']
        self.assertEqual((s['retained_cents'],s['cash_due_cents'],s['commission_due_cents']),(10,0,10))
        self.assertEqual(self.pay(sid,'0.01').status_code,409)
        self.assertEqual(self.pay(sid,'0.10','commission').status_code,200)
        self.closed('Retourné');sid=self.issue();s=self.detail(sid)['statement']
        self.assertEqual((s['cod_cents'],s['retained_cents'],s['commission_due_cents']),(0,0,450))
    def test_payment_replay_reference_and_invalid_values(self):
        self.closed();self.terms();sid=self.issue();key=secrets.token_hex(16)
        a=self.pay(sid,'1.10',reference='REC-A',request_key=key);b=self.pay(sid,'1.10',reference='REC-A',request_key=key)
        self.assertEqual(a.json['transaction_id'],b.json['transaction_id']);self.assertTrue(b.json['already_recorded'])
        self.assertEqual(self.pay(sid,'1.11',reference='REC-A',request_key=key).status_code,409)
        self.assertEqual(self.pay(sid,'1.10',reference='rec-a').status_code,409)
        for amount in [0,-1,'NaN','1.001',True,None]:self.assertEqual(self.pay(sid,amount).status_code,400)
        for kw in [dict(paid_on='2999-01-01'),dict(paid_on='2026-1-01'),dict(method='Crypto'),dict(reference=''),dict(request_key='short')]:self.assertEqual(self.pay(sid,**kw).status_code,400)
        self.assertEqual(len(self.detail(sid)['transactions']),1)
    def test_void_cancel_release_and_old_replay(self):
        p=self.closed();self.terms();token=self.preview().json['token'];sid=self.confirm(token).json['statement_id']
        tx=self.pay(sid,'10').json['transaction_id'];url=BASE+f'/statements/{sid}/cancel'
        self.assertEqual(self.mutate(self.admin,url,dict(reason='')).status_code,400)
        self.assertEqual(self.mutate(self.admin,url,dict(reason='Test')).status_code,409)
        self.assertEqual(self.mutate(self.admin,BASE+f'/transactions/{tx}/void',dict(reason='Erreur de saisie')).status_code,200)
        self.assertEqual(self.detail(sid)['statement']['cash_remaining_cents'],8975)
        self.assertEqual(self.mutate(self.admin,url,dict(reason='Correction privée')).status_code,200)
        self.assertEqual(self.detail(sid)['statement']['status'],'Annulé')
        self.assertEqual(self.admin.get(BASE).json['summary']['cod_cents'],0)
        self.assertEqual(self.confirm(token).json['statement_id'],sid)
        self.assertEqual(self.pay(sid).status_code,409)
        self.assertFalse(self.admin.get('/api/parcels/'+str(p['id'])).json['parcel']['financial_locked'])
        events=self.client.get('/api/parcels/'+str(p['id'])).json['events'];self.assertNotIn('Correction privée',str(events))
        newer=self.issue();self.assertNotEqual(newer,sid)
        self.assertEqual(len(self.detail(sid)['lines']),1)
    def test_scopes_csrf_and_no_client_commissions(self):
        self.closed();self.closed(did=5);self.terms();self.terms(5);a=self.issue();b=self.issue(5)
        self.assertEqual([x['id'] for x in self.driver.get(BASE).json['statements']],[a])
        self.assertEqual(self.driver.get(BASE+f'/statements/{b}').status_code,404)
        self.assertEqual(self.driver.get(BASE+'/terms/5/history').status_code,404)
        self.assertEqual(len(self.driver.get(BASE+'/terms').json),1)
        for url in [BASE,BASE+'/terms',BASE+'/export',BASE+f'/statements/{a}']:
            self.assertEqual(self.client.get(url).status_code,403)
            self.assertEqual(system.app.test_client().get(url).status_code,401)
        self.assertEqual(self.mutate(self.driver,BASE+'/preview',dict(driver_id=3)).status_code,403)
        self.assertEqual(self.mutate(self.driver,BASE+'/terms/3',{},'put').status_code,403)
        self.assertEqual(self.admin.post(BASE+'/preview',json=dict(driver_id=3)).status_code,403)
        export=self.driver.get(BASE+'/export').get_data(as_text=True)
        self.assertIn('Amine',export);self.assertNotIn('Youssef',export)
    def test_periods_limits_and_bad_json(self):
        self.closed();self.terms()
        for kw in [dict(period_from='oops'),dict(period_from='2026-12-01',period_to='2026-01-01'),dict(period_to='2000-01-01')]:self.assertEqual(self.preview(**kw).status_code,400)
        for did in [True,{},[],None,'invalid','3.1']:self.assertEqual(self.preview(did).status_code,400)
        for value in [[],True,'bad']:
            self.assertEqual(self.mutate(self.admin,BASE+'/preview',value).status_code,400)
        with system.conn() as c:
            c.executemany('INSERT INTO parcels(tracking,client_id,driver_id,city_id,amount,status,updated_at) VALUES(?,2,3,1,100,?,?)',[(f'LIMIT-{i}','Livré',system.now()) for i in range(500)])
        self.assertEqual(self.preview().status_code,400)
    def test_export_formula_safety(self):
        with system.conn() as c:c.execute("UPDATE users SET name='=1+1' WHERE id=3")
        self.closed();self.terms();self.issue()
        raw=self.admin.get(BASE+'/export').get_data(as_text=True)
        rows=list(csv.reader(io.StringIO(raw.lstrip('\ufeff')),delimiter=';'))
        self.assertEqual(rows[1][1],"'=1+1");self.assertEqual(rows[1][3],'100.00')
    def test_parallel_confirm_is_exactly_once(self):
        self.closed();self.terms();token=self.preview().json['token'];task=('post',BASE+f'/preview/{token}/confirm',{})
        rows=self.parallel([task,task]);self.assertEqual([r.status_code for r in rows],[200,200])
        self.assertEqual(rows[0].json['statement_id'],rows[1].json['statement_id'])
        with system.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM driver_statement_lines WHERE active=1').fetchone()[0],1)
    def test_parallel_payment_cannot_overpay(self):
        self.closed();self.terms(mode='gross');sid=self.issue()
        tasks=[('post',BASE+f'/statements/{sid}/transactions',dict(kind='cash',amount=70,method='Espèces',reference='R-'+str(i),paid_on='2020-01-01',request_key=secrets.token_hex(16))) for i in range(2)]
        rows=self.parallel(tasks);self.assertEqual(sorted(r.status_code for r in rows),[200,409])
        self.assertEqual(self.detail(sid)['statement']['cash_remaining_cents'],3000)
    def test_parallel_reassignment_and_issue_never_change_a_locked_parcel(self):
        p=self.closed();self.terms();token=self.preview().json['token']
        rows=self.parallel([('post',BASE+f'/preview/{token}/confirm',{}),('patch','/api/parcels/'+str(p['id']),dict(driver_id=5))])
        self.assertEqual(sum(r.status_code==200 for r in rows),1)
        with system.conn() as c:
            line=c.execute('SELECT * FROM driver_statement_lines WHERE parcel_id=? AND active=1',(p['id'],)).fetchone()
            driver=c.execute('SELECT driver_id FROM parcels WHERE id=?',(p['id'],)).fetchone()[0]
            self.assertEqual(driver,3 if line else 5)

if __name__=='__main__':unittest.main()
