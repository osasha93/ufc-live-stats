"""
Картинка боя: HTML-карточка (card.py, скилл social-canvas) → PNG через Playwright/Chromium.
Браузер запускается один раз и живёт весь цикл (обновление каждые 5 с — рендер ~0.3 с).
Если Chromium недоступен или упал — запасной рисунок Pillow (render_pillow.py), чтобы бот не молчал.
"""
import atexit

import card
import render_pillow
from fight import FightView

_browser = None
_page = None
_playwright = None
_disabled = False


def _get_page():
    global _browser, _page, _playwright
    if _page is None:
        from playwright.sync_api import sync_playwright
        _playwright = sync_playwright().start()
        _browser = _playwright.chromium.launch(args=["--font-render-hinting=none"])
        _page = _browser.new_page(viewport={"width": card.W, "height": card.H}, device_scale_factor=1)
        atexit.register(close)
    return _page


def close() -> None:
    global _browser, _page, _playwright
    try:
        if _browser:
            _browser.close()
        if _playwright:
            _playwright.stop()
    except Exception:
        pass
    _browser = _page = _playwright = None


def render_html(view: FightView, event_name: str, photos=(None, None)) -> bytes:
    page = _get_page()
    page.set_content(card.build_html(view, event_name, photos), wait_until="load")
    page.evaluate("document.fonts.ready")
    overflow = page.evaluate("document.querySelector('.canvas').scrollHeight - document.querySelector('.canvas').clientHeight")
    if overflow > 0:
        print(f"⚠️ Карточка не влезает по высоте на {overflow}px")
    return page.screenshot(clip={"x": 0, "y": 0, "width": card.W, "height": card.H})


def render(view: FightView, event_name: str, photos=(None, None)) -> bytes:
    """PNG карточки. Сначала HTML (social-canvas); при сбое Chromium — Pillow до конца запуска."""
    global _disabled
    if not _disabled:
        try:
            return render_html(view, event_name, photos)
        except Exception as e:
            print(f"⚠️ HTML-рендер недоступен ({type(e).__name__}: {e}) — рисую запасной вариант Pillow.")
            _disabled = True
            close()
    return render_pillow.render(view, event_name, photos)
