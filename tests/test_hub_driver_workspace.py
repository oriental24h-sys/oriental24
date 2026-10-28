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
        cls.m = importlib.reload(importlib.import_module('app'))
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
        r=self.client.post('/api/login',json={'email':self.email,'password':'TestPassword!123'},
                           environ_overrides={'REMOTE_ADDR':f'10.{int(unique[:2],16)}.{int(unique[2:4],16)}.{int(unique[4:6],16)}'})
        self.assertEqual(r.status_code,200,r.json)
        r=self.client.get('/api/bootstrap')
        self.assertEqual(r.status_code,200,r.json)
        self.headers={'X-CSRF-Token':r.json['csrf']}

    def test_manager_analytics_real_scope_csv_details_and_inactive_guard(self):
        pid,tracking=self.parcel(None,'En livraison',self.driver,self.hub)
        other,foreign_tracking=self.parcel(None,'En livraison',self.other_driver,self.foreign)
        with self.m.conn() as c:
            c.execute("UPDATE ops_assignments SET created_at='2026-01-01T10:00:00+01:00' WHERE parcel_id IN (?,?)",(pid,other))
            c.execute("INSERT INTO ops_attempts(parcel_id,driver_id,actor_id,outcome,note,request_key,payload_hash,created_at,operational_hub_id) VALUES(?,?,?,'Reporté','',?,'hash','2026-01-01T11:00:00+01:00',?)",(pid,self.driver,self.manager,uuid.uuid4().hex,self.hub))
        endpoint='/api/hub-manager-analytics?from=2026-01-01&to=2026-01-02'
        r=self.client.get(endpoint);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['hub']['id'],self.hub)
        self.assertEqual((r.json['summary']['assigned'],r.json['summary']['processed'],r.json['summary']['delivered']),(1,1,0))
        self.assertIn(tracking,[p['tracking'] for p in r.json['parcels']])
        self.assertNotIn(foreign_tracking,str(r.json))
        self.assertEqual(self.client.get(endpoint+'&driver_id='+str(self.other_driver)).status_code,404)
        self.assertEqual(self.client.get(endpoint+'&hub_id='+str(self.foreign)).status_code,400)
        for view in ('daily','drivers','hub'):
            r=self.client.get(endpoint+'&format=csv&view='+view);self.assertEqual(r.status_code,200)
            self.assertNotIn(foreign_tracking,r.data.decode())
        self.assertEqual(self.client.post('/api/hub-manager-analytics',json={},headers=self.headers).status_code,405)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.client.get(endpoint).status_code,403)

    def test_analytics_counts_real_driver_status_edits_and_preserves_after_recovery(self):
        from werkzeug.security import generate_password_hash
        from hub_manager_analytics import TZ
        from datetime import datetime
        with self.m.conn() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash('TestPassword!123'),self.driver))
        courier=self.m.app.test_client()
        r=courier.post('/api/login',json={'email':'driver'+self.email,'password':'TestPassword!123'})
        self.assertEqual(r.status_code,200,r.json)
        headers={'X-CSRF-Token':courier.get('/api/bootstrap').json['csrf']}
        ids=[]
        for outcome in ('Livré','Annulé','Intéressé','Reporté'):
            initial='Reçu par le livreur' if outcome=='Annulé' else 'En livraison'
            pid,_=self.parcel(None,initial,self.driver,self.hub);ids.append(pid)
            with self.m.conn() as c:
                self.m.event(c,pid,initial,'Remise physique au livreur',{'id':self.manager})
                reason=c.execute('SELECT code FROM ops_reasons WHERE active=1 ORDER BY code LIMIT 1').fetchone()
            if outcome in ('Livré','Reporté'):
                payload=dict(outcome=outcome,revision=0,request_key=uuid.uuid4().hex)
                if outcome=='Livré':
                    payload['simple_delivery']=True
                else:
                    self.assertIsNotNone(reason,'Fixture must provide an active reason for a postponed delivery')
                    payload.update(reason_code=reason['code'],next_attempt_at=datetime.now(TZ).date().isoformat())
                r=courier.post(f'/api/logistics/parcels/{pid}/attempts',json=payload,headers=headers)
            else:
                r=courier.patch(f'/api/parcels/{pid}',json=dict(status=outcome,revision=0,note='Résultat confirmé par le livreur'),headers=headers)
            self.assertEqual(r.status_code,200,r.json)
        day=datetime.now(TZ).date().isoformat()
        endpoint=f'/api/hub-manager-analytics?from={day}&to={day}'
        result=self.client.get(endpoint)
        self.assertEqual(result.status_code,200,result.json)
        row=result.json['rows'][0]
        self.assertEqual((row['assigned'],row['processed'],row['pending'],row['progress'],row['delivery_rate']),(4,4,0,100,25))
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM ops_attempts WHERE parcel_id IN (?,?,?,?)',ids).fetchone()[0],2)
        r=self.scan('receive',[(pid,1) for pid in ids[1:]],hub=self.hub)
        self.assertEqual(r.status_code,200,r.json)
        row=self.client.get(endpoint).json['rows'][0]
        self.assertEqual((row['assigned'],row['processed'],row['pending'],row['progress'],row['delivery_rate']),(1,1,0,100,100))
        self.assertEqual(sum(row['daily'].values()),1)
        evidence={p['parcel_id']:p['evidence_source'] for p in self.client.get(endpoint).json['parcels']}
        self.assertEqual(evidence[ids[0]],'attempt')
        self.assertTrue(all(pid not in evidence for pid in ids[1:]))

    def test_admin_hub_analytics_real_auth_filter_details_csv_and_manager_isolation(self):
        from datetime import datetime
        from hub_manager_analytics import TZ
        pid,tracking=self.parcel(None,'En livraison',self.driver,self.hub)
        other,foreign_tracking=self.parcel(None,'En livraison',self.other_driver,self.foreign)
        day=datetime.now(TZ).date().isoformat()
        endpoint=f'/api/admin-hub-analytics?from={day}&to={day}'
        self.assertEqual(self.m.app.test_client().get(endpoint).status_code,401)
        self.assertEqual(self.client.get(endpoint).status_code,403)
        admin=self.m.app.test_client()
        self.assertEqual(admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'}).status_code,200)
        result=admin.get(endpoint);self.assertEqual(result.status_code,200,result.json)
        ids={r['id'] for r in result.json['rows']}
        self.assertTrue({self.hub,self.foreign}.issubset(ids))
        self.assertTrue({tracking,foreign_tracking}.issubset({p['tracking'] for p in result.json['parcels']}))
        filtered=endpoint+'&hub_id='+str(self.hub)
        r=admin.get(filtered);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual([h['id'] for h in r.json['rows']],[self.hub])
        self.assertEqual({p['tracking'] for p in r.json['parcels']},{tracking})
        for view in ('general','hubs','daily'):
            r=admin.get(filtered+'&format=csv&view='+view)
            self.assertEqual(r.status_code,200)
            self.assertIn('text/csv',r.content_type)
            self.assertNotIn(foreign_tracking,r.data.decode())
        for extra in ('&driver_id=1','&hub_id=bad','&format=bad','&view=bad'):
            self.assertEqual(admin.get(endpoint+extra).status_code,400)
        self.assertEqual(admin.get(endpoint+'&hub_id=2147483647').status_code,404)
        self.assertEqual(admin.post('/api/admin-hub-analytics',json={}).status_code,405)
        manager=self.client.get(f'/api/hub-manager-analytics?from={day}&to={day}')
        self.assertEqual(manager.status_code,200,manager.json)
        self.assertEqual(manager.json['hub']['id'],self.hub)
        self.assertNotIn(foreign_tracking,str(manager.json))

    def test_admin_hub_full_receipt_real_csrf_and_manager_visibility(self):
        from hub_billing import generate, local_now
        self.parcel(None,'Livré',self.driver,self.hub)
        admin=self.m.app.test_client()
        self.assertEqual(admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'}).status_code,200)
        bootstrap=admin.get('/api/bootstrap').json;csrf={'X-CSRF-Token':bootstrap['csrf']}
        r=admin.put('/api/hub-billing/terms/'+str(self.hub),json=dict(mode='net',revision=0,delivered='12',returned='0',refused='0'),headers=csrf)
        self.assertEqual(r.status_code,200,r.json)
        with self.m.conn() as c:
            c.execute('BEGIN IMMEDIATE');generate(c,local_now(),bootstrap['user']['id'],'test:'+uuid.uuid4().hex)
            sid=c.execute('SELECT id FROM hub_billing_statements WHERE hub_id=?',(self.hub,)).fetchone()[0]
        endpoint=f'/api/hub-billing/{sid}/paid'
        payload=dict(amount_cents=8800,method='Espèces',reference='TEST-'+uuid.uuid4().hex,paid_on=local_now().date().isoformat(),confirmed=True,request_key=uuid.uuid4().hex)
        self.assertEqual(admin.post(endpoint,json=payload).status_code,403)
        self.assertEqual(self.client.post(endpoint,json=payload,headers=self.headers).status_code,403)
        r=admin.post(endpoint,json=payload,headers=csrf);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['invoice']['state'],'Paid')
        self.assertEqual(self.client.get(f'/api/hub-billing/{sid}').json['invoice']['state'],'Paid')
        self.assertEqual(admin.post(endpoint,json=payload,headers=csrf).json['already_recorded'],True)
        with self.m.conn() as c:
            row=c.execute("SELECT actor_id FROM audit_log WHERE action='hub_invoice_paid' AND entity_id=?",(str(sid),)).fetchone()
            self.assertEqual(row['actor_id'],bootstrap['user']['id'])

    def test_hub_billing_real_auth_scope_admin_controls_and_csrf(self):
        # Exercise the real manager capability allowlist, not only module decorators.
        r=self.client.get('/api/hub-billing')
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['hub']['id'],self.hub)
        self.assertNotIn('schedule',r.json)
        self.assertEqual(self.client.get('/api/hub-billing/preview').status_code,403)
        self.assertEqual(self.client.put('/api/hub-billing/terms/'+str(self.hub),json={},headers=self.headers).status_code,403)
        admin=self.m.app.test_client()
        self.assertEqual(admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'}).status_code,200)
        payload=dict(mode='gross',revision=0,delivered='10',returned='4',refused='3')
        endpoint='/api/hub-billing/terms/'+str(self.hub)
        self.assertEqual(admin.put(endpoint,json=payload).status_code,403)
        csrf=admin.get('/api/bootstrap').json['csrf']
        r=admin.put(endpoint,json=payload,headers={'X-CSRF-Token':csrf})
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(admin.get('/api/hub-billing').status_code,200)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.client.get('/api/hub-billing').status_code,403)

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

    def test_driver_cannot_attempt_parcel_still_in_hub_stock(self):
        from werkzeug.security import generate_password_hash
        with self.m.conn() as c:
            c.execute('UPDATE users SET password=? WHERE id=?',(generate_password_hash('TestPassword!123'),self.driver))
        courier=self.m.app.test_client()
        login=courier.post('/api/login',json={'email':'driver'+self.email,'password':'TestPassword!123'})
        self.assertEqual(login.status_code,200,login.json)
        headers={'X-CSRF-Token':courier.get('/api/bootstrap').json['csrf']}
        pid,_=self.parcel(self.hub,'En livraison',self.driver,self.hub)
        response=courier.post(
            f'/api/logistics/parcels/{pid}/attempts',
            json={'outcome':'Reporté','revision':0,'request_key':uuid.uuid4().hex},
            headers=headers,
        )
        self.assertEqual(response.status_code,409,response.json)
        with self.m.conn() as c:
            row=c.execute('SELECT status,current_hub_id,ops_revision FROM parcels WHERE id=?',(pid,)).fetchone()
            attempts=c.execute('SELECT COUNT(*) FROM ops_attempts WHERE parcel_id=?',(pid,)).fetchone()[0]
        self.assertEqual(tuple(row),('En livraison',self.hub,0))
        self.assertEqual(attempts,0)

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

    def test_sent_transfers_remain_visible_with_manifest_without_mutation_rights(self):
        from werkzeug.security import generate_password_hash
        unique=uuid.uuid4().hex
        with self.m.conn() as c:
            old_central=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
            old_city_hub=c.execute('SELECT hub_id FROM cities WHERE id=?',(self.city,)).fetchone()[0]
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(self.hub),))
            c.execute('UPDATE cities SET hub_id=? WHERE id=?',(self.foreign,self.city))
            outside=c.execute("INSERT INTO ops_hubs(name,city_id,address,created_at) VALUES('Unrelated',?,'',?)",(self.city,self.m.now())).lastrowid
            for role,hub in (('destination',self.foreign),('unrelated',outside)):
                c.execute("INSERT INTO users(name,email,password,role,agent_hub_id,created_at) VALUES(?,?,?,'hub_manager',?,?)",(role,role+unique+'@example.test',generate_password_hash('TransferTest!123'),hub,self.m.now()))
        def restore():
            with self.m.conn() as c:
                if old_central:c.execute("UPDATE settings SET value=? WHERE key='central_hub_id'",(old_central[0],))
                else:c.execute("DELETE FROM settings WHERE key='central_hub_id'")
                c.execute('UPDATE cities SET hub_id=? WHERE id=?',(old_city_hub,self.city))
                c.execute('UPDATE ops_hubs SET active=1 WHERE id=?',(self.hub,))
        self.addCleanup(restore)
        browsers={};headers={}
        for n,role in enumerate(('destination','unrelated')):
            browser=self.m.app.test_client()
            r=browser.post('/api/login',json={'email':role+unique+'@example.test','password':'TransferTest!123'},environ_overrides={'REMOTE_ADDR':f'10.71.0.{n+1}'})
            self.assertEqual(r.status_code,200,r.json)
            browsers[role]=browser;headers[role]={'X-CSRF-Token':browser.get('/api/bootstrap').json['csrf']}
        destination=browsers['destination'];unrelated=browsers['unrelated']
        first,second=self.parcel(self.hub),self.parcel(self.hub)
        ids={first[0],second[0]};trackings={first[1],second[1]}
        foreign,_=self.parcel(outside)
        with self.m.conn() as c:c.execute('UPDATE parcels SET origin_hub_id=? WHERE id=?',(self.hub,foreign))
        created=self.post('logistics/documents',dict(kind='transfer',palette_purpose='standard',source_hub_id=self.hub,destination_hub_id=self.foreign,parcel_ids=list(ids),note=''))
        self.assertEqual(created.status_code,200,created.json)
        did=created.json['id'];path=f'/api/logistics/documents/{did}'
        self.assertEqual(destination.get(path).json['lines'],[])
        self.assertEqual(unrelated.get(path).status_code,404)
        self.assertEqual(self.post(f'logistics/documents/{did}/departure-scan',dict(tracking=first[1])).status_code,200)
        # Partial departure retains the source manifest, but only dispatched lines reach the destination.
        self.assertEqual({l['tracking'] for l in self.client.get(path).json['lines']},trackings)
        self.assertEqual({l['tracking'] for l in destination.get(path).json['lines']},{first[1]})
        self.assertEqual(destination.get(f'/api/parcels/{first[0]}').status_code,404)
        self.assertEqual(self.post(f'logistics/documents/{did}/departure-scan',dict(tracking=second[1])).status_code,200)
        def assert_source_tracking():
            rows={p['id']:p for p in self.client.get('/api/bootstrap').json['parcels']}
            self.assertTrue(ids <= rows.keys())
            self.assertNotIn(foreign,rows)  # An origin_hub_id alone is never departure evidence.
            for pid in ids:
                self.assertTrue(rows[pid]['hub_read_only'])
                self.assertFalse(rows[pid]['hub_status_editable'])
                detail=self.client.get(f'/api/parcels/{pid}')
                self.assertEqual(detail.status_code,200,detail.json)
                r=self.client.patch(f'/api/parcels/{pid}',json={'status':'Reporté','revision':detail.json['parcel']['ops_revision']},headers=self.headers)
                self.assertEqual(r.status_code,404,r.json)
            doc=self.client.get(path)
            self.assertEqual(doc.status_code,200,doc.json)
            self.assertEqual({l['tracking'] for l in doc.json['lines']},trackings)
            self.assertEqual(doc.json['count'],2)
            listed=next(d for d in self.client.get('/api/logistics/documents').json if d['id']==did)
            self.assertEqual({l['tracking'] for l in listed['lines']},trackings)
        assert_source_tracking()
        for pid in ids:
            self.assertEqual(unrelated.get(f'/api/parcels/{pid}').status_code,404)
        candidates=self.client.get('/api/logistics/palette-candidates',query_string={'source_hub_id':self.hub,'destination_hub_id':self.foreign,'mode':'standard'})
        self.assertEqual(candidates.status_code,200,candidates.json)
        self.assertFalse(ids & {p['id'] for p in candidates.json['rows']})
        for pid,tracking in (first,second):
            r=destination.post(path+'/receive',json={'tracking':tracking},headers=headers['destination'])
            self.assertEqual(r.status_code,200,r.json)
        assert_source_tracking()
        self.assertEqual(self.client.get(path).json['status'],'Reçu')
        self.assertEqual({l['tracking'] for l in destination.get(path).json['lines']},trackings)
        with self.m.conn() as c:
            # History is retained even after a later onward movement; no transfer line is active anymore.
            c.execute('UPDATE parcels SET current_hub_id=? WHERE id IN (?,?)',(outside,first[0],second[0]))
        assert_source_tracking()
        self.assertEqual({l['tracking'] for l in destination.get(path).json['lines']},trackings)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.client.get(path).status_code,403)
        self.assertFalse(ids & {p['id'] for p in self.client.get('/api/bootstrap').json['parcels']})

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

    def test_manager_driver_billing_documents_payments_and_foreign_scope(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self.parcel(None,'Livré',self.driver,self.hub)
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        r=self.post(f"driver-finance/preview/{r.json['token']}/confirm",{});self.assertEqual(r.status_code,200,r.json)
        sid=r.json['statement_id'];endpoint=f'/api/billing/livreur/{sid}'
        r=self.client.get('/api/billing?kind=livreur&size=10');self.assertEqual(r.status_code,200,r.json)
        self.assertIn(sid,[x['id'] for x in r.json['rows']])
        self.assertEqual(self.client.get('/api/billing?kind=client').status_code,403)
        for fmt in ('csv','pdf'):
            r=self.client.get(endpoint+'/'+fmt);self.assertEqual(r.status_code,200,r.data[:100])
            if fmt=='pdf':
                from pypdf import PdfReader
                from io import BytesIO
                text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(r.data)).pages)
                with self.m.conn() as c:hubname=c.execute('SELECT name FROM ops_hubs WHERE id=?',(self.hub,)).fetchone()[0]
                self.assertIn(hubname,text)
                self.assertIn('Local Driver',text)
                self.assertNotIn('Olivraison',text)
                self.assertNotIn('002323896000034',text)
        r=self.client.get('/api/billing/export?kind=livreur');self.assertEqual(r.status_code,200)
        info=self.client.get(endpoint).json['invoice']
        payload=dict(version=info['version'],request_key=uuid.uuid4().hex,confirmed=True,method='Espèces',reference='test-'+uuid.uuid4().hex,payment_date=datetime.now(ZoneInfo('Africa/Casablanca')).date().isoformat())
        self.assertEqual(self.client.post(endpoint+'/settle',json=payload).status_code,403)
        r=self.client.post(endpoint+'/settle',json=payload,headers=self.headers);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['invoice']['state'],'Paid')
        self.assertTrue(self.client.post(endpoint+'/settle',json=payload,headers=self.headers).json['already_recorded'])
        with self.m.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM driver_transactions WHERE statement_id=?',(sid,)).fetchone()[0],2)
            self.assertEqual(c.execute('SELECT created_by FROM driver_transactions WHERE statement_id=? LIMIT 1',(sid,)).fetchone()[0],self.manager)
        current=self.client.get(endpoint).json['invoice']
        correction=dict(version=current['version'],request_key=uuid.uuid4().hex,confirmed=True,reason='Erreur de saisie du reçu')
        r=self.client.post(endpoint+'/reopen',json=correction,headers=self.headers);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['invoice']['state'],'Not Paid')
        tx=dict(kind='cash',amount='1',method='Espèces',reference=uuid.uuid4().hex,paid_on=payload['payment_date'],note='',request_key=uuid.uuid4().hex)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/transactions',tx).status_code,200)
        self.assertEqual(self.client.get(endpoint).json['invoice']['state'],'Partiel')
        with self.m.conn() as c:c.execute('UPDATE driver_statements SET hub_id=? WHERE id=?',(self.foreign,sid))
        for suffix in ('','/csv','/pdf'):
            self.assertEqual(self.client.get(endpoint+suffix).status_code,404)
        self.assertEqual(self.client.post(endpoint+'/settle',json=payload,headers=self.headers).status_code,404)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/transactions',tx).status_code,404)
        r=self.client.get('/api/billing?kind=livreur&size=10');self.assertNotIn(sid,[x['id'] for x in r.json['rows']])
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/cancel',{}).status_code,403)
        self._exercise_new_cmd_stock_lifecycle()

    def test_invoice_scope_confirm_and_no_cancel_permissions(self):
        local,_=self.parcel(None,'Livré',self.driver,self.hub)
        self.parcel(None,'Livré',self.driver,self.foreign)
        self.parcel(None,'Livré',self.driver) # unknown legacy evidence: Admin only
        r=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(r.status_code,200,r.json)
        self.assertEqual([p['parcel_id'] for p in r.json['lines']],[local]);token=r.json['token']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertEqual(r.status_code,200,r.json);sid=r.json['statement_id']
        r=self.post(f'driver-finance/preview/{token}/confirm',{});self.assertTrue(r.json['already_created'])
        r=self.client.get(f'/api/driver-finance/statements/{sid}');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json['statement']['hub_id'],self.hub)
        self.assertEqual(self.post(f'driver-finance/statements/{sid}/transactions',{}).status_code,400)
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

    def test_manager_cannot_close_delivery_or_return_via_generic_patch(self):
        for target in ('Livré','Retourné'):
            with self.subTest(target=target):
                pid,_=self.parcel(self.hub,'En livraison',self.driver,self.hub)
                r=self.status_patch(pid,target)
                self.assertEqual(r.status_code,409,r.json)
                with self.m.conn() as c:
                    row=c.execute('SELECT status,ops_revision FROM parcels WHERE id=?',(pid,)).fetchone()
                    self.assertEqual(tuple(row),('En livraison',0))
        # Ordinary non-final corrections remain available with the existing reason checks.
        pid,_=self.parcel(self.hub,'Refusé',self.driver,self.hub)
        self.assertEqual(self.status_patch(pid,'Reporté').status_code,200)

    def test_manager_cannot_edit_parcel_after_physical_handoff_to_driver(self):
        pid,_=self.parcel(self.hub)
        self.assertEqual(self.scan('assign',[(pid,0)]).status_code,200)
        row=next(p for p in self.client.get('/api/bootstrap').json['parcels'] if p['id']==pid)
        self.assertFalse(row['hub_status_editable'])
        # The Hub may track its dispatched parcel, but cannot alter it after custody passed to the driver.
        r=self.status_patch(pid,'Reporté',revision=1)
        self.assertEqual(r.status_code,409,r.json)
        self.assertEqual(self.status_patch(pid,'Retourné',revision=1).status_code,409)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1).status_code,409)
        row=self.client.get(f'/api/parcels/{pid}').json['parcel']
        self.assertFalse(row['hub_status_editable'])
        self.assertEqual(row['status'],'Reçu par le livreur')
        with self.m.conn() as c:
            # Rejected status edits must not create successful-change audit entries.
            self.assertEqual(c.execute("SELECT count(*) FROM audit_log WHERE entity_id=? AND action='hub_parcel_status_changed'",(str(pid),)).fetchone()[0],0)

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

    def test_admin_client_invoice_filters_and_morocco_local_date_window(self):
        from datetime import datetime, timezone
        from zoneinfo import ZoneInfo
        from werkzeug.security import generate_password_hash
        unique=uuid.uuid4().hex
        with self.m.conn() as c:
            admin_email='billing-admin-'+unique+'@example.test'
            c.execute("INSERT INTO users(name,email,password,role,created_at) VALUES('Billing Admin',?,?,'admin',?)",
                      (admin_email,generate_password_hash('TestPassword!123'),self.m.now()))
            first=c.execute("INSERT INTO users(name,email,password,role,company,created_at) VALUES(?,?,'unused','client',?,?)",
                            ('Client A','billing-a-'+unique+'@example.test','Vitex '+unique,self.m.now())).lastrowid
            second=c.execute("INSERT INTO users(name,email,password,role,company,created_at) VALUES(?,?,'unused','client',?,?)",
                             ('Client B','billing-b-'+unique+'@example.test','RayanShop '+unique,self.m.now())).lastrowid
            local=datetime(2026,1,1,0,30,tzinfo=ZoneInfo('Africa/Casablanca'))
            utc_created=local.astimezone(timezone.utc).isoformat(timespec='seconds')
            paid=c.execute("INSERT INTO invoices(client_id,cod,fees,total,status,created_at) VALUES(?,100,10,90,'Réglée',?)",(first,utc_created)).lastrowid
            unpaid=c.execute("INSERT INTO invoices(client_id,cod,fees,total,status,created_at) VALUES(?,100,10,90,'À régler','2026-01-01T02:00:00+00:00')",(first,)).lastrowid
            other=c.execute("INSERT INTO invoices(client_id,cod,fees,total,status,created_at) VALUES(?,100,10,90,'Réglée','2026-01-01T00:30:00+00:00')",(second,)).lastrowid
        admin=self.m.app.test_client()
        login=admin.post('/api/login',json={'email':admin_email,'password':'TestPassword!123'})
        self.assertEqual(login.status_code,200,login.json)
        base='/api/billing?kind=client'
        r=admin.get(base+f'&party={first}&state=Paid')
        self.assertEqual(r.status_code,200,r.json)
        self.assertEqual([x['id'] for x in r.json['rows']],[paid])
        r=admin.get(base+f'&q=FAC-{other:04d}')
        self.assertEqual([x['id'] for x in r.json['rows']],[other])
        r=admin.get(base+'&from=2026-01-01T00%3A00&to=2026-01-01T00%3A59')
        self.assertIn(paid,[x['id'] for x in r.json['rows']])
        self.assertNotIn(unpaid,[x['id'] for x in r.json['rows']])
        r=admin.get(base+'&from=2026-01-01T00%3A00&to=2026-01-01T00%3A59&party='+str(first)+'&state=Paid')
        self.assertEqual([x['id'] for x in r.json['rows']],[paid])

    def _exercise_new_cmd_stock_lifecycle(self):
        from werkzeug.security import generate_password_hash
        unique=uuid.uuid4().hex
        client_email='stock-client-'+unique+'@example.test';admin_email='stock-admin-'+unique+'@example.test'
        with self.m.conn() as c:
            previous=c.execute("SELECT value FROM settings WHERE key='central_hub_id'").fetchone()
            previous_central=previous['value'] if previous else None
            c.execute("INSERT INTO settings(key,value) VALUES('central_hub_id',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(str(self.hub),))
            client_id=c.execute("INSERT INTO users(name,email,password,role,company,created_at) VALUES(?, ?, ?,'client', ?,?)",
                                ('Stock Client',client_email,generate_password_hash('ClientPass!123'),'Stock Shop',self.m.now())).lastrowid
            c.execute("INSERT INTO users(name,email,password,role,created_at) VALUES(?,?,?,'admin',?)",
                      ('Stock Admin',admin_email,generate_password_hash('AdminPass!123'),self.m.now()))
        def restore_central_setting():
            with self.m.conn() as c:
                if previous_central is None:c.execute("DELETE FROM settings WHERE key='central_hub_id'")
                else:c.execute("UPDATE settings SET value=? WHERE key='central_hub_id'",(previous_central,))
        self.addCleanup(restore_central_setting)
        client=self.m.app.test_client();admin=self.m.app.test_client()
        self.assertEqual(client.post('/api/login',json={'email':client_email,'password':'ClientPass!123'},environ_overrides={'REMOTE_ADDR':'10.61.0.1'}).status_code,200)
        self.assertEqual(admin.post('/api/login',json={'email':admin_email,'password':'AdminPass!123'},environ_overrides={'REMOTE_ADDR':'10.62.0.1'}).status_code,200)
        client_headers={'X-CSRF-Token':client.get('/api/bootstrap').json['csrf']}
        admin_headers={'X-CSRF-Token':admin.get('/api/bootstrap').json['csrf']}
        created=client.post('/api/products',json={'name':'Stock Item','reference':'SKU-'+unique[:10]},headers=client_headers)
        self.assertEqual(created.status_code,200,created.json)
        with self.m.conn() as c:product_id=c.execute('SELECT id FROM products WHERE reference=?',('SKU-'+unique[:10],)).fetchone()[0]
        stocked=admin.post(f'/api/products/{product_id}/movements',json={'delta':10,'note':'استلام ابتدائي'},headers=admin_headers)
        self.assertEqual(stocked.status_code,200,stocked.json)
        base={'recipient':'Test Recipient','phone':'0612345678','address':'Agadir','city_id':self.city,'amount':'120','note':'','items':[{'product_id':product_id,'quantity':3}]}
        # A regular CMD stores a product description only and must not move stock.
        normal=client.post('/api/parcels',json={**base,'product':'Stock Item × 3'},headers=client_headers)
        self.assertEqual(normal.status_code,200,normal.json)
        normal_id=next(p['id'] for p in client.get('/api/bootstrap').json['parcels'] if p['tracking']==normal.json['tracking'])
        normal_label=client.post('/api/labels',json={'ids':[normal_id]},headers=client_headers)
        self.assertEqual(normal_label.status_code,200,normal_label.json)
        self.assertFalse(normal_label.json[0]['stock_return_required'])
        self.assertEqual(normal_label.json[0]['stock_lines'],[])
        # Stock CMD reserves first; physical deduction happens at Central when Admin creates the parcel.
        prep=client.post('/api/fulfillment/orders',json={**base,'request_key':uuid.uuid4().hex},headers=client_headers)
        self.assertEqual(prep.status_code,200,prep.json)
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual((product['quantity'],product['reserved'],product['available']),(10,3,7))
        cancelled=client.post(f"/api/fulfillment/orders/{prep.json['id']}/cancel",json={'reason':'Client annule'},headers=client_headers)
        self.assertEqual(cancelled.status_code,200,cancelled.json)
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual((product['quantity'],product['reserved'],product['available']),(10,0,10))
        prep=client.post('/api/fulfillment/orders',json={**base,'request_key':uuid.uuid4().hex},headers=client_headers)
        self.assertEqual(prep.status_code,200,prep.json)
        other_hub=admin.post(f"/api/fulfillment/orders/{prep.json['id']}/ship",json={'hub_id':self.foreign,'checked':True},headers=admin_headers)
        self.assertEqual(other_hub.status_code,409,other_hub.json)
        shipped=admin.post(f"/api/fulfillment/orders/{prep.json['id']}/ship",json={'hub_id':self.hub,'checked':True},headers=admin_headers)
        self.assertEqual(shipped.status_code,200,shipped.json)
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual((product['quantity'],product['reserved'],product['available']),(7,0,7))
        detail=client.get(f"/api/fulfillment/orders/{prep.json['id']}").json
        self.assertEqual(detail['status'],'Préparé');self.assertTrue(detail['tracking'])
        self.assertEqual(detail['dispatch_hub_id'],self.hub);self.assertTrue(detail['stock_deducted_at'])
        stock_label=client.post('/api/labels',json={'ids':[detail['parcel_id']]},headers=client_headers)
        self.assertEqual(stock_label.status_code,200,stock_label.json)
        self.assertTrue(stock_label.json[0]['stock_return_required'])
        self.assertEqual(stock_label.json[0]['stock_order_id'],prep.json['id'])
        self.assertEqual(stock_label.json[0]['stock_lines'],[{'sku':'SKU-'+unique[:10],'name':'Stock Item','quantity':3}])
        with self.m.conn() as c:
            deduction=c.execute('SELECT delta,note FROM movements WHERE fulfillment_order_id=?',(prep.json['id'],)).fetchall()
            self.assertEqual([r['delta'] for r in deduction],[-3])
            self.assertIn('CMD stock créée',deduction[0]['note'])
        # A physical driver scan is not the inventory trigger; the stock was already debited at preparation.
        dispatch={'mode':'assign','scans':[{'parcel_id':detail['parcel_id'],'revision':0}],'hub_id':None,'request_key':uuid.uuid4().hex,'confirmed':True}
        departed=admin.post(f"/api/drivers-workspace/{self.driver}/scan-batch",json=dispatch,headers=admin_headers)
        self.assertEqual(departed.status_code,200,departed.json)
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual(product['quantity'],7)
        # The actual return palette runs from a secondary Hub to Central; only its receive scan restores stock.
        with self.m.conn() as c:
            c.execute("UPDATE parcels SET status='Refusé',current_hub_id=?,ops_revision=ops_revision+1 WHERE id=?",(self.foreign,detail['parcel_id']))
        palette=admin.post('/api/logistics/documents',json={
            'kind':'transfer','palette_purpose':'return_to_central','source_hub_id':self.foreign,
            'destination_hub_id':self.hub,'parcel_ids':[detail['parcel_id']],
            'transport':'Test return','tracking_code':'RET-'+unique[:8],'lots':1,'note':''
        },headers=admin_headers)
        self.assertEqual(palette.status_code,200,palette.json)
        did=palette.json['id']
        scanned_out=admin.post(f'/api/logistics/documents/{did}/departure-scan',json={'tracking':detail['tracking']},headers=admin_headers)
        self.assertEqual(scanned_out.status_code,200,scanned_out.json)
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual(product['quantity'],7)
        manifest=admin.get(f'/api/reception-collection/transfer/{did}')
        self.assertEqual(manifest.status_code,200,manifest.json)
        line_ids=[line['id'] for line in manifest.json['lines'] if not line['received_at']]
        receive_payload={'snapshot':manifest.json['snapshot'],'line_ids':line_ids,'confirmed':True,'request_key':uuid.uuid4().hex}
        received=admin.post(f'/api/reception-collection/transfer/{did}',json=receive_payload,headers=admin_headers)
        self.assertEqual(received.status_code,200,received.json)
        self.assertEqual(received.json['stock_restocked'],[detail['tracking']])
        product=next(p for p in client.get('/api/products').json if p['id']==product_id)
        self.assertEqual((product['quantity'],product['reserved'],product['available']),(10,0,10))
        self.assertTrue(client.get(f"/api/fulfillment/orders/{prep.json['id']}").json['stock_restocked_at'])
        replay=admin.post(f'/api/reception-collection/transfer/{did}',json=receive_payload,headers=admin_headers)
        self.assertEqual(replay.status_code,200,replay.json)
        self.assertTrue(replay.json['replayed'])
        with self.m.conn() as c:
            restocks=c.execute('SELECT delta,note FROM movements WHERE fulfillment_order_id=? AND delta>0',(prep.json['id'],)).fetchall()
            self.assertEqual(len(restocks),1)
            self.assertEqual(restocks[0]['delta'],3)
            self.assertIn('Retour palette reçu',restocks[0]['note'])
        self.assertEqual(admin.post(f"/api/fulfillment/orders/{prep.json['id']}/restock",json={'checked':True,'reason':'manual'},headers=admin_headers).status_code,409)

    def test_hub_manager_can_access_hub_invoice_list_with_canonical_role(self):
        response=self.client.get('/api/logistics/hub/invoices')
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['hub']['id'],self.hub)
        self.assertEqual(response.json['invoices'],[])
        self.assertTrue(response.json['read_only'])

    def test_manager_finance_overview_and_export_are_own_hub_only(self):
        self.parcel(None,'Livré',self.driver,self.hub)
        preview=self.post('driver-finance/preview',dict(driver_id=self.driver))
        self.assertEqual(preview.status_code,200,preview.json)
        issued=self.post(f"driver-finance/preview/{preview.json['token']}/confirm",{})
        self.assertEqual(issued.status_code,200,issued.json)
        sid=issued.json['statement_id']
        listing=self.client.get('/api/driver-finance')
        self.assertEqual(listing.status_code,200,listing.json)
        self.assertEqual([s['id'] for s in listing.json['statements']],[sid])
        self.assertGreater(listing.json['summary']['cod_cents'],0)
        exported=self.client.get('/api/driver-finance/export')
        self.assertEqual(exported.status_code,200)
        self.assertIn(f'DRV-{sid:06d}',exported.get_data(as_text=True))
        with self.m.conn() as c:c.execute('UPDATE driver_statements SET hub_id=? WHERE id=?',(self.foreign,sid))
        listing=self.client.get('/api/driver-finance')
        self.assertEqual(listing.status_code,200,listing.json)
        self.assertEqual(listing.json['statements'],[])
        self.assertEqual(listing.json['summary']['cod_cents'],0)
        self.assertNotIn(f'DRV-{sid:06d}',self.client.get('/api/driver-finance/export').get_data(as_text=True))
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.client.get('/api/driver-finance').status_code,403)
        self.assertEqual(self.client.get('/api/driver-finance/export').status_code,403)

    def test_manager_configures_only_own_driver_terms_then_issues_statement(self):
        with self.m.conn() as c:c.execute('DELETE FROM driver_terms WHERE driver_id=?',(self.driver,))
        r=self.client.get('/api/driver-finance/terms');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual({d['id'] for d in r.json},{self.driver})
        self.assertIsNone(r.json[0]['terms'])
        data=dict(mode='gross',delivered='15',returned='5',refused='3',revision=0,overrides=[])
        endpoint=f'/api/driver-finance/terms/{self.driver}'
        self.assertEqual(self.client.put(endpoint,json=data).status_code,403)
        self.assertEqual(self.client.put(f'/api/driver-finance/terms/{self.other_driver}',json=data,headers=self.headers).status_code,404)
        r=self.client.put(endpoint,json=data,headers=self.headers);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.client.put(endpoint,json=data,headers=self.headers).status_code,409)
        r=self.client.get(endpoint+'/history');self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(r.json[0]['actor_id'],self.manager)
        self.assertEqual(self.client.get(f'/api/driver-finance/terms/{self.other_driver}/history').status_code,404)
        pid,_=self.parcel(None,'Refusé',self.driver,self.hub)
        preview=self.post('driver-finance/preview',dict(driver_id=self.driver));self.assertEqual(preview.status_code,200,preview.json)
        issued=self.post(f"driver-finance/preview/{preview.json['token']}/confirm",{});self.assertEqual(issued.status_code,200,issued.json)
        sid=issued.json['statement_id']
        before=self.client.get(f'/api/driver-finance/statements/{sid}').json
        r=self.client.put(endpoint,json={**data,'revision':1,'refused':'9'},headers=self.headers);self.assertEqual(r.status_code,200,r.json)
        self.assertEqual(self.client.get(f'/api/driver-finance/statements/{sid}').json,before)
        with self.m.conn() as c:c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        self.assertEqual(self.client.put(endpoint,json={**data,'revision':2},headers=self.headers).status_code,403)

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
        # A Hub Manager cannot close delivery through generic PATCH, even with a valid OTP.
        # Final delivery must use the logistics attempt flow or an Admin-supervised correction.
        self.assertEqual(self.status_patch(pid,'Livré',revision=1).status_code,409)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='9999').status_code,409)
        self.assertEqual(self.status_patch(pid,'Livré',revision=1,otp='1234').status_code,409)

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

    def test_admin_partial_account_edit_preserves_activation_and_skips_unrelated_hub_validation(self):
        admin=self.m.app.test_client()
        login=admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'})
        self.assertEqual(login.status_code,200,login.json)
        csrf=admin.get('/api/bootstrap').json['csrf']
        headers={'X-CSRF-Token':csrf}

        # Editing ordinary profile fields must not silently deactivate an active driver.
        response=admin.patch(f'/api/users/{self.driver}',json={
            'name':'Driver renamed','phone':'0612345678','company':'ORIENTAL24'
        },headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        with self.m.conn() as c:
            driver=c.execute('SELECT active,driver_blocked,name FROM users WHERE id=?',(self.driver,)).fetchone()
            self.assertEqual((driver['active'],driver['driver_blocked'],driver['name']),(1,0,'Driver renamed'))

        # A name/phone edit should still work if the manager's Hub is inactive;
        # only an explicit activation or Hub reassignment should validate that Hub.
        with self.m.conn() as c:
            c.execute('UPDATE ops_hubs SET active=0 WHERE id=?',(self.hub,))
        response=admin.patch(f'/api/users/{self.manager}',json={
            'name':'Manager renamed','phone':'0698765432','company':'ORIENTAL24'
        },headers=headers)
        self.assertEqual(response.status_code,200,response.json)
        with self.m.conn() as c:
            manager=c.execute('SELECT active,agent_hub_id,name FROM users WHERE id=?',(self.manager,)).fetchone()
            self.assertEqual((manager['active'],manager['agent_hub_id'],manager['name']),(1,self.hub,'Manager renamed'))

if __name__=='__main__': unittest.main()
