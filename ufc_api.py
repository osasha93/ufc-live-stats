"""
UFC live API (тот же источник, из которого ufc.com рисует статистику на страницах турнира и боя):
  event/live/<ID турнира>.json — кард, статусы боёв, какой бой и раунд идут сейчас;
  fight/live/<ID боя>.json     — статистика боя по раундам, результат, оценки судей.
Турнир определяется сам: по времени старта из schedule.json (пишет tapology-bot),
иначе — ближайший предстоящий со страницы ufc.com/events.
"""
import json
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

API = "https://d29dxerjsp82wz.cloudfront.net/api/v3"
UFC = "https://www.ufc.com"
API_HEADERS = {"User-Agent": "Mozilla/5.0", "Origin": UFC, "Referer": UFC + "/"}
PAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
UFC_ORGANIZATION_ID = 1        # остальные: 67 — DWCS, 68 — Road to UFC
START_TOLERANCE = timedelta(hours=3)
SCAN_BACK, SCAN_AHEAD, MAX_MISSES = 15, 40, 8

session = requests.Session()


def parse_time(s: str) -> datetime:
    """'2026-10-17T21:00Z' / '2026-10-18T02:19:37Z' → aware UTC."""
    s = s.rstrip("Z")
    fmt = "%Y-%m-%dT%H:%M:%S" if s.count(":") == 2 else "%Y-%m-%dT%H:%M"
    return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)


def api_from_html(html: str) -> str | None:
    """Адрес API со страницы ufc.com (страницы сами грузят статистику с этого CloudFront)."""
    m = re.search(r"([a-z0-9]+\.cloudfront\.net)", html)
    return f"https://{m.group(1)}/api/v3" if m else None


def refresh_api() -> bool:
    """Сервер API сменился? Берём актуальный адрес с главной ufc.com. True — адрес новый."""
    global API
    try:
        found = api_from_html(session.get(UFC, headers=PAGE_HEADERS, timeout=20).text)
    except requests.RequestException:
        return False
    if found and found != API:
        print(f"🔄 Адрес UFC API сменился: {API} → {found}")
        API = found
        return True
    return False


def _get_json(path: str, retry: bool = True) -> dict | None:
    try:
        resp = session.get(f"{API}/{path}", headers=API_HEADERS, timeout=15)
    except requests.ConnectionError as e:
        print(f"⚠️ UFC API {path}: {e}")
        return _get_json(path, False) if retry and refresh_api() else None
    except requests.RequestException as e:
        print(f"⚠️ UFC API {path}: {e}")
        return None
    if resp.status_code == 403 and retry and refresh_api():
        return _get_json(path, False)
    if not resp.ok:
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def get_event(event_id: int) -> dict | None:
    data = _get_json(f"event/live/{event_id}.json")
    return (data or {}).get("LiveEventDetail") or None


def get_fight(fight_id: int) -> dict | None:
    data = _get_json(f"fight/live/{fight_id}.json")
    return (data or {}).get("LiveFightDetail") or None


# ---------- Определение турнира ----------
def is_ufc(ev: dict) -> bool:
    return (ev.get("Organization") or {}).get("OrganizationId") == UFC_ORGANIZATION_ID \
        and bool(ev.get("StartTime")) and ev.get("Status") != "Canceled"


def find_event_id(start: datetime, hint: int | None, fetch=get_event) -> int | None:
    """ID турнира UFC, начинающегося около start. Номера идут не по датам, поэтому перебор вокруг hint
    (последний найденный ID) до MAX_MISSES пустых номеров подряд выше hint."""
    hint = hint or 1336
    misses = 0
    for event_id in range(hint - SCAN_BACK, hint + SCAN_AHEAD):
        ev = fetch(event_id)
        if not ev or not ev.get("EventId"):
            if event_id > hint:
                misses += 1
                if misses >= MAX_MISSES:
                    break
            continue
        misses = 0
        if is_ufc(ev) and abs(parse_time(ev["StartTime"]) - start) <= START_TOLERANCE:
            return event_id
    return None


def parse_events_page(html: str) -> list[str]:
    """Ссылки /event/… со страницы ufc.com/events по порядку (первая — ближайший турнир)."""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.select('a[href^="/event/"]'):
        href = a["href"].split("#")[0].split("?")[0]
        if href not in links:
            links.append(href)
    return links


def parse_event_page_id(html: str) -> int | None:
    """ID турнира в UFC API со страницы турнира на ufc.com (тикер data-fmid — так его брал старый код)."""
    soup = BeautifulSoup(html, "html.parser")
    ticker = soup.find("div", id="c-listing-ticker") or soup.find("div", class_="c-listing-ticker--footer")
    fmid = ticker.get("data-fmid") if ticker else None
    return int(fmid) if fmid and fmid.isdigit() else None


def discover_from_ufc_com(now: datetime, max_pages: int = 3, fetch_page=None, fetch_event=get_event) -> int | None:
    """Ближайший турнир UFC, который идёт сейчас или впереди: ufc.com/events → страница турнира → ID."""
    fetch_page = fetch_page or (lambda url: session.get(url, headers=PAGE_HEADERS, timeout=20).text)
    try:
        links = parse_events_page(fetch_page(f"{UFC}/events"))
    except requests.RequestException as e:
        print(f"⚠️ ufc.com/events: {e}")
        return None
    for href in links[:max_pages]:
        try:
            event_id = parse_event_page_id(fetch_page(UFC + href))
        except requests.RequestException:
            continue
        ev = event_id and fetch_event(event_id)
        if ev and is_ufc(ev) and ev.get("Status") != "Final" \
                and parse_time(ev["StartTime"]) <= now + timedelta(days=8):
            return event_id
    return None


# ---------- Фото бойцов (страница боя на ufc.com) ----------
def matchup_url(event_id: int, fight_id: int) -> str:
    return f"{UFC}/matchup/{event_id}/{fight_id}/post"


def parse_matchup_photos(html: str) -> list[str | None]:
    """[фото красного угла, фото синего] из drupal-settings-json страницы боя."""
    m = re.search(r'<script[^>]+data-drupal-selector="drupal-settings-json"[^>]*>(.*?)</script>', html, re.S)
    photos: list[str | None] = [None, None]
    if not m:
        return photos
    try:
        athletes = json.loads(m.group(1)).get("matchup", {}).get("athletes", [])
    except ValueError:
        return photos
    for i, athlete in enumerate(athletes[:2]):
        img = athlete.get("img") or ""
        if img.startswith("http"):
            photos[i] = img
    return photos


def fighter_photos(event_id: int, fight_id: int) -> list[bytes | None]:
    """Байты фото обоих бойцов (или None) — запрашивается один раз на бой."""
    try:
        urls = parse_matchup_photos(session.get(matchup_url(event_id, fight_id), headers=PAGE_HEADERS, timeout=20).text)
    except requests.RequestException:
        return [None, None]
    result = []
    for url in urls:
        try:
            resp = session.get(url, headers={**PAGE_HEADERS, "Referer": UFC + "/"}, timeout=20) if url else None
            result.append(resp.content if resp is not None and resp.ok else None)
        except requests.RequestException:
            result.append(None)
    return result
