import requests
import os
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/api/matchup/{EVENT_ID}/{FIGHT_ID}/post"
headers = {"User-Agent": "Mozilla/5.0"}

resp = requests.get(url, headers=headers, timeout=15, verify=False)
print(f"Статус ответа: {resp.status_code}")
print(f"Первые 500 символов ответа:\n{resp.text[:500]}")
