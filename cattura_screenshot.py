"""
Cattura screenshot del sito nuovo e del sito originale per la presentazione.
"""
from playwright.sync_api import sync_playwright
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR = os.path.join(BASE_DIR, 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()

    # --- Screenshot del NUOVO sito ---
    page = browser.new_page(viewport={'width': 1280, 'height': 800})

    # Homepage nuovo sito
    page.goto(f'file:///{BASE_DIR}/index.html'.replace('\\', '/'))
    page.wait_for_timeout(1500)
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'nuovo_homepage.png'), full_page=False)
    print('Screenshot: nuovo_homepage.png')

    # Scroll alla sezione notizie
    page.evaluate('window.scrollTo(0, 800)')
    page.wait_for_timeout(800)
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'nuovo_notizie.png'), full_page=False)
    print('Screenshot: nuovo_notizie.png')

    # Scroll alla sezione offerta formativa
    page.evaluate('window.scrollTo(0, 2500)')
    page.wait_for_timeout(800)
    page.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'nuovo_offerta.png'), full_page=False)
    print('Screenshot: nuovo_offerta.png')

    # Mobile view
    page_mobile = browser.new_page(viewport={'width': 375, 'height': 812})
    page_mobile.goto(f'file:///{BASE_DIR}/index.html'.replace('\\', '/'))
    page_mobile.wait_for_timeout(1500)
    page_mobile.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'nuovo_mobile.png'), full_page=False)
    print('Screenshot: nuovo_mobile.png')

    # --- Screenshot del VECCHIO sito ---
    page_old = browser.new_page(viewport={'width': 1280, 'height': 800})
    try:
        page_old.goto('https://www.saettalivatinoravanusa.edu.it/', timeout=15000)
        page_old.wait_for_timeout(3000)
        page_old.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'vecchio_homepage.png'), full_page=False)
        print('Screenshot: vecchio_homepage.png')

        # Mobile vecchio sito
        page_old_mobile = browser.new_page(viewport={'width': 375, 'height': 812})
        page_old_mobile.goto('https://www.saettalivatinoravanusa.edu.it/', timeout=15000)
        page_old_mobile.wait_for_timeout(3000)
        page_old_mobile.screenshot(path=os.path.join(SCREENSHOTS_DIR, 'vecchio_mobile.png'), full_page=False)
        print('Screenshot: vecchio_mobile.png')
    except Exception as e:
        print(f'Errore screenshot vecchio sito: {e}')

    browser.close()

print('Screenshot completati!')
