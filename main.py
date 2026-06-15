import requests
from bs4 import BeautifulSoup
import os

EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-fight-night-june-20-2026")

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(EVENT_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# --- 1. Ищем Event ID ---
event_id = None
ticker = soup.find("div", id="c-listing-ticker")
if not ticker:
    ticker = soup.find("div", class_="c-listing-ticker--footer")
if ticker and ticker.get("data-fmid"):
    event_id = int(ticker["data-fmid"])

print(f"Event ID из HTML: {event_id}")

# --- 2. Собираем все Fight ID ---
fight_cards = soup.select("div.c-listing-ticker-fightcard[data-fmid]")
fight_ids = [int(card["data-fmid"]) for card in fight_cards]

print(f"Количество боёв: {len(fight_ids)}")
print("Fight ID (порядок снизу вверх):")
for fid in fight_ids:
    print(f"  {fid}")

# Примечание: порядок в HTML обычно от главного боя к первому, поэтому если хотим от первого к главному – reverse()
fight_ids.reverse()
print("Fight ID (от первого к главному):")
for fid in fight_ids:
    print(f"  {fid}")
