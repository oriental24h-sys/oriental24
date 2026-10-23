"""Chromium DOM + real Flask/SQLite endpoint. Camera hardware is simulated.
Run: python tests/browser/test_ramassage_collect.py (requires playwright + Chromium).
"""
import sys,json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
from test_reception_collection import ReceptionCollectionTests
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
appjs=(root/'static/app.js').read_text()
modal=appjs[appjs.index('function closeModal()'):appjs.index('document.addEventListener("keydown",',appjs.index('function closeModal()'))]
palette=(root/'static/palette-scan.js').read_text()
partner=(root/'static/partner-palettes.js').read_text()
context=partner[partner.index('function ppContext('):partner.index('\n',partner.index('function ppContext('))]
styles='\n'.join((root/'static'/p).read_text() for p in ['style.css','partner-palettes.css'])
bootstrap='''let S={user:{id:1,role:'admin'}},modalCleanup=null;
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),icon=()=>'';
const ppIdentity=()=>S.user.id+':'+S.user.role;
const rbStatusTag=s=>'<span class="tag blue">'+esc(s)+'</span>';
const financeKey=()=>crypto.randomUUID().replaceAll('-','');
const refresh=async()=>{},renderView=async()=>{},toast=t=>window.lastToast=t,ppError=(ctx,e)=>{throw e};
async function api(path,method='GET',data){const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
'''
with sync_playwright() as p:
 browser=p.chromium.launch()
 for kind,role in [('transfer','admin'),('transfer','agent'),('partner','admin'),('partner','agent'),('return','client'),('return','agent'),('fusion','agent')]:
  t=ReceptionCollectionTests();t.setUp()
  if kind=='transfer':bid=t.transfer();t.dispatch(bid)
  elif kind=='fusion':
   a=t.palette('partner',(3,));b=t.palette('partner',(4,))
   with t.conn() as c:
    bid=c.execute("INSERT INTO fusion_batches(hub_destination_id,created_by,created_at) VALUES(90,1,'2026-01-02')").lastrowid
    c.executemany('INSERT INTO fusion_batch_palettes VALUES(?,?)',[(bid,a),(bid,b)])
  else:bid=t.palette(kind)
  headers=t.admin if role=='admin' else t.central if role=='agent' else t.t.headers('client',None,2)
  before=t.t.parcel_state(3)['status'];writes=[];lose_response=[True]
  page=browser.new_page(viewport={'width':1200,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  def handler(route):
   req=route.request;path=req.url.split('https://reception.test')[-1]
   if path.startswith('/api/'):
    if req.method=='POST':writes.append(json.loads(req.post_data))
    response=t.client.open(path,method=req.method,headers=headers,json=json.loads(req.post_data) if req.post_data else None)
    # Simulate lost response AFTER server commit: second click must safely replay.
    if req.method=='POST' and response.status_code==200 and lose_response[0]:
     lose_response[0]=False;route.abort();return
    route.fulfill(status=response.status_code,body=response.get_data(as_text=True),content_type='application/json')
   else:route.fulfill(body='<html><meta charset="utf-8"><style>'+styles+'</style><body><div id="modal-root"></div></body></html>',content_type='text/html')
  page.route('**/*',handler);page.goto('https://reception.test/')
  page.add_script_tag(content=bootstrap+modal+context+palette+(root/'static/reception-collection.js').read_text())
  page.evaluate("role=>{S.user.role=role;window.tones=[];ppTone=(f)=>tones.push(f);window.cameraStopped=0;ppRxCam=(box,btn,state,callback)=>{window.cameraScan=callback;return{stop(){cameraStopped++},active:()=>false,start:async()=>true}}}",role)
  page.evaluate('([kind,id])=>openReceptionCollection(kind,id)',[kind,bid])
  def scan(code):page.locator('#rb-collect-input').fill(code);page.locator('#rb-collect-input').press('Enter')
  count=page.locator('#rb-collect-count');button=page.locator('#rb-collect-confirm')
  assert button.is_disabled();scan('TRK-STANDARD');assert count.inner_text().startswith('1')
  assert not writes and t.t.parcel_state(3)['status']==before
  scan(' trk-standard ');assert 'DOUBLE' in page.locator('#rb-collect-feedback').inner_text();assert count.inner_text().startswith('1');assert page.evaluate('tones.slice(-2)')==[180,130]
  page.evaluate("cameraScan('TRK-STANDARD')");assert count.inner_text().startswith('1')
  scan('OTHER');assert 'Hors bon' in page.locator('#rb-collect-feedback').inner_text();assert page.evaluate('tones.slice(-3)')==[520]*3
  page.locator('[data-rb-undo]').first.click();assert count.inner_text().startswith('0')
  scan('TRK-STANDARD');page.locator('#rb-collect-reset').click();assert count.inner_text().startswith('0')
  page.locator('[data-o24-snd]').click();page.evaluate('tones=[]');scan('TRK-STANDARD');assert page.evaluate('tones')==[]
  page.locator('[data-o24-snd]').click();page.evaluate("cameraScan('TRK-INVOICED')");assert count.inner_text().startswith('2');assert button.is_enabled();assert not writes
  page.screenshot(path='/home/user/reception-'+kind+'-'+role+'.png',full_page=True)
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
  assert page.evaluate("document.querySelector('.modal-body').scrollWidth<=document.querySelector('.modal-body').clientWidth")
  page.screenshot(path='/home/user/reception-'+kind+'-'+role+'-mobile.png',full_page=True)
  button.click();page.wait_for_function("document.querySelector('#rb-collect-feedback').textContent.includes('Réessayez')")
  assert t.t.parcel_state(3)['status']==('Retourné' if kind=='return' else 'Réceptionné')
  assert page.locator('#rb-collect-input').is_disabled()
  button.click();page.wait_for_function("!document.querySelector('#rb-collect-confirm')")
  assert len(writes)==2 and writes[0]==writes[1];assert page.evaluate('cameraStopped')>0
  page.evaluate('([kind,id])=>openReceptionCollection(kind,id)',[kind,bid]);scan('TRK-STANDARD');assert 'DOUBLE' in page.locator('#rb-collect-feedback').inner_text();assert button.is_disabled()
  assert not errors,errors
  print(kind+'/'+role+': DOM, local scans/no writes, duplicate low tones, camera callback, undo/reset, mute, mobile, atomic batch, lost-response replay, received duplicate PASS')
  page.close();t.tearDown()
 browser.close()
