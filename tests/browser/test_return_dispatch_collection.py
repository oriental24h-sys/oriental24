"""Chromium DOM + real Flask/SQLite endpoint. Camera hardware is simulated.
Run: python tests/browser/test_ramassage_collect.py (requires playwright + Chromium).
"""
import sys,json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
from test_dispatch_collection import DispatchCollectionTests
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
from return_scan import register_return_scan
setup_widgets = """
const input=(name,label,value='',type='text')=>`<label class="field"><span>${esc(label)}</span><input id="f-${name}" name="${name}" value="${esc(value)}" type="${type}"></label>`;
const select=(name,label,options)=>`<label class="field"><span>${esc(label)}</span><select id="f-${name}" name="${name}">${options.map(x=>`<option value="${x[0]}">${esc(x[1])}</option>`).join('')}</select></label>`;
"""
with sync_playwright() as p:
 browser=p.chromium.launch()
 for role in ['admin','agent']:
  t=DispatchCollectionTests();t.setUp();register_return_scan(t.t.app,t.t.services)
  with t.conn() as c:c.execute("UPDATE parcels SET client_id=2,current_hub_id=10,status='Refusé' WHERE id IN (3,4)")
  headers=t.admin if role=='admin' else t.source
  page=browser.new_page(viewport={'width':1100,'height':1000});writes=[];lost=[True];errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def handler(route):
   req=route.request;path=req.url.split('https://reception.test')[-1]
   if path.startswith('/api/'):
    if req.method=='POST':writes.append(json.loads(req.post_data))
    r=t.client.open(path,method=req.method,headers=headers,json=json.loads(req.post_data) if req.post_data else None)
    if req.method=='POST' and r.status_code==200 and lost[0]:lost[0]=False;route.abort();return
    route.fulfill(status=r.status_code,body=r.get_data(as_text=True),content_type='application/json')
   else:route.fulfill(body='<html><meta charset="utf-8"><style>'+styles+(root/'static/return-scan.css').read_text()+'</style><body><div id="modal-root"></div></body></html>',content_type='text/html')
  page.route('**/*',handler);page.goto('https://reception.test/')
  page.add_script_tag(content=bootstrap+modal+context+palette+setup_widgets+(root/'static/return-scan.js').read_text())
  page.evaluate("role=>{S.user.role=role;window.tones=[];ppTone=f=>tones.push(f)}",role)
  page.evaluate('rpScanStart()');page.locator('#f-rp-sc-client').select_option('2');page.locator('#f-rp-sc-hub').select_option('10');page.get_by_role('button',name='Commencer le scan').click()
  def scan(code):page.evaluate('(code)=>rpScanCode(code,false)',code)
  scan('TRK-STANDARD');assert not writes;assert page.locator('#rp-sc-count').inner_text().startswith('1')
  scan('TRK-STANDARD');assert 'DOUBLE' in page.locator('#rp-sc-msg').inner_text();assert page.evaluate('tones.slice(-2)')==[180,130]
  page.locator('[data-rp-remove]').click();assert page.locator('#rp-sc-count').inner_text().startswith('0')
  scan('TRK-STANDARD');page.locator('#rp-sc-reset').click();assert page.locator('#rp-sc-count').inner_text().startswith('0')
  scan('TRK-STANDARD');scan('TRK-INVOICED');assert not writes
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate("document.querySelector('.modal-body').scrollWidth<=document.querySelector('.modal-body').clientWidth")
  page.screenshot(path='/home/user/dispatch-return-direct-'+role+'.png',full_page=True)
  page.locator('#rp-sc-validate').click();page.wait_for_function("document.querySelector('#rp-sc-msg').textContent.includes('Réessayez')")
  assert page.locator('#f-rp-sc-input').is_disabled()
  page.locator('#rp-sc-validate').click();page.wait_for_function("!document.querySelector('#rp-sc-box')")
  assert writes[0]==writes[1]
  with t.conn() as c:assert c.execute("SELECT count(*) FROM ops_documents WHERE kind='return_palette' AND status='En transit'").fetchone()[0]==1
  assert not errors,errors
  print(role+': direct return local scans, duplicate low sound, undo/reset, one final dispatch and same-key retry PASS')
  page.close();t.tearDown()
 browser.close()
