import requests
from bs4 import BeautifulSoup
import os
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем панель Round 1
panel = soup.find("div", id="tab-panel-stats-fight-overview-2")
if panel:
    print("=== СЫРОЙ ТЕКСТ ПАНЕЛИ ROUND 1 ===")
    print(panel.get_text(separator="\n", strip=True)[:2000])
else:
    print("Панель Round 1 не найдена.")
