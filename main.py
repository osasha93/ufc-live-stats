import requests
from bs4 import BeautifulSoup
import os
import time
import re

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем число 44 внутри любого div.c-stat-metric-compare
for tag in soup.find_all('div', class_='c-stat-metric-compare'):
    if '44' in tag.get_text():
        print("=== НАЙДЕН БЛОК С 44 ===")
        print(tag.prettify()[:2000])
        break
else:
    print("Блок с 44 не найден.")
    # Поищем 44 в любом месте страницы
    if '44' in soup.get_text():
        print("Число 44 присутствует в тексте страницы, но не внутри c-stat-metric-compare.")
    else:
        print("Число 44 отсутствует в тексте страницы.")
