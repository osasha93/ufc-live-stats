import requests
import os
import json
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/api/matchup/{EVENT_ID}/{FIGHT_ID}/post"
headers = {"User-Agent": "Mozilla/5.0"}

resp = requests.get(url, headers=headers, timeout=15)
data = resp.json()

# Выведем первые 3000 символов JSON, чтобы увидеть структуру
print(json.dumps(data, indent=2)[:3000])
