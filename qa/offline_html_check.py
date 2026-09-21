"""Test the standalone HTML directly and in an opaque sandbox iframe, without a server."""
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
ROOT=Path(__file__).resolve().parents[1];FILE=ROOT.parent/'ORIENTAL24-demo.html'
with sync_playwright() as pw:
    browser=pw.chromium.launch(args=['--no-sandbox']);page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[];network=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
    page.goto(FILE.as_uri());page.wait_for_selector('.public-hero');page.evaluate('offlineConfirmReset()');page.wait_for_selector('.stats')
    for view in ['dashboard','parcels','pickups','pallets','stock','print','invoices','driver-finance','drivers','clients','requests','tickets','settings','profile','analytics']:
        page.evaluate(f"navigate('{view}')")
        assert 'Impossible de charger' not in page.locator('#content').inner_text(),view
    page.evaluate("navigate('parcels')");page.get_by_role('button',name='Nouveau colis',exact=True).click()
    for field,val in [('recipient','Destinataire HTML Test'),('phone','0600000000'),('address','Adresse fictive de test'),('amount','100.10')]:page.locator('#f-'+field).fill(val)
    page.locator('#f-client_id').select_option('2');page.locator('#f-city_id').select_option('1')
    page.locator('#modal-form button[type=submit]').click();page.wait_for_selector('#modal-form',state='detached')
    assert page.evaluate("S.parcels.some(p=>p.recipient==='Destinataire HTML Test')")
    pid=page.evaluate("S.parcels.find(p=>p.recipient==='Destinataire HTML Test').id")
    page.evaluate(f"assignDriver({pid})");page.locator('#f-driver_id').select_option('3');page.locator('#modal-form button[type=submit]').click();page.wait_for_selector('#modal-form',state='detached')
    page.evaluate(f"changeStatus({pid})");page.locator('#f-status').select_option('Livré');page.locator('#modal-form button[type=submit]').click();page.wait_for_selector('#modal-form',state='detached')
    page.wait_for_selector(".detail-grid");page.get_by_role("button",name="Fermer",exact=True).click()
    page.evaluate("openDriverFinance('rates')");page.get_by_role('button',name='Configurer le barème',exact=True).first.click();page.wait_for_selector('#driver-terms-form')
    page.locator('#f-mode').select_option('gross')
    for k,v in [('delivered','10.25'),('returned','4.50'),('refused','2.00')]:page.locator('#f-'+k).fill(v)
    page.get_by_role('button',name='Enregistrer le barème',exact=True).click()
    try:page.wait_for_selector('#driver-terms-form',state='detached',timeout=5000)
    except Exception:
        print('OFFLINE FORM DEBUG',page.locator('#driver-terms-form').inner_text(),errors,flush=True);raise
    page.get_by_role('button',name='Nouveau relevé').click();page.locator('#f-driver_id').select_option('3');page.get_by_role('button',name='Vérifier les montants').click();page.wait_for_selector('#finance-confirm')
    page.locator('#finance-confirm').click();page.wait_for_selector('.finance-detail-heading')
    page.get_by_role('button',name='Enregistrer une remise',exact=True).click();page.locator('#f-amount').fill('50.10');page.locator('#f-reference').fill('HTML-TEST-001');page.get_by_role('button',name='Confirmer le règlement').click();page.wait_for_selector('.finance-detail-heading')
    assert page.evaluate('financeDetail.statement.status')=='Partiel'
    page.get_by_role('button',name='Fermer',exact=True).click()
    page.evaluate("navigate('dashboard')");page.screenshot(path=str(ROOT/'qa/html-admin.png'),full_page=True,animations='disabled')
    page.reload();page.wait_for_selector('.public-hero');page.evaluate("offlineSwitch('client')");page.wait_for_selector('.stats')
    assert page.evaluate("S.parcels.some(p=>p.recipient==='Destinataire HTML Test')")
    for view in ['parcels','pickups','stock','invoices','tickets','requests','profile']:
        page.evaluate(f"navigate('{view}')");assert 'Impossible de charger' not in page.locator('#content').inner_text(),view
    page.evaluate('previewLabels([S.parcels.find(p=>OFFLINE_CODES[p.tracking]).id])');page.wait_for_selector('.shipping-label');page.wait_for_function("[...document.querySelectorAll('.shipping-label img')].every(i=>i.complete&&i.naturalWidth>0)")
    page.get_by_role('button',name='Fermer',exact=True).click()
    page.evaluate('openImports()');expect(page.locator('.modal-body')).to_contain_text('version complète');page.get_by_role('button',name='Fermer',exact=True).click()
    page.evaluate("offlineSwitch('livreur')");page.wait_for_selector('.stats');assert page.evaluate('S.parcels.every(p=>p.driver_id===3)')
    page.evaluate("openDriverFinance()");page.wait_for_selector('#finance-statements')
    expect(page.get_by_role('button',name='Nouveau relevé')).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844});assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(ROOT/'qa/html-mobile.png'),full_page=True,animations='disabled')
    # Opaque origin: storage and navigation APIs must not be required by the preview.
    sandbox=browser.new_page(viewport={'width':1440,'height':1000});sandbox.on('pageerror',lambda e:errors.append(str(e)))
    sandbox.on('request',lambda r:network.append(r.url) if r.url.startswith(('http:','https:')) else None)
    sandbox.set_content('<iframe sandbox="allow-scripts" style="width:100%;height:960px;border:0"></iframe>')
    sandbox.locator('iframe').evaluate('(e,html)=>e.srcdoc=html',FILE.read_text())
    frame=sandbox.frame_locator('iframe');frame.locator('.public-hero').wait_for()
    frame.locator('.offline-bar').get_by_role('button',name='Admin',exact=True).click();frame.locator('.stats').wait_for()
    frame.locator('[data-nav="parcels"]').click();sandbox.mouse.move(700,100);frame.locator('.tracking').first.click();frame.locator('.timeline').wait_for()
    frame.get_by_role('button',name='Fermer',exact=True).click()
    frame.locator('.offline-bar').get_by_role('button',name='Mode d’emploi').click();expect(frame.locator('.modal-body')).to_contain_text('uniquement dans l’onglet')
    assert not errors,errors
    assert not network,network
    print('PASS: standalone file, all role views, local parcel workflow, driver rates/statement/partial cash, reload persistence, existing QR labels, unsupported-action notice, mobile, opaque sandbox fallback. No JS errors and no HTTP requests.')
    browser.close()
