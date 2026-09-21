"""Verify the research-led UX changes on the real API and the standalone HTML."""
import os,sys,tempfile,threading,shutil,csv,io,re
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
TEMP=tempfile.mkdtemp(prefix='o24-pilotage-');os.environ['DB_PATH']=str(Path(TEMP)/'test.sqlite')
import app
server=make_server('127.0.0.1',0,app.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
BASE=f'http://127.0.0.1:{server.server_port}'
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(args=['--no-sandbox']);errors=[]
  for offline in [False,True]:
   page=browser.new_page(viewport={'width':1440,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
   def role(name):
    if offline:
     page.evaluate(f"offlineSwitch('{name}')");page.wait_for_selector('.stats')
    else:
     page.goto(BASE+'/login');page.get_by_role('button',name={'admin':'Admin','client':'Client','livreur':'Livreur'}[name],exact=True).click();page.wait_for_selector('.stats')
   if offline:page.goto((ROOT.parent/'ORIENTAL24-demo.html').as_uri());page.wait_for_selector('.public-hero')
   role('admin');expect(page.locator('.pilotage-queue')).to_have_count(5)
   base=page.evaluate('S.parcels');assert len(base)==48
   for key in ['unassigned','delivery','scheduled','exceptions','uninvoiced']:
    expected=[p for p in base if {'unassigned':not p['driver_id'] and p['status'] not in ['Livré','Refusé','Retourné'],'delivery':p['status']=='En livraison','scheduled':p['status']=='Programmé','exceptions':p['status'] in ['Retourné','Refusé'],'uninvoiced':p['status'] in ['Livré','Retourné','Refusé'] and not p['invoice_id']}[key]]
    page.evaluate(f"openParcelQueue('{key}')")
    assert set(page.evaluate('filteredParcels().map(p=>p.id)'))=={p['id'] for p in expected},key
   page.locator('.pilotage-parcels .tabs').get_by_role('button',name=re.compile('^Tous les colis')).click()
   assert len(page.evaluate('filteredParcels()'))==48
   page.get_by_label('Page 2',exact=True).click();page.get_by_label('Page 3',exact=True).click()
   page.locator('.pilotage-parcels .tabs').get_by_role('button',name=re.compile('^En livraison')).click()
   assert page.evaluate('listPage')==1
   assert all(p['status']=='En livraison' for p in page.evaluate('filteredParcels()'))
   page.locator('.pilotage-parcels .tabs').get_by_role('button',name=re.compile('^Tous les colis')).click()
   assert len(page.evaluate('filteredParcels()'))==48
   chosen=next(p for p in base if p['status']=='Livré' and p['driver_id'] and p['client_id']==2)
   day=chosen['created_at'][:10]
   page.locator('#status-filter').select_option('Livré');page.locator('#pilotage-city').select_option(str(chosen['city_id']))
   page.locator('#pilotage-driver').select_option(str(chosen['driver_id']));page.locator('#pilotage-client').select_option('2')
   page.locator('#pilotage-from').fill(day);page.locator('#pilotage-to').fill(day)
   expected=[p for p in base if p['status']=='Livré' and p['city_id']==chosen['city_id'] and p['driver_id']==chosen['driver_id'] and p['client_id']==2 and p['created_at'][:10]==day]
   assert {p['id'] for p in page.evaluate('filteredParcels()')}=={p['id'] for p in expected}
   with page.expect_download() as dl:page.get_by_role('button',name='Exporter cette vue',exact=True).click()
   data=Path(dl.value.path()).read_text(encoding='utf-8-sig');csvrows=list(csv.reader(io.StringIO(data),delimiter=';'))
   assert {r[0] for r in csvrows[1:]}=={p['tracking'] for p in expected}
   assert dl.value.suggested_filename=='ORIENTAL24-colis-filtres.csv'
   page.screenshot(path=str(ROOT/'qa'/('pilotage-filters-html.png' if offline else 'pilotage-filters.png')),full_page=True,animations='disabled')
   page.get_by_title('Retirer ce filtre',exact=True).first.click();assert page.evaluate('filters.status')==''
   page.locator('#pilotage-from').fill('2999-01-01');expect(page.locator('.pilotage-date-error')).to_be_visible();assert not page.evaluate('filteredParcels()')
   page.get_by_title('Réinitialiser les filtres',exact=True).click();assert len(page.evaluate('filteredParcels()'))==48
   # Accents are optional in search; CSV exports every filtered page and neutralizes formula cells.
   page.locator('#parcel-search').fill('said');assert page.evaluate('filteredParcels().length')>0;assert all('Saïdia'==p['city'] for p in page.evaluate('filteredParcels()'))
   page.get_by_title('Réinitialiser les filtres',exact=True).click()
   page.evaluate('S.parcels[0].invoice_id=9001;S.parcels[0].financial_locked=1')
   page.locator('#pilotage-billing').select_option('invoiced');assert page.evaluate('filteredParcels().length')==1
   page.locator('#pilotage-billing').select_option('driverLocked');assert page.evaluate('filteredParcels().length')==1
   page.locator('#pilotage-billing').select_option('driverOpen');assert page.evaluate('filteredParcels().length')==47
   page.get_by_title('Réinitialiser les filtres',exact=True).click()
   page.evaluate("S.parcels[0].recipient='=1+1'")
   with page.expect_download() as dl:page.get_by_role('button',name='Exporter cette vue',exact=True).click()
   csvrows=list(csv.reader(io.StringIO(Path(dl.value.path()).read_text(encoding='utf-8-sig')),delimiter=';'))
   assert len(csvrows)==49 and csvrows[1][1]=="'=1+1"
   page.get_by_title('Actualiser les données',exact=True).click();page.wait_for_function("S.parcels[0].recipient!=='=1+1'")
   page.evaluate("navigate('dashboard')");page.screenshot(path=str(ROOT/'qa'/('pilotage-dashboard-html.png' if offline else 'pilotage-dashboard.png')),full_page=True,animations='disabled')
   role('client');expect(page.locator('.pilotage-queue')).to_have_count(4);page.evaluate("openParcelQueue('uninvoiced')")
   expect(page.locator('#pilotage-driver')).to_have_count(0);expect(page.locator('#pilotage-client')).to_have_count(0)
   assert all(p['client_id']==2 for p in page.evaluate('filteredParcels()'))
   role('livreur');expect(page.locator('.pilotage-queue')).to_have_count(4);page.evaluate("openParcelQueue('driverOpen')")
   assert all(p['driver_id']==3 and not p['financial_locked'] for p in page.evaluate('filteredParcels()'))
   page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
   page.screenshot(path=str(ROOT/'qa'/('pilotage-mobile-html.png' if offline else 'pilotage-mobile.png')),full_page=True,animations='disabled')
   page.close()
  assert not errors,errors
  print('PASS: both server + HTML; role-specific operational queues; tabs reset correctly; combined inclusive dates/city/client/driver/status filters; invalid dates; accent-insensitive search; chips; 48-row filtered CSV across pages; formula safety; refresh; mobile; zero JS errors.')
  browser.close()
finally:server.shutdown();shutil.rmtree(TEMP)
