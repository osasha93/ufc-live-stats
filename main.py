import requests
from bs4 import BeautifulSoup
import os
import time

# Временные настройки
FIGHT_ID = 12826
EVENT_ID = 1313
STATS_URL = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(STATS_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Выведем начало HTML
print("=== HTML (первые 2000 символов) ===")
print(soup.prettify()[:2000])

# Ищем все div с классом, содержащим 'stat'
print("\n=== Блоки со словом 'stat' в классе ===")
for div in soup.find_all("div", class_=lambda c: c and "stat" in c):
    print(div.get("class"), div.get_text(strip=True)[:100])

# Ищем таблицы
print("\n=== Таблицы ===")
for table in soup.find_all("table"):
    print(table.get("class"))
