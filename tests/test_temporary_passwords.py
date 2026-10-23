"""Exercise the complete application, authentication, CSRF, hashing and session revocation."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

class TemporaryPasswordTests(unittest.TestCase):
    def test_real_application_credentials_flow(self):
        code=r'''
import app,json
from werkzeug.security import check_password_hash
client=app.app.test_client()
r=client.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'});assert r.status_code==200,r.json
boot=client.get('/api/bootstrap').json;admin_id=boot['user']['id'];headers={'X-CSRF-Token':boot['csrf']}
with app.conn() as c:
    city=c.execute('SELECT id FROM cities LIMIT 1').fetchone()[0]
    hub=c.execute("INSERT INTO ops_hubs(name,city_id,address,active,created_at) VALUES('Credential test hub',?,'Test',1,?)",(city,app.now())).lastrowid
    support_city=c.execute('SELECT id FROM cities WHERE id NOT IN (SELECT city_id FROM support_cities) LIMIT 1').fetchone()[0]
created=[]
for role,kind in (('client','vendeur'),('client','societe_livraison'),('livreur','vendeur'),('support','vendeur'),('hub_manager','vendeur')):
    d=dict(role=role,name='Credential Test',email=role+'-'+kind+'@credentials.test',client_type=kind,phone='0600000000',company='Test',generate_password=True)
    if role=='livreur':d['driver_hub_id']=hub
    if role=='hub_manager':d['agent_hub_id']=hub
    if role=='support':d['city_ids']=[support_city]
    r=client.post('/api/users',json=d,headers=headers);assert r.status_code==200,(role,r.json)
    p=r.json['temporary_password'];uid=r.json['id'];assert len(p)>=24 and 'no-store' in r.headers['Cache-Control']
    with app.conn() as c:
        stored=c.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()[0]
        assert stored!=p and check_password_hash(stored,p)
        assert p not in '\n'.join(c.iterdump())
    assert p.encode() not in client.get('/api/bootstrap').data
    created.append((uid,d['email'],p))
uid,email,old=created[0]
target=app.app.test_client();assert target.post('/api/login',json={'email':email,'password':old}).status_code==200
tb=target.get('/api/bootstrap').json
url=f'/api/users/{uid}/reset-password';body={'current_password':'Oriental24!Demo','confirmed':True}
assert client.post(url,json=body).status_code==403
assert target.post(url,json=body,headers={'X-CSRF-Token':tb['csrf']}).status_code==403
assert client.post(url,json={**body,'current_password':'wrong'},headers=headers).status_code==403
assert client.post(f'/api/users/{admin_id}/reset-password',json=body,headers=headers).status_code==403
r=client.post(url,json=body,headers=headers);assert r.status_code==200,r.json
new=r.json['temporary_password'];assert new!=old and 'no-store' in r.headers['Cache-Control']
assert target.get('/api/bootstrap').status_code==401
assert target.post('/api/login',json={'email':email,'password':old}).status_code==401
assert target.post('/api/login',json={'email':email,'password':new}).status_code==200
assert client.get(url).status_code==405
with app.conn() as c:
    assert new not in '\n'.join(c.iterdump())
    assert c.execute('SELECT count(*) FROM auth_sessions WHERE user_id=? AND revoked_at IS NOT NULL',(uid,)).fetchone()[0]>=1
for _ in range(6):last=client.post(url,json={**body,'current_password':'wrong'},headers=headers)
assert last.status_code==429,last.status_code
print('PASS: four account types, hash-only storage, no-store responses, admin-only reset, CSRF, reauthentication, revocation, no retrieval, rate limit')
'''
        with tempfile.TemporaryDirectory() as tmp:
            env={**os.environ,'DB_PATH':str(Path(tmp)/'test.sqlite'),'SECRET_KEY':'isolated-test-key-not-for-production-123','APP_ENV':'development'}
            result=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
