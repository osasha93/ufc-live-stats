import requests
from bs4 import BeautifulSoup
import os
import re

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем любой элемент, содержащий число 44
for tag in soup.find_all(text=re.compile(r'\b44\b')):
    parent = tag.find_parent('div', class_='c-stat-metric-compare')
    if parent:
        print("=== НАЙДЕН БЛОК С 44 ===")
        print(parent.prettify()[:1500])
        break
else:
    print("Блок с 44 не найден.")
