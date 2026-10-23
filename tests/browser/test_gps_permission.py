"""Chromium uses simulated coordinates; no production data or real tracking."""
import os,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from playwright.sync_api import sync_playwright
with tempfile.TemporaryDirectory() as tmp:
 os.environ.update(DB_PATH=tmp+'/gps.sqlite',SECRET_KEY='gps-browser-isolated-test-key',APP_ENV='development')
 import app
 policy=app.app.test_client().get('/app').headers['Permissions-Policy']
 with sync_playwright() as pw:
  browser=pw.chromium.launch()
  context=browser.new_context(permissions=['geolocation'],geolocation={'latitude':30.427755,'longitude':-9.598107})
  page=context.new_page()
  for value,allowed in [('geolocation=(), microphone=(), camera=(self)',False),(policy,True)]:
   page.unroute('**/*')
   page.route('**/*',lambda route:route.fulfill(body='<html><body>GPS permission test</body></html>',headers={'Content-Type':'text/html','Permissions-Policy':value}))
   page.goto('https://gps-test.example/app')
   r=page.evaluate('''()=>new Promise(resolve=>navigator.geolocation.getCurrentPosition(p=>resolve({ok:true,lat:p.coords.latitude,lng:p.coords.longitude}),e=>resolve({ok:false,code:e.code}),{timeout:5000}))''')
   assert r['ok']==allowed,r
   if allowed:assert r['lat']==30.427755 and r['lng']==-9.598107
   else:assert r['code']==1
  browser.close()
 print('PASS: original response blocks GPS despite permission; corrected real application header permits simulated GPS on same origin')
