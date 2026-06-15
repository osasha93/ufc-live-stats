import requests
from bs4 import BeautifulSoup
import os

EVENT_URL = "https://www.ufc.com/event/ufc-fight-night-june-20-2026"

headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(EVENT_URL, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# --- Event ID ---
ticker = soup.find("div", id="c-listing-ticker")
if not ticker:
    ticker = soup.find("div", class_="c-listing-ticker--footer")
event_id = int(ticker["data-fmid"]) if ticker and ticker.get("data-fmid") else None

print(f"Event ID: {event_id}")

# --- Fight IDs (снизу вверх, т.е. от первого боя к главному) ---
fight_cards = soup.select("div.c-listing-ticker-fightcard[data-fmid]")
fight_ids = [int(card["data-fmid"]) for card in fight_cards]
# Порядок в HTML: первый в DOM – главный бой, последний – прелимы.
# Чтобы получить от первого боя к главному, переворачиваем список.
fight_ids_reversed = list(reversed(fight_ids))

print(f"Количество боёв: {len(fight_ids_reversed)}")
print("Fight ID (от первого к главному):")
for fid in fight_ids_reversed:
    print(f"  {fid}")
