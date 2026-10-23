"""Real Chromium picker + scoped Flask candidate API; stale route response regression."""
import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root),str(root/'tests')]
from test_palette_destination_transit import PaletteDestinationTransitTests
from playwright.sync_api import sync_playwright
appjs=(root/'static/app.js').read_text();logjs=(root/'static/logistics.js').read_text()
modal=appjs[appjs.index('function closeModal()'):appjs.index('document.addEventListener("keydown",',appjs.index('function closeModal()'))]
picker=logjs[logjs.index('async function hubPaletteNew('):logjs.index('async function newOpsDocument(')]
agency=appjs[appjs.index('function parcelAgencyCell('):appjs.index('function parcelTable(')]
styles='\n'.join((root/'static'/f).read_text() for f in ['style.css','logistics.css'])
setup='''let S={user:{id:1,role:'admin',agent_hub_id:90}},modalCleanup=null,hubPaletteDialog=null,hubPaletteTab='default';
const $=s=>document.querySelector(s),esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),icon=()=>'',empty=(a,b)=>'<p>'+a+' · '+b+'</p>';
const cfg={central_hub_id:90,central_hub:{id:90,name:'Central',active:true},hubs:[{id:90,name:'Central',active:1},{id:10,name:'Hub A',active:1},{id:20,name:'Hub B',active:1}]};cfg.palette_targets=cfg.hubs;
const opsLoadConfig=async()=>cfg,toast=t=>window.lastToast=t,renderView=async()=>{},openOpsDocument=async id=>window.lastDoc=id;
async function api(path,method='GET',data){const r=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});const d=await r.json();if(!r.ok)throw Error(d.error);return d}
'''
with sync_playwright() as pw:
 browser=pw.chromium.launch()
 for role in ['admin','agent']:
  t=PaletteDestinationTransitTests();t.setUp();page=browser.new_page(viewport={'width':1100,'height':900});errors=[];held=[];hold=[False]
  page.on('pageerror',lambda e:errors.append(str(e)))
  headers=t.t.headers('admin') if role=='admin' else t.t.headers('agent',90,990)
  def handler(route):
   path=route.request.url.split('https://palette.test')[-1]
   if path.startswith('/api/'):
    r=t.client.open(path,method=route.request.method,headers=headers,json=json.loads(route.request.post_data) if route.request.post_data else None)
    if hold[0]:hold[0]=False;held.append((route,r));return
    route.fulfill(status=r.status_code,body=r.get_data(as_text=True),content_type='application/json')
   else:route.fulfill(body='<html><meta charset="utf-8"><style>'+styles+'</style><div id="modal-root"></div></html>',content_type='text/html')
  page.route('**/*',handler);page.goto('https://palette.test');page.add_script_tag(content=setup+modal+picker+agency);page.evaluate('role=>S.user.role=role',role)
  page.evaluate('hubPaletteNew()');page.evaluate('hubPaletteLoadCandidates()')
  assert page.locator('.hp-pick').count()==2
  page.locator('#hp-select-all').click();assert page.locator('.hp-pick:checked').count()==2;assert page.locator('#hp-create').is_enabled()
  page.locator('#hp-clear-all').click();assert page.locator('#hp-create').is_disabled()
  page.locator('#hp-select-all').click();page.locator('#hp-destination').select_option('20')
  page.wait_for_function("document.querySelectorAll('.hp-pick').length===1")
  assert 'CAND-7' in page.locator('#hp-candidates').inner_text();assert page.locator('.hp-pick:checked').count()==0
  page.locator('#hp-destination').select_option('10');page.wait_for_function("document.querySelectorAll('.hp-pick').length===2")
  hold[0]=True;page.get_by_role('button',name='Charger les colis admissibles').click()
  page.wait_for_function("document.querySelector('#hp-candidates').textContent.includes('Chargement')")
  page.locator('#hp-destination').select_option('20');page.wait_for_function("document.querySelectorAll('.hp-pick').length===1")
  assert held
  route,r=held.pop();route.fulfill(status=r.status_code,body=r.get_data(as_text=True),content_type='application/json')
  page.evaluate('()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))')
  assert 'CAND-7' in page.locator('#hp-candidates').inner_text();assert page.locator('.hp-pick').count()==1
  page.set_viewport_size({'width':390,'height':844})
  assert page.evaluate("document.querySelector('.modal-body').scrollWidth<=document.querySelector('.modal-body').clientWidth")
  assert page.locator('.hp-pick').first.bounding_box()['width']<=20
  page.screenshot(path='/home/user/palette-destination-'+role+'.png',full_page=True)
  for direction,label in [('central','Transit vers Hub Central'),('destination','Transit vers ville de destination')]:
   html=page.evaluate('(direction)=>parcelAgencyCell({transit_direction:direction,status:"Transit",driver:"Old courier",transit_destination:"Hub A"})',direction)
   assert label in html and 'À l’agence' not in html and 'Old courier' not in html
  assert 'trajet à vérifier' in page.evaluate("parcelAgencyCell({status:'Transit'})")
  assert 'À l’agence' in page.evaluate("parcelAgencyCell({status:'Réceptionné'})")
  assert not errors,errors
  print(role+': city-filtered picker, select/deselect all, route change resets, stale response ignored, mobile checkboxes and transit labels PASS')
  page.close();t.tearDown()
 browser.close()
