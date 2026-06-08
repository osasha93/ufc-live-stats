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

# ---------- Вспомогательные функции ----------
def get_event_data():
    fight_ids = [int(f.strip()) for f in FIGHT_IDS_RAW.split(",") if f.strip()]
    return EVENT_ID, fight_ids

def parse_metric(text, metric_name):
    """
    Извлекает пару абсолютных чисел для метрики.
    Пример: '13 (76%) Total Strikes 8 (38%)' -> (13, 8)
    """
    # Экранируем название метрики для использования в regex
    pattern = re.compile(
        r'(\d+)\s*\(\d+%\)\s*' + re.escape(metric_name) + r'\s*(\d+)\s*\(\d+%\)',
        re.IGNORECASE
    )
    match = pattern.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
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

    # Статус завершения
    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # --- Имена бойцов (все возможные селекторы) ---
    names = []
    # Пробуем несколько вариантов
    selectors = [
        "div.c-fighter-bio__name",
        "span.c-fighter__name",
        "div.c-fighter-compare__name",
        "h1.c-fighter__name"
    ]
    for sel in selectors:
        elems = soup.select(sel)
        for el in elems:
            text = el.get_text(strip=True)
            if text and text not in names:
                names.append(text)
        if len(names) >= 2:
            break

    # Запасной: заголовок страницы
    if len(names) < 2:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text()
            parts = title.split(" vs ")
            if len(parts) == 2:
                names = [parts[0].strip(), parts[1].strip()]
    # Заглушка
    while len(names) < 2:
        names.append("Fighter " + str(len(names)+1))

    # --- Фотографии бойцов ---
    photos = []
    photo_selectors = [
        "div.c-fighter-compare__image img",
        "div.c-fighter__image img",
        "div.c-fighter-bio__image img",
        "img.c-fighter__image"
    ]
    for sel in photo_selectors:
        imgs = soup.select(sel)
        for img in imgs:
            src = img.get("src")
            if src:
                if src.startswith("/"):
                    src = "https://www.ufc.com" + src
                if src not in photos:
                    photos.append(src)
        if len(photos) >= 2:
            break
    while len(photos) < 2:
        photos.append(None)

    # --- Статистика по раундам ---
    containers = soup.find_all("div", class_="c-stat-group__container")
    round_data = []
    for cont in containers:
        # Заголовок раунда (Round 1, Full Fight, ...)
        label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        if not label:
            label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__title"))
        title = label.get_text(strip=True) if label else ""
        if not title:
            if not round_data:
                title = "Full Fight"
            else:
                continue

        # Текст всех метрик внутри контейнера
        metrics_block = cont.find("div", class_="c-stat-metric-compare-group")
        if not metrics_block:
            continue
        full_text = metrics_block.get_text(separator=" ", strip=True)

        # Извлекаем четыре метрики
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

# ---------- Генерация картинки (улучшенный дизайн) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    rounds = data["rounds"]

    # Цветовая схема
    BG = (18, 22, 33)
    TEXT = (220, 220, 220)
    RED = (235, 64, 64)
    BLUE = (64, 120, 235)
    GOLD = (255, 210, 50)

    # Шрифты
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_metric = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_title = font_name = font_metric = ImageFont.load_default()

    # Загружаем фото
    def load_photo(url):
        if not url:
            return None
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content)).resize((72, 72))
                # Круглая маска
                mask = Image.new("L", (72, 72), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, 72, 72), fill=255)
                img.putalpha(mask)
                return img
        except:
            pass
        return None

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

    # Максимальные значения для шкал (по каждой метрике отдельно)
    max_vals = {}
    for m in ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]:
        vals = [v for rd in rounds for v in rd.get(m, (0,0))]
        max_vals[m] = max(vals) if vals else 1

    # Размеры
    img_w = 720
    header_h = 120
    round_h = 30  # высота одной метрической строки
    metrics = ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]
    num_metrics = len(metrics)
    num_rounds = len(rounds)
    img_h = header_h + num_rounds * (num_metrics * (round_h + 6) + 20) + 50

    img = Image.new("RGB", (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    # Шапка
    y = 20
    if photo1:
        img.paste(photo1, (30, y), photo1)
    draw.text((115, y+20), names[0], fill=RED, font=font_name)
    if photo2:
        img.paste(photo2, (img_w-102, y), photo2)
    name2_w = draw.textlength(names[1], font=font_name)
    draw.text((img_w-115-name2_w, y+20), names[1], fill=BLUE, font=font_name)

    # Линия
    draw.line([(20, y+85), (img_w-20, y+85)], fill=(80, 80, 100), width=2)
    y = header_h

    # Раунды
    for rd in rounds:
        title = rd["title"]
        draw.text((30, y), title, fill=GOLD, font=font_title)
        y += 30
        for m in metrics:
            f1, f2 = rd.get(m, (0,0))
            max_m = max_vals[m] if max_vals[m] > 0 else 1
            bar_w = 180
            w1 = int((f1 / max_m) * bar_w)
            w2 = int((f2 / max_m) * bar_w)

            # Иконка метрики
            icons = {
                "Total Strikes": "👊",
                "Takedowns": "⬇️",
                "Sig. Strikes": "🎯",
                "Knockdowns": "💥"
            }
            icon = icons.get(m, "")
            draw.text((40, y+4), f"{icon} {m}", fill=TEXT, font=font_metric)

            # Красная шкала
            draw.rectangle([(180, y+2), (180+w1, y+14)], fill=RED)
            draw.text((185+w1, y+2), str(f1), fill=TEXT, font=font_metric)
            # Синяя шкала
            draw.rectangle([(180, y+18), (180+w2, y+30)], fill=BLUE)
            draw.text((185+w2, y+18), str(f2), fill=TEXT, font=font_metric)
            y += 36
        y += 15

    # Статус
    if data.get("finished"):
        status_text = "✅ Fight Finished"
        status_color = (80, 200, 80)
    else:
        status_text = "🔴 LIVE"
        status_color = RED
    draw.text((30, y+10), status_text, fill=status_color, font=font_title)

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
