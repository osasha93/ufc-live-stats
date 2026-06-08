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

# ---------- Извлечение данных ----------
def get_event_data():
    fight_ids = [int(f.strip()) for f in FIGHT_IDS_RAW.split(",") if f.strip()]
    return EVENT_ID, fight_ids

def extract_metric_value(text, metric_name):
    """Извлекает пару чисел для метрики из строки типа '48(69%)Total Strikes65(56%)'"""
    pattern = re.compile(r'(\d+)\s*\(\d+%\)\s*' + re.escape(metric_name) + r'\s*(\d+)\s*\(\d+%\)')
    match = pattern.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    # Запасной вариант: ищем просто два числа перед и после названия
    parts = text.split(metric_name)
    if len(parts) == 2:
        nums1 = re.findall(r'\d+', parts[0])
        nums2 = re.findall(r'\d+', parts[1])
        if nums1 and nums2:
            return int(nums1[-1]), int(nums2[0])  # последнее число до, первое после
    return None, None

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

    # Контейнеры раундов
    containers = soup.find_all("div", class_="c-stat-group__container")
    round_data = []   # список словарей: { 'title': 'Round 1', 'Total Strikes': (f1,f2), ... }

    for cont in containers:
        # Определяем заголовок (Round 1, Full Fight, и т.д.)
        label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        if not label:
            label = cont.find(["div", "span"], class_=re.compile(r"c-stat-group__title"))
        title = label.get_text(strip=True) if label else ""
        if not title:
            # Если заголовка нет, но контейнер первый — возможно, это full fight
            if not round_data:
                title = "Full Fight"
            else:
                continue  # пропускаем неизвестные

        # Ищем метрики внутри этого контейнера
        metrics_block = cont.find("div", class_="c-stat-metric-compare-group")
        if not metrics_block:
            continue
        # Собираем текст всех метрик в одну строку (для упрощения)
        all_text = metrics_block.get_text(separator=" ", strip=True)
        # Извлекаем четыре нужные метрики
        total_strikes = extract_metric_value(all_text, "Total Strikes")
        takedowns = extract_metric_value(all_text, "Takedowns")
        sig_strikes = extract_metric_value(all_text, "Sig. Strikes")
        knockdowns = extract_metric_value(all_text, "Knockdowns")

        round_data.append({
            "title": title,
            "Total Strikes": total_strikes,
            "Takedowns": takedowns,
            "Sig. Strikes": sig_strikes,
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

# ---------- Генерация картинки (улучшенная) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    rounds = data["rounds"]

    # Рассчитаем размеры
    bar_width = 140
    row_height = 20
    header_height = 80
    round_spacing = 20
    metrics = ["Total Strikes", "Takedowns", "Sig. Strikes", "Knockdowns"]
    num_metrics = len(metrics)
    num_rounds = len(rounds)

    img_width = 600
    img_height = header_height + num_rounds * (num_metrics * (row_height + 2) + 30) + 50

    img = Image.new("RGB", (img_width, img_height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font_title = font_name = font_small = ImageFont.load_default()

    # Верхний блок: фото и имена
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
        img.paste(photo2, (img_width - 80, 20))
    # Выравнивание имени второго бойца по правому краю
    name2_width = draw.textlength(names[1], font=font_name)
    draw.text((img_width - 90 - name2_width, 30), names[1], fill="blue", font=font_name)

    y = 100
    # Для каждого раунда рисуем блок
    for rd in rounds:
        title = rd["title"]
        draw.text((20, y), title, fill="black", font=font_title)
        y += 25
        for metric in metrics:
            f1_val, f2_val = rd.get(metric, (0, 0))
            if f1_val is None:
                f1_val, f2_val = 0, 0
            # Нормализуем длину шкалы по максимальному значению во всех раундах (для этой метрики?)
            # Чтобы шкалы были наглядны, найдём максимум для этой метрики по всем раундам
            max_val = 1
            for r in rounds:
                v1, v2 = r.get(metric, (0, 0))
                if v1 is not None:
                    max_val = max(max_val, v1, v2)
            w1 = int((f1_val / max_val) * bar_width)
            w2 = int((f2_val / max_val) * bar_width)

            draw.text((20, y+2), metric, fill="black", font=font_small)
            # Красная шкала
            draw.rectangle([(150, y+2), (150 + w1, y+18)], fill="red")
            draw.text((155, y+3), str(f1_val), fill="white", font=font_small)
            # Синяя шкала
            draw.rectangle([(150, y+22), (150 + w2, y+38)], fill="blue")
            draw.text((155, y+23), str(f2_val), fill="white", font=font_small)
            y += 45
        y += 15  # дополнительный отступ между раундами

    # Статус
    if data.get("finished"):
        draw.text((20, y+10), "Fight finished", fill="green", font=font_title)
    elif data.get("not_started"):
        draw.text((20, y+10), "Not started yet", fill="orange", font=font_title)
    else:
        draw.text((20, y+10), "LIVE", fill="red", font=font_title)

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
