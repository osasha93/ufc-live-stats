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

def extract_metric_value(container, metric_name):
    """Извлекает пару чисел для метрики из контейнера раунда"""
    # Ищем блок с классом, соответствующим метрике (например, 'total_strikes')
    metric_class = {
        "Total Strikes": "total_strikes",
        "Takedowns": "takedowns",
        "Sig. Strikes": "sig_strikes",
        "Knockdowns": "knockdowns"
    }.get(metric_name)
    if not metric_class:
        return 0, 0
    block = container.find("div", class_=re.compile(f"c-stat-metric-compare.*{metric_class}"))
    if not block:
        return 0, 0
    # Ищем цифры внутри блока metric
    metric_div = block.find("div", class_="c-stat-metric-compare__metric")
    if not metric_div:
        return 0, 0
    text = metric_div.get_text(strip=True)
    numbers = re.findall(r'\d+', text)
    if len(numbers) >= 2:
        return int(numbers[0]), int(numbers[1])
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

    # --- Имена бойцов ---
    names = []
    # Способ 1: c-fighter-bio__name
    name_blocks = soup.find_all("div", class_="c-fighter-bio__name")
    if not name_blocks:
        name_blocks = soup.find_all("span", class_=re.compile("c-fighter__name"))
    for block in name_blocks:
        text = block.get_text(strip=True)
        if text:
            names.append(text)
    # Если не нашли, пробуем заголовок
    if len(names) < 2:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text()
            parts = title.split(" vs ")
            if len(parts) == 2:
                names = [parts[0].strip(), parts[1].strip()]
    # Заглушка
    if len(names) < 2:
        names = ["Red Corner", "Blue Corner"]

    # --- Фотографии бойцов ---
    photos = []
    # Ищем контейнеры с классом, содержащим 'fighter' и 'image'
    photo_containers = soup.find_all("div", class_=re.compile("c-fighter.*image"))
    if not photo_containers:
        photo_containers = soup.find_all("div", class_="c-fighter-compare__image")
    for cont in photo_containers:
        img = cont.find("img")
        if img and img.get("src"):
            src = img["src"]
            if src.startswith("/"):
                src = "https://www.ufc.com" + src
            photos.append(src)
    # Дополняем до двух (если не хватает)
    while len(photos) < 2:
        photos.append(None)

    # --- Статистика по раундам ---
    containers = soup.find_all("div", class_="c-stat-group__container")
    round_data = []
    for cont in containers:
        # Ищем заголовок
        label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        if not label:
            label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__title"))
        title = label.get_text(strip=True) if label else ""
        if not title:
            if not round_data:
                title = "Full Fight"
            else:
                continue

        # Извлекаем четыре метрики
        total_s = extract_metric_value(cont, "Total Strikes")
        takedowns = extract_metric_value(cont, "Takedowns")
        sig_s = extract_metric_value(cont, "Sig. Strikes")
        knockdowns = extract_metric_value(cont, "Knockdowns")

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

# ---------- Генерация картинки (современный дизайн) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    rounds = data["rounds"]

    # Цветовая схема
    BG_COLOR = (20, 20, 30)         # тёмно-синий фон
    TEXT_COLOR = (255, 255, 255)
    RED_BAR = (220, 50, 50)
    BLUE_BAR = (50, 130, 220)
    GOLD = (255, 215, 0)

    # Шрифты (используем стандартные, но можно загрузить кастомный)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except:
        font_large = font_name = font_small = ImageFont.load_default()

    # Загружаем фото бойцов
    def load_photo(url):
        if not url:
            return None
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content)).resize((70, 70))
                # Делаем круглую маску (опционально)
                mask = Image.new("L", (70, 70), 0)
                draw_mask = ImageDraw.Draw(mask)
                draw_mask.ellipse((0, 0, 70, 70), fill=255)
                img.putalpha(mask)
                return img
        except:
            pass
        return None

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

    # Определяем максимальные значения для шкал (по каждой метрике отдельно)
    max_vals = {}
    for metric in ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]:
        vals = []
        for rd in rounds:
            v1, v2 = rd.get(metric, (0, 0))
            vals.extend([v1, v2])
        max_vals[metric] = max(vals) if vals else 1

    # Размеры картинки
    img_width = 700
    row_height = 30
    header_height = 110
    round_spacing = 15
    metrics_count = 4
    num_rounds = len(rounds)
    img_height = header_height + num_rounds * (metrics_count * (row_height + 6) + 25) + 50

    img = Image.new("RGB", (img_width, img_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # --- Шапка с именами и фото ---
    y = 20
    if photo1:
        img.paste(photo1, (30, y), photo1)
    draw.text((110, y + 20), names[0], fill=RED_BAR, font=font_name)
    if photo2:
        img.paste(photo2, (img_width - 100, y), photo2)
    name2_w = draw.textlength(names[1], font=font_name)
    draw.text((img_width - 110 - name2_w, y + 20), names[1], fill=BLUE_BAR, font=font_name)

    # Разделительная линия
    draw.line([(20, y + 80), (img_width - 20, y + 80)], fill=(80, 80, 100), width=2)
    y = 110

    # --- Статистика по раундам ---
    for rd in rounds:
        title = rd["title"]
        draw.text((30, y), title, fill=GOLD, font=font_large)
        y += 35
        for metric in ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]:
            f1_val, f2_val = rd.get(metric, (0, 0))
            max_val = max_vals[metric] if max_vals[metric] > 0 else 1
            bar_max = 180
            w1 = int((f1_val / max_val) * bar_max)
            w2 = int((f2_val / max_val) * bar_max)

            # Название метрики
            draw.text((40, y + 4), metric, fill=TEXT_COLOR, font=font_small)
            # Шкала красного
            draw.rectangle([(170, y + 2), (170 + w1, y + 14)], fill=RED_BAR)
            draw.text((175 + w1, y + 1), str(f1_val), fill=TEXT_COLOR, font=font_small)
            # Шкала синего
            draw.rectangle([(170, y + 18), (170 + w2, y + 30)], fill=BLUE_BAR)
            draw.text((175 + w2, y + 17), str(f2_val), fill=TEXT_COLOR, font=font_small)
            y += 36
        y += 10  # промежуток между раундами

    # Статус боя
    if data.get("finished"):
        status = "✓ Fight Finished"
        color = (50, 200, 50)
    else:
        status = "● LIVE"
        color = RED_BAR
    draw.text((30, y + 10), status, fill=color, font=font_large)

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
