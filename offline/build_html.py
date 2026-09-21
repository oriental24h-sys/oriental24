"""Generate one standalone, offline HTML demo from the application UI + simulated adapter.
Always seeds a fresh temporary database; never reads or writes the live database.
"""
import base64, json, os, re, sys, tempfile, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));temp=tempfile.mkdtemp(prefix='o24-html-seed-')
os.environ['ORIENTAL24_MODE']='demo'
os.environ['ORIENTAL24_DEMO_AGENT']='1'
os.environ['DB_PATH']=str(Path(temp)/'seed.sqlite')
import app
try:
    with app.conn() as c:
        tables=['cities','parcels','events','invoices','tickets','messages','products','movements','pickups','pallets','requests','stock_requests','ops_hubs']
        seed={table:[dict(r) for r in c.execute('SELECT * FROM '+table)] for table in tables}
        seed['users']=[dict(r) for r in c.execute('SELECT id,name,email,role,company,phone,active,client_type,agent_hub_id FROM users')]
        seed['settings']={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
        for e in seed['events']:e['actor']=next(u['name'] for u in seed['users'] if u['id']==e['actor_id'])
    seed['announcements']=[
        dict(id=1,title='Démo · Modèle d’import',body='Le modèle Excel de la version serveur reprend les villes ouvertes dans vos paramètres.',kind='important',audience=['admin','client'],active=True,position=1,link_kind='template',link_label='Télécharger le modèle Excel',link_url='',revision=1),
        dict(id=2,title='Démo · Informations de service',body='L’administration peut publier ici ses consignes et choisir les espaces qui les verront.',kind='warning',audience=['admin','client','livreur'],active=True,position=2,link_kind='none',link_label='',link_url='',revision=1),
        dict(id=3,title='إعلانات ORIENTAL24 · تجريبي',body='يمكن للإدارة تغيير هذه الرسالة ونشر التعليمات هنا. هذه مجرد رسالة للتجربة.',kind='info',audience=['admin','client','livreur'],active=True,position=3,link_kind='none',link_label='',link_url='',revision=1),
        dict(id=4,title='Votre communication, au même endroit.',body='Bandeau de démonstration ORIENTAL24. Personnalisez le titre, le message et la visibilité depuis Annonces & bandeau.',kind='banner',audience=['admin','client','livreur'],active=True,position=4,link_kind='none',link_label='',link_url='',revision=1)
    ]
    from logistics import REASONS
    seed['followup_reasons']=[{'code':code,'label':label,'active':1} for code,label in REASONS]
    seed.update(version=1,statuses=app.STATUSES,status_policy=app.status_policy(),terms={},statements=[],transactions=[],lines=[],audit=[],previews={})
    cl=app.app.test_client();cl.post('/api/login',json={'email':'admin@oriental24.ma','password':'Oriental24!Demo'})
    csrf=cl.get('/api/bootstrap').json['csrf']
    labels=cl.post('/api/labels',json={'ids':[p['id'] for p in seed['parcels']]},headers={'X-CSRF-Token':csrf}).json
    codes={p['tracking']:{k:p[k] for k in ['qr','barcode']} for p in labels}
finally:shutil.rmtree(temp)
assets={name:'data:image/png;base64,'+base64.b64encode((ROOT/'static'/f'{name}.png').read_bytes()).decode() for name in ['logo','wordmark','van']}
def jsjson(data):return json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
scripts=[]
for filename in ['app.js','operations.js','driver-finance.js','pilotage.js','logistics.js','parcel-contacts.js','parcel-state.js','parcel-copy.js','parcel-city.js','parcel-claim.js','workspace-ui.js','driver-workspace.js','driver-invoice.js','driver-invoice-print.js','billing.js','security.js','partner-palettes.js','reception-extras.js']:
    s=(ROOT/'static'/filename).read_text()
    s=re.sub(r'\bhistory\.replaceState\(null, "", "/(?:login|app)"\);','/* Standalone file: keep the current URL. */',s)
    s=re.sub(r'^boot\(\);\s*$','',s,flags=re.M)
    for name in assets:s=s.replace('/static/'+name+'.png','${OFFLINE_ASSETS.'+name+'}')
    scripts.append(s)
css='\n'.join((ROOT/'static'/file).read_text() for file in ['style.css','operations.css','driver-finance.css','pilotage.css','logistics.css','parcel-contacts.css','parcel-state.css','parcel-city.css','parcel-claim.css','workspace-ui.css','driver-workspace.css','billing.css','partner-palettes.css'])
css+='''
body{padding-top:48px}.offline-bar{position:fixed;inset:0 0 auto;z-index:2000;height:48px;display:flex;align-items:center;justify-content:space-between;gap:12px;background:#071d3c;color:white;padding:0 20px;font-size:11px;box-shadow:0 2px 8px #061b3826}.offline-bar strong{color:#ff9b54;font-size:11px}.offline-bar>div{display:flex;align-items:center;gap:7px}.offline-bar .offline-label{color:#c4d1e2;font-size:10px}.offline-bar button{color:white;background:#ffffff10;border:1px solid #ffffff22;border-radius:5px;padding:6px 10px;font-size:10px;white-space:nowrap}.offline-bar button:hover{background:#ff7c19;border-color:#ff7c19}.sidebar{top:48px;height:calc(100vh - 48px)}.topbar{top:48px}.modal-backdrop{z-index:2100}#toast-root{position:relative;z-index:2200}.offline-safety{max-width:450px;color:#becbdf}.offline-bar .offline-reset{color:#ffb580}
@media(max-width:760px){body{padding-top:86px}.offline-bar{height:86px;flex-direction:column;justify-content:center;gap:8px;padding:8px}.offline-bar>div{gap:5px}.offline-bar button{padding:6px 9px;font-size:10px}.offline-bar .offline-label{font-size:9px}.offline-bar strong{font-size:10px}.sidebar{top:86px;height:calc(100vh - 86px)}.topbar{top:86px}.offline-safety{display:none}}
@media print{body{padding-top:0}.offline-bar{display:none!important}}
'''
head='''<!doctype html><html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#071d3c"><title>ORIENTAL24 — Démo HTML autonome</title>'''
bar='''<div class="offline-bar"><div><strong>ORIENTAL24 · HTML DÉMO</strong><span class="offline-label">Simulation locale · Aucun serveur</span></div><div><button onclick="closeModal();renderPublic();window.scrollTo(0,0)">Accueil</button><button onclick="offlineSwitch('admin')">Admin</button><button onclick="offlineSwitch('client')">Client</button><button onclick="offlineSwitch('livreur')">Livreur</button><button onclick="offlineSwitch('agent')">Agent</button><button onclick="offlineInfo()" aria-label="Mode d’emploi">?</button><button class="offline-reset" onclick="offlineReset()">Réinitialiser</button></div></div>'''
body='''<div id="root"><div class="boot">ORIENTAL<span>24</span><small>Démo HTML sans installation…</small></div></div><div id="modal-root"></div><div id="toast-root" aria-live="polite"></div><div id="print-root"></div>'''
data='const OFFLINE_SEED='+jsjson(seed)+';\nconst OFFLINE_CODES='+jsjson(codes)+';\nconst OFFLINE_ASSETS='+jsjson(assets)+';\n'
html=head+'<link rel="icon" href="'+assets['wordmark']+'"><style>'+css+'</style></head><body>'+bar+body+'<script>'+data+'\n'.join(scripts)+'\n'+(ROOT/'offline/driver_workspace.js').read_text()+'\n'+(ROOT/'offline/billing.js').read_text()+'\n'+(ROOT/'offline/partner_palettes.js').read_text()+'\n'+(ROOT/'offline/adapter.js').read_text()+'</script></body></html>'
dest=ROOT.parent/'ORIENTAL24-demo.html';dest.write_text(html)
print(dest, len(html.encode()),'bytes; 48 fictitious parcels; no server dependencies')
