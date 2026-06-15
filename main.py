import requests
import os
import json
import urllib3

# Отключаем предупреждения SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/api/matchup/{EVENT_ID}/{FIGHT_ID}/post"
headers = {"User-Agent": "Mozilla/5.0"}

# verify=False – игнорируем ошибки SSL
resp = requests.get(url, headers=headers, timeout=15, verify=False)
print(f"Статус ответа: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    # Выводим только статистику раундов (если есть)
    rounds = data.get("stats", {}).get("rounds", [])
    print(f"Количество раундов: {len(rounds)}")
    for rd in rounds:
        label = rd.get("label", "?")
        ts_red = rd.get("total_strikes_red", 0)
        ts_blue = rd.get("total_strikes_blue", 0)
        sig_red = rd.get("sig_strikes_red", 0)
        sig_blue = rd.get("sig_strikes_blue", 0)
        print(f"{label}: Total {ts_red}-{ts_blue}, Sig {sig_red}-{sig_blue}")
else:
    print(f"Ошибка API: {resp.status_code}")
    print(resp.text[:500])
