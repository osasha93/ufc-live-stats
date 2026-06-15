import requests
from bs4 import BeautifulSoup
import os
import json
import re

# ---------- Настройки ----------
EVENT_URL = os.environ.get("EVENT_URL", "https://www.ufc.com/event/ufc-fight-night-june-20-2026")
# Временный домен, чтобы завершить диагностику (потом будет автоматически)
CLOUDFRONT_DOMAIN = "d29dxerjsp82wz.cloudfront.net"

# ---------- 1. Event ID и Fight ID из HTML ----------
def fetch_ids_from_html():
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(EVENT_URL, headers=headers, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    ticker = soup.find("div", id="c-listing-ticker")
    if not ticker:
        ticker = soup.find("div", class_="c-listing-ticker--footer")
    if not ticker or not ticker.get("data-fmid"):
        raise Exception("Event ID не найден – возможно, кард ещё не опубликован.")
    event_id = int(ticker["data-fmid"])

    fight_cards = soup.select("div.c-listing-ticker-fightcard[data-fmid]")
    fight_ids = [int(card["data-fmid"]) for card in fight_cards]

    return event_id, fight_ids

# ---------- 2. Получение статусов через Event API ----------
def fetch_fight_statuses(domain, event_id, fight_ids):
    url = f"https://{domain}/api/v3/event/live/{event_id}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        print(f"Ошибка Event API: {resp.status_code} {resp.text[:200]}")
        return None
    data = resp.json()
    api_fights = data.get("LiveEventDetail", {}).get("FightCard", [])
    status_map = {f["FightId"]: f.get("Status", "?") for f in api_fights if "FightId" in f}
    return [status_map.get(fid, "?") for fid in fight_ids]

# ---------- 3. Пример статистики первого боя ----------
def get_fight_stats(domain, fight_id):
    url = f"https://{domain}/api/v3/fight/live/{fight_id}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code != 200:
        print(f"Ошибка Fight API: {resp.status_code}")
        return None
    lf = resp.json().get("LiveFightDetail", {})
    fighters = lf.get("Fighters", [])
    names = [f"{f.get('Name', {}).get('FirstName', '')} {f.get('Name', {}).get('LastName', '')}".strip() for f in fighters[:2]]
    result = lf.get("Result", {})
    method = result.get("Method", "")
    ending_round = result.get("EndingRound", "")
    ending_time = result.get("EndingTime", "")
    result_str = f"{method} (R{ending_round} {ending_time})" if method else ""
    rounds = lf.get("RoundStats", [])
    print(f"  Имена: {names}")
    print(f"  Результат: {result_str}")
    print(f"  Количество раундов в API: {len(rounds)}")
    if rounds:
        for rd in rounds[0].get("Rounds", [])[:1]:  # первый раунд
            print(f"  Пример Round {rd['RoundNumber']}: Total Strikes red={rd.get('TotalStrikesLanded','?')}, blue={rd.get('TotalStrikesLanded','?')}")

# ========== ДИАГНОСТИКА ==========
print("=== 1. ПОЛУЧЕНИЕ ID ИЗ HTML ===")
event_id, fight_ids = fetch_ids_from_html()
print(f"Event ID: {event_id}")
print(f"Fight IDs (порядок в DOM, первый бой → главный): {fight_ids}")

print("\n=== 2. СТАТУСЫ БОЁВ ===")
statuses = fetch_fight_statuses(CLOUDFRONT_DOMAIN, event_id, fight_ids)
if statuses:
    for fid, st in zip(fight_ids, statuses):
        print(f"  {fid}: {st}")
else:
    print("Не удалось получить статусы.")

print("\n=== 3. ПРИМЕР СТАТИСТИКИ ПЕРВОГО БОЯ ===")
first_fight = fight_ids[0]
get_fight_stats(CLOUDFRONT_DOMAIN, first_fight)

print("\nДиагностика завершена.")
