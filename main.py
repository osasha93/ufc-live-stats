
import requests
from bs4 import BeautifulSoup
import os
import json
import time
import io
import re
from PIL import Image, ImageDraw, ImageFont

# ---------- Настройки (из секретов) ----------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID")  # если нужна тема, иначе пусто

FIGHT_ID = int(os.environ.get("FIGHT_ID", "12826"))  # 12826 – тестовый прошедший бой
EVENT_ID = 1313
STATS_URL = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post"

MSG_ID_FILE = "live_message_id.txt"
STATE_FILE = "live_state.json"   # хранит, завершён ли бой

# ---------- Telegram API ----------
def send_photo(photo_bytes, caption=""):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": ("stats.png", photo_bytes, "image/png")}
    data = {"chat_id": CHAT_ID, "caption": caption}
    if THREAD_ID:
        data["message_thread_id"] = int(THREAD_ID)
    r = requests.post(url, data=data, files=files)
    return r.json()

def edit_message_media(message_id, photo_bytes, caption=""):
    """Редактирует существующее фото-сообщение."""
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
    r = requests.post(url, data=data, files=files)
    return r.json()

# ---------- Парсинг статистики ----------
def get_fight_stats():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    # Добавляем случайный параметр, чтобы избежать кеширования
    url = STATS_URL + "?t=" + str(int(time.time()))
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Проверяем, завершён ли бой (по ключевым словам)
    body_text = soup.get_text()
    is_finished = any(word in body_text for word in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # Ищем таблицу значимых ударов (Significant Strikes)
    table = soup.find("div", class_="c-stat-compare__table")
    if not table:
        table = soup.find("div", class_="c-stat-compare__group")
    if not table:
        print("Таблица статистики не найдена")
        return None

    # Заголовки раундов (R1, R2, R3...)
    headers_th = table.find_all("th", class_=re.compile("c-stat-compare__head"))
    num_rounds = len(headers_th) if headers_th else 0
    if num_rounds == 0:
        headers_th = table.find_all("th")
        num_rounds = len(headers_th)

    # Строки с данными бойцов (первые две)
    rows = table.find_all("tr", class_=re.compile("c-stat-compare__row"))
    if len(rows) < 2:
        rows = table.find_all("tr")
        rows = [r for r in rows if r.find("td")]
    if len(rows) < 2:
        print("Не найдены строки с данными бойцов")
        return None

    f1_stats, f2_stats = [], []
    for i, row in enumerate(rows[:2]):
        cells = row.find_all("td")
        vals = []
        for cell in cells[1:]:  # первая ячейка — имя
            try:
                vals.append(int(cell.get_text(strip=True)))
            except:
                vals.append(0)
        if i == 0:
            f1_stats = vals
        else:
            f2_stats = vals

    # Оставляем только первые num_rounds значений
    f1_stats = f1_stats[:num_rounds]
    f2_stats = f2_stats[:num_rounds]

    # Дополняем до 3 раундов нулями (для единообразия)
    while len(f1_stats) < 3:
        f1_stats.append(0)
        f2_stats.append(0)

    return {
        "rounds": num_rounds,
        "f1": f1_stats,
        "f2": f2_stats,
        "finished": is_finished
    }

# ---------- Генерация картинки ----------
def generate_image(stats):
    f1, f2 = stats["f1"], stats["f2"]
    max_val = max(max(f1), max(f2), 1)
    bar_max_width = 220
    img_w, img_h = 480, 240
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = small = ImageFont.load_default()

    draw.text((10, 10), "Significant Strikes", fill="black", font=font)
    y = 40
    for r in range(3):
        if r >= stats["rounds"] and f1[r] == 0 and f2[r] == 0:
            continue  # не рисуем пустые раунды
        draw.text((10, y), f"R{r+1}", fill="black", font=font)
        # Красная шкала
        w1 = int((f1[r] / max_val) * bar_max_width)
        draw.rectangle([(60, y+2), (60 + w1, y+20)], fill="red")
        draw.text((65, y+3), str(f1[r]), fill="white", font=small)
        # Синяя шкала
        w2 = int((f2[r] / max_val) * bar_max_width)
        draw.rectangle([(60, y+22), (60 + w2, y+40)], fill="blue")
        draw.text((65, y+23), str(f2[r]), fill="white", font=small)
        y += 50

    # Статус боя
    if stats.get("finished"):
        draw.text((10, y+10), "Fight finished", fill="green", font=font)
    else:
        draw.text((10, y+10), "LIVE", fill="red", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

# ---------- Основная логика ----------
def main():
    # Если бой уже завершён, не тратим запросы
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            if state.get("finished", False):
                print("Бой завершён ранее, пропускаем.")
                return

    stats = get_fight_stats()
    if not stats:
        print("Статистика недоступна.")
        return

    # Сохраняем статус завершения
    if stats["finished"]:
        with open(STATE_FILE, "w") as f:
            json.dump({"finished": True}, f)

    img_bytes = generate_image(stats)

    # Отправляем или редактируем сообщение
    if os.path.exists(MSG_ID_FILE):
        with open(MSG_ID_FILE, "r") as f:
            msg_id = int(f.read().strip())
        print(f"Редактируем сообщение {msg_id}")
        edit_message_media(msg_id, img_bytes, caption="")
    else:
        print("Отправляем новое сообщение")
        result = send_photo(img_bytes, caption="")
        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            with open(MSG_ID_FILE, "w") as f:
                f.write(str(msg_id))
        else:
            print("Ошибка отправки:", result)

if __name__ == "__main__":
    main()
