import requests
from bs4 import BeautifulSoup
import os
import json
import time
import io
import re
from PIL import Image, ImageDraw, ImageFont

# ---------- Настройки ----------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID")

EVENT_URL = os.environ.get("EVENT_URL", "")
EVENT_ID = int(os.environ["EVENT_ID"])

CURRENT_INDEX_FILE = "current_index.txt"
FIGHT_IDS_FILE = "fight_ids.json"
MSG_ID_FILE = "live_message_id.txt"

# ---------- Telegram API ----------
def send_photo(photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": ("stats.png", photo_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    if THREAD_ID:
        data["message_thread_id"] = int(THREAD_ID)
    return requests.post(url, data=data, files=files).json()

def edit_message_media(message_id, photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageMedia"
    media = {"type": "photo", "media": "attach://photo", "caption": caption}
    files = {"photo": ("stats.png", photo_bytes, "image/png")}
    data = {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "media": json.dumps(media)
    }
    if THREAD_ID:
        data["message_thread_id"] = int(THREAD_ID)
    return requests.post(url, data=data, files=files).json()

# ---------- Сбор ID боёв ----------
def fetch_fight_ids(event_url):
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(event_url, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    cards = soup.select("div.c-listing-ticker-fightcard[data-fmid]")
    if not cards:
        raise Exception("Бои ещё не добавлены на страницу события.")
    fight_ids = [int(card["data-fmid"]) for card in cards]
    fight_ids.reverse()   # от первого боя к главному
    return fight_ids

# ---------- Парсинг метрик ----------
def parse_metric_from_element(metric_el):
    red_num = metric_el.find("span", class_="c-stat-metric-compare__number")
    red_pct = metric_el.find("span", class_="c-stat-metric-compare__percent")
    red_att = metric_el.find("span", class_="c-stat-metric-compare__value_of")
    blue_num = metric_el.find("span", class_="c-stat-metric-compare__value_2 c-stat-metric-compare__number")
    blue_pct = metric_el.find("span", class_="c-stat-metric-compare__percent_2")
    blue_att = metric_el.find("span", class_="c-stat-metric-compare__value_2_of")

    def extract_int(span):
        if span:
            digits = re.sub(r'\D', '', span.get_text(strip=True))
            return int(digits) if digits else 0
        return 0

    def extract_attempts_text(span):
        if span:
            text = span.get_text(strip=True)
            match = re.search(r'of\s+\d+', text)
            if match:
                return match.group(0)
        return ""

    v1 = extract_int(red_num)
    p1 = extract_int(red_pct)
    a1_text = extract_attempts_text(red_att)
    v2 = extract_int(blue_num)
    p2 = extract_int(blue_pct)
    a2_text = extract_attempts_text(blue_att)
    return (v1, p1, a1_text), (v2, p2, a2_text)

# ---------- Статистика боя ----------
def get_fight_stats(event_id, fight_id):
    url = f"https://www.ufc.com/matchup/{event_id}/{fight_id}/post?t={int(time.time())}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки боя {fight_id}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Статус завершения
    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # Имена бойцов
    names = []
    try:
        json_script = soup.find("script", {"data-drupal-selector": "drupal-settings-json"})
        if json_script and json_script.string:
            data = json.loads(json_script.string)
            athletes = data.get("matchup", {}).get("athletes", [])
            if len(athletes) >= 2:
                for athlete in athletes[:2]:
                    given = athlete.get("name_given", "")
                    family = athlete.get("name_family", "")
                    full_name = f"{given} {family}".strip() or "Unknown"
                    names.append(full_name)
    except:
        pass
    while len(names) < 2:
        names.append("Red Corner" if len(names) == 0 else "Blue Corner")

    # Фото
    photos = []
    try:
        if 'data' in locals():
            athletes = data.get("matchup", {}).get("athletes", [])
            for athlete in athletes[:2]:
                img_url = athlete.get("img", "")
                if img_url and img_url.startswith("http"):
                    photos.append(img_url)
                else:
                    photos.append(None)
    except:
        pass
    while len(photos) < 2:
        photos.append(None)

    # Раунды (через табы)
    round_data = []
    tab_buttons = soup.select("button.c-tabs__nav-btn")
    for btn in tab_buttons:
        round_title = btn.get_text(strip=True)
        if round_title == "Full Fight":
            continue
        panel_id = btn.get("aria-controls")
        if not panel_id:
            continue
        panel = soup.find("div", id=panel_id)
        if not panel:
            continue
        container = panel.find("div", class_="c-stat-group__container")
        if not container:
            continue
        metrics_block = container.find("div", class_="c-stat-metric-compare-group")
        if not metrics_block:
            continue

        total_strikes_el = metrics_block.find("div", class_="total_strikes")
        takedowns_el = metrics_block.find("div", class_="takedowns")
        sig_strikes_el = metrics_block.find("div", class_="sig_strikes")
        knockdowns_el = metrics_block.find("div", class_="knockdowns")

        total_s = parse_metric_from_element(total_strikes_el) if total_strikes_el else ((0,0,""),(0,0,""))
        takedowns = parse_metric_from_element(takedowns_el) if takedowns_el else ((0,0,""),(0,0,""))
        sig_s = parse_metric_from_element(sig_strikes_el) if sig_strikes_el else ((0,0,""),(0,0,""))
        knockdowns = parse_metric_from_element(knockdowns_el) if knockdowns_el else ((0,0,""),(0,0,""))

        round_data.append({
            "title": round_title,
            "Total Strikes": total_s,
            "Takedowns": takedowns,
            "Sig. Strikes": sig_s,
            "Knockdowns": knockdowns
        })

    if not round_data:
        return {"not_started": True, "names": names, "photos": photos, "winner_idx": -1}

    return {
        "not_started": False,
        "names": names,
        "photos": photos,
        "winner_idx": -1,
        "rounds": round_data,
        "finished": finished
    }

# ---------- Генерация картинки ----------
# (оставьте вашу текущую функцию generate_image без изменений)
# ...

# ---------- Основная логика ----------
def main():
    if os.path.exists(FIGHT_IDS_FILE):
        with open(FIGHT_IDS_FILE, 'r') as f:
            old_data = json.load(f)
        if isinstance(old_data, dict) and old_data.get("event_url") != EVENT_URL:
            print("Обнаружен новый турнир! Сбрасываем прогресс.")
            if os.path.exists(CURRENT_INDEX_FILE):
                os.remove(CURRENT_INDEX_FILE)
            if os.path.exists(FIGHT_IDS_FILE):
                os.remove(FIGHT_IDS_FILE)
            if os.path.exists(MSG_ID_FILE):
                os.remove(MSG_ID_FILE)

    current_index = 0
    if os.path.exists(CURRENT_INDEX_FILE):
        with open(CURRENT_INDEX_FILE, 'r') as f:
            current_index = int(f.read().strip())
        print(f"Загружен current_index: {current_index}")

    fight_ids = None
    if os.path.exists(FIGHT_IDS_FILE):
        with open(FIGHT_IDS_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                fight_ids = data
                with open(FIGHT_IDS_FILE, 'w') as fw:
                    json.dump({"event_url": EVENT_URL, "fights": fight_ids}, fw)
            else:
                fight_ids = data.get("fights", [])
        print(f"Загружен список боёв: {len(fight_ids)} ID")
    else:
        if not EVENT_URL:
            raise Exception("Укажите EVENT_URL в секретах GitHub")
        fight_ids = fetch_fight_ids(EVENT_URL)
        with open(FIGHT_IDS_FILE, 'w') as f:
            json.dump({"event_url": EVENT_URL, "fights": fight_ids}, f)
        print(f"Список боёв сохранён: {len(fight_ids)} ID")

    if current_index >= len(fight_ids):
        print("Все бои турнира обработаны.")
        return

    current_fight_id = fight_ids[current_index]
    print(f"Обрабатываем бой {current_fight_id}")
    data = get_fight_stats(EVENT_ID, current_fight_id)
    if not data:
        print("Не удалось получить данные боя.")
        return

    if data.get("not_started") and not os.path.exists(MSG_ID_FILE):
        print("Бой ещё не начался, ждём.")
        return

    img_bytes = generate_image(data)

    if os.path.exists(MSG_ID_FILE):
        with open(MSG_ID_FILE, "r") as f:
            msg_id = int(f.read().strip())
        edit_message_media(msg_id, img_bytes, caption="")
        print(f"Сообщение {msg_id} обновлено.")
    else:
        result = send_photo(img_bytes, caption="")
        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            with open(MSG_ID_FILE, "w") as f:
                f.write(str(msg_id))
            print(f"Новое сообщение {msg_id} создано.")
        else:
            print("Ошибка отправки:", result)
            return

    if data.get("finished"):
        if os.path.exists(MSG_ID_FILE):
            os.remove(MSG_ID_FILE)
        current_index += 1
        with open(CURRENT_INDEX_FILE, 'w') as f:
            f.write(str(current_index))
        print(f"Бой завершён. Обновлён current_index: {current_index}")

if __name__ == "__main__":
    main()
