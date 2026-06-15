import requests
from bs4 import BeautifulSoup
import os
import json
import time

# ---------- Только отладка ----------
EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12711   # первый бой нового турнира

def get_fight_stats(event_id, fight_id):
    url = f"https://www.ufc.com/matchup/{event_id}/{fight_id}/post?t={int(time.time())}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки боя {fight_id}: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    # Ищем контейнеры раундов
    containers = soup.find_all("div", class_="c-stat-group__container")
    print(f"Найдено контейнеров c-stat-group__container: {len(containers)}")

    if not containers:
        # Альтернативные контейнеры
        containers = soup.find_all("div", class_=re.compile("c-stat-group"))
        print(f"Альтернативных контейнеров: {len(containers)}")

    for i, cont in enumerate(containers[:3]):  # первые 3 для примера
        labels = cont.find_all(["div", "span"], class_=re.compile(r"c-stat-group__label"))
        label_texts = [l.get_text(strip=True) for l in labels]
        print(f"Контейнер {i}: заголовки {label_texts}")

        metrics_block = cont.find("div", class_="c-stat-metric-compare-group")
        if metrics_block:
            for metric in ["total_strikes", "sig_strikes", "takedowns", "knockdowns"]:
                el = metrics_block.find("div", class_=metric)
                if el:
                    print(f"  {metric}: найдена")
                else:
                    print(f"  {metric}: НЕ НАЙДЕНА")
        else:
            print("  блок метрик не найден")

    # Попробуем найти табы
    tab_buttons = soup.select("button.c-tabs__nav-btn")
    print(f"Табов: {len(tab_buttons)}")
    for btn in tab_buttons[:5]:
        print(f"  {btn.get_text(strip=True)}")

if __name__ == "__main__":
    get_fight_stats(EVENT_ID, FIGHT_ID)
