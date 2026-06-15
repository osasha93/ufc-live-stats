import requests
from bs4 import BeautifulSoup
import os
import json
import re

# ---------- Настройки ----------
EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-fight-night-june-20-2026")
MANUAL_EVENT_ID = os.environ.get("EVENT_ID", None)

FALLBACK_DOMAIN = "d29dxerjsp82wz.cloudfront.net"   # резерв на случай, если новый домен не найден
DOMAIN_FILE = "cloudfront_domain.txt"

# ---------- 1. Определение CloudFront домена ----------
def find_cloudfront_domain():
    # Пробуем найти на странице события
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(EVENT_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all('script'):
            if script.string and 'cloudfront' in script.string:
                match = re.search(r'(https?://[a-zA-Z0-9.-]+\.cloudfront\.net)', script.string)
                if match:
                    domain = match.group(1).replace('https://', '').replace('http://', '')
                    with open(DOMAIN_FILE, 'w') as f:
                        f.write(domain)
                    print(f"Найден домен на странице: {domain}")
                    return domain
    except Exception as e:
        print(f"Ошибка при поиске домена: {e}")

    # Если не найден, пробуем загрузить из файла
    if os.path.exists(DOMAIN_FILE):
        with open(DOMAIN_FILE, 'r') as f:
            domain = f.read().strip()
            if domain:
                print(f"Домен загружен из файла: {domain}")
                return domain

    # Иначе используем резервный
    print(f"Использую резервный домен: {FALLBACK_DOMAIN}")
    return FALLBACK_DOMAIN

# ---------- 2. Получение Event ID ----------
def find_event_id(domain):
    if MANUAL_EVENT_ID:
        return int(MANUAL_EVENT_ID)

    # Пробуем найти на странице события
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(EVENT_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all('script'):
            if script.string and 'eventId' in script.string:
                match = re.search(r'"eventId"\s*:\s*"?(\d+)"?', script.string)
                if match:
                    return int(match.group(1))
    except Exception as e:
        print(f"Ошибка при поиске eventId на странице: {e}")

    # Пробуем через API предстоящих событий
    try:
        api_url = f"https://{domain}/api/v3/event/upcoming.json?limit=1"
        headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
        resp = requests.get(api_url, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            events = data.get("LiveEventDetails", [])
            if events:
                return events[0].get("EventId")
    except Exception as e:
        print(f"Ошибка при запросе upcoming.json: {e}")

    return None

# ---------- Диагностика ----------
print("=== ДИАГНОСТИКА ===")
domain = find_cloudfront_domain()
print(f"CloudFront домен: {domain}")

event_id = find_event_id(domain)
if event_id:
    print(f"Определённый event_id: {event_id}")
else:
    print("Не удалось определить Event ID. Укажите его вручную в секретах GitHub (EVENT_ID).")
    exit(1)

# Загружаем список боёв
test_url = f"https://{domain}/api/v3/event/live/{event_id}.json"
headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
resp = requests.get(test_url, headers=headers, timeout=15)
if resp.status_code == 200:
    data = resp.json()
    fights = data.get("LiveEventDetail", {}).get("FightCard", [])
    print(f"Количество боёв: {len(fights)}")
    print("Список боёв (FightID, Order, Status):")
    for f in fights:
        print(f"  {f.get('FightId')} (order {f.get('FightOrder')}) - {f.get('Status')}")
else:
    print(f"Ошибка загрузки FightCard: {resp.status_code} {resp.text[:200]}")
