import requests
from bs4 import BeautifulSoup
import os
import json
import re

# ---------- Настройки ----------
EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-freedom-250")
MANUAL_EVENT_ID = os.environ.get("EVENT_ID", None)

DEFAULT_CLOUDFRONT_DOMAIN = "d29dxerjsp82wz.cloudfront.net"

# ---------- 1. Определение CloudFront домена ----------
def find_cloudfront_domain():
    # Ищем в скриптах страницы события
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(EVENT_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all('script'):
            if script.string and 'cloudfront' in script.string:
                match = re.search(r'(https?://[a-zA-Z0-9.-]+\.cloudfront\.net)', script.string)
                if match:
                    return match.group(1).replace('https://', '')
    except:
        pass
    return DEFAULT_CLOUDFRONT_DOMAIN

# ---------- 2. Автоматическое получение event_id ----------
def find_event_id(domain):
    # Если задан вручную, вернуть его
    if MANUAL_EVENT_ID:
        return int(MANUAL_EVENT_ID)

    # Пробуем найти в скриптах страницы события (вдруг повезёт)
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(EVENT_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for script in soup.find_all('script'):
            if script.string and 'eventId' in script.string:
                match = re.search(r'"eventId"\s*:\s*"?(\d+)"?', script.string)
                if match:
                    return int(match.group(1))
    except:
        pass

    # Если не нашли, попробуем через API предстоящих событий
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
print(f"Автоматически определённый event_id: {event_id}")

if event_id:
    # Дополнительно проверим, что API жив и отвечает
    test_url = f"https://{domain}/api/v3/event/live/{event_id}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    resp = requests.get(test_url, headers=headers, timeout=15)
    print(f"Статус ответа Event API: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        # Покажем названия первых трёх боёв, чтобы убедиться, что данные корректны
        fights = data.get("LiveEventDetail", {}).get("FightCard", [])
        print(f"Количество боёв в карде: {len(fights)}")
        for f in fights[:3]:
            print(f"  - {f.get('FightId')} (order {f.get('FightOrder')}) status: {f.get('Status')}")
    else:
        print(f"Ответ Event API: {resp.text[:300]}")
else:
    print("Не удалось определить event_id. Проверьте секрет EVENT_ID или страницу события.")
