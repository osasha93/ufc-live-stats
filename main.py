import requests
from bs4 import BeautifulSoup
import os

EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-fight-night-june-20-2026")

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(EVENT_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем блок c-listing-ticker (или его footer-версию)
ticker = soup.find("div", id="c-listing-ticker")
if not ticker:
    ticker = soup.find("div", class_="c-listing-ticker--footer")

if ticker:
    print("=== БЛОК C-LISTING-TICKER ===")
    # Выводим первые 3000 символов HTML этого блока
    print(ticker.prettify()[:3000])
    print("\n=== АТРИБУТ data-fmid ===")
    print(ticker.get("data-fmid"))
else:
    print("Блок не найден. Возможно, кард ещё не опубликован.")
