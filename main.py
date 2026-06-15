import requests
import json
import time

FIGHT_ID = 12710
url = f"https://d29dxerjsp82wz.cloudfront.net/api/v3/fight/live/{FIGHT_ID}.json?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}

resp = requests.get(url, headers=headers, timeout=15)
data = resp.json()

# Выведем ключи LiveFightDetail
lf = data.get("LiveFightDetail", {})
print("=== Ключи LiveFightDetail ===")
print(list(lf.keys()))

# Ищем, где могут быть раунды
for key in lf:
    if "round" in key.lower() or "stat" in key.lower() or "strike" in key.lower():
        print(f"\n=== Поле '{key}' ===")
        print(json.dumps(lf[key], indent=2)[:2000])
