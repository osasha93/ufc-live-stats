import requests
from bs4 import BeautifulSoup
import os
import re

EVENT_URL = os.environ["EVENT_URL"]

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(EVENT_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

print("=== ССЫЛКИ С MATCHUP (если есть) ===")
for a in soup.find_all("a", href=True):
    if "matchup" in a["href"]:
        print(a["href"])

print("\n=== ХЭШИ БОЁВ ===")
for a in soup.find_all("a", href=re.compile(r'#\d+')):
    print(a["href"])

print("\n=== ФРАГМЕНТЫ JS, где встречается 'event' ===")
for script in soup.find_all("script"):
    if script.string and "event" in script.string.lower():
        # Выводим первые 500 символов каждого подходящего скрипта
        print(script.string[:500])
        print("---")
