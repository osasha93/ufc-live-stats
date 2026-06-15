import requests
import json
import time

FIGHT_ID = 12710
url = f"https://d29dxerjsp82wz.cloudfront.net/api/v3/fight/live/{FIGHT_ID}.json?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}

resp = requests.get(url, headers=headers, timeout=15)
print(f"Статус: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    # Выведем первые 3000 символов JSON, чтобы увидеть структуру
    print(json.dumps(data, indent=2)[:3000])
else:
    print(f"Ошибка: {resp.text[:500]}")
