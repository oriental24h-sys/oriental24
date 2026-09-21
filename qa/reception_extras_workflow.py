"""v1.4.16 browser QA: reception incidents, agent account, alerts, client tariffs,
partner API keys — against an isolated demo server AND the standalone HTML demo."""
import os, sys, tempfile, threading, shutil, io
from pathlib import Path
from werkzeug.serving import make_server
from playwright.sync_api import sync_playwright, expect

expect.set_options(timeout=15000)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp(prefix='o24-v1416-')
os.environ['DB_PATH'] = str(Path(TMP) / 'test.sqlite')
os.environ['ORIENTAL24_MODE'] = 'demo'
os.environ['ORIENTAL24_DEMO_AGENT'] = '1'
import app  # noqa: E402

c = app.app.test_client()
c.post('/api/login', json=dict(email='admin@oriental24.ma', password='Oriental24!Demo'))
H = {'X-CSRF-Token': c.get('/api/bootstrap').json['csrf']}
from PIL import Image  # petit PNG valide pour les photos d'incident
_buf = io.BytesIO(); Image.new('RGB', (32, 24), (255, 124, 25)).save(_buf, 'PNG')
TINY_PNG = _buf.getvalue()

# --- vorbereiten : société + colis + hub + palette en transit ---------------
r = c.post('/api/users', json=dict(name='TDP', company='Transport Démo Partenaire', email='societe@example.test',
           password='Oriental24!Demo', phone='0600000000', role='client', client_type='societe_livraison'), headers=H)
uid = r.json['id']
for i in range(4):
    assert c.post('/api/parcels', json=dict(client_id=uid, tracking=f'REX-000{i}/Cd', recipient=f'Client {i}',
                  phone='0600000000', address='Rue', city_id=1, amount=120, product='Objet'), headers=H).status_code == 200
with app.conn() as db:
    HID = db.execute('SELECT id FROM ops_hubs ORDER BY id LIMIT 1').fetchone()['id']
    PIDS = [r['id'] for r in db.execute('SELECT id FROM parcels WHERE client_id=?', (uid,))]
assert len(PIDS) == 4
trs = [f'REX-000{i}/Cd' for i in range(4)]
did = c.post('/api/partner-palettes', json={'parcel_ids': PIDS, 'destination_hub_id': HID, 'client_id': uid, 'request_key': 'REX-DRAFT-00000000000001',
             'partner_reference': 'REX-DEMO', 'transport': 'Navette'}, headers=H).json['id']
rev = c.get(f'/api/partner-palettes/{did}').json['revision']
r = c.post(f'/api/partner-palettes/{did}/dispatch', json={'confirmed': True, 'revision': rev, 'request_key': 'REX-DISPATCH-0000001'}, headers=H)
assert r.status_code == 200, r.json

server = make_server('127.0.0.1', 0, app.app, threaded=True)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{server.server_port}'


def login(page, email):
    page.goto(BASE + '/login')
    page.locator('#f-email').fill(email)
    page.locator('#f-password').fill('Oriental24!Demo')
    page.locator('#login-form button[type=submit]').click()
    page.wait_for_selector('.sidebar', state='attached', timeout=20000)
    page.wait_for_selector('#content .card', state='attached', timeout=20000)


try:
    with sync_playwright() as pw:
        b = pw.chromium.launch(args=['--no-sandbox'])
        page = b.new_page(viewport={'width': 1440, 'height': 1000})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))

        # ============ 1 · Agent réception : visibilité bornée au hub ============
        login(page, 'agent@oriental24.ma')
        expect(page.locator('.sidebar')).to_contain_text('Palettes partenaires')
        expect(page.locator('.sidebar')).to_contain_text('Alertes')
        expect(page.locator('.sidebar')).not_to_contain_text('Facturation')
        expect(page.locator('.sidebar')).not_to_contain_text('Colis')
        # Redirection automatique vers les palettes pour un agent
        expect(page.locator('#content')).to_contain_text('Palettes partenaires', timeout=20000)
        page.screenshot(path=str(ROOT / 'qa/v1416-agent-home.png'))

        # ============ 2 · Incidents de réception (UI agent) ============
        page.evaluate(f'openPartnerPalette({did})')
        page.wait_for_selector('#pp-receive-form')
        # Colis manquant (ligne attendue)
        page.get_by_role('button', name='Colis manquant', exact=True).click()
        page.wait_for_selector('#pp-incident-form')
        page.wait_for_function("document.querySelectorAll('#f-line_id option').length>=1")
        page.locator('#f-note').fill('Absent physiquement dans le carton')
        page.locator('#pp-incident-form input[name=confirmed]').check()
        page.locator('#pp-incident-form button[type=submit]').click()
        expect(page.locator('#pp-incidents')).to_contain_text('Colis manquant', timeout=20000)
        # Colis endommagé avec photo obligatoire
        page.get_by_role('button', name='Colis endommagé', exact=True).click()
        page.wait_for_selector('#pp-incident-form')
        page.locator('#f-tracking').fill(trs[3])
        page.locator('#f-note').fill('Carton écrasé, contenu vérifié endommagé')
        page.locator('#pp-incident-form input[name=photo]').set_input_files(
            dict(name='degat.png', mimeType='image/png', buffer=TINY_PNG))
        page.locator('#pp-incident-form input[name=confirmed]').check()
        page.locator('#pp-incident-form button[type=submit]').click()
        expect(page.locator('#pp-incidents')).to_contain_text('Colis endommagé', timeout=20000)
        # Colis imprévu
        page.get_by_role('button', name='Colis imprévu', exact=True).click()
        page.wait_for_selector('#pp-incident-form')
        page.locator('#f-tracking').fill('INCONNU-77')
        page.locator('#f-note').fill('Colis trouvé sans manifeste')
        page.locator('#pp-incident-form input[name=confirmed]').check()
        page.locator('#pp-incident-form button[type=submit]').click()
        page.wait_for_timeout(600)
        expect(page.locator('#pp-incidents')).to_contain_text('Colis imprévu')
        page.screenshot(path=str(ROOT / 'qa/v1416-agent-incidents.png'), animations='disabled')
        page.screenshot(path=str(ROOT / 'qa/v1416-agent-incidents-full.png'), full_page=True, animations='disabled')

        # ============ 3 · Société répond à l'incident manquant ============
        login(page, 'societe@example.test')
        page.evaluate(f'openPartnerPalette({did})')
        page.wait_for_selector('#pp-incidents')
        expect(page.locator('#pp-incidents')).to_contain_text('Colis manquant')
        page.locator('#pp-incidents button', has_text='Répondre').first.click()
        page.wait_for_selector('#modal-root form')
        page.locator('#f-response').fill('Vérifié côté dépôt : il reste chez nous, nous le renverrons.')
        page.locator('#modal-root form button[type=submit]').click()
        page.wait_for_timeout(800)
        expect(page.locator('#pp-incidents')).to_contain_text('Réponse société')
        page.screenshot(path=str(ROOT / 'qa/v1416-company-reply.png'), animations='disabled')

        # ============ 4 · Admin : endommagé -> affectation bloquée -> décision ============
        login(page, 'admin@oriental24.ma')
        page.evaluate(f'openPartnerPalette({did})')
        page.wait_for_selector('#pp-incidents')
        page.locator('#pp-incidents button', has_text='Décider').first.click()
        page.wait_for_selector('#modal-root form')
        page.locator('#f-action').select_option('release')
        page.locator('#f-note').fill('Réparé par atelier interne, libéré pour livraison')
        page.locator('#modal-root form button[type=submit]').click()
        page.wait_for_timeout(800)
        expect(page.locator('#pp-incidents')).to_contain_text('colis débloqué')

        # ============ 5 · Tarifs par client (Admin UI) ============
        page.evaluate('closeModal()')
        page.evaluate("navigate('clients')")
        page.wait_for_selector('#content table')
        company_row = page.locator('#content tr', has_text='Transport Démo Partenaire')
        company_row.locator('button[title="Tarifs par ville"]').click()
        page.wait_for_selector('#modal-root table')
        oujda_row = page.locator('#modal-root tr', has_text='Oujda')
        oujda_inputs = oujda_row.locator('input[type=number]')
        oujda_inputs.nth(0).fill('19.5')
        oujda_inputs.nth(1).fill('7')
        oujda_row.locator('button', has_text='Enregistrer').click()
        page.wait_for_timeout(800)
        expect(page.locator('#modal-root')).to_contain_text('Modifié')
        page.screenshot(path=str(ROOT / 'qa/v1416-tariffs.png'), animations='disabled')
        page.evaluate('closeModal()')

        # ============ 6 · Clé API partenaire (Admin UI) + appel réel ============
        company_row.locator("button[title='Clé API partenaire']").click()
        page.wait_for_selector('#pp-key-form')
        page.locator('#pp-key-form input[name=label]').fill('ERP principal')
        page.locator('#pp-key-form button[type=submit]').click()
        page.wait_for_selector('.pp-key')
        key = page.locator('.pp-key').inner_text()
        assert key.startswith('O24K-'), key
        page.screenshot(path=str(ROOT / 'qa/v1416-apikey.png'), animations='disabled')
        page.evaluate('closeModal()')
        rc = page.evaluate("""async(k)=>{const r=await fetch('/api/partner/v1/cities',{headers:{Authorization:'Bearer '+k}});return {s:r.status,j:await r.json()}}""", key)
        assert rc['s'] == 200 and rc['j']['cities'], rc
        rc = page.evaluate("""async(k)=>{const r=await fetch('/api/partner/v1/parcels',{method:'POST',headers:{Authorization:'Bearer '+k,'Content-Type':'application/json','Idempotency-Key':'BROWSER-TEST-000000001'},body:JSON.stringify({tracking:'API-001',recipient:'Client API',phone:'0600000000',city:'Oujda',address:'Rue',amount:99})});return {s:r.status,j:await r.json()}}""", key)
        assert rc['s'] == 201 and rc['j']['tracking'] == 'API-001', rc
        assert rc['j']['fee'] == 19.5, ('tarif client appliqué via API', rc)

        # ============ 7 · Alertes (vue + seuils) ============
        page.evaluate("navigate('alerts')")
        page.wait_for_selector('#content .card')
        expect(page.locator('#content')).to_contain_text('Alertes de retard')
        page.screenshot(path=str(ROOT / 'qa/v1416-alerts.png'), animations='disabled')

        # ============ 8 · HTML autonome : agent + incident + alertes ============
        page.goto((ROOT.parent / 'ORIENTAL24-demo.html').as_uri())
        page.get_by_role('button', name='Agent', exact=True).first.click()
        page.wait_for_selector('.sidebar', state='attached', timeout=20000)
        expect(page.locator('.sidebar')).to_contain_text('Alertes')
        page.evaluate("navigate('alerts')")
        page.wait_for_selector('#content .card', timeout=20000)
        expect(page.locator('#content')).to_contain_text('Alertes de retard')
        page.screenshot(path=str(ROOT / 'qa/v1416-html-agent-alerts.png'), animations='disabled')

        b.close()
    assert not errors, errors
    print('PASS: agent hub-scoped home; incidents missing/damaged/extra via UI; company reply; admin damaged release; '
          'client tariffs UI; partner API key UI + real calls incl. custom tariff; alerts view; standalone HTML agent + alerts. Zero JS errors.')
finally:
    server.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)
