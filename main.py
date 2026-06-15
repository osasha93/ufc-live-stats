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

panel = soup.find("div", id="tab-panel-stats-fight-overview-2")
if panel:
    # Выводим ВЕСЬ HTML панели (или первые 5000 символов)
    html_content = panel.prettify()
    print(html_content[:5000])
else:
    print("Панель не найдена.")
