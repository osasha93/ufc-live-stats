import requests
from bs4 import BeautifulSoup
import os
import json
import time
import io
from PIL import Image, ImageDraw, ImageFont

# ---------- Настройки ----------
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
THREAD_ID = os.environ.get("TELEGRAM_THREAD_ID")

EVENT_URL = os.environ.get("EVENT_URL", "")
EVENT_ID = int(os.environ["EVENT_ID"])

CURRENT_INDEX_FILE = "current_index.txt"
FIGHT_IDS_FILE = "fight_ids.json"
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

# ---------- API-запросы ----------
def fetch_event_api():
    url = f"https://d29dxerjsp82wz.cloudfront.net/api/v3/event/live/{EVENT_ID}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Ошибка Event API: {e}")
        return None

def fetch_fight_api(fight_id):
    url = f"https://d29dxerjsp82wz.cloudfront.net/api/v3/fight/live/{fight_id}.json"
    headers = {"User-Agent": "Mozilla/5.0", "Origin": "https://www.ufc.com", "Referer": "https://www.ufc.com/"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Ошибка Fight API для {fight_id}: {e}")
        return None

# ---------- Список боёв из Event API ----------
def fetch_fight_ids_from_api():
    data = fetch_event_api()
    if not data:
        return None
    ld = data.get("LiveEventDetail", {})
    fights = ld.get("FightCard", [])
    fights_sorted = sorted(fights, key=lambda x: x.get("FightOrder", 999))
    return [f["FightId"] for f in fights_sorted if "FightId" in f]

# ---------- Статистика боя ----------
def get_fight_stats(fight_id):
    data = fetch_fight_api(fight_id)
    if not data:
        return None

    lf = data.get("LiveFightDetail", {})
    if not lf.get("OfficialStats"):
        return {"not_started": True}

    fighters = lf.get("Fighters", [])
    names = []
    winner_idx = -1
    for i, f in enumerate(fighters[:2]):
        name = f"{f.get('Name', {}).get('FirstName', '')} {f.get('Name', {}).get('LastName', '')}".strip()
        names.append(name or "Unknown")
        if f.get("Outcome", {}).get("Outcome") == "Win":
            winner_idx = i

    result = lf.get("Result", {})
    method = result.get("Method", "")
    ending_round = result.get("EndingRound", "")
    ending_time = result.get("EndingTime", "")
    result_str = f"{method} (R{ending_round} {ending_time})" if method and ending_round else ""

    # Фото
    photos = [None, None]
    try:
        page_url = f"https://www.ufc.com/matchup/{EVENT_ID}/{fight_id}/post"
        page_resp = requests.get(page_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(page_resp.text, "html.parser")
        json_script = soup.find("script", {"data-drupal-selector": "drupal-settings-json"})
        if json_script and json_script.string:
            page_data = json.loads(json_script.string)
            athletes = page_data.get("matchup", {}).get("athletes", [])
            for i, athlete in enumerate(athletes[:2]):
                img = athlete.get("img", "")
                if img and img.startswith("http"):
                    photos[i] = img
    except:
        pass

    round_stats_all = lf.get("RoundStats", [])
    if len(round_stats_all) < 1:
        return {"not_started": True, "names": names, "photos": photos, "winner_idx": winner_idx, "result_str": result_str}

    red_rounds = {rd["RoundNumber"]: rd for rd in round_stats_all[0].get("Rounds", [])}
    blue_rounds = {}
    if len(round_stats_all) >= 2:
        blue_rounds = {rd["RoundNumber"]: rd for rd in round_stats_all[1].get("Rounds", [])}

    max_round = max(max(red_rounds.keys()) if red_rounds else 0, max(blue_rounds.keys()) if blue_rounds else 0)
    if max_round == 0:
        return {"not_started": True, "names": names, "photos": photos, "winner_idx": winner_idx, "result_str": result_str}

    round_list = []
    for rnum in range(1, max_round + 1):
        red = red_rounds.get(rnum, {})
        blue = blue_rounds.get(rnum, {})
        if (red.get("TotalStrikesLanded", 0) == 0 and blue.get("TotalStrikesLanded", 0) == 0 and
            red.get("SigStrikesLanded", 0) == 0 and blue.get("SigStrikesLanded", 0) == 0):
            continue

        total_s = (red.get("TotalStrikesLanded", 0), blue.get("TotalStrikesLanded", 0))
        sig_s = (red.get("SigStrikesLanded", 0), blue.get("SigStrikesLanded", 0))
        takedowns = (red.get("TakedownsLanded", 0), blue.get("TakedownsLanded", 0))
        knockdowns = (red.get("Knockdowns", 0), blue.get("Knockdowns", 0))

        round_list.append({
            "title": f"Round {rnum}",
            "Total Strikes": ((total_s[0], 0, ""), (total_s[1], 0, "")),
            "Sig. Strikes": ((sig_s[0], 0, ""), (sig_s[1], 0, "")),
            "Takedowns": ((takedowns[0], 0, ""), (takedowns[1], 0, "")),
            "Knockdowns": ((knockdowns[0], 0, ""), (knockdowns[1], 0, ""))
        })

    finished = lf.get("Status") == "Final"

    return {
        "not_started": len(round_list) == 0,
        "names": names,
        "photos": photos,
        "winner_idx": winner_idx,
        "rounds": round_list,
        "finished": finished,
        "result_str": result_str
    }

# ---------- Генерация картинки ----------
def generate_image(data):
    names = data["names"]
    photos = data["photos"]
    winner_idx = data.get("winner_idx", -1)
    rounds = data["rounds"]
    result_str = data.get("result_str", "")

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

    def load_photo(url):
        if not url:
            return None
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.ufc.com/",
            "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8"
        }
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
            pass
        return None

    def draw_initials(draw, xy, name, color):
        x, y = xy
        r = 36
        draw.ellipse([x, y, x+72, y+72], fill=color)
        initials = "".join([n[0].upper() for n in name.split() if n])[:2]
        bbox = draw.textbbox((0,0), initials, font=font_initials)
        w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
        draw.text((x + 36 - w//2, y + 36 - h//2), initials, fill="white", font=font_initials)

    photo1 = load_photo(photos[0])
    photo2 = load_photo(photos[1])

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

    if result_str:
        draw.text((30, y + 10), f"Result: {result_str}", fill=GREEN, font=font_title)
        y += 30

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
    if os.path.exists(FIGHT_IDS_FILE):
        with open(FIGHT_IDS_FILE, 'r') as f:
            old_data = json.load(f)
        if isinstance(old_data, dict) and old_data.get("event_url") != EVENT_URL:
            print("Обнаружен новый турнир! Сбрасываем прогресс.")
            if os.path.exists(CURRENT_INDEX_FILE):
                os.remove(CURRENT_INDEX_FILE)
            if os.path.exists(FIGHT_IDS_FILE):
                os.remove(FIGHT_IDS_FILE)
            if os.path.exists(MSG_ID_FILE):
                os.remove(MSG_ID_FILE)

    current_index = 0
    if os.path.exists(CURRENT_INDEX_FILE):
        with open(CURRENT_INDEX_FILE, 'r') as f:
            current_index = int(f.read().strip())
        print(f"Загружен current_index: {current_index}")

    fight_ids = None
    if os.path.exists(FIGHT_IDS_FILE):
        with open(FIGHT_IDS_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                fight_ids = data
                with open(FIGHT_IDS_FILE, 'w') as fw:
                    json.dump({"event_url": EVENT_URL, "fights": fight_ids}, fw)
            else:
                fight_ids = data.get("fights", [])
        print(f"Загружен список боёв: {len(fight_ids)} ID")
    else:
        fight_ids = fetch_fight_ids_from_api()
        if not fight_ids:
            print("Не удалось получить список боёв через API.")
            return
        with open(FIGHT_IDS_FILE, 'w') as f:
            json.dump({"event_url": EVENT_URL, "fights": fight_ids}, f)
        print(f"Список боёв сохранён: {len(fight_ids)} ID")

    if current_index >= len(fight_ids):
        print("Все бои турнира обработаны.")
        return

    current_fight_id = fight_ids[current_index]
    print(f"Обрабатываем бой {current_fight_id}")
    data = get_fight_stats(current_fight_id)
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
        current_index += 1
        with open(CURRENT_INDEX_FILE, 'w') as f:
            f.write(str(current_index))
        print(f"Бой завершён. Обновлён current_index: {current_index}")

if __name__ == "__main__":
    main()
