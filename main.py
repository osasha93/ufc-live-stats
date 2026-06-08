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

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_IDS_RAW = os.environ["FIGHT_IDS"]

STATE_FILE = "state.json"
MSG_ID_FILE = "live_message_id.txt"

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

def get_event_data():
    fight_ids = [int(f.strip()) for f in FIGHT_IDS_RAW.split(",") if f.strip()]
    return EVENT_ID, fight_ids

def parse_metric_from_element(metric_el):
    red_num = metric_el.find("span", class_="c-stat-metric-compare__number")
    red_pct = metric_el.find("span", class_="c-stat-metric-compare__percent")
    blue_num = metric_el.find("span", class_="c-stat-metric-compare__value_2 c-stat-metric-compare__number")
    blue_pct = metric_el.find("span", class_="c-stat-metric-compare__percent_2")

    def extract_int(span):
        if span:
            digits = re.sub(r'\D', '', span.get_text(strip=True))
            return int(digits) if digits else 0
        return 0

    v1 = extract_int(red_num)
    p1 = extract_int(red_pct)
    v2 = extract_int(blue_num)
    p2 = extract_int(blue_pct)
    return (v1, p1), (v2, p2)

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

    # Победитель
    winner_idx = -1
    fighter_img_div = soup.find("div", class_="fighter-img")
    if fighter_img_div:
        left_winner = fighter_img_div.find("a", class_="left")
        right_winner = fighter_img_div.find("a", class_="right")
        if left_winner and left_winner.find("div", class_=re.compile("fighter-names__winner--show")):
            winner_idx = 0
        elif right_winner and right_winner.find("div", class_=re.compile("fighter-names__winner--show")):
            winner_idx = 1

    if winner_idx == -1:
        try:
            json_script = soup.find("script", {"data-drupal-selector": "drupal-settings-json"})
            if json_script and json_script.string:
                data = json.loads(json_script.string)
                athletes = data.get("matchup", {}).get("athletes", [])
                for i, athlete in enumerate(athletes[:2]):
                    if athlete.get("outcome") is True:
                        winner_idx = i
                        break
        except:
            pass

    # Имена и фото из JSON
    names = []
    photos = []
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
                    img_url = athlete.get("img", "")
                    if img_url and img_url.startswith("http"):
                        photos.append(img_url)
                    else:
                        photos.append(None)
    except:
        pass

    while len(names) < 2:
        names.append("Red Corner" if len(names) == 0 else "Blue Corner")
    while len(photos) < 2:
        photos.append(None)

    # Статус завершения
    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # --- ДИАГНОСТИКА КОНТЕЙНЕРОВ ---
    containers = soup.find_all("div", class_="c-stat-group__container")
    print(f"Найдено контейнеров c-stat-group__container: {len(containers)}")
    for i, cont in enumerate(containers):
        label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        if not label:
            label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__title"))
        title = label.get_text(strip=True) if label else "БЕЗ НАЗВАНИЯ"
        print(f"  Контейнер {i}: заголовок = '{title}'")
        # Проверим наличие блока метрик
        metrics_block = cont.find("div", class_="c-stat-metric-compare-group")
        if metrics_block:
            # Проверим каждую метрику
            for metric_class in ["total_strikes", "takedowns", "sig_strikes", "knockdowns"]:
                el = metrics_block.find("div", class_=metric_class)
                if el:
                    print(f"    Метрика {metric_class}: найдена")
                else:
                    print(f"    Метрика {metric_class}: НЕ НАЙДЕНА")
        else:
            print("    Блок метрик не найден")

    # Обычный парсинг (для дальнейшего использования)
    round_data = []
    for cont in containers:
        label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        if not label:
            label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__title"))
        title = label.get_text(strip=True) if label else ""
        if not title:
            if not round_data:
                title = "Full Fight"
            else:
                continue

        metrics_block = cont.find("div", class_="c-stat-metric-compare-group")
        if not metrics_block:
            continue
        total_strikes_el = metrics_block.find("div", class_="total_strikes")
        takedowns_el = metrics_block.find("div", class_="takedowns")
        sig_strikes_el = metrics_block.find("div", class_="sig_strikes")
        knockdowns_el = metrics_block.find("div", class_="knockdowns")

        total_s = parse_metric_from_element(total_strikes_el) if total_strikes_el else ((0,0),(0,0))
        takedowns = parse_metric_from_element(takedowns_el) if takedowns_el else ((0,0),(0,0))
        sig_s = parse_metric_from_element(sig_strikes_el) if sig_strikes_el else ((0,0),(0,0))
        knockdowns = parse_metric_from_element(knockdowns_el) if knockdowns_el else ((0,0),(0,0))

        round_data.append({
            "title": title,
            "Total Strikes": total_s,
            "Takedowns": takedowns,
            "Sig. Strikes": sig_s,
            "Knockdowns": knockdowns
        })

    if not round_data:
        return {"not_started": True, "names": names, "photos": photos, "winner_idx": winner_idx}

    return {
        "not_started": False,
        "names": names,
        "photos": photos,
        "winner_idx": winner_idx,
        "rounds": round_data,
        "finished": finished
    }

# ---------- Генерация картинки (упрощённая для теста) ----------
def generate_image(data):
    # Просто отправляем текстовое сообщение, чтобы не усложнять
    return None

def main():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    else:
        event_id, fight_ids = get_event_data()
        state = {
            "event_id": event_id,
            "fight_ids": fight_ids,
            "current_index": 0,
            "finished_all": False
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

    if state.get("finished_all"):
        print("Все бои турнира завершены.")
        return

    current_fight_id = state["fight_ids"][state["current_index"]]
    event_id = state["event_id"]

    data = get_fight_stats(event_id, current_fight_id)
    if not data:
        print("Не удалось получить данные боя.")
        return

    if data.get("not_started"):
        print("Бой ещё не начался, ждём.")
        return

    print("Данные боя получены успешно!")

if __name__ == "__main__":
    main()
