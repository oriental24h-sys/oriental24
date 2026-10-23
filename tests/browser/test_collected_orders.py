"""Collected seller orders: Chromium rendering with real Flask fixture API."""
import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root),str(root/'tests')]
from test_ramassage_bon import RamassageBonTests
from playwright.sync_api import sync_playwright
styles='\n'.join((root/'static'/p).read_text() for p in ['style.css','partner-palettes.css'])
source=(root/'static/ramassage-bon.js').read_text()
setup='''let S={user:{id:1,role:'admin'}};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),icon=()=>'',date=esc;
const heading=(t,s,a)=>`<header><h1>${t}</h1><p>${s}</p>${a}</header>`;
const stat=(t,n,a,b,c,s)=>`<article class="card" style="padding:20px"><h3>${t}</h3><strong>${n}</strong><p>${s}</p></article>`;
const simpleTable=(cols,rows)=>`<div class="table-wrap"><table><thead><tr>${cols.map(x=>'<th>'+x+'</th>').join('')}</tr></thead><tbody>${rows.map(r=>'<tr>'+r.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')}</tbody></table></div>`;
const navigate=v=>window.lastNavigation=v;
const openOpsDocument=id=>window.lastDocument=id;
async function api(path){const r=await fetch('/api'+path);const d=await r.json();if(!r.ok)throw Error(d.error);return d}
async function renderView(){document.querySelector('main').innerHTML=await ramassageCollectedView()}
'''
with sync_playwright() as p:
 browser=p.chromium.launch()
 for role in ['admin','agent']:
  t=RamassageBonTests();t.setUp();t.collected_setup();page=browser.new_page(viewport={'width':1280,'height':900});errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  def handler(route):
   path=route.request.url.split('https://collected.test')[-1]
   if path.startswith('/api/'):
    response=t.client.get(path,headers=t.hdr(role,1 if role=='admin' else 910,10))
    route.fulfill(status=response.status_code,body=response.get_data(as_text=True),content_type='application/json')
   else:route.fulfill(body='<html><meta charset="utf-8"><style>'+styles+'</style><body><main style="padding:24px"></main></body></html>',content_type='text/html')
  page.route('**/*',handler);page.goto('https://collected.test/');page.add_script_tag(content=setup+source)
  page.evaluate('role=>{S.user.role=role}',role);page.evaluate('renderView()')
  assert page.locator('h1').inner_text()=='Les CMD ramassées';assert page.locator('tbody tr').count()==2
  assert page.get_by_text('Hub d’origine',exact=True).count()==(1 if role=='admin' else 0)
  page.locator('input[name=q]').fill('O24-101');page.get_by_role('button',name='Rechercher',exact=True).click();page.wait_for_function("document.querySelectorAll('tbody tr').length===1")
  assert 'O24-101' in page.locator('tbody').inner_text()
  page.locator('input[name=q]').fill('');page.get_by_role('button',name='Rechercher',exact=True).click();page.wait_for_function("document.querySelectorAll('tbody tr').length===2")
  page.get_by_role('button',name='Transferts vers le Central').click();assert page.evaluate('lastNavigation')=='palette-hub'
  page.screenshot(path='/home/user/cmd-ramassees-'+role+'.png',full_page=True)
  assert not errors,errors
  print(role+': collected list, scoped API, search, role-specific hub filter and transfer navigation PASS')
  page.close();t.tearDown()
 browser.close()
