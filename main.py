import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12711   # первый бой

def parse_metric_from_element(metric_el):
    # та же функция, что и в рабочем коде
    ...

def get_fight_stats(event_id, fight_id):
    url = f"https://www.ufc.com/matchup/{event_id}/{fight_id}/post?t={int(time.time())}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Ошибка загрузки: {e}")
        return

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Табы
    tab_buttons = soup.select("button.c-tabs__nav-btn")
    print(f"=== ТАБЫ ({len(tab_buttons)}) ===")
    for btn in tab_buttons:
        print(f"  '{btn.get_text(strip=True)}' -> aria-controls='{btn.get('aria-controls')}'")

    # 2. Панели
    panels = soup.select("div.c-tabs__pane")
    print(f"\n=== ПАНЕЛИ ({len(panels)}) ===")
    for i, panel in enumerate(panels):
        pid = panel.get('id', '')
        container = panel.find("div", class_="c-stat-group__container")
        print(f"Панель {i} (id='{pid}'): контейнер найден = {container is not None}")
        if container:
            metrics_block = container.find("div", class_="c-stat-metric-compare-group")
            if metrics_block:
                for m in ["total_strikes", "sig_strikes", "takedowns", "knockdowns"]:
                    el = metrics_block.find("div", class_=m)
                    if el:
                        # пробуем извлечь числа
                        res = parse_metric_from_element(el)
                        print(f"  {m}: {res}")
                    else:
                        print(f"  {m}: НЕ НАЙДЕН")

    # 3. Попробуем пройти по табам и панелям вручную
    print("\n=== РУЧНОЙ ПРОХОД ===")
    for btn in tab_buttons:
        round_title = btn.get_text(strip=True)
        panel_id = btn.get("aria-controls")
        if not panel_id:
            continue
        panel = soup.find("div", id=panel_id)
        if not panel:
            print(f"Панель для '{round_title}' не найдена")
            continue
        container = panel.find("div", class_="c-stat-group__container")
        if not container:
            print(f"Контейнер для '{round_title}' не найден")
            continue
        metrics_block = container.find("div", class_="c-stat-metric-compare-group")
        if not metrics_block:
            print(f"Блок метрик для '{round_title}' не найден")
            continue
        # выводим текст метрик для отладки
        print(f"'{round_title}' метрики: {metrics_block.get_text(strip=True)[:200]}")

if __name__ == "__main__":
    get_fight_stats(EVENT_ID, FIGHT_ID)
