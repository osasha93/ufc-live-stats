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
FIGHT_IDS_RAW = os.environ["FIGHT_IDS"]   # "12827,12761,..."

STATE_FILE = "state.json"
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

# ---------- Извлечение данных боя ----------
def get_event_data():
    fight_ids = [int(f.strip()) for f in FIGHT_IDS_RAW.split(",") if f.strip()]
    return EVENT_ID, fight_ids

def parse_metric(text, metric_name):
    pattern = re.compile(
        r'(\d+)\s*\(\d+%\)\s*' + re.escape(metric_name) + r'\s*(\d+)\s*\(\d+%\)',
        re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    parts = text.split(metric_name)
    if len(parts) == 2:
        nums_left = re.findall(r'(\d+)\s*\(\d+%\)', parts[0])
        nums_right = re.findall(r'(\d+)\s*\(\d+%\)', parts[1])
        if nums_left and nums_right:
            return int(nums_left[-1]), int(nums_right[0])
    return 0, 0

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

    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

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
                    full_name = f"{given} {family}".strip()
                    if not full_name:
                        full_name = "Unknown"
                    names.append(full_name)
                    img_url = athlete.get("img", "")
                    if img_url and img_url.startswith("http"):
                        photos.append(img_url)
                    else:
                        photos.append(None)
    except Exception as e:
        print(f"Ошибка парсинга JSON: {e}")

    while len(names) < 2:
        names.append("Red Corner" if len(names) == 0 else "Blue Corner")
    while len(photos) < 2:
        photos.append(None)

    containers = soup.find_all("div", class_="c-stat-group__container")
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
        full_text = metrics_block.get_text(separator=" ", strip=True)

        total_s = parse_metric(full_text, "Total Strikes")
        takedowns = parse_metric(full_text, "Takedowns")
        sig_s = parse_metric(full_text, "Sig. Strikes")
        knockdowns = parse_metric(full_text, "Knockdowns")

        round_data.append({
            "title": title,
            "Total Strikes": total_s,
            "Takedowns": takedowns,
            "Sig. Strikes": sig_s,
            "Knockdowns": knockdowns
        })

    if not round_data:
        return {"not_started": True, "names": names, "photos": photos}

    return {
        "not_started": False,
        "names": names[:2],
        "photos": photos[:2],
        "rounds": round_data,
        "finished": finished
    }

# ---------- Генерация картинки (исправленная загрузка фото) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    rounds = data["rounds"]

    BG = (18, 22, 35)
    TEXT = (220, 220, 220)
    RED = (225, 65, 65)
    BLUE = (65, 125, 225)
    GOLD = (255, 210, 50)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_metric = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_number = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    except:
        font_title = font_name = font_metric = font_number = ImageFont.load_default()

    # ---------- ИСПРАВЛЕННАЯ ЗАГРУЗКА ФОТО ----------
    def load_photo(url):
        if not url:
            return None
        headers = {"User-Agent": "Mozilla/5.0"}   # <-- добавляем заголовок
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                img.thumbnail((80, 80), Image.LANCZOS)
                mask = Image.new("L", (80, 80), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 80, 80), fill=255)
                img.putalpha(mask)
                return img
        except Exception as e:
            print(f"Ошибка загрузки фото {url}: {e}")
        return None

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

    # Максимальные значения для шкал
    max_vals = {}
    for m in ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]:
        vals = [v for rd in rounds for v in rd.get(m, (0,0))]
        max_vals[m] = max(vals) if vals else 1

    img_w = 700
    header_h = 110
    metrics = ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]
    row_h = 38
    num_metrics = len(metrics)
    num_rounds = len(rounds)
    img_h = header_h + num_rounds * (num_metrics * row_h + 30) + 50

    img = Image.new("RGB", (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    y = 20
    if photo1:
        img.paste(photo1, (25, y), photo1)
    draw.text((115, y + 28), names[0], fill=RED, font=font_name)
    if photo2:
        img.paste(photo2, (img_w - 105, y), photo2)
    name2_w = draw.textlength(names[1], font=font_name)
    draw.text((img_w - 115 - name2_w, y + 28), names[1], fill=BLUE, font=font_name)

    draw.line([(20, y + 85), (img_w - 20, y + 85)], fill=(100, 100, 130), width=2)
    y = header_h

    center_x = img_w // 2

    for rd in rounds:
        title = rd["title"]
        draw.text((30, y), title, fill=GOLD, font=font_title)
        y += 30
        for m in metrics:
            f1, f2 = rd.get(m, (0,0))
            max_m = max_vals[m] if max_vals[m] > 0 else 1
            bar_max = 150
            w1 = int((f1 / max_m) * bar_max) if f1 > 0 else 0
            w2 = int((f2 / max_m) * bar_max) if f2 > 0 else 0

            metric_text = m
            text_w = draw.textlength(metric_text, font=font_metric)
            draw.text((center_x - text_w//2, y), metric_text, fill=TEXT, font=font_metric)

            bar_y = y + 18
            red_left = center_x - w1 - 5
            draw.rectangle([(red_left, bar_y), (center_x - 5, bar_y + 10)], fill=RED)
            draw.text((red_left - 25, bar_y - 2), str(f1), fill=RED, font=font_number)

            blue_right = center_x + 5 + w2
            draw.rectangle([(center_x + 5, bar_y), (blue_right, bar_y + 10)], fill=BLUE)
            draw.text((blue_right + 5, bar_y - 2), str(f2), fill=BLUE, font=font_number)

            y += row_h
        y += 10

    if data.get("finished"):
        status = "Fight Finished"
        color = (80, 200, 80)
    else:
        status = "LIVE"
        color = RED
    draw.text((30, y + 10), status, fill=color, font=font_title)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------- Основная логика ----------
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
        state["current_index"] += 1
        if state["current_index"] >= len(state["fight_ids"]):
            state["finished_all"] = True
            print("Все бои турнира обработаны.")
        else:
            print(f"Переход к следующему бою ID {state['fight_ids'][state['current_index']]}")
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)

if __name__ == "__main__":
    main()
