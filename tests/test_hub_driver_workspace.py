"""Real HTTP regression tests on an isolated demo database, never a live DB."""
import importlib
import os
import tempfile
import unittest
import uuid


class HubDriverWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.env = {k: os.environ.get(k) for k in ('DB_PATH', 'ORIENTAL24_MODE')}
        os.environ['DB_PATH'] = cls.tmp.name + '/test.sqlite'
        os.environ['ORIENTAL24_MODE'] = 'demo'
        cls.m = importlib.import_module('app')
        cls.m.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        for k,v in cls.env.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v
        cls.tmp.cleanup()

    def setUp(self):
        from werkzeug.security import generate_password_hash
        m = self.m
        unique = uuid.uuid4().hex
        with m.conn() as c:
            city = c.execute('SELECT id FROM cities LIMIT 1').fetchone()[0]
            self.city = city
            self.hub = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)", ('Local '+unique,city,m.now())).lastrowid
            self.foreign = c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES(?,?,'',?)", ('Other '+unique,city,m.now())).lastrowid
            self.email = unique+'@example.test'
            self.manager = c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,'hub_manager',?,?)",('Manager',self.email,generate_password_hash('TestPassword!123'),self.hub,m.now())).lastrowid
            self.driver = c.execute("INSERT INTO users(name,email,password,role,driver_hub_id,created_at) VALUES(?,?,'unused','livreur',?,?)",('Local Driver','driver'+self.email,self.hub,m.now())).lastrowid
            self.other_driver = c.execute("INSERT INTO users(name,email,password,role,driver_hub_id,created_at) VALUES(?,?,'unused','livreur',?,?)",('Foreign Driver','other'+self.email,self.foreign,m.now())).lastrowid
            self.client_id=c.execute("SELECT id FROM users WHERE role='client' LIMIT 1").fetchone()[0]
            c.execute("INSERT INTO driver_terms VALUES(?,'gross',1500,500,500,1,1,?)",(self.driver,m.now()))
        self.client=m.app.test_client()
        r=self.client.post('/api/login',json={'email':self.email,'password':'TestPassword!123'})
        self.assertEqual(r.status_code,200,r.json)
        r=self.client.get('/api/bootstrap')
        self.assertEqual(r.status_code,200,r.json)
        self.headers={'X-CSRF-Token':r.json['csrf']}

    def test_read_notification_retention_and_first_read_timestamp(self):
        from datetime import datetime, timedelta
        old = (datetime.fromisoformat(self.m.now()) - timedelta(hours=3)).isoformat(timespec='seconds')
        recent = (datetime.fromisoformat(self.m.now()) - timedelta(minutes=30)).isoformat(timespec='seconds')
        with self.m.conn() as c:
            def add(read_at, owner=None):
                return c.execute("INSERT INTO ops_notifications(user_id,title,body,created_at,read_at) VALUES(?,'Test','',?,?)", (owner or self.manager, old, read_at)).lastrowid
            expired, fresh, unread, foreign = add(old), add(recent), add(None), add(None, self.other_driver)
        response = self.client.get('/api/logistics/notifications')
        self.assertEqual(response.status_code, 200)
        ids = {n['id'] for n in response.json['items']}
        self.assertNotIn(expired, ids)
        self.assertIn(fresh, ids)
        self.assertIn(unread, ids)
        self.assertNotIn(foreign, ids)
        r = self.client.patch('/api/logistics/notifications', json={'all': True}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT read_at FROM ops_notifications WHERE id=?', (fresh,)).fetchone()[0], recent)
            self.assertIsNotNone(c.execute('SELECT read_at FROM ops_notifications WHERE id=?', (unread,)).fetchone()[0])
            self.assertIsNone(c.execute('SELECT read_at FROM ops_notifications WHERE id=?', (foreign,)).fetchone()[0])
            self.assertIsNone(c.execute('SELECT id FROM ops_notifications WHERE id=?', (expired,)).fetchone())

    def palette_client_fixture(self):
        with self.m.conn() as c:
            c.execute("UPDATE users SET role='client',client_type='societe_livraison' WHERE id=?",(self.manager,))
        def order(owner=None):
            pid,_=self.parcel(status='Créé')
            with self.m.conn() as c:
                c.execute('UPDATE parcels SET client_id=?,current_hub_id=NULL,driver_id=NULL WHERE id=?',(owner or self.manager,pid))
            return pid
        self.palette_order=order
        first=order()
        r=self.post('partner-palettes',{'parcel_ids':[first],'destination_hub_id':self.hub,'request_key':uuid.uuid4().hex})
        self.assertEqual(r.status_code,200,r.json)
        return r.json,first

    def palette_action(self,doc,action,**extra):
        data={'revision':doc['revision'],'request_key':uuid.uuid4().hex,'confirmed':True,**extra}
        return self.post('partner-palettes/'+str(doc['id'])+'/'+action,data)

    def test_client_palette_add_dispatch_and_lock(self):
        doc,first=self.palette_client_fixture();second=self.palette_order()
        r=self.palette_action(doc,'add',parcel_ids=[second]);self.assertEqual(r.status_code,200,r.json)
        doc=r.json
        d=self.client.get('/api/partner-palettes/'+str(doc['id'])).json
        self.assertEqual(d['count'],2)
        self.assertEqual(d['status'],'Préparé')
        r=self.palette_action(doc,'dispatch');self.assertEqual(r.status_code,200,r.json);doc=r.json
        self.assertEqual(doc['status'],'En transit')
        for action,extras in [('add',{'parcel_ids':[self.palette_order()]}),('delete',{}),('cancel',{'reason':'No longer wanted'})]:
            r=self.palette_action(doc,action,**extras);self.assertEqual(r.status_code,409,r.json)
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM ops_document_lines WHERE document_id=? AND active=1',(doc['id'],)).fetchone()[0],2)
            self.assertEqual(c.execute('SELECT status FROM parcels WHERE id=?',(first,)).fetchone()[0],'Créé')

    def test_client_palette_add_retry_and_stale_confirmation(self):
        doc,first=self.palette_client_fixture();second=self.palette_order()
        data={'revision':doc['revision'],'request_key':uuid.uuid4().hex,'confirmed':True,'parcel_ids':[second]}
        path='partner-palettes/'+str(doc['id'])+'/add'
        r=self.post(path,data);self.assertEqual(r.status_code,200,r.json)
        retry=self.post(path,data);self.assertEqual(retry.status_code,200,retry.json);self.assertTrue(retry.json['replayed'])
        self.assertEqual(self.client.get('/api/partner-palettes/'+str(doc['id'])).json['count'],2)
        r=self.palette_action(doc,'dispatch');self.assertEqual(r.status_code,409,r.json)
        r=self.palette_action(doc,'delete');self.assertEqual(r.status_code,409,r.json)
        current=retry.json
        r=self.palette_action(current,'add',parcel_ids=[second]);self.assertEqual(r.status_code,409,r.json)

    def test_client_palette_add_is_atomic_and_scoped(self):
        doc,first=self.palette_client_fixture();second=self.palette_order();foreign=self.palette_order(self.client_id)
        r=self.palette_action(doc,'add',parcel_ids=[second,foreign]);self.assertEqual(r.status_code,404,r.json)
        d=self.client.get('/api/partner-palettes/'+str(doc['id'])).json
        self.assertEqual(d['count'],1);self.assertEqual(d['revision'],doc['revision'])
        for ids in [[],[True],[second,second],list(range(1,502))]:
            r=self.palette_action(doc,'add',parcel_ids=ids);self.assertEqual(r.status_code,400,r.json)
        other=self.post('partner-palettes',{'parcel_ids':[second],'destination_hub_id':self.hub,'request_key':uuid.uuid4().hex})
        self.assertEqual(other.status_code,200,other.json)
        r=self.palette_action(doc,'add',parcel_ids=[second]);self.assertEqual(r.status_code,409,r.json)
        with self.m.conn() as c:c.execute('UPDATE ops_documents SET client_id=? WHERE id=?',(self.client_id,doc['id']))
        for action in ['add','delete','dispatch']:
            r=self.palette_action(doc,action,parcel_ids=[second]);self.assertEqual(r.status_code,404,r.json)

    def test_client_palette_delete_preserves_orders_and_audit(self):
        doc,first=self.palette_client_fixture()
        data={'revision':doc['revision'],'request_key':uuid.uuid4().hex,'confirmed':True}
        path='partner-palettes/'+str(doc['id'])+'/delete'
        r=self.post(path,data);self.assertEqual(r.status_code,200,r.json);self.assertTrue(r.json['deleted'])
        retry=self.post(path,data);self.assertEqual(retry.status_code,200,retry.json);self.assertTrue(retry.json['replayed'])
        listing=self.client.get('/api/partner-palettes').json
        self.assertNotIn(doc['id'],[r['id'] for r in listing['rows']])
        self.assertEqual(self.client.get('/api/partner-palettes/'+str(doc['id'])).status_code,404)
        sync=self.post('partner-palettes/daily-draft',{'destination_hub_id':self.hub})
        self.assertEqual(sync.status_code,200,sync.json)
        self.assertFalse(sync.json.get('id'))
        candidates=self.client.get('/api/partner-palettes/candidates').json
        self.assertIn(first,[r['id'] for r in candidates['rows']])
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT status FROM parcels WHERE id=?',(first,)).fetchone()[0],'Créé')
            self.assertIsNotNone(c.execute("SELECT id FROM ops_audit WHERE document_id=? AND action='Brouillon supprimé par le client'",(doc['id'],)).fetchone())

    def test_client_palette_mutations_require_confirmation_and_csrf(self):
        doc,first=self.palette_client_fixture()
        for action in ['add','delete','dispatch']:
            r=self.palette_action(doc,action,confirmed=False,parcel_ids=[self.palette_order()]);self.assertEqual(r.status_code,400,r.json)
            r=self.client.post('/api/partner-palettes/'+str(doc['id'])+'/'+action,json={'confirmed':True,'revision':doc['revision'],'request_key':uuid.uuid4().hex})
            self.assertEqual(r.status_code,403,r.json)

    def test_session_history_purges_old_rows_and_keeps_current_session(self):
        import time
        t=int(time.time())
        with self.m.conn() as c:
            old=c.execute("INSERT INTO auth_sessions(user_id,token_hash,created_at,last_seen,expires_at,user_agent,network) VALUES(?,?,?,?,?,'Test old','masked')",(self.manager,uuid.uuid4().hex,t-31*86400,t-31*86400,t-30*86400)).lastrowid
            audit=c.execute("INSERT INTO auth_events(user_id,action,network,created_at) VALUES(?,'Test retained event','masked',?)",(self.manager,t-31*86400)).lastrowid
        r=self.client.get('/api/security/sessions')
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['retention_days'],30)
        self.assertNotIn(old,[x['id'] for x in r.json['sessions']])
        self.assertTrue(any(x['current'] and x['active'] for x in r.json['sessions']))
        with self.m.conn() as c:
            self.assertIsNone(c.execute('SELECT id FROM auth_sessions WHERE id=?',(old,)).fetchone())
            self.assertIsNotNone(c.execute('SELECT id FROM auth_events WHERE id=?',(audit,)).fetchone())
        self.assertEqual(self.client.get('/api/bootstrap').status_code,200)

    def company_order_payload(self,pid,**changes):
        p=self.client.get('/api/parcels/'+str(pid)).json['parcel']
        d={k:p[k] for k in ('tracking','recipient','phone','address','city_id','amount','product','note')}
        d.update(revision=p['ops_revision'],not_allowed_to_open=not p['open_allowed'],is_exchange=bool(p['is_exchange']))
        return {**d,**changes}

    def test_company_edit_updates_draft_snapshot_and_revision(self):
        doc,pid=self.palette_client_fixture()
        payload=self.company_order_payload(pid,tracking='EDIT-'+uuid.uuid4().hex[:12],recipient='Changed recipient',amount=234.56)
        r=self.client.patch(f'/api/parcels/{pid}/company-edit',json=payload,headers=self.headers)
        self.assertEqual(r.status_code,200,r.json)
        updated=self.client.get('/api/parcels/'+str(pid)).json['parcel']
        self.assertEqual(updated['recipient'],'Changed recipient');self.assertEqual(updated['amount'],234.56)
        palette=self.client.get('/api/partner-palettes/'+str(doc['id'])).json
        self.assertEqual(palette['lines'][0]['tracking'],payload['tracking'])
        self.assertEqual(palette['lines'][0]['recipient'],'Changed recipient')
        self.assertEqual(palette['revision'],doc['revision']+1)
        self.assertTrue(updated['company_order_editable'])
        self.assertEqual(self.palette_action(doc,'dispatch').status_code,409)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}/company-edit',json=payload,headers=self.headers).status_code,409)

    def test_company_order_sent_is_locked_and_cannot_be_deleted(self):
        doc,pid=self.palette_client_fixture();payload=self.company_order_payload(pid)
        self.assertEqual(self.palette_action(doc,'dispatch').status_code,200)
        p=self.client.get('/api/parcels/'+str(pid)).json['parcel'];self.assertFalse(p['company_order_editable'])
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}/company-edit',json=payload,headers=self.headers).status_code,409)
        r=self.client.delete(f'/api/parcels/{pid}/company-edit',json={'revision':p['ops_revision'],'confirmed':True},headers=self.headers)
        self.assertEqual(r.status_code,409)
        self.assertEqual(self.client.get('/api/partner-palettes/'+str(doc['id'])).json['count'],1)

    def test_company_order_delete_draft_and_empty_palette(self):
        doc,first=self.palette_client_fixture();second=self.palette_order()
        r=self.palette_action(doc,'add',parcel_ids=[second]);self.assertEqual(r.status_code,200)
        for pid,remaining in [(first,1),(second,0)]:
            payload=self.company_order_payload(pid)
            r=self.client.delete(f'/api/parcels/{pid}/company-edit',json={'revision':payload['revision'],'confirmed':True},headers=self.headers)
            self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(self.client.get('/api/parcels/'+str(pid)).status_code,404)
            self.assertNotIn(pid,[p['id'] for p in self.client.get('/api/bootstrap').json['parcels']])
            r=self.client.get('/api/partner-palettes/'+str(doc['id']))
            if remaining:self.assertEqual(r.json['count'],remaining)
            else:self.assertEqual(r.status_code,404)
            with self.m.conn() as c:
                self.assertEqual(c.execute('SELECT status FROM parcels WHERE id=?',(pid,)).fetchone()[0],'Annulé')
                self.assertIsNotNone(c.execute('SELECT parcel_id FROM company_deleted_orders WHERE parcel_id=?',(pid,)).fetchone())
        self.assertNotIn(first,[p['id'] for p in self.client.get('/api/partner-palettes/candidates').json['rows']])

    def test_company_order_scope_validation_and_duplicate_tracking(self):
        doc,pid=self.palette_client_fixture();other=self.palette_order();foreign=self.palette_order(self.client_id)
        original=self.company_order_payload(pid)
        duplicate=self.company_order_payload(other)['tracking']
        for changed,code in [({'tracking':duplicate},409),({'amount':-1},400),({'phone':'bad'},400),({'client_id':self.client_id},400),({'city_id':False},400),({'status':'Livré'},400)]:
            r=self.client.patch(f'/api/parcels/{pid}/company-edit',json={**original,**changed},headers=self.headers)
            self.assertEqual(r.status_code,code,r.json)
        self.assertEqual(self.client.get('/api/partner-palettes/'+str(doc['id'])).json['revision'],doc['revision'])
        self.assertEqual(self.client.patch(f'/api/parcels/{foreign}/company-edit',json=original,headers=self.headers).status_code,404)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}/company-edit',json=original).status_code,403)
        with self.m.conn() as c:c.execute("UPDATE users SET client_type='vendeur' WHERE id=?",(self.manager,))
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}/company-edit',json=original,headers=self.headers).status_code,403)

    def test_company_order_unassigned_edit_and_city_tariff(self):
        doc,first=self.palette_client_fixture();pid=self.palette_order()
        with self.m.conn() as c:
            city=c.execute("INSERT INTO cities(name,region,delivery,pickup,fee,return_fee) VALUES(?,'Test',1,1,42,13)",('Edit city '+uuid.uuid4().hex,)).lastrowid
        payload=self.company_order_payload(pid,city_id=city)
        r=self.client.patch(f'/api/parcels/{pid}/company-edit',json=payload,headers=self.headers)
        self.assertEqual(r.status_code,200,r.json)
        p=self.client.get('/api/parcels/'+str(pid)).json['parcel']
        self.assertEqual(p['city_id'],city);self.assertTrue(p['company_order_editable'])
        self.assertEqual(self.client.delete(f'/api/parcels/{pid}/company-edit',json={'revision':p['ops_revision'],'confirmed':False},headers=self.headers).status_code,400)

    def client_extra_fixture(self,kind='vendeur'):
        with self.m.conn() as c:c.execute("UPDATE users SET role='client',client_type=? WHERE id=?",(kind,self.manager))
        r=self.client.get('/api/client-profile');self.assertEqual(r.status_code,200,r.json)
        return {k:r.json[k] for k in ('city','cin','website','language','preferences','address','legal_id','revision','dossier_revision')}

    def test_extra_profile_both_types_preserve_existing_dossier(self):
        for kind in ['vendeur','societe_livraison']:
            d=self.client_extra_fixture(kind);d.update(city='Agadir',cin='AB123456',website='https://example.test',language='en',address='Adresse de test',legal_id='123456789012345')
            r=self.client.patch('/api/client-profile',json=d,headers=self.headers);self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(r.json['city'],'Agadir')
            with self.m.conn() as c:
                dossier=c.execute('SELECT * FROM account_dossiers WHERE user_id=?',(self.manager,)).fetchone()
                self.assertEqual(dossier['billing_address'],'Adresse de test');self.assertEqual(dossier['legal_id'],d['legal_id'])
            self.assertEqual(self.client.get('/api/bootstrap').json['user']['profile_language'],'en')
            self.assertEqual(self.client.patch('/api/client-profile',json=d,headers=self.headers).status_code,409)

    def test_extra_profile_validation_scope_and_bank_for_seller(self):
        self.assertEqual(self.client.get('/api/client-profile').status_code,403)
        d=self.client_extra_fixture()
        for update in [{'website':'javascript:alert(1)'},{'language':'xx'},{'cin':'<script>'},{'preferences':{'payment':False}},{'user_id':self.other_driver}]:
            self.assertEqual(self.client.patch('/api/client-profile',json={**d,**update},headers=self.headers).status_code,400)
        self.assertEqual(self.client.patch('/api/client-profile',json=d).status_code,403)
        r=self.client.patch('/api/profile',json={'name':'Seller','phone':'0600000000','company':'Test','bank_name':'My Bank','bank_rib':'0'*24},headers=self.headers)
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.client.get('/api/bootstrap').json['user']['bank_name'],'My Bank')
        with self.m.conn() as c:self.assertIsNone(c.execute('SELECT * FROM client_profile_extras WHERE user_id=?',(self.other_driver,)).fetchone())

    def test_extra_profile_notifications_are_applied(self):
        from client_profile_extras import notification_enabled
        d=self.client_extra_fixture();d['preferences']['status:Livré']=False;d['preferences']['payment']=False
        self.assertEqual(self.client.patch('/api/client-profile',json=d,headers=self.headers).status_code,200)
        pid,_=self.parcel(status='Créé')
        with self.m.conn() as c:
            c.execute('UPDATE parcels SET client_id=? WHERE id=?',(self.manager,pid))
            self.m.ops_notify_event(c,pid,'Livré',{'id':self.other_driver})
            self.assertIsNone(c.execute('SELECT id FROM ops_notifications WHERE user_id=? AND parcel_id=?',(self.manager,pid)).fetchone())
            self.assertFalse(notification_enabled(c,self.manager,'payment'))
            self.m.ops_notify_event(c,pid,'Réceptionné',{'id':self.other_driver})
            self.assertIsNotNone(c.execute('SELECT id FROM ops_notifications WHERE user_id=? AND parcel_id=?',(self.manager,pid)).fetchone())

    def test_google_disabled_and_invalid_state_fail_closed(self):
        from unittest.mock import patch
        self.client_extra_fixture()
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'','GOOGLE_CLIENT_SECRET':'','GOOGLE_REDIRECT_URI':''}):
            r=self.client.get('/api/google/status');self.assertFalse(r.json['configured']);self.assertFalse(r.json['linked'])
            self.assertEqual(self.client.post('/api/google/sheets/preview',json={'sheet_id':'abc'},headers=self.headers).status_code,503)
        with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'https://example.test/google/callback'}):
            self.assertEqual(self.client.get('/google/callback?state=wrong&code=test').status_code,400)
            self.assertEqual(self.client.post('/api/google/link',json={'current_password':'bad'},headers=self.headers).status_code,403)

    def test_google_link_preview_is_scoped_and_requires_confirmation(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from urllib.parse import urlsplit,parse_qs
        self.client_extra_fixture('societe_livraison')
        config={'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'https://example.test/google/callback'}
        with patch.dict(os.environ,config):
            link=self.client.post('/api/google/link',json={'current_password':'TestPassword!123'},headers=self.headers)
            self.assertEqual(link.status_code,200,link.json)
            query=parse_qs(urlsplit(link.json['url']).query)
            claims={'sub':'fake-sub-'+uuid.uuid4().hex,'email':'linked@example.test','email_verified':True,'nonce':query['nonce'][0]}
            tokens=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'access_token':'fake-secret-token','refresh_token':'fake-refresh-token','id_token':'fake-id','expires_in':3600})
            with patch('requests.post',return_value=tokens),patch('google.oauth2.id_token.verify_oauth2_token',return_value=claims):
                r=self.client.get('/google/callback',query_string={'state':query['state'][0],'code':'fake-code'})
            self.assertEqual(r.status_code,302)
            status=self.client.get('/api/google/status');self.assertTrue(status.json['linked']);self.assertNotIn('tokens',status.json)
            with self.m.conn() as c:
                stored=c.execute('SELECT tokens FROM google_accounts WHERE user_id=?',(self.manager,)).fetchone()[0]
                self.assertNotIn('fake-secret-token',stored)
                before=c.execute('SELECT count(*) FROM parcels WHERE client_id=?',(self.manager,)).fetchone()[0]
                city=c.execute('SELECT name FROM cities WHERE id=?',(self.city,)).fetchone()[0]
            import json
            values=[['tracking','destinataire','telephone','adresse','ville','montant','produit','note'],['GS-'+uuid.uuid4().hex[:12],'Client test','0600000000','Adresse test',city,'123','Produit','Test']]
            class SheetResponse:
                def __enter__(self):return self
                def __exit__(self,*args):pass
                def raise_for_status(self):pass
                def iter_content(self,*args):yield json.dumps({'values':values}).encode()
            with patch('requests.get',return_value=SheetResponse()) as get:
                r=self.client.post('/api/google/sheets/preview',json={'sheet_id':'a'*30,'sheet_name':'Feuille 1'},headers=self.headers)
            self.assertEqual(r.status_code,200,r.json)
            self.assertEqual(r.json['total'],1)
            self.assertIn('sheets.googleapis.com',get.call_args.args[0])
            with self.m.conn() as c:self.assertEqual(c.execute('SELECT count(*) FROM parcels WHERE client_id=?',(self.manager,)).fetchone()[0],before)
            self.assertEqual(self.client.delete('/api/google/link',headers=self.headers).status_code,200)
            self.assertFalse(self.client.get('/api/google/status').json['linked'])

    def test_google_login_only_for_linked_account_and_nonce_required(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        from urllib.parse import urlsplit,parse_qs
        self.client_extra_fixture()
        config={'GOOGLE_CLIENT_ID':'test-client','GOOGLE_CLIENT_SECRET':'test-secret','GOOGLE_REDIRECT_URI':'https://example.test/google/callback'}
        with patch.dict(os.environ,config):
            response=self.client.post('/api/google/link',json={'current_password':'TestPassword!123'},headers=self.headers)
            query=parse_qs(urlsplit(response.json['url']).query)
            claims={'sub':'linked-login-'+uuid.uuid4().hex,'email':'login@example.test','email_verified':True,'nonce':'wrong-nonce'}
            tokens=SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'access_token':'test-token','refresh_token':'test-refresh','id_token':'test-id','expires_in':3600})
            with patch('requests.post',return_value=tokens),patch('google.oauth2.id_token.verify_oauth2_token',return_value=claims):
                r=self.client.get('/google/callback',query_string={'state':query['state'][0],'code':'fake-code'})
            self.assertEqual(r.status_code,400)
            self.assertFalse(self.client.get('/api/google/status').json['linked'])
            with self.m.conn() as c:
                c.execute('INSERT INTO google_accounts VALUES(?,?,?,?,?)',(self.manager,claims['sub'],claims['email'],'not-a-real-token',self.m.now()))
            browser=self.m.app.test_client()
            response=browser.get('/google/login');self.assertEqual(response.status_code,302)
            query=parse_qs(urlsplit(response.headers['Location']).query);claims['nonce']=query['nonce'][0]
            with patch('requests.post',return_value=tokens),patch('google.oauth2.id_token.verify_oauth2_token',return_value=claims):
                r=browser.get('/google/callback',query_string={'state':query['state'][0],'code':'fake-code'})
            self.assertEqual(r.status_code,302)
            self.assertEqual(browser.get('/api/bootstrap').json['user']['id'],self.manager)
            self.assertEqual(browser.get('/google/callback',query_string={'state':query['state'][0],'code':'fake-code'}).status_code,400)

    def test_extra_profile_billing_summary_matches_own_invoices(self):
        self.client_extra_fixture()
        with self.m.conn() as c:
            c.execute("INSERT INTO invoices(client_id,cod,fees,total,status,created_at) VALUES(?,300,50,250,'À régler',?)",(self.manager,self.m.now()))
            c.execute("INSERT INTO invoices(client_id,cod,fees,total,status,created_at) VALUES(?,900,100,800,'À régler',?)",(self.client_id,self.m.now()))
        summary=self.client.get('/api/client-profile').json['billing']
        self.assertEqual(summary['cod'],300)
        self.assertEqual(summary['fees'],50)
        self.assertEqual(summary['remaining'],250)
        self.assertEqual(summary['owed'],0)

    def post(self,path,data):
        return self.client.post('/api/'+path,json=data,headers=self.headers)

    def parcel(self,hub=None,status='Réceptionné',driver=None,assignment=None):
        m=self.m;tracking='TEST-'+uuid.uuid4().hex
        with m.conn() as c:
            pid=c.execute('''INSERT INTO parcels(tracking,client_id,driver_id,recipient,phone,address,city_id,amount,fee,return_fee,status,product,note,created_at,updated_at,current_hub_id)
                VALUES(?,?,?,'Recipient','0600000000','Test address',?,100,25,10,?,'','',?,?,?)''',
                (tracking,self.client_id,driver,self.city,status,m.now(),m.now(),hub)).lastrowid
            if assignment:
                c.execute('INSERT INTO ops_assignments(parcel_id,new_driver_id,actor_id,created_at,hub_id) VALUES(?,?,?,?,?)',(pid,driver,self.manager,m.now(),assignment))
        return pid,tracking

    def scan(self,mode,items,hub=None,key=None,driver=None):
        return self.post(f'drivers-workspace/{driver or self.driver}/scan-batch',dict(mode=mode,scans=[dict(parcel_id=p,revision=r) for p,r in items],hub_id=hub,request_key=key or uuid.uuid4().hex,confirmed=True))

    def test_assign_receive_and_replay(self):
        pid,tracking=self.parcel(self.hub)
        preview=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='assign'))
        self.assertEqual(preview.status_code,200,preview.json)
        key=uuid.uuid4().hex
        r=self.scan('assign',[(pid,0)],key=key);self.assertEqual(r.status_code,200,r.json)
        r=self.scan('assign',[(pid,0)],key=key);self.assertTrue(r.json['replayed'])
        r=self.client.get(f'/api/drivers-workspace/{self.driver}');self.assertEqual([p['id'] for p in r.json['parcels']],[pid])
        r=self.client.get('/api/logistics/hub/drivers');self.assertEqual(r.json['drivers'][0]['outstanding'],1)
        r=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='receive'));self.assertEqual(r.status_code,200,r.json)
        r=self.scan('receive',[(pid,1)]);self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['current_hub_id'],p['driver_id'],p['status']),(self.hub,self.driver,'Reçu par le livreur'))

    def test_hub_keeps_read_only_tracking_after_driver_handoff(self):
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,200)
        data=self.client.get('/api/bootstrap').json
        row=next(p for p in data['parcels'] if p['id']==pid)
        self.assertEqual(row['status'],'Reçu par le livreur')
        self.assertIsNone(row['current_hub_id'])
        detail=self.client.get(f'/api/parcels/{pid}')
        self.assertEqual(detail.status_code,200,detail.json)
        self.assertTrue(any(e['status']=='Reçu par le livreur' for e in detail.json['events']))
        # Existing physical mutation scope stays closed, even though tracking can read it.
        from hub_access import hub_parcel_scope
        with self.m.conn() as c:
            clause,args=hub_parcel_scope(c,'p',self.hub)
            self.assertIsNone(c.execute(f'SELECT p.id FROM parcels p WHERE p.id=? AND {clause}',[pid]+args).fetchone())
            c.execute("UPDATE parcels SET status='Livré' WHERE id=?",(pid,))
        row=next(p for p in self.client.get('/api/bootstrap').json['parcels'] if p['id']==pid)
        self.assertEqual(row['status'],'Livré')

    def test_tracking_does_not_leak_foreign_or_unproven_driver_orders(self):
        remote,_=self.parcel(None,status='En livraison',driver=self.other_driver,assignment=self.foreign)
        unproven,_=self.parcel(None,status='Reçu par le livreur',driver=self.driver)
        transit,_=self.parcel(None,status='Transit',driver=self.driver,assignment=self.hub)
        moved,_=self.parcel(self.foreign,status='Réceptionné',driver=self.driver,assignment=self.hub)
        ids={p['id'] for p in self.client.get('/api/bootstrap').json['parcels']}
        for pid in (remote,unproven,transit,moved):
            self.assertNotIn(pid,ids)
            self.assertEqual(self.client.get(f'/api/parcels/{pid}').status_code,404)

    def test_cross_hub_driver_and_parcel_denied_atomic_batch(self):
        pid,_=self.parcel(self.hub);foreign,tracking=self.parcel(self.foreign)
        r=self.scan('assign',[(pid,0),(foreign,0)]);self.assertEqual(r.status_code,404,r.json)
        with self.m.conn() as c:self.assertIsNone(c.execute('SELECT driver_id FROM parcels WHERE id=?',(pid,)).fetchone()[0])
        r=self.post(f'drivers-workspace/{self.driver}/scan-preview',dict(tracking=tracking,mode='assign'));self.assertEqual(r.status_code,404)
        r=self.scan('assign',[(pid,0)],driver=self.other_driver);self.assertEqual(r.status_code,404)
        self.assertEqual(self.client.get(f'/api/drivers-workspace/{self.other_driver}').status_code,404)

    def test_evening_recovery_preserves_driver_outcome_and_followup(self):
        for status in ('Reporté','Programmé','Refusé','Retourné','En livraison','Reçu par le livreur'):
            with self.subTest(status=status):
                pid,_=self.parcel(None,status,self.driver,self.hub)
                with self.m.conn() as c:
                    reason=c.execute('SELECT code FROM ops_reasons WHERE active=1 LIMIT 1').fetchone()[0]
                    c.execute("UPDATE parcels SET reason_code=?,next_attempt_at='2026-12-01T12:00',note='Appeler demain' WHERE id=?",(reason,pid))
                    before=dict(c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone())
                r=self.scan('receive',[(pid,0)]);self.assertEqual(r.status_code,200,r.json)
                with self.m.conn() as c:
                    after=dict(c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone())
                    for key in ('status','reason_code','next_attempt_at','note','driver_id','amount','invoice_id','updated_at','status_updated_at'):
                        self.assertEqual(after[key],before[key],key)
                    self.assertEqual(after['current_hub_id'],self.hub)
                row=next(p for p in self.client.get('/api/bootstrap').json['parcels'] if p['id']==pid)
                self.assertEqual(row['status'],status);self.assertTrue(row['driver_returned'])
                self.assertTrue(row['current_hub_name'])
                # Replay is safe and the parcel is no longer in the courier's outstanding tour.
                self.assertEqual(self.scan('receive',[(pid,1)]).status_code,200)
                self.assertNotIn(pid,[p['id'] for p in self.client.get(f'/api/drivers-workspace/{self.driver}').json['parcels']])

    def test_return_hub_tampering_and_stale_revision(self):
        pid,_=self.parcel(None,'Reçu par le livreur',self.driver,self.hub)
        self.assertEqual(self.scan('receive',[(pid,0)],self.foreign).status_code,403)
        self.assertEqual(self.scan('receive',[(pid,99)],self.hub).status_code,409)

    def test_closed_recovery_keeps_financial_attribution(self):
        pid,_=self.parcel(None,'Refusé',self.driver,self.hub)
        r=self.scan('receive',[(pid,0)]);self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['status'],p['driver_id'],p['current_hub_id']),('Refusé',self.driver,self.hub))
        pid,_=self.parcel(None,'Livré',self.driver,self.hub)
        self.assertEqual(self.scan('receive',[(pid,0)]).status_code,409)

    def test_invoice_scope_confirm_and_no_payment_permissions(self):
        local,_=self.parcel(None,'Livré',self.driver,self.hub)
        self.parcel(None,'Livré',self.driver,self.foreign)
        self.parcel(None,'Livré',self.driver) # unknown legacy evidence: Admin only
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        self.assertEqual([p['parcel_id'] for p in r.json['lines']],[local]);token=r.json['token']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertEqual(r.status_code,200,r.json);sid=r.json['statement_id']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertTrue(r.json['already_created'])
        r=self.client.get(f'/api/driver-finance/statements/{sid}');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['statement']['hub_id'],self.hub)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/transactions',{}).status_code,403)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/cancel',{}).status_code,403)
        self.assertEqual(self.post('driver-finance/preview',dict(driver_id=self.other_driver)).status_code,404)
        with self.m.conn() as c:c.execute('UPDATE driver_statements SET hub_id=? WHERE id=?',(self.foreign,sid))
        self.assertEqual(self.client.get(f'/api/driver-finance/statements/{sid}').status_code,404)

    def test_inactive_hub_and_csrf(self):
        pid,_=self.parcel(self.hub)
        r=self.client.post(f'/api/drivers-workspace/{self.driver}/scan-preview',json={'tracking':'anything','mode':'assign'});self.assertEqual(r.status_code,403)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,403)
        self.assertEqual(self.post('driver-finance/preview',dict(driver_id=self.driver)).status_code,403)

    def test_preassigned_physical_dispatch_records_hub(self):
        pid,_=self.parcel(self.hub,driver=self.driver)
        r=self.scan('assign',[(pid,0)]);self.assertEqual(r.status_code,200,r.json)
        r=self.scan('receive',[(pid,1)]);self.assertEqual(r.status_code,200,r.json)

    def status_patch(self,pid,status,revision=0,**fields):
        return self.client.patch(f'/api/parcels/{pid}',json={'status':status,'revision':revision,**fields},headers=self.headers)

    def test_manager_status_change_and_audit(self):
        pid,_=self.parcel(self.hub)
        r=self.status_patch(pid,'Reporté',note='Client indisponible')
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            p=c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone()
            self.assertEqual((p['status'],p['ops_revision'],p['current_hub_id']),('Reporté',1,self.hub))
            e=c.execute('SELECT * FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
            self.assertEqual((e['actor_id'],e['status']),(self.manager,'Reporté'))
        self.assertEqual(self.status_patch(pid,'Intéressé',revision=1).status_code,200)

    def test_delivered_is_immutable_for_manager(self):
        for final in ('Livré',):
            with self.subTest(final=final):
                pid,_=self.parcel(self.hub,final,self.driver,self.hub)
                for target in ('Réceptionné','Reporté',final):
                    r=self.status_patch(pid,target)
                    self.assertEqual(r.status_code,409,r.json)
                with self.m.conn() as c:
                    p=c.execute('SELECT status,ops_revision FROM parcels WHERE id=?',(pid,)).fetchone()
                    self.assertEqual(tuple(p),(final,0))

    def test_manager_can_close_open_parcel_but_not_reopen(self):
        for target in ('Livré','Retourné'):
            with self.subTest(target=target):
                pid,_=self.parcel(self.hub,'En livraison',self.driver,self.hub)
                r=self.status_patch(pid,target)
                self.assertEqual(r.status_code,200,r.json)
                self.assertEqual(self.status_patch(pid,'En livraison',revision=1).status_code,409 if target=='Livré' else 200)
        # Refusé is not one of the two immutable statuses requested.
        pid,_=self.parcel(self.hub,'Refusé',self.driver,self.hub)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,200)

    def test_manager_changes_driver_tour_status_and_locks_only_delivered(self):
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,200)
        row=next(p for p in self.client.get('/api/bootstrap').json['parcels'] if p['id']==pid)
        self.assertTrue(row['hub_status_editable'])
        r=self.status_patch(pid,'Reporté',revision=1);self.assertEqual(r.status_code,200,r.json)
        r=self.status_patch(pid,'Retourné',revision=2);self.assertEqual(r.status_code,200,r.json)
        r=self.status_patch(pid,'En livraison',revision=3);self.assertEqual(r.status_code,200,r.json)
        r=self.status_patch(pid,'Livré',revision=4);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.status_patch(pid,'Reporté',revision=5).status_code,409)
        row=self.client.get(f'/api/parcels/{pid}').json['parcel']
        self.assertFalse(row['hub_status_editable'])
        with self.m.conn() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM audit_log WHERE entity_id=? AND action='hub_parcel_status_changed'",(str(pid),)).fetchone()[0],4)

    def test_foreign_driver_tour_cannot_be_changed(self):
        pid,_=self.parcel(None,'En livraison',self.other_driver,self.foreign)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,404)

    def test_driver_can_add_motif_and_note_without_status_change(self):
        from werkzeug.security import generate_password_hash
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,200)
        with self.m.conn() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash('TestPassword!123'),self.driver))
            email=c.execute('SELECT email FROM users WHERE id=?',(self.driver,)).fetchone()[0]
            reason=c.execute('SELECT code FROM ops_reasons WHERE active=1 LIMIT 1').fetchone()[0]
            before=dict(c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone())
        browser=self.m.app.test_client()
        self.assertEqual(browser.post('/api/login',json={'email':email,'password':'TestPassword!123'}).status_code,200)
        headers={'X-CSRF-Token':browser.get('/api/bootstrap').json['csrf']}
        # The exact modal prerequisites must both succeed for the courier.
        self.assertEqual(browser.get(f'/api/parcels/{pid}').status_code,200)
        vocabulary=browser.get('/api/logistics/followup-reasons')
        self.assertEqual(vocabulary.status_code,200,vocabulary.json)
        self.assertEqual(set(vocabulary.json),{'reasons'})
        self.assertIn(reason,[r['code'] for r in vocabulary.json['reasons']])
        self.assertEqual(browser.get('/api/logistics/config').status_code,403)
        payload=dict(reason_code=reason,note='Client joignable après 18h',revision=before['ops_revision'])
        endpoint=f'/api/parcels/{pid}/followup'
        self.assertEqual(browser.patch(endpoint,json=payload).status_code,403)
        r=browser.patch(endpoint,json=payload,headers=headers);self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            after=dict(c.execute('SELECT * FROM parcels WHERE id=?',(pid,)).fetchone())
            for key in ('status','amount','fee','driver_id','note','current_hub_id','next_attempt_at','status_updated_at'):
                self.assertEqual(after[key],before[key])
            self.assertEqual(after['reason_code'],reason)
            ev=c.execute('SELECT * FROM events WHERE parcel_id=? ORDER BY id DESC LIMIT 1',(pid,)).fetchone()
            self.assertEqual(ev['actor_id'],self.driver);self.assertIn(payload['note'],ev['note'])
        # Visible to the Hub in the existing chronology.
        self.assertTrue(any(payload['note'] in e['note'] for e in self.client.get(f'/api/parcels/{pid}').json['events']))
        self.assertEqual(browser.patch(endpoint,json=payload,headers=headers).status_code,409)
        self.assertEqual(browser.patch(endpoint,json={**payload,'revision':after['ops_revision'],'status':'Livré'},headers=headers).status_code,400)
        other,_=self.parcel(None,'En livraison',self.other_driver,self.foreign)
        self.assertEqual(browser.patch(f'/api/parcels/{other}/followup',json=payload,headers=headers).status_code,404)
        with self.m.conn() as c:c.execute("UPDATE parcels SET status='Livré' WHERE id=?",(pid,))
        self.assertEqual(browser.patch(endpoint,json={**payload,'revision':after['ops_revision']},headers=headers).status_code,409)

    def test_driver_simple_delivery_uses_order_cod_without_receiver(self):
        from werkzeug.security import generate_password_hash
        with self.m.conn() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash('TestPassword!123'),self.driver))
            email=c.execute('SELECT email FROM users WHERE id=?',(self.driver,)).fetchone()[0]
        browser=self.m.app.test_client()
        self.assertEqual(browser.post('/api/login',json={'email':email,'password':'TestPassword!123'}).status_code,200)
        headers={'X-CSRF-Token':browser.get('/api/bootstrap').json['csrf']}
        for amount in (0,125.50):
            pid,_=self.parcel(None,'En livraison',self.driver,self.hub)
            with self.m.conn() as c:c.execute('UPDATE parcels SET amount=? WHERE id=?',(amount,pid))
            endpoint=f'/api/logistics/parcels/{pid}/attempts'
            payload=dict(outcome='Livré',revision=0,request_key=uuid.uuid4().hex,simple_delivery=True)
            bad={**payload,'collected_amount':999}
            self.assertEqual(browser.post(endpoint,json=bad,headers=headers).status_code,400)
            r=browser.post(endpoint,json=payload,headers=headers);self.assertEqual(r.status_code,200,r.json)
            self.assertTrue(browser.post(endpoint,json=payload,headers=headers).json['already_recorded'])
            with self.m.conn() as c:
                attempt=c.execute('SELECT * FROM ops_attempts WHERE parcel_id=?',(pid,)).fetchone()
                self.assertEqual(attempt['amount_cents'],round(amount*100))
                self.assertFalse(attempt['receiver'])
                self.assertEqual(c.execute('SELECT status FROM parcels WHERE id=?',(pid,)).fetchone()[0],'Livré')
        pid,_=self.parcel(None,'En livraison',self.driver,self.hub)
        with self.m.conn() as c:c.execute("UPDATE parcels SET otp_required=1,otp_code='1234' WHERE id=?",(pid,))
        endpoint=f'/api/logistics/parcels/{pid}/attempts'
        payload=dict(outcome='Livré',revision=0,request_key=uuid.uuid4().hex,simple_delivery=True)
        self.assertEqual(browser.post(endpoint,json=payload,headers=headers).status_code,400)
        self.assertEqual(browser.post(endpoint,json={**payload,'otp':'1234'},headers=headers).status_code,200)

    def test_status_scope_fields_revision_csrf_and_inactive_hub(self):
        pid,_=self.parcel(self.hub)
        foreign,_=self.parcel(self.foreign)
        self.assertEqual(self.status_patch(foreign,'Reporté').status_code,404)
        self.assertEqual(self.status_patch(pid,'Reporté',driver_id=self.other_driver).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',amount=1).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',revision=True).status_code,403)
        self.assertEqual(self.status_patch(pid,'Reporté',revision=99).status_code,409)
        self.assertEqual(self.status_patch(pid,'Unknown').status_code,400)
        self.assertEqual(self.status_patch(pid,'Vers Hub Central').status_code,409)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}',json={'status':'Reporté','revision':0}).status_code,403)
        self.assertEqual(self.client.patch(f'/api/parcels/{pid}',json={'status':'Reporté'},headers=self.headers).status_code,403)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,403)

    def test_status_keeps_invoice_and_document_locks(self):
        pid,_=self.parcel(self.hub)
        with self.m.conn() as c:
            invoice=c.execute('INSERT INTO invoices(client_id,created_at) VALUES(?,?)',(self.client_id,self.m.now())).lastrowid
            c.execute('UPDATE parcels SET invoice_id=? WHERE id=?',(invoice,pid))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)
        pid,tracking=self.parcel(self.hub)
        with self.m.conn() as c:
            doc=c.execute("INSERT INTO ops_documents(reference,kind,note,created_by,created_at,source_hub_id) VALUES(?,'transfer','',?,?,?)",('DOC-'+uuid.uuid4().hex,self.manager,self.m.now(),self.hub)).lastrowid
            c.execute("INSERT INTO ops_document_lines(document_id,parcel_id,tracking,recipient,city,initial_status) VALUES(?,?,?,'Test','Test','Réceptionné')",(doc,pid,tracking))
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)
        # Financial line guard still applies to non-final source statuses too.
        pid,_=self.parcel(self.hub,'Refusé',self.driver,self.hub)
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        r=self.post(f"driver-finance/preview/{r.json['token']}/confirm",{});self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,409)

    def test_manager_scheduling_and_otp_checks_preserved(self):
        from datetime import datetime,timedelta
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.status_patch(pid,'Programmé').status_code,400)
        with self.m.conn() as c:
            reason=c.execute('SELECT code FROM ops_reasons WHERE active=1 LIMIT 1').fetchone()[0]
        future=(datetime.now()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')
        r=self.status_patch(pid,'Programmé',reason_code=reason,next_attempt_at=future)
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:c.execute("UPDATE parcels SET otp_required=1,otp_code='1234' WHERE id=?",(pid,))
        self.assertEqual(self.status_patch(pid,'Livré',revision=1).status_code,400)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='9999').status_code,400)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='1234').status_code,200)

    def test_admin_can_still_correct_final_status(self):
        pid,_=self.parcel(self.hub,'Livré',self.driver,self.hub)
        admin=self.m.app.test_client()
        r=admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'})
        self.assertEqual(r.status_code,200,r.json)
        csrf=admin.get('/api/bootstrap').json['csrf']
        r=admin.patch(f'/api/parcels/{pid}',json={'status':'Reporté','revision':0,'note':'Correction administrative'},headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200,r.json)

    def test_company_profile_http_save_and_private_bootstrap(self):
        with self.m.conn() as c:c.execute("UPDATE users SET role='client',client_type='societe_livraison' WHERE id=?",(self.manager,))
        data={'name':'My Company','phone':'0600000000','company':'Test','bank_name':'Test Bank','bank_rib':'0'*24}
        r=self.client.patch('/api/profile',json=data,headers=self.headers)
        self.assertEqual(r.status_code,200,r.json)
        r=self.client.get('/api/bootstrap');self.assertEqual(r.json['user']['bank_rib'],'0'*24)
        self.assertTrue(all('bank_rib' not in u and 'profile_image' not in u for u in r.json['users']))
        self.assertEqual(self.client.patch('/api/profile',json=data).status_code,403)
        data['bank_rib']='wrong';data['name']='MUST NOT SAVE'
        self.assertEqual(self.client.patch('/api/profile',json=data,headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/api/bootstrap').json['user']['name'],'My Company')

    def test_company_profile_rolls_back_with_wrong_password(self):
        with self.m.conn() as c:c.execute("UPDATE users SET role='client',client_type='societe_livraison' WHERE id=?",(self.manager,))
        data={'name':'Changed','phone':'0600000000','company':'Test','bank_name':'MUST NOT SAVE','password':'NewPassword123!','current_password':'incorrect'}
        r=self.client.patch('/api/profile',json=data,headers=self.headers);self.assertEqual(r.status_code,400)
        u=self.client.get('/api/bootstrap').json['user']
        self.assertEqual(u['bank_name'],'');self.assertEqual(u['name'],'Manager')

    def test_non_company_profile_cannot_add_bank_or_image(self):
        for fields in ({'bank_name':'Bank'},{'bank_rib':'0'*24},{'profile_image':''}):
            r=self.client.patch('/api/profile',json={'name':'Manager','phone':'0600000000','company':'Test',**fields},headers=self.headers)
            self.assertEqual(r.status_code,403,r.json)

if __name__=='__main__': unittest.main()
