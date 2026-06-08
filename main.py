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

EVENT_URL = os.environ["EVENT_URL"]   # https://www.ufc.com/event/ufc-fight-night-june-06-2026

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

# ---------- Получение event_id и списка fight_id ----------
def get_event_data():
    slug = EVENT_URL.rstrip("/").split("/")[-1]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": EVENT_URL,
        "X-Requested-With": "XMLHttpRequest"
    }

    # Способ 1: через API
    api_url = f"https://www.ufc.com/api/event/{slug}"
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        if resp.status_code == 200 and resp.text.strip().startswith('{'):
            data = resp.json()
            event_id = data.get("eventId")
            if event_id:
                fights = data.get("fights", [])
                fight_ids = [f["fightId"] for f in fights if "fightId" in f]
                if fight_ids:
                    return event_id, fight_ids
    except:
        pass

    # Способ 2: парсинг HTML страницы события (поиск eventId в JS)
    resp = requests.get(EVENT_URL, headers={"User-Agent": headers["User-Agent"]}, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    # Ищем в скриптах drupalSettings или window.__INITIAL_STATE__
    for script in soup.find_all("script"):
        if script.string and "eventId" in script.string:
            match = re.search(r'"eventId"\s*:\s*"(\d+)"', script.string)
            if not match:
                match = re.search(r'"eventId"\s*:\s*(\d+)', script.string)
            if match:
                event_id = int(match.group(1))
                # Теперь ищем fight_id в том же скрипте или в хэшах
                # Часто fightId перечислены рядом: "fights":[{"fightId":"12711"},...]
                fights_match = re.findall(r'"fightId"\s*:\s*"(\d+)"', script.string)
                if not fights_match:
                    fights_match = re.findall(r'"fightId"\s*:\s*(\d+)', script.string)
                if fights_match:
                    fight_ids = [int(f) for f in fights_match]
                    return event_id, fight_ids

    # Если ничего не помогло – исключение
    raise Exception("Не удалось получить event_id и fight_ids ни через API, ни из HTML.")

# ---------- Парсинг статистики боя ----------
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

    # Проверка завершения боя
    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # Имена бойцов
    names = []
    name_blocks = soup.find_all("div", class_=re.compile("c-fighter-compare__name"))
    if not name_blocks:
        name_blocks = soup.find_all("span", class_=re.compile("c-fighter__name"))
    for block in name_blocks:
        text = block.get_text(strip=True)
        if text:
            names.append(text)
    if len(names) < 2:
        title = soup.find("title")
        if title:
            parts = title.get_text().split(" vs ")
            if len(parts) == 2:
                names = [parts[0].strip(), parts[1].strip()]
    if len(names) < 2:
        names = ["Red Corner", "Blue Corner"]

    # Фото бойцов
    photos = []
    photo_containers = soup.find_all("div", class_=re.compile("c-fighter-compare__image"))
    if not photo_containers:
        photo_containers = soup.find_all("div", class_=re.compile("c-fighter__image"))
    for container in photo_containers:
        img = container.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("/"):
                src = "https://www.ufc.com" + src
            photos.append(src)
    while len(photos) < 2:
        photos.append(None)

    # Значимые удары по раундам
    round_containers = soup.find_all("div", class_="c-stat-group__container")
    rounds_data = []
    for container in round_containers:
        sig_block = container.find("div", class_=lambda c: c and "sig_strikes" in c and "c-stat-metric-compare" in c)
        if sig_block:
            metric = sig_block.find("div", class_="c-stat-metric-compare__metric")
            if metric:
                nums = re.findall(r'\d+', metric.get_text())
                if len(nums) >= 2:
                    rounds_data.append((int(nums[0]), int(nums[1])))

    if not rounds_data:
        return {"not_started": True, "names": names, "photos": photos}

    f1_sig = [r[0] for r in rounds_data]
    f2_sig = [r[1] for r in rounds_data]

    return {
        "not_started": False,
        "names": names[:2],
        "photos": photos[:2],
        "f1_sig": f1_sig,
        "f2_sig": f2_sig,
        "finished": finished
    }

# ---------- Генерация картинки (без изменений) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    f1, f2 = data.get("f1_sig", []), data.get("f2_sig", [])

    width, height = 600, 400
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font_title = font_name = font_small = ImageFont.load_default()

    def load_photo(url):
        if not url:
            return None
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).resize((60, 60))
        except:
            pass
        return None

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

    if photo1:
        img.paste(photo1, (20, 20))
    draw.text((90, 30), names[0], fill="red", font=font_name)

    if photo2:
        img.paste(photo2, (width - 80, 20))
    draw.text((width - 90 - draw.textlength(names[1], font=font_name), 30), names[1], fill="blue", font=font_name)

    if f1 and f2:
        max_val = max(max(f1), max(f2), 1)
        bar_max_width = 200
        y = 100
        draw.text((20, y), "Significant Strikes", fill="black", font=font_title)
        y += 40
        for idx, (s1, s2) in enumerate(zip(f1, f2)):
            draw.text((20, y), f"R{idx+1}", fill="black", font=font_small)
            w1 = int((s1 / max_val) * bar_max_width)
            draw.rectangle([(70, y+2), (70 + w1, y+18)], fill="red")
            draw.text((75, y+3), str(s1), fill="white", font=font_small)
            w2 = int((s2 / max_val) * bar_max_width)
            draw.rectangle([(70, y+22), (70 + w2, y+38)], fill="blue")
            draw.text((75, y+23), str(s2), fill="white", font=font_small)
            y += 45
    else:
        draw.text((20, 100), "Waiting for fight to start...", fill="gray", font=font_title)

    if data.get("finished"):
        draw.text((20, 350), "Fight finished", fill="green", font=font_title)
    elif data.get("not_started"):
        draw.text((20, 350), "Not started yet", fill="orange", font=font_title)
    else:
        draw.text((20, 350), "LIVE", fill="red", font=font_title)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------- Основная логика (без изменений) ----------
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
