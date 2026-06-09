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

INDEX_FILE = "current_index.txt"
MSG_ID_FILE = "live_message_id.txt"
FIGHT_IDS_FILE = "fight_ids.json"   # список боёв сохраним один раз

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
    return [int(card["data-fmid"]) for card in cards]

# ---------- Парсинг метрик (без изменений) ----------
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
                    img_sml = athlete.get("img_sml_screens", "")
                    if not img_url.startswith("http"):
                        img_url = ""
                    if not img_sml.startswith("http"):
                        img_sml = ""
                    photos.append((img_url, img_sml))
    except:
        pass

    while len(names) < 2:
        names.append("Red Corner" if len(names) == 0 else "Blue Corner")
    while len(photos) < 2:
        photos.append(("", ""))

    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    tab_buttons = soup.select("button.c-tabs__nav-btn")
    round_data = []

    for btn in tab_buttons:
        round_title = btn.get_text(strip=True)
        if not round_title.startswith("Round"):
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

        all_values = [total_s[0][0], total_s[1][0], sig_s[0][0], sig_s[1][0],
                      takedowns[0][0], takedowns[1][0], knockdowns[0][0], knockdowns[1][0]]
        if sum(all_values) == 0:
            continue

        round_data.append({
            "title": round_title,
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

# ---------- Генерация картинки (без изменений) ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    winner_idx = data.get("winner_idx", -1)
    rounds = data["rounds"]

    BG = (18, 22, 35)
    TEXT = (220, 220, 220)
    RED = (225, 65, 65)
    BLUE = (65, 125, 225)
    GOLD = (255, 210, 50)
    GREEN = (80, 200, 80)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_metric = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_number = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_initials = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font_title = font_name = font_metric = font_number = font_initials = ImageFont.load_default()

    def load_photo(primary_url, fallback_url=None):
        if not primary_url:
            return None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.ufc.com/",
            "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8"
        }
        for url in (primary_url, fallback_url):
            if not url:
                continue
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    img.thumbnail((72, 72), Image.LANCZOS)
                    mask = Image.new("L", (72, 72), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, 72, 72), fill=255)
                    img.putalpha(mask)
                    return img
            except:
                continue
        return None

    def draw_initials(draw, xy, name, color):
        x, y = xy
        r = 36
        draw.ellipse([x, y, x+72, y+72], fill=color)
        initials = "".join([n[0].upper() for n in name.split() if n])[:2]
        bbox = draw.textbbox((0,0), initials, font=font_initials)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x + 36 - w//2, y + 36 - h//2), initials, fill="white", font=font_initials)

    photo1 = load_photo(photos[0][0], photos[0][1])
    photo2 = load_photo(photos[1][0], photos[1][1])

    name1 = names[0] + (" WIN" if winner_idx == 0 and data.get("finished") else "")
    name2 = names[1] + (" WIN" if winner_idx == 1 and data.get("finished") else "")

    max_vals = {}
    for m in ["Total Strikes", "Sig. Strikes", "Takedowns", "Knockdowns"]:
        vals = []
        for rd in rounds:
            (v1, _, _), (v2, _, _) = rd.get(m, ((0,0,""),(0,0,"")))
            vals.extend([v1, v2])
        max_vals[m] = max(vals) if vals else 1

    img_w = 760
    header_h = 120
    metrics = ["Total Strikes", "Sig. Strikes", "Takedowns", "Knockdowns"]
    row_h = 46
    num_metrics = len(metrics)
    num_rounds = len(rounds)
    img_h = header_h + num_rounds * (num_metrics * row_h + 30) + 60

    img = Image.new("RGB", (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    y = 20
    if photo1:
        img.paste(photo1, (25, y), photo1)
    else:
        draw_initials(draw, (25, y), names[0], RED)
    draw.text((110, y+28), name1, fill=RED, font=font_name)

    if photo2:
        img.paste(photo2, (img_w-97, y), photo2)
    else:
        draw_initials(draw, (img_w-97, y), names[1], BLUE)
    name2_w = draw.textlength(name2, font=font_name)
    draw.text((img_w - 110 - name2_w, y+28), name2, fill=BLUE, font=font_name)

    draw.line([(20, y+85), (img_w-20, y+85)], fill=(100, 100, 130), width=2)
    y = header_h
    center_x = img_w // 2

    for rd in rounds:
        title = rd["title"]
        draw.text((30, y), title, fill=GOLD, font=font_title)
        y += 30
        for m in metrics:
            (v1, p1, a1_text), (v2, p2, a2_text) = rd.get(m, ((0,0,""),(0,0,"")))
            max_m = max_vals[m] if max_vals[m] > 0 else 1
            bar_max = 150
            w1 = int((v1 / max_m) * bar_max) if v1 > 0 else 0
            w2 = int((v2 / max_m) * bar_max) if v2 > 0 else 0

            text_w = draw.textlength(m, font=font_metric)
            draw.text((center_x - text_w//2, y), m, fill=TEXT, font=font_metric)

            bar_y = y + 18
            red_left = center_x - w1 - 5
            draw.rectangle([(red_left, bar_y), (center_x - 5, bar_y + 10)], fill=RED)
            if m == "Takedowns" and a1_text:
                red_text = f"{v1} {a1_text} ({p1}%)" if p1 > 0 else f"{v1} {a1_text}"
            else:
                red_text = f"{v1} ({p1}%)" if p1 > 0 else str(v1)
            rtext_w = draw.textlength(red_text, font=font_number)
            draw.text((red_left - 5 - rtext_w, bar_y - 2), red_text, fill=RED, font=font_number)

            blue_right = center_x + 5 + w2
            draw.rectangle([(center_x + 5, bar_y), (blue_right, bar_y + 10)], fill=BLUE)
            if m == "Takedowns" and a2_text:
                blue_text = f"{v2} {a2_text} ({p2}%)" if p2 > 0 else f"{v2} {a2_text}"
            else:
                blue_text = f"{v2} ({p2}%)" if p2 > 0 else str(v2)
            draw.text((blue_right + 5, bar_y - 2), blue_text, fill=BLUE, font=font_number)

            y += row_h
        y += 10

    if data.get("finished"):
        status = "Fight Finished"
        color = GREEN
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
    # Определяем список боёв (один раз)
    if not os.path.exists(FIGHT_IDS_FILE):
        if not EVENT_URL:
            raise Exception("EVENT_URL не задан")
        fight_ids = fetch_fight_ids(EVENT_URL)
        with open(FIGHT_IDS_FILE, 'w') as f:
            json.dump({"ids": fight_ids, "event_id": EVENT_ID}, f)
    else:
        with open(FIGHT_IDS_FILE, 'r') as f:
            data = json.load(f)
            fight_ids = data["ids"]
            # EVENT_ID берём из сохранённого, если не задан (на случай смены)
            if not EVENT_ID:
                EVENT_ID = data["event_id"]

    # Текущий индекс
    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r') as f:
            current_index = int(f.read().strip())
    else:
        current_index = 0

    # Проверяем, не вышли ли за границу
    if current_index >= len(fight_ids):
        print("Все бои обработаны.")
        return

    current_fight = fight_ids[current_index]
    print(f"Обрабатываем бой {current_fight} (индекс {current_index})")
    data = get_fight_stats(EVENT_ID, current_fight)

    if data is None:
        print("Не удалось получить данные.")
        return

    if data.get("not_started"):
        print("Бой ещё не начался.")
        # Не увеличиваем индекс, но и не отправляем
        return

    img_bytes = generate_image(data)

    # Отправляем или редактируем сообщение
    if os.path.exists(MSG_ID_FILE):
        with open(MSG_ID_FILE, 'r') as f:
            msg_id = int(f.read().strip())
        edit_message_media(msg_id, img_bytes, caption="")
        print("Сообщение обновлено.")
    else:
        result = send_photo(img_bytes, caption="")
        if result.get("ok"):
            msg_id = result["result"]["message_id"]
            with open(MSG_ID_FILE, 'w') as f:
                f.write(str(msg_id))
            print("Новое сообщение создано.")
        else:
            print("Ошибка отправки:", result)
            return

    # Если бой завершён, переходим к следующему
    if data.get("finished"):
        # Удаляем старое сообщение? Не обязательно, просто записываем новый индекс
        current_index += 1
        with open(INDEX_FILE, 'w') as f:
            f.write(str(current_index))
        # Удаляем MSG_ID_FILE, чтобы для следующего боя создать новое сообщение
        if os.path.exists(MSG_ID_FILE):
            os.remove(MSG_ID_FILE)
        print(f"Бой завершён. Следующий индекс: {current_index}")
    else:
        # Если бой не завершён, сохраняем индекс как есть (можно не менять)
        with open(INDEX_FILE, 'w') as f:
            f.write(str(current_index))

if __name__ == "__main__":
    main()import requests
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
                    img_sml = athlete.get("img_sml_screens", "")
                    if not img_url.startswith("http"):
                        img_url = ""
                    if not img_sml.startswith("http"):
                        img_sml = ""
                    photos.append((img_url, img_sml))
    except:
        pass

    while len(names) < 2:
        names.append("Red Corner" if len(names) == 0 else "Blue Corner")
    while len(photos) < 2:
        photos.append(("", ""))

    body_text = soup.get_text()
    finished = any(w in body_text for w in ["Win", "Loss", "Draw", "KO/TKO", "Submission", "Decision"])

    tab_buttons = soup.select("button.c-tabs__nav-btn")
    round_data = []

    for btn in tab_buttons:
        round_title = btn.get_text(strip=True)
        if not round_title.startswith("Round"):
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

        all_values = [total_s[0][0], total_s[1][0], sig_s[0][0], sig_s[1][0],
                      takedowns[0][0], takedowns[1][0], knockdowns[0][0], knockdowns[1][0]]
        if sum(all_values) == 0:
            continue

        round_data.append({
            "title": round_title,
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

# ---------- Генерация картинки ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    winner_idx = data.get("winner_idx", -1)
    rounds = data["rounds"]

    BG = (18, 22, 35)
    TEXT = (220, 220, 220)
    RED = (225, 65, 65)
    BLUE = (65, 125, 225)
    GOLD = (255, 210, 50)
    GREEN = (80, 200, 80)

    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        font_name = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_metric = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
        font_number = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
        font_initials = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font_title = font_name = font_metric = font_number = font_initials = ImageFont.load_default()

    def load_photo(primary_url, fallback_url=None):
        if not primary_url:
            return None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.ufc.com/",
            "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8"
        }
        for url in (primary_url, fallback_url):
            if not url:
                continue
            try:
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code == 200:
                    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
                    img.thumbnail((72, 72), Image.LANCZOS)
                    mask = Image.new("L", (72, 72), 0)
                    ImageDraw.Draw(mask).ellipse((0, 0, 72, 72), fill=255)
                    img.putalpha(mask)
                    return img
            except:
                continue
        return None

    def draw_initials(draw, xy, name, color):
        x, y = xy
        r = 36
        draw.ellipse([x, y, x+72, y+72], fill=color)
        initials = "".join([n[0].upper() for n in name.split() if n])[:2]
        bbox = draw.textbbox((0,0), initials, font=font_initials)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x + 36 - w//2, y + 36 - h//2), initials, fill="white", font=font_initials)

    photo1 = load_photo(photos[0][0], photos[0][1])
    photo2 = load_photo(photos[1][0], photos[1][1])

    name1 = names[0] + (" WIN" if winner_idx == 0 and data.get("finished") else "")
    name2 = names[1] + (" WIN" if winner_idx == 1 and data.get("finished") else "")

    max_vals = {}
    for m in ["Total Strikes", "Sig. Strikes", "Takedowns", "Knockdowns"]:
        vals = []
        for rd in rounds:
            (v1, _, _), (v2, _, _) = rd.get(m, ((0,0,""),(0,0,"")))
            vals.extend([v1, v2])
        max_vals[m] = max(vals) if vals else 1

    img_w = 760
    header_h = 120
    metrics = ["Total Strikes", "Sig. Strikes", "Takedowns", "Knockdowns"]
    row_h = 46
    num_metrics = len(metrics)
    num_rounds = len(rounds)
    img_h = header_h + num_rounds * (num_metrics * row_h + 30) + 60

    img = Image.new("RGB", (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    y = 20
    if photo1:
        img.paste(photo1, (25, y), photo1)
    else:
        draw_initials(draw, (25, y), names[0], RED)
    draw.text((110, y+28), name1, fill=RED, font=font_name)

    if photo2:
        img.paste(photo2, (img_w-97, y), photo2)
    else:
        draw_initials(draw, (img_w-97, y), names[1], BLUE)
    name2_w = draw.textlength(name2, font=font_name)
    draw.text((img_w - 110 - name2_w, y+28), name2, fill=BLUE, font=font_name)

    draw.line([(20, y+85), (img_w-20, y+85)], fill=(100, 100, 130), width=2)
    y = header_h
    center_x = img_w // 2

    for rd in rounds:
        title = rd["title"]
        draw.text((30, y), title, fill=GOLD, font=font_title)
        y += 30
        for m in metrics:
            (v1, p1, a1_text), (v2, p2, a2_text) = rd.get(m, ((0,0,""),(0,0,"")))
            max_m = max_vals[m] if max_vals[m] > 0 else 1
            bar_max = 150
            w1 = int((v1 / max_m) * bar_max) if v1 > 0 else 0
            w2 = int((v2 / max_m) * bar_max) if v2 > 0 else 0

            text_w = draw.textlength(m, font=font_metric)
            draw.text((center_x - text_w//2, y), m, fill=TEXT, font=font_metric)

            bar_y = y + 18
            red_left = center_x - w1 - 5
            draw.rectangle([(red_left, bar_y), (center_x - 5, bar_y + 10)], fill=RED)
            if m == "Takedowns" and a1_text:
                red_text = f"{v1} {a1_text} ({p1}%)" if p1 > 0 else f"{v1} {a1_text}"
            else:
                red_text = f"{v1} ({p1}%)" if p1 > 0 else str(v1)
            rtext_w = draw.textlength(red_text, font=font_number)
            draw.text((red_left - 5 - rtext_w, bar_y - 2), red_text, fill=RED, font=font_number)

            blue_right = center_x + 5 + w2
            draw.rectangle([(center_x + 5, bar_y), (blue_right, bar_y + 10)], fill=BLUE)
            if m == "Takedowns" and a2_text:
                blue_text = f"{v2} {a2_text} ({p2}%)" if p2 > 0 else f"{v2} {a2_text}"
            else:
                blue_text = f"{v2} ({p2}%)" if p2 > 0 else str(v2)
            draw.text((blue_right + 5, bar_y - 2), blue_text, fill=BLUE, font=font_number)

            y += row_h
        y += 10

    if data.get("finished"):
        status = "Fight Finished"
        color = GREEN
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
    # Отладка: смотрим, что лежит в рабочей директории
    print("Содержимое рабочей директории:")
    for f in os.listdir('.'):
        print(" -", f)
    print(f"STATE_FILE существует: {os.path.exists(STATE_FILE)}")
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f:
            print(f"Содержимое {STATE_FILE}: {f.read()}")

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
    else:
        if not EVENT_URL:
            raise Exception("Укажите EVENT_URL в секретах GitHub")
        fight_ids = fetch_fight_ids(EVENT_URL)
        state = {
            "event_id": EVENT_ID,
            "fight_ids": fight_ids,
            "current_index": 0,
            "finished_all": False
        }
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        print(f"Старт: event_id={EVENT_ID}, боёв: {len(fight_ids)}, ID: {fight_ids}")

    if state.get("finished_all"):
        print("Все бои турнира завершены.")
        return

    current_fight_id = state["fight_ids"][state["current_index"]]
    event_id = state["event_id"]

    print(f"Обрабатываем бой {current_fight_id}")
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
        print(f"Обновлённый {STATE_FILE} сохранён.")

if __name__ == "__main__":
    main()
