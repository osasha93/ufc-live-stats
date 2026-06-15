import requests
from bs4 import BeautifulSoup
import os
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
print(f"Загружаем URL: {url}")
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Выводим язык страницы
html_tag = soup.find('html')
lang = html_tag.get('lang', 'не указан') if html_tag else 'нет html'
print(f"Язык страницы: {lang}")

# Выводим первые 3000 символов HTML
print("\n=== ПЕРВЫЕ 3000 СИМВОЛОВ HTML ===")
print(soup.prettify()[:3000])
