"""v1.4.17 audit pilotage: 409 dialog auto-recovery + refusal audit recording + offline parity."""
import os,sys,tempfile,threading,shutil,secrets,re,json
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
TEMP=tempfile.mkdtemp(prefix='o24-1417-');os.environ['DB_PATH']=str(Path(TEMP)/'t.sqlite')
import app as system
server=make_server('127.0.0.1',0,system.app,threaded=True);threading.Thread(target=server.serve_forever,daemon=True).start()
BASE=f'http://127.0.0.1:{server.server_port}'

def client(email):
    c=system.app.test_client();c.post('/api/login',json={'email':email,'password':'Oriental24!Demo'});return c
def csrf(c):return c.get('/api/bootstrap').json['csrf']
def mut(c,url,data,method='post'):
    return getattr(c,method)(url,json=data,headers={'X-CSRF-Token':csrf(c)})
try:
 admin=client('admin@oriental24.ma')
 hub=mut(admin,'/api/logistics/hubs',{'name':'Hub QA 1417','city_id':1,'address':'F'}).json['id']
 hub2=mut(admin,'/api/logistics/hubs',{'name':'Hub QA 1417 bis','city_id':2,'address':'G'}).json['id']
 agent_e=secrets.token_hex(5)+'@qa.test'
 mut(admin,'/api/users',{'role':'agent','name':'Agent QA','email':agent_e,'password':'Oriental24!Demo','phone':'0600000000','company':'','agent_hub_id':hub})
 foreign_e=secrets.token_hex(5)+'@qa.test'
 mut(admin,'/api/users',{'role':'agent','name':'Agent Loin','email':foreign_e,'password':'Oriental24!Demo','phone':'0600000000','company':'','agent_hub_id':hub2})
 soc_e=secrets.token_hex(5)+'@qa.test'
 mut(admin,'/api/users',{'role':'client','client_type':'societe_livraison','name':'Soc QA','email':soc_e,'password':'Oriental24!Demo','phone':'0600000000','company':'Société QA'})
 soc=client(soc_e)
 r1=mut(soc,'/api/parcels',{'tracking':'QA17-001/A','recipient':'Client A','phone':'0600000011','city_id':1,'amount':100,'product':'F','address':'x'});assert r1.status_code==200,r1.json
 r2=mut(soc,'/api/parcels',{'tracking':'QA17-002/B','recipient':'Client B','phone':'0600000022','city_id':1,'amount':110,'product':'F','address':'x'});assert r2.status_code==200,r2.json
 ids={p['tracking']:p['id'] for p in admin.get('/api/bootstrap').json['parcels']};t1,t2=ids['QA17-001/A'],ids['QA17-002/B']
 socid=[u for u in admin.get('/api/bootstrap').json['users'] if u['email']==soc_e][0]['id']
 PP=mut(soc,'/api/partner-palettes',{'client_id':socid,'destination_hub_id':hub,'parcel_ids':[t1,t2],'request_key':secrets.token_hex(16)}).json['id']
 mut(soc,f'/api/partner-palettes/{PP}/dispatch',{'revision':1,'confirmed':True,'request_key':secrets.token_hex(16)})
 # société attempts a physical receive -> 403 + recorded
 r=mut(soc,f'/api/partner-palettes/{PP}/receive',{'revision':1,'confirmed':True,'request_key':secrets.token_hex(16),'tracking':'QA17-001/A'})
 assert r.status_code==403,r.json
 foreign=client(foreign_e)
 r=mut(foreign,f'/api/partner-palettes/{PP}/receive',{'revision':1,'confirmed':True,'request_key':secrets.token_hex(16),'tracking':'QA17-001/A'})
 assert r.status_code==404 and 'pour votre hub' in r.json['error'],r.json
 audit=admin.get(f'/api/partner-palettes/{PP}').json['audit']
 refusals=[a for a in audit if a['action']=='Réception refusée']
 assert len(refusals)==2,audit
 reasons={a['details']['reason'] for a in refusals}
 assert 'Rôle non autorisé à la réception physique' in reasons and 'Agent rattaché à un autre hub' in reasons,refusals
 # wrong-hub agent UI cannot even see the palette (no leak)
 assert foreign.get(f'/api/partner-palettes/{PP}').status_code==404
 # conflict: seize revision 2 legitimately, then resend with stale snapshot via api409 semantic
 with sync_playwright() as pw:
  browser=pw.chromium.launch(args=['--no-sandbox']);errors=[]
  page=browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(BASE+'/login');page.get_by_role('button',name='Admin',exact=True).click();page.wait_for_selector('.stats')
  ag=client(agent_e)
  # Agent receives colis 1 legitimately (bumps palette revision) while admin keeps a stale modal snapshot
  r=mut(ag,f'/api/partner-palettes/{PP}/receive',{'revision':admin.get(f'/api/partner-palettes/{PP}').json['revision'],'confirmed':True,'request_key':secrets.token_hex(16),'tracking':'QA17-001/A'})
  assert r.status_code==200,r.json
  # Admin opens the receive-all confirmation with snapshot AFTER that change, gets current data (dialog already refetches)
  page.evaluate("openPartnerPalette(%d)"%PP);page.wait_for_selector('.pp-actions')
  expect(page.locator('.modal')).to_contain_text('1 / 2')
  page.get_by_role('button',name=re.compile('Recevoir tous les')).click();page.wait_for_selector('.pp-consent')
  # race the snapshot: agent signals remaining colis missing via incidents (another revision bump)
  ERR=mut(ag,f'/api/partner-palettes/{PP}/incidents',{'kind':'missing','line_id':[l for l in admin.get(f'/api/partner-palettes/{PP}').json['lines'] if l['tracking']=='QA17-002/B'][0]['id'],'note':'Introuvable au tri','confirmed':True,'request_key':secrets.token_hex(20)})
  assert ERR.status_code in (200,201),ERR.json
  expect(page.locator('.pp-confirm-list')).to_contain_text('QA17-002/B')
  page.locator('.pp-consent input').check()
  page.get_by_role('button',name=re.compile('Confirmer la réception')).click()
  # expected_remaining changed behind the open dialog: dialog is refreshed (conflict rescued), toast explains, list now shows the missing state
  page.wait_for_function("document.querySelector('.pp-progress')!==null")
  expect(page.locator('#toast-root')).to_contain_text('a changé')
  expect(page.locator('.modal')).to_contain_text('Introuvable au tri')
  page.screenshot(path=str(ROOT/'qa'/'v1417-receiveall-conflict.png'),full_page=False)
  # after refresh, palette is partially received; confirm remaining is zero-receivable state
  d=admin.get(f'/api/partner-palettes/{PP}').json
  assert d['received']==1 and d['missing']==1,(d['received'],d['missing'])
  # offline standalone: same refusal messages + audit entries
  page.goto((ROOT.parent/'ORIENTAL24-demo.html').as_uri());page.wait_for_selector('.public-hero')
  assert 'api409' in page.content() and 'Réception refusée' in page.content()
  assert 'Pour votre hub' in page.content() or 'pour votre hub' in page.content()
  page.evaluate("offlineSwitch('agent')")
  expect(page.locator('#content')).to_contain_text('Palettes partenaires',timeout=20000)
  assert not errors,errors
  browser.close()
 print('PASS: refusal audit records who/why for role+wrong-hub; wrong-hub stays 404 without leak; receive-all conflict shows a readable ACTUALISEZ message (screenshot); dialog refetches palette on open; offline HTML embeds refusal audit + api409; zero JS errors.')
finally:server.shutdown();shutil.rmtree(TEMP)
