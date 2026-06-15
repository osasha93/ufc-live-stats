import requests
from bs4 import BeautifulSoup
import os

EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-fight-night-june-20-2026")

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(EVENT_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# --- 1. Ищем Event ID ---
event_id = None
# Ищем контейнер с id="c-listing-ticker" или class="c-listing-ticker--footer"
ticker = soup.find("div", id="c-listing-ticker")
if not ticker:
    ticker = soup.find("div", class_="c-listing-ticker--footer")
if ticker and ticker.get("data-fmid"):
    event_id = int(ticker["data-fmid"])
    print(f"Event ID из HTML: {event_id}")
else:
    print("Не удалось найти Event ID в HTML. Возможно, кард ещё не опубликован.")

# --- 2. Собираем все Fight ID ---
fight_cards = soup.select("div.c-listing-ticker-fightcard[data-fmid]")
fight_ids = [int(card["data-fmid"]) for card in fight_cards]

print(f"Количество боёв: {len(fight_ids)}")
print("Fight ID (порядок в HTML):")
for fid in fight_ids:
    print(f"  {fid}")

# Порядок в HTML обычно от главного боя к первому, поэтому для live-режима переворачиваем
fight_ids_reversed = list(reversed(fight_ids))
print("Fight ID (от первого к главному):")
for fid in fight_ids_reversed:
    print(f"  {fid}")
