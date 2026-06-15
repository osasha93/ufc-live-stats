import requests
from bs4 import BeautifulSoup
import os
import json
import time
import re

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710  # второй бой

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Все кнопки-вкладки
tab_buttons = soup.select("button.c-tabs__nav-btn")
print(f"=== ТАБЫ ({len(tab_buttons)}) ===")
for btn in tab_buttons:
    print(f"  '{btn.get_text(strip())}' -> aria-controls='{btn.get('aria-controls')}'")

# Все панели
panels = soup.select("div.c-tabs__pane")
print(f"\n=== ПАНЕЛИ ({len(panels)}) ===")
for i, panel in enumerate(panels):
    pid = panel.get("id", "без id")
    container = panel.find("div", class_="c-stat-group__container")
    print(f"Панель {i} (id='{pid}'): контейнер найден = {container is not None}")
    if container:
        # Ищем все c-stat-metric-compare внутри контейнера
        metric_blocks = panel.find_all("div", class_="c-stat-metric-compare")
        for block in metric_blocks:
            label_el = block.find("span", class_="c-stat-metric-compare__label")
            label = label_el.get_text(strip=True) if label_el else "без названия"
            print(f"    metric block label='{label}'")

if __name__ == "__main__":
    pass
