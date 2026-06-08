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

FIGHT_ID = int(os.environ.get("FIGHT_ID", "12826"))
EVENT_ID = int(os.environ.get("EVENT_ID", "1313"))
STATS_URL = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post"

MSG_ID_FILE = "live_message_id.txt"
STATE_FILE = "live_state.json"

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

# ---------- Парсинг страницы ----------
def get_fight_data():
    headers = {"User-Agent": "Mozilla/5.0"}
    url = STATS_URL + "?t=" + str(int(time.time()))
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Имена бойцов (ищем блоки c-fighter-compare__name)
    names = []
    name_blocks = soup.find_all("div", class_=re.compile("c-fighter-compare__name"))
    if not name_blocks:
        name_blocks = soup.find_all("span", class_=re.compile("c-fighter__name"))
    for block in name_blocks:
        text = block.get_text(strip=True)
        if text:
            names.append(text)
    if len(names) < 2:
        # Запасной вариант: парсим title страницы "Fighter1 vs Fighter2"
        title = soup.find("title")
        if title:
            parts = title.get_text().split(" vs ")
            if len(parts) == 2:
                names = [parts[0].strip(), parts[1].strip()]
    if len(names) < 2:
        print("Не удалось определить имена бойцов")
        names = ["Red Corner", "Blue Corner"]

    # 2. Фото бойцов
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
    # Если нашли меньше двух, дополняем заглушками
    while len(photos) < 2:
        photos.append(None)

    # 3. Статистика по раундам
    # Ищем контейнеры с раундами. У них должен быть внутренний заголовок "Round X"
    round_containers = soup.find_all("div", class_="c-stat-group__container")
    rounds_data = []
    for container in round_containers:
        # Проверяем, есть ли метка раунда
        label = container.find(class_=re.compile("c-stat-group__label"))
        if not label:
            label = container.find(class_=re.compile("c-stat-group__title"))
        if label and "round" in label.get_text().lower():
            # Это раунд
            sig_block = container.find("div", class_=lambda c: c and "sig_strikes" in c and "c-stat-metric-compare" in c)
            if sig_block:
                metric = sig_block.find("div", class_="c-stat-metric-compare__metric")
                if metric:
                    nums = re.findall(r'\d+', metric.get_text())
                    if len(nums) >= 2:
                        rounds_data.append((int(nums[0]), int(nums[1])))
        else:
            # Если метки нет, но контейнер первый или их всего 3/5, считаем раундом (упрощённо)
            # Но в нашем тестовом примере метки не было, однако мы знаем, что все 4 контейнера были раундами.
            # Чтобы не потерять, если меток нет – берём все контейнеры с sig_strikes
            pass

    # Если меток нет, используем старый метод (все контейнеры с sig_strikes)
    if not rounds_data:
        for container in round_containers:
            sig_block = container.find("div", class_=lambda c: c and "sig_strikes" in c and "c-stat-metric-compare" in c)
            if sig_block:
                metric = sig_block.find("div", class_="c-stat-metric-compare__metric")
                if metric:
                    nums = re.findall(r'\d+', metric.get_text())
                    if len(nums) >= 2:
                        rounds_data.append((int(nums[0]), int(nums[1])))

    if not rounds_data:
        print("Не найдено данных по раундам")
        return None

    f1_sig = [r[0] for r in rounds_data]
    f2_sig = [r[1] for r in rounds_data]

    # Определяем завершённость боя
    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    return {
        "names": names[:2],
        "photos": photos[:2],
        "f1_sig": f1_sig,
        "f2_sig": f2_sig,
        "finished": finished
    }

# ---------- Генерация картинки с фото и именами ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    f1, f2 = data["f1_sig"], data["f2_sig"]

    # Параметры изображения
    width, height = 600, 400
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Шрифты
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font_title = font_name = font_small = ImageFont.load_default()

    # Загружаем фото бойцов (если есть URL)
    def load_photo(url):
        if not url:
            return None
        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                photo_img = Image.open(io.BytesIO(r.content)).resize((60, 60))
                return photo_img
        except:
            pass
        return None

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

    # Размещение фото и имён
    if photo1:
        img.paste(photo1, (20, 20))
    draw.text((90, 30), names[0], fill="red", font=font_name)

    if photo2:
        img.paste(photo2, (width - 80, 20))
    draw.text((width - 90 - draw.textlength(names[1], font=font_name), 30), names[1], fill="blue", font=font_name)

    # Шкалы значимых ударов
    max_val = max(max(f1), max(f2), 1)
    bar_max_width = 200
    y = 100
    draw.text((20, y), "Significant Strikes", fill="black", font=font_title)
    y += 40

    for idx, (s1, s2) in enumerate(zip(f1, f2)):
        round_num = idx + 1
        draw.text((20, y), f"R{round_num}", fill="black", font=font_small)
        # Красный боец
        w1 = int((s1 / max_val) * bar_max_width)
        draw.rectangle([(70, y+2), (70 + w1, y+18)], fill="red")
        draw.text((75, y+3), str(s1), fill="white", font=font_small)
        # Синий боец
        w2 = int((s2 / max_val) * bar_max_width)
        draw.rectangle([(70, y+22), (70 + w2, y+38)], fill="blue")
        draw.text((75, y+23), str(s2), fill="white", font=font_small)
        y += 45

    # Статус
    if data["finished"]:
        status = "Fight finished"
        color = "green"
    else:
        status = "LIVE"
        color = "red"
    draw.text((20, y+10), status, fill=color, font=font_title)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------- Основная логика ----------
def main():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            if json.load(f).get("finished"):
                print("Бой завершён ранее.")
                return

    data = get_fight_data()
    if not data:
        print("Данные не получены.")
        return

    if data["finished"]:
        with open(STATE_FILE, "w") as f:
            json.dump({"finished": True}, f)

    img_bytes = generate_image(data)

    if os.path.exists(MSG_ID_FILE):
        with open(MSG_ID_FILE, "r") as f:
            msg_id = int(f.read().strip())
        print(f"Редактируем сообщение {msg_id}")
        edit_message_media(msg_id, img_bytes, caption="")
    else:
        print("Отправляем новое сообщение")
        result = send_photo(img_bytes, caption="")
        if result.get("ok"):
            with open(MSG_ID_FILE, "w") as f:
                f.write(str(result["result"]["message_id"]))
        else:
            print("Ошибка отправки:", result)

if __name__ == "__main__":
    main()
