from playwright.sync_api import sync_playwright
import json
from pathlib import Path
BASE=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000');page.wait_for_selector('.public-hero')
    page.screenshot(path=str(BASE/'landing.png'),full_page=True,animations="disabled")
    page.goto('http://127.0.0.1:3000/login')
    page.get_by_role('button',name='Admin',exact=True).click()
    page.wait_for_selector('.sidebar')
    page.screenshot(path=str(BASE/'dashboard.png'),full_page=True,animations="disabled")
    views=['parcels','drivers','clients','pickups','pallets','stock','print','invoices','driver-finance','requests','tickets','settings','profile','analytics']
    for view in views:
        page.locator(f'[data-nav="{view}"]').click()
        page.wait_for_function(f'document.title.startsWith({json.dumps({"parcels":"Gestion","drivers":"Livreurs","clients":"Clients","pickups":"Ramassages","pallets":"Palettes","stock":"Stock","print":"Centre","invoices":"Facturation","driver-finance":"Caisse","requests":"Demandes","tickets":"Réclamations","settings":"Paramètres","profile":"Mon profil","analytics":"Statistiques"}[view])})')
        page.wait_for_timeout(100)
        assert 'Impossible de charger' not in page.locator('#content').inner_text(),view
    page.locator('[data-nav="settings"]').click()
    page.screenshot(path=str(BASE/'settings.png'),full_page=True,animations="disabled")
    page.get_by_role('button',name='Ajouter une ville').click()
    page.wait_for_selector('#modal-form')
    page.screenshot(path=str(BASE/'modal.png'),full_page=True,animations="disabled")
    page.keyboard.press('Escape')
    page.locator('[data-nav="parcels"]').click()
    page.locator('.tracking').first.click()
    page.wait_for_selector('.timeline')
    page.keyboard.press('Escape')
    page.set_viewport_size({'width':390,'height':844})
    page.evaluate("navigate('dashboard')")
    page.wait_for_selector('.stats')
    page.wait_for_timeout(300)
    page.screenshot(path=str(BASE/'mobile.png'),full_page=True,animations="disabled")
    print('Page errors:',errors)
    assert not errors
    print('All views rendered successfully')
    browser.close()
