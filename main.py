import requests
from bs4 import BeautifulSoup
import os
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710   # бой, для которого мы ищем данные

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем вкладки и панели
tab_buttons = soup.select("button.c-tabs__nav-btn")
print("=== ВКЛАДКИ ===")
for btn in tab_buttons:
    print(f"  '{btn.get_text(strip=True)}' -> aria-controls='{btn.get('aria-controls')}'")

# Находим панель для Round 1 (должна быть tab-panel-stats-fight-overview-2)
panel_id = "tab-panel-stats-fight-overview-2"
panel = soup.find("div", id=panel_id)
if panel:
    print(f"\n=== ПАНЕЛЬ {panel_id} ===")
    metric_blocks = panel.find_all("div", class_="c-stat-metric-compare")
    if not metric_blocks:
        metric_blocks = panel.select('.c-stat-metric-compare-group .c-stat-metric-compare')
    print(f"Найдено метрик: {len(metric_blocks)}")
    for block in metric_blocks:
        label_el = block.find("span", class_="c-stat-metric-compare__label")
        label = label_el.get_text(strip=True) if label_el else "без названия"
        red_num = block.find("span", class_="c-stat-metric-compare__number")
        blue_num = block.find("span", class_="c-stat-metric-compare__value_2 c-stat-metric-compare__number")
        red_val = red_num.get_text(strip=True) if red_num else "?"
        blue_val = blue_num.get_text(strip=True) if blue_num else "?"
        print(f"  {label}: red={red_val}, blue={blue_val}")
else:
    print(f"Панель {panel_id} не найдена.")
    # Попробуем найти любую панель с Round 1
    for btn in tab_buttons:
        if btn.get_text(strip=True) == "Round 1":
            pid = btn.get("aria-controls")
            panel = soup.find("div", id=pid)
            if panel:
                print(f"Найдена панель {pid}")
                metric_blocks = panel.find_all("div", class_="c-stat-metric-compare")
                print(f"Метрик в ней: {len(metric_blocks)}")
                for block in metric_blocks:
                    label_el = block.find("span", class_="c-stat-metric-compare__label")
                    label = label_el.get_text(strip=True) if label_el else "без названия"
                    red_num = block.find("span", class_="c-stat-metric-compare__number")
                    blue_num = block.find("span", class_="c-stat-metric-compare__value_2 c-stat-metric-compare__number")
                    red_val = red_num.get_text(strip=True) if red_num else "?"
                    blue_val = blue_num.get_text(strip=True) if blue_num else "?"
                    print(f"  {label}: red={red_val}, blue={blue_val}")
            break

if __name__ == "__main__":
    pass
