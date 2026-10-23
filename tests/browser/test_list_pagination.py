from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
app=(root/'static/app.js').read_text();pilot=(root/'static/pilotage.js').read_text()
draw=pilot[pilot.index('drawParcelTable = function ()'):pilot.index('function parcelCsvCell')]
setup='''let S={user:{id:1,role:'admin'}},listPage=1,filters={};let source=Array.from({length:123},(_,i)=>({id:i+1}));
const $=s=>document.querySelector(s),filteredParcels=()=>source,queueAllowed=()=>false,esc=String,icon=()=>'';
const parcelTable=rows=>'<table><thead><tr><th>Commande</th></tr></thead><tbody>'+rows.map(p=>'<tr><td>CMD-'+p.id+'</td></tr>').join('')+'</tbody></table>';
const parcelPagination=(page,pages)=>'<span>'+page+' / '+pages+'</span>';let drawParcelTable;
'''
with sync_playwright() as p:
 browser=p.chromium.launch();page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('**/*',lambda r:r.fulfill(body='<div id="content"><section class="card"><div id="parcel-table"></div></section></div><div id="modal-root"></div>',content_type='text/html'))
 page.goto('https://pagination.test');page.add_script_tag(content=setup+(root/'static/list-pagination.js').read_text()+draw)
 for role in ['admin','agent','client','livreur','support']:
  page.evaluate('(r)=>{S.user.role=r;source=Array.from({length:123},(_,i)=>({id:i+1}));listPage=1;drawParcelTable()}',role)
  page.locator('#parcel-table select').select_option('50');assert page.locator('#parcel-table tbody tr').count()==50
  page.get_by_role('button',name='Page suivante').click();assert page.locator('tbody tr').first.inner_text()=='CMD-51';assert page.locator('tbody tr').count()==50
  page.get_by_role('button',name='Page suivante').click();assert page.locator('tbody tr').count()==23;assert page.get_by_role('button',name='Page suivante').is_disabled()
  page.locator('select').select_option('100');assert page.locator('tbody tr').first.inner_text()=='CMD-1';assert page.locator('tbody tr').count()==100
  page.evaluate('source=source.slice(0,2);drawParcelTable()');assert page.locator('tbody tr').count()==2
  page.evaluate('source=[];drawParcelTable()');assert '0–0 sur 0' in page.locator('#parcel-table').inner_text()
 # Generic lists: rows are detached rather than merely hidden (bulk actions see the page).
 page.evaluate('''document.querySelector('#content').innerHTML='<section class="card" id="generic">'+parcelTable(Array.from({length:123},(_,i)=>({id:i+1})))+'</section>';''')
 page.wait_for_selector('#generic select');page.locator('#generic select').select_option('50');assert page.locator('#generic tbody tr').count()==50
 page.get_by_role('button',name='Page suivante').click();assert page.locator('#generic tbody tr').first.inner_text()=='CMD-51'
 page.get_by_role('button',name='Page suivante').click();assert page.locator('#generic tbody tr').count()==23
 page.evaluate("document.querySelector('#modal-root').innerHTML=parcelTable(Array.from({length:123},(_,i)=>({id:i+1})))")
 assert page.locator('#modal-root tbody tr').count()==123
 page.set_viewport_size({'width':390,'height':844});page.add_style_tag(content=(root/'static/list-pagination.css').read_text())
 assert page.locator('#generic select').is_visible()
 assert not errors,errors
 print('PASS: five roles; 50 / 50 / 23; size reset; filtered and empty results; generic lists; scan/modal exclusion; mobile selector')
 browser.close()
