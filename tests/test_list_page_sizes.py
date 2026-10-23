import os,subprocess,sys,tempfile,unittest
from pathlib import Path
class ListPageSizesTests(unittest.TestCase):
 def test_real_application_server_sizes(self):
  code='''
import app
c=app.app.test_client()
assert c.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'}).status_code==200
for endpoint in ['/api/partner-palettes','/api/return-palettes','/api/palette-console','/api/billing']:
 for size in [10,20,30,50,80,100,200,500]:
  r=c.get(endpoint+'?size='+str(size)+'&page=9999')
  assert r.status_code==200,(endpoint,size,r.json)
  assert r.json['size']==size and len(r.json['rows'])<=size
 for size in [0,-1,501,9999,'abc']:
  assert c.get(endpoint+'?size='+str(size)).status_code==400,(endpoint,size)
print('All server list sizes accepted; invalid sizes rejected; last-page bounds preserved')
'''
  with tempfile.TemporaryDirectory() as tmp:
   r=subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1],env={**os.environ,'DB_PATH':tmp+'/test.sqlite','SECRET_KEY':'page-size-test-not-production','APP_ENV':'development'},capture_output=True,text=True,timeout=90)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
