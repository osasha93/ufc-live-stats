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
EVENT_ID = int(os.environ.get("EVENT_ID", "1313"))   # теперь передаём в секретах
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

# ---------- Парсинг статистики (новая логика) ----------
def get_fight_stats():
    headers = {"User-Agent": "Mozilla/5.0"}
    url = STATS_URL + "?t=" + str(int(time.time()))
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Проверка завершения боя
    body_text = soup.get_text()
    is_finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    # Находим все контейнеры раундов
    round_containers = soup.find_all("div", class_="c-stat-group__container")
    if not round_containers:
        print("Не найдены контейнеры раундов (c-stat-group__container)")
        return None

    f1_sig = []
    f2_sig = []

    for container in round_containers:
        # Ищем блок с классом sig_strikes
        sig_block = container.find("div", class_=lambda c: c and "sig_strikes" in c and "c-stat-metric-compare" in c)
        if not sig_block:
            continue
        # Текст внутри c-stat-metric-compare__metric
        metric = sig_block.find("div", class_="c-stat-metric-compare__metric")
        if not metric:
            continue
        text = metric.get_text(strip=True)
        # Извлекаем все числа (например, "16Sig. Strikes31" -> [16, 31])
        numbers = re.findall(r'\d+', text)
        if len(numbers) >= 2:
            f1_sig.append(int(numbers[0]))
            f2_sig.append(int(numbers[1]))

    if not f1_sig:
        print("Не удалось извлечь значимые удары")
        return None

    # Дополняем до 5 раундов нулями (если бой ещё идёт)
    while len(f1_sig) < 5:
        f1_sig.append(0)
        f2_sig.append(0)

    return {
        "rounds": len([x for x in f1_sig if x > 0 or f2_sig[f1_sig.index(x)] > 0]),  # количество активных раундов
        "f1": f1_sig,
        "f2": f2_sig,
        "finished": is_finished
    }

# ---------- Генерация картинки (аналогично предыдущей) ----------
def generate_image(stats):
    f1, f2 = stats["f1"], stats["f2"]
    # Берём только не нулевые раунды для отображения
    non_zero = [(i, s1, s2) for i, (s1, s2) in enumerate(zip(f1, f2)) if s1 > 0 or s2 > 0]
    if not non_zero:
        non_zero = [(0, 0, 0)]  # заглушка

    max_val = max(max(f1), max(f2), 1)
    bar_max_width = 220
    img_w, img_h = 480, 50 + len(non_zero) * 55 + 30
    img = Image.new("RGB", (img_w, img_h), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    except:
        font = small = ImageFont.load_default()

    draw.text((10, 10), "Significant Strikes", fill="black", font=font)
    y = 40
    for idx, s1, s2 in non_zero:
        round_num = idx + 1
        draw.text((10, y), f"R{round_num}", fill="black", font=font)
        # Красный
        w1 = int((s1 / max_val) * bar_max_width)
        draw.rectangle([(60, y+2), (60 + w1, y+20)], fill="red")
        draw.text((65, y+3), str(s1), fill="white", font=small)
        # Синий
        w2 = int((s2 / max_val) * bar_max_width)
        draw.rectangle([(60, y+22), (60 + w2, y+40)], fill="blue")
        draw.text((65, y+23), str(s2), fill="white", font=small)
        y += 55

    status = "Fight finished" if stats.get("finished") else "LIVE"
    draw.text((10, y+5), status, fill="green" if stats["finished"] else "red", font=font)

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

    stats = get_fight_stats()
    if not stats:
        print("Статистика недоступна.")
        return

    if stats["finished"]:
        with open(STATE_FILE, "w") as f:
            json.dump({"finished": True}, f)

    img_bytes = generate_image(stats)

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
