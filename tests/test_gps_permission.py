import os,subprocess,sys,tempfile,unittest
from pathlib import Path
class GpsPermissionTests(unittest.TestCase):
 def test_header_and_driver_map_flow(self):
  code=r'''
import app
client=app.app.test_client();r=client.get('/app')
assert r.headers['Permissions-Policy']=='geolocation=(self), microphone=(), camera=(self)'
with app.conn() as c:driver=dict(c.execute("SELECT * FROM users WHERE role='livreur' AND active=1 LIMIT 1").fetchone())
assert client.post('/api/login',json={'email':driver['email'],'password':'Oriental24!Demo'}).status_code==200
csrf=client.get('/api/bootstrap').json['csrf'];payload={'lat':30.427755,'lng':-9.598107}
assert client.post('/api/driver/position',json=payload).status_code==403
assert client.post('/api/driver/position',json=payload,headers={'X-CSRF-Token':csrf}).status_code==200
admin=app.app.test_client();assert admin.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'}).status_code==200
r=admin.get('/api/control-tower/map-data');assert r.status_code==200,r.json
d=next(d for d in r.json['map_drivers'] if d['id']==driver['id'])
assert d['pos']['lat']==payload['lat'] and d['pos']['lng']==payload['lng'] and d['gps_state']=='enabled' and d['online'],d
assert app.app.test_client().post('/api/driver/position',json=payload).status_code==401
'''
  with tempfile.TemporaryDirectory() as tmp:
   r=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'DB_PATH':tmp+'/gps.sqlite','SECRET_KEY':'gps-isolated-test-key','APP_ENV':'development'},capture_output=True,text=True,timeout=90)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
