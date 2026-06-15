import requests
import os
import json
import re
from bs4 import BeautifulSoup

EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-freedom-250")
EVENT_ID = int(os.environ.get("EVENT_ID", "1309"))   # твой текущий ID

def get_cloudfront_domain():
    # Попробуем найти домен в скриптах страницы события
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
    # Резервный
    return "d29dxerjsp82wz.cloudfront.net"

def get_event_id_from_page():
    """Извлекает event_id из JS на странице события."""
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
    return None

domain = get_cloudfront_domain()
print(f"CloudFront домен: {domain}")

auto_event_id = get_event_id_from_page()
print(f"Автоматически определённый event_id: {auto_event_id}")
print(f"Секретный event_id: {EVENT_ID}")

# Проверим, что API работает с полученным доменом
if auto_event_id:
    test_url = f"https://{domain}/api/v3/event/live/{auto_event_id}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    resp = requests.get(test_url, headers=headers, timeout=15)
    if resp.status_code == 200:
        print("Event API доступен! Вот первые 500 символов ответа:")
        print(resp.text[:500])
    else:
        print(f"Event API вернул статус {resp.status_code}")
