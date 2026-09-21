"""Session revocation, auth throttling, production guardrails and offline recovery."""
import unittest,os,json,time,sqlite3,tempfile,subprocess,sys,hashlib
from pathlib import Path
from contextlib import contextmanager

@contextmanager
def db(path):
    c=sqlite3.connect(path)
    try:
        yield c
        c.commit()
    finally:c.close()

from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from flask import Flask
import test_app as f
from runtime import configure
from manage import snapshot

class SecurityTests(unittest.TestCase):
    setUp=f.PlatformTests.setUp
    data=f.PlatformTests.data
    mutate=f.PlatformTests.mutate
    def signin(self,email='client@oriental24.ma',password='Oriental24!Demo',headers=None):
        c=f.system.app.test_client();r=c.post('/api/login',json={'email':email,'password':password},headers=headers);return c,r
    def sessions(self,cl):return cl.get('/api/security/sessions').json['sessions']
    def test_missing_csrf_in_cookie_does_not_allow_missing_header(self):
        with self.admin.session_transaction() as s:s.pop('csrf')
        self.assertEqual(self.admin.patch('/api/settings',json={'announcement':'blocked'}).status_code,403)
    def test_session_token_is_not_in_list_or_database(self):
        with self.client.session_transaction() as s:raw=s['sid']
        content=self.client.get('/api/security/sessions').get_data(as_text=True)
        self.assertNotIn(raw,content);self.assertNotIn('token_hash',content)
        with f.system.conn() as c:
            row=c.execute('SELECT token_hash FROM auth_sessions WHERE user_id=2').fetchone()
            self.assertEqual(row[0],hashlib.sha256(raw.encode()).hexdigest())
    def test_other_session_revoke_blocks_copied_cookie(self):
        other,_=self.signin();copy=f.system.app.test_client();copy.set_cookie('session',other.get_cookie('session').value)
        sid=next(s['id'] for s in self.sessions(other) if s['current'])
        self.assertEqual(self.mutate(self.client,'/api/security/sessions/'+str(sid),{},'delete').status_code,200)
        self.assertEqual(other.get('/api/bootstrap').status_code,401);self.assertEqual(copy.get('/api/bootstrap').status_code,401)
        self.assertEqual(self.client.get('/api/bootstrap').status_code,200)
        self.assertTrue(self.mutate(self.client,'/api/security/sessions/'+str(sid),{},'delete').json['already_revoked'])
    def test_scope_csrf_and_current_revocation(self):
        sid=next(s['id'] for s in self.sessions(self.client) if s['current'])
        self.assertEqual(self.mutate(self.admin,'/api/security/sessions/'+str(sid),{},'delete').status_code,404)
        self.assertEqual(self.client.delete('/api/security/sessions/'+str(sid),json={}).status_code,403)
        self.assertTrue(self.mutate(self.client,'/api/security/sessions/'+str(sid),{},'delete').json['current'])
        self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
    def test_revoke_all_other_sessions_requires_password(self):
        other,_=self.signin();url='/api/security/sessions/revoke-others'
        self.assertEqual(self.mutate(self.client,url,{'current_password':'wrong'}).status_code,400)
        self.assertEqual(other.get('/api/bootstrap').status_code,200)
        self.assertEqual(self.mutate(self.client,url,{'current_password':'Oriental24!Demo'}).status_code,200)
        self.assertEqual(other.get('/api/bootstrap').status_code,401)
        self.assertEqual(self.client.get('/api/bootstrap').status_code,200)
    def test_logout_invalidates_replayed_cookie(self):
        copy=f.system.app.test_client();copy.set_cookie('session',self.client.get_cookie('session').value)
        self.mutate(self.client,'/api/logout',{})
        self.assertEqual(copy.get('/api/bootstrap').status_code,401)
    def test_password_change_rotates_current_and_revokes_all_old(self):
        other,_=self.signin();copy=f.system.app.test_client();copy.set_cookie('session',self.client.get_cookie('session').value)
        before=self.data(self.client)['csrf']
        r=self.mutate(self.client,'/api/profile',dict(name='Client test',phone='0600000000',company='Test',current_password='Oriental24!Demo',password='LongNewTestPassword!14'),'patch')
        self.assertEqual(r.status_code,200,r.json);self.assertNotEqual(self.data(self.client)['csrf'],before)
        for c in [other,copy]:self.assertEqual(c.get('/api/bootstrap').status_code,401)
        self.assertEqual(self.signin(password='LongNewTestPassword!14')[1].status_code,200)
    def test_admin_reset_revokes_sessions(self):
        d=dict(name='Client test',phone='0600000000',company='Test',active=True,password='AdminChangedPassword!')
        self.assertEqual(self.mutate(self.admin,'/api/users/2',d,'patch').status_code,200)
        self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
    def test_deactivate_then_reactivate_does_not_revive_session(self):
        copy=f.system.app.test_client();copy.set_cookie('session',self.client.get_cookie('session').value)
        d=dict(name='Client test',phone='0600000000',company='Test',active=False)
        self.mutate(self.admin,'/api/users/2',d,'patch');d['active']=True;self.mutate(self.admin,'/api/users/2',d,'patch')
        self.assertEqual(copy.get('/api/bootstrap').status_code,401)
    def test_idle_and_absolute_expiry_on_server(self):
        with f.system.conn() as c:c.execute('UPDATE auth_sessions SET last_seen=? WHERE user_id=2',(int(time.time())-f.system.app.config['AUTH_IDLE_SECONDS']-1,))
        self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
        other,_=self.signin()
        with f.system.conn() as c:c.execute('UPDATE auth_sessions SET expires_at=? WHERE user_id=2',(int(time.time())-1,))
        self.assertEqual(other.get('/api/bootstrap').status_code,401)
    def test_old_signed_cookie_without_server_session_refused(self):
        guest=f.system.app.test_client()
        with guest.session_transaction() as s:s['uid']=1;s['csrf']='old'
        self.assertEqual(guest.get('/api/bootstrap').status_code,401)
    def test_login_throttle_and_untrusted_forwarded_ip(self):
        for n in range(5):self.assertEqual(self.signin(password='wrong',headers={'X-Forwarded-For':'198.51.100.'+str(n+1)})[1].status_code,401)
        r=self.signin()[1];self.assertEqual(r.status_code,429);self.assertTrue(1<=int(r.headers['Retry-After'])<=900)
        with patch('security.time.time',return_value=time.time()+901):self.assertEqual(self.signin()[1].status_code,200)
    def test_parallel_guesses_cannot_overrun_reservation(self):
        with patch('security.check_password_hash',return_value=False):
            with ThreadPoolExecutor(max_workers=8) as pool:codes=list(pool.map(lambda _:self.signin(email='unknown@example.test')[1].status_code,range(8)))
        self.assertEqual(codes.count(401),5);self.assertEqual(codes.count(429),3)
    def test_https_preview_origin_on_exact_host_only(self):
        old=f.system.app.config.get('SESSION_COOKIE_PARTITIONED')
        try:
            f.system.app.config['SESSION_COOKIE_PARTITIONED']=True
            self.assertEqual(self.signin(headers={'Host':'3000-preview.e2b.app','Origin':'https://3000-preview.e2b.app'})[1].status_code,200)
            self.assertEqual(self.signin(headers={'Host':'3000-preview.e2b.app','Origin':'https://evil.example.test'})[1].status_code,403)
        finally:f.system.app.config['SESSION_COOKIE_PARTITIONED']=old
    def test_cross_origin_login_and_session_mutation_rejected(self):
        c,r=self.signin(headers={'Origin':'https://evil.example.test'});self.assertEqual(r.status_code,403)
        r=self.client.patch('/api/profile',json={},headers={'Origin':'https://evil.example.test','X-CSRF-Token':self.data(self.client)['csrf']});self.assertEqual(r.status_code,403)
    def test_registration_can_be_closed_and_is_throttled(self):
        guest=f.system.app.test_client();old=f.system.app.config['PUBLIC_REGISTRATION']
        try:
            f.system.app.config['PUBLIC_REGISTRATION']=False;self.assertEqual(guest.post('/api/register',json={}).status_code,403)
            f.system.app.config['PUBLIC_REGISTRATION']=True
            for _ in range(5):self.assertEqual(guest.post('/api/register',json={}).status_code,400)
            self.assertEqual(guest.post('/api/register',json={}).status_code,429)
        finally:f.system.app.config['PUBLIC_REGISTRATION']=old
    def test_ten_active_sessions_maximum(self):
        clients=[self.signin()[0] for _ in range(11)]
        self.assertEqual(clients[0].get('/api/bootstrap').status_code,401)
        self.assertEqual(sum(s['active'] for s in self.sessions(clients[-1])),10)
    def test_deployment_status_private_and_secret_free(self):
        self.assertEqual(self.client.get('/api/security/deployment').status_code,403)
        r=self.admin.get('/api/security/deployment');self.assertTrue(r.json['server_sessions']);self.assertNotIn(f.system.app.secret_key,r.get_data(as_text=True))
    def test_operator_password_reset_revokes_sessions_without_printing_password(self):
        env={**os.environ,'ORIENTAL24_MODE':'demo','DB_PATH':self.path}
        pw='LocalOperatorResetPassword!42'
        r=subprocess.run([sys.executable,'manage.py','reset-password','--email','client@oriental24.ma'],cwd=Path(__file__).parent,env=env,input=pw+'\n'+pw+'\n',capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertNotIn(pw,r.stdout+r.stderr)
        self.assertEqual(self.client.get('/api/bootstrap').status_code,401)
        self.assertEqual(self.signin(password=pw)[1].status_code,200)
    def test_security_retention_preserves_business_and_active_sessions(self):
        old=int(time.time())-100*86400
        with f.system.conn() as c:
            c.execute("INSERT INTO auth_sessions(user_id,token_hash,created_at,last_seen,expires_at,user_agent,network) VALUES(2,'obsolete-test',?,?,?,'Test','Test')",(old,old,old+3600))
            c.execute("INSERT INTO auth_events(user_id,action,network,created_at) VALUES(2,'Obsolete test','Test',?)",(old,))
        r=subprocess.run([sys.executable,'manage.py','prune-security'],cwd=Path(__file__).parent,env={**os.environ,'ORIENTAL24_MODE':'demo','DB_PATH':self.path},capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        with f.system.conn() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM auth_sessions WHERE token_hash='obsolete-test'").fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM parcels').fetchone()[0],48)
        self.assertEqual(self.client.get('/api/bootstrap').status_code,200)
    def test_backup_restore_no_overwrite_and_revoke_restored_sessions(self):
        with tempfile.TemporaryDirectory() as t:
            backup=Path(t)/'backup.sqlite';restored=Path(t)/'restored.sqlite'
            snapshot(self.path,backup);before=hashlib.sha256(backup.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):snapshot(self.path,backup)
            self.assertEqual(before,hashlib.sha256(backup.read_bytes()).hexdigest());snapshot(backup,restored,True)
            with db(restored) as c:
                self.assertEqual(c.execute('SELECT count(*) FROM parcels').fetchone()[0],48)
                self.assertEqual(c.execute('SELECT count(*) FROM auth_sessions WHERE revoked_at IS NULL').fetchone()[0],0)
            self.assertEqual(restored.stat().st_mode&0o777,0o600)

class ProductionConfigurationTests(unittest.TestCase):
    def env(self,t,**kw):
        e=dict(ORIENTAL24_MODE='production',DB_PATH=str(Path(t)/'production.sqlite'),SECRET_KEY='test-key-not-for-real-deployment-'*2,ORIENTAL24_TRUSTED_HOSTS='delivery.example.test')
        e.update(kw);return e
    def test_missing_secrets_hosts_and_demo_database_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            for kwargs in [dict(SECRET_KEY=''),dict(ORIENTAL24_TRUSTED_HOSTS=''),dict(DB_PATH='relative.sqlite'),dict(ORIENTAL24_TRUSTED_HOSTS='*')]:
                with patch.dict(os.environ,self.env(t,**kwargs),clear=True),self.assertRaises(RuntimeError):configure(Flask('test'),t)
            target=Path(t)/'production.sqlite'
            with db(target) as c:
                c.execute('CREATE TABLE settings(key TEXT,value TEXT)');c.execute("INSERT INTO settings VALUES('dataset_kind','demo')")
            before=target.read_bytes()
            with patch.dict(os.environ,self.env(t),clear=True),self.assertRaises(RuntimeError):configure(Flask('test'),t)
            self.assertEqual(before,target.read_bytes())
    def test_secure_flags_and_no_automatic_proxy_trust(self):
        with tempfile.TemporaryDirectory() as t,patch.dict(os.environ,self.env(t),clear=True):
            a=Flask('test');configure(a,t)
            self.assertTrue(a.config['SESSION_COOKIE_SECURE']);self.assertFalse(a.config['PUBLIC_REGISTRATION']);self.assertFalse(a.config['DEMO_MODE']);self.assertEqual(a.config['SESSION_COOKIE_NAME'],'__Host-o24_session')
    def test_clean_boot_admin_creation_tls_hosts_and_disabled_registration(self):
        with tempfile.TemporaryDirectory() as t:
            env={**os.environ,**self.env(t)};root=Path(__file__).parent
            code="""import app,json
c=app.app.test_client()
with app.conn() as d:counts=[d.execute('SELECT count(*) FROM '+n).fetchone()[0] for n in ['users','parcels','cities']]
https=c.get('/',base_url='https://delivery.example.test')
print(json.dumps(dict(counts=counts,plain=c.get('/',base_url='http://delivery.example.test',headers={'X-Forwarded-Proto':'https'}).status_code,secure=https.status_code,badhost=c.get('/',base_url='https://bad.example.test').status_code,reg=c.post('/api/register',json={},base_url='https://delivery.example.test').status_code,hsts=https.headers.get('Strict-Transport-Security'),has_config=b'\"demo\": false' in https.data)))
"""
            r=subprocess.run([sys.executable,'-c',code],cwd=root,env=env,capture_output=True,text=True,check=True);d=json.loads(r.stdout)
            self.assertEqual(d['counts'],[0,0,0]);self.assertEqual((d['plain'],d['secure'],d['badhost'],d['reg']),(400,200,400,403));self.assertTrue(d['hsts']);self.assertTrue(d['has_config'])
            cmd=[sys.executable,'manage.py','init-admin','--email','first@example.test','--name','Initial Test Admin']
            pw='VeryLongTestPassword!42';r=subprocess.run(cmd,cwd=root,env=env,input=pw+'\n'+pw+'\n',capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr);self.assertNotIn(pw,r.stdout+r.stderr)
            r=subprocess.run(cmd,cwd=root,env=env,input=pw+'\n'+pw+'\n',capture_output=True,text=True);self.assertNotEqual(r.returncode,0)
            with db(env['DB_PATH']) as c:self.assertEqual(c.execute("SELECT count(*) FROM users WHERE role='admin'").fetchone()[0],1)
            with patch.dict(os.environ,{**env,'ORIENTAL24_MODE':'demo'},clear=True),self.assertRaises(RuntimeError):configure(Flask('test'),t)

if __name__=='__main__':unittest.main()
