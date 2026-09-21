"""Company prepares/sends; Admin receives partially then fully. Isolated server + HTML."""
import os,sys,tempfile,threading,shutil,json
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect
from pypdf import PdfReader
expect.set_options(timeout=15000)
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));TMP=tempfile.mkdtemp(prefix='o24-partner-palettes-');os.environ['DB_PATH']=str(Path(TMP)/'test.sqlite');os.environ['ORIENTAL24_MODE']='demo'
import app
c=app.app.test_client();c.post('/api/login',json=dict(email='admin@oriental24.ma',password='Oriental24!Demo'));H={'X-CSRF-Token':c.get('/api/bootstrap').json['csrf']}
r=c.post('/api/users',json=dict(name='Société fictive',company='Transport Démo Partenaire',email='societe@example.test',password='Oriental24!Demo',phone='0600000000',role='client',client_type='societe_livraison'),headers=H);assert r.status_code==200;uid=r.json['id']
for i in range(4):assert c.post('/api/parcels',json=dict(client_id=uid,tracking=f'PART-0000{i}/Ab',recipient=f'Destinataire fictif {i}',phone='0600000000',address='Adresse fictive',city_id=1,amount=199,product='Produit fictif'),headers=H).status_code==200
with app.conn() as db:before=[tuple(r) for r in db.execute('SELECT id,tracking,client_id,amount,fee,return_fee,invoice_id FROM parcels ORDER BY id')]
server=make_server('127.0.0.1',0,app.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start();BASE=f'http://127.0.0.1:{server.server_port}'
def login(page,email):
 page.goto(BASE+'/login');page.locator('#f-email').fill(email);page.locator('#f-password').fill('Oriental24!Demo');page.locator('#login-form button[type=submit]').click();page.wait_for_selector('.stats')
def dialog(page):return page.locator('#modal-root .modal')
def confirm(page,label):
 page.get_by_role('button',name=label,exact=True).click();page.wait_for_selector('.modal input[name=confirmed]');page.locator('.modal input[name=confirmed]').check();page.locator('.modal form button[type=submit]').click()
try:
 with sync_playwright() as pw:
  b=pw.chromium.launch(args=['--no-sandbox']);page=b.new_page(viewport={'width':1440,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  login(page,'societe@example.test');expect(page.locator('.sidebar')).to_contain_text('Palettes partenaires');page.evaluate("navigate('partner-palettes')");page.get_by_role('button',name='Préparer une palette',exact=True).click();expect(dialog(page)).to_contain_text('Aucun hub');page.evaluate('closeModal()')
  login(page,'admin@oriental24.ma');page.evaluate("navigate('partner-palettes')");page.get_by_role('button',name='Ajouter un hub',exact=True).click();page.locator('#f-name').fill('Hub Oujda · démo');page.locator('#f-city_id').select_option('1');page.locator('#f-address').fill('Adresse fictive du hub');page.locator('.modal form button[type=submit]').click();page.wait_for_selector('.modal',state='detached')
  login(page,'societe@example.test');page.evaluate("navigate('partner-palettes')");page.get_by_role('button',name='Préparer une palette',exact=True).click();page.wait_for_selector('.pp-candidate');expect(page.locator('.pp-candidate')).to_have_count(4)
  page.locator('#pp-select-visible').click();expect(page.locator('#pp-selection-count')).to_contain_text('4 colis');page.locator('.pp-candidate input').nth(3).uncheck()
  page.locator('#f-partner_reference').fill('Palette société · DEMO-007');page.locator('#f-transport').fill('Navette de démonstration');dialog(page).screenshot(path=str(ROOT/'qa/partner-palettes-company-draft.png'),animations='disabled');page.locator('.modal form button[type=submit]').click();expect(dialog(page)).to_contain_text('Brouillon');page.wait_for_selector('.pp-document-head')
  did=page.evaluate("async()=> (await api('/partner-palettes')).rows[0].id")
  confirm(page,'Confirmer l’envoi');expect(dialog(page)).to_contain_text('Envoyée · à recevoir');expect(page.locator('#pp-receive-form')).to_have_count(0);assert page.evaluate("S.parcels.every(p=>p.status==='Créé')")
  login(page,'admin@oriental24.ma');page.evaluate("navigate('partner-palettes')");page.wait_for_selector('#content .tracking');expect(page.locator('#content')).to_contain_text('Transport Démo Partenaire');page.get_by_role('button',name='Réceptionner',exact=False).first.click();page.wait_for_selector('#pp-receive-form');first=page.evaluate('(id)=>api("/partner-palettes/"+id).then(d=>d.lines[0].tracking)',did)
  page.locator('#pp-receive-form #f-tracking').fill(first.lower());page.locator('#pp-receive-form input[name=confirmed]').check();page.locator('#pp-receive-form button[type=submit]').click();expect(dialog(page)).to_contain_text('Réception partielle');expect(page.locator('.pp-progress')).to_contain_text('2 restant(s)');dialog(page).screenshot(path=str(ROOT/'qa/partner-palettes-admin-partial.png'),animations='disabled')
  # Repeat a scan: no second receipt, and missing parcels remain locked.
  page.locator('#pp-receive-form #f-tracking').fill(first);page.locator('#pp-receive-form input[name=confirmed]').check();page.locator('#pp-receive-form button[type=submit]').click();page.wait_for_function("document.querySelector('#pp-receive-form #f-tracking')?.value===''");expect(page.locator('.pp-progress')).to_contain_text('2 restant(s)')
  # Simulate a lost response after a successful server mutation; retry frozen confirmation.
  page.evaluate("() => {window.ppOriginalApi=api;window.ppLost=false;api=async(...args)=>{const r=await ppOriginalApi(...args);if(args[0].endsWith('/receive-all')&&!ppLost){ppLost=true;throw Error('Réponse perdue simulée')}return r}}")
  confirm(page,'Recevoir tous les 2 restants');expect(page.locator('.modal .form-error')).to_contain_text('Réponse perdue simulée');page.locator('.modal form button[type=submit]').click();expect(dialog(page)).to_contain_text('Réceptionnée');expect(page.locator('.pp-progress')).to_contain_text('Aucun colis attendu');page.evaluate('() => {api=ppOriginalApi}')
  assert page.evaluate('(id)=>api("/partner-palettes/"+id).then(d=>d.audit.filter(a=>a.action===\'Réception complète confirmée\').length)',did)==1
  with page.expect_download() as download:page.get_by_role('button',name='CSV',exact=True).click()
  path=download.value.path();text=Path(path).read_text('utf-8-sig');assert first in text and 'Reçu' in text
  page.evaluate('()=>{window.print=()=>{}}');page.evaluate('(id)=>ppPrint(id)',did);expect(page.locator('#print-root')).to_contain_text(first);page.emulate_media(media='print');pdf=ROOT.parent/'ORIENTAL24-exemple-palette-partenaire.pdf';page.pdf(path=str(pdf),format='A4',prefer_css_page_size=True,print_background=True);assert first in ''.join(p.extract_text() for p in PdfReader(pdf).pages);page.emulate_media(media='screen')
  page.set_viewport_size({'width':390,'height':844});page.evaluate('(id)=>openPartnerPalette(id)',did);expect(dialog(page)).to_contain_text('Réceptionnée');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');dialog(page).screenshot(path=str(ROOT/'qa/partner-palettes-mobile.png'),animations='disabled')
  page.set_viewport_size({'width':1440,'height':1000});login(page,'societe@example.test');page.evaluate("navigate('partner-palettes')");expect(page.locator('#content')).to_contain_text('Réceptionnée');page.evaluate('(id)=>openPartnerPalette(id)',did);expect(page.locator('#pp-receive-form')).to_have_count(0)
  # Async owner guard: a detail response cannot render under another session.
  page.evaluate('(id)=>{window.ppSavedApi=api;api=async(...args)=>{const d=await ppSavedApi(...args);if(args[0]===\'/partner-palettes/\'+id){window.ppDelayed=true;await new Promise(r=>window.ppRelease=r)}return d};window.ppTask=openPartnerPalette(id)}',did);page.wait_for_function('window.ppDelayed');page.evaluate('async()=>{S.user.id=999;closeModal();ppRelease();await ppTask;api=ppSavedApi}');expect(dialog(page)).to_have_count(0)
  login(page,'client@oriental24.ma');expect(page.locator('.sidebar')).not_to_contain_text('Palettes partenaires')
  # Standalone: real local UI, same physical confirmation rules.
  page.goto((ROOT.parent/'ORIENTAL24-demo.html').as_uri());page.get_by_role('button',name='Admin',exact=True).first.click();page.wait_for_selector('.stats')
  local=page.evaluate("async()=>{const u=await api('/users','POST',{name:'Société locale fictive',company:'Partenaire local',email:'soc-local@example.test',phone:'0600000000',role:'client',client_type:'societe_livraison',password:'Oriental24!Demo'});const h=await api('/logistics/hubs','POST',{name:'Hub local fictif',city_id:1,address:'Adresse démo'});for(let i=0;i<3;i++)await api('/parcels','POST',{client_id:u.id,tracking:'LOCAL-000'+i+'/Ab',recipient:'Destinataire local',phone:'0600000000',city_id:1,address:'Adresse fictive',amount:100});await api('/login','POST',{email:'soc-local@example.test',password:'Oriental24!Demo'});await enterApp();return u.id}")
  page.evaluate("navigate('partner-palettes')");page.get_by_role('button',name='Préparer une palette',exact=True).click();page.wait_for_selector('.pp-candidate');page.locator('.pp-candidate input').nth(0).check();page.locator('.pp-candidate input').nth(1).check();page.locator('.modal form button[type=submit]').click();page.wait_for_selector('.pp-document-head');ldid=page.evaluate("async()=> (await api('/partner-palettes')).rows[0].id");confirm(page,'Confirmer l’envoi');expect(dialog(page)).to_contain_text('Envoyée · à recevoir')
  page.evaluate("async()=>{closeModal();await api('/login','POST',{email:'admin@oriental24.ma',password:'Oriental24!Demo'});await enterApp()}");page.evaluate('(id)=>openPartnerPalette(id)',ldid);page.wait_for_selector('#pp-receive-form');code=page.evaluate('(id)=>api("/partner-palettes/"+id).then(d=>d.lines[0].tracking)',ldid);page.locator('#pp-receive-form #f-tracking').fill(code);page.locator('#pp-receive-form input[name=confirmed]').check();page.locator('#pp-receive-form button[type=submit]').click();expect(dialog(page)).to_contain_text('Réception partielle');confirm(page,'Recevoir tous les 1 restants');expect(dialog(page)).to_contain_text('Réceptionnée')
  assert page.evaluate('localDemo.parcels.filter(p=>p.client_id==='+str(local)+').every(p=>p.tracking.startsWith("LOCAL-")&&p.amount===100&&p.fee===25)')
  page.reload();page.get_by_role('button',name='Admin',exact=True).first.click();page.wait_for_selector('.stats');page.evaluate('(id)=>openPartnerPalette(id)',ldid);expect(dialog(page)).to_contain_text('Réceptionnée');assert not errors,errors;b.close()
 with app.conn() as db:
  assert before==[tuple(r) for r in db.execute('SELECT id,tracking,client_id,amount,fee,return_fee,invoice_id FROM parcels ORDER BY id')]
  for table in ['invoices','client_receipts','driver_statements','driver_transactions']:assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
 print('PASS: no-hub guidance; Admin creates shared hub; company draft/select/send; Admin scan partial, duplicate, full physical receipt; lost-response retry exactly once; company follow-up; seller menu hidden; scoped CSV + printable PDF; mobile; async owner guard; standalone full cycle/persistence; original tracking/ownership/COD/fees/invoice untouched; no financial entries. Zero JavaScript errors.')
finally:server.shutdown();shutil.rmtree(TMP)
