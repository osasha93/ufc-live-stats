import requests
from bs4 import BeautifulSoup
import os
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710   # бой 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем все панели с классом round- (например, round-0, round-1, ...)
round_panels = soup.select('div.c-tabs__pane[class*="round-"]')
print(f"Найдено round-панелей: {len(round_panels)}")

for panel in round_panels:
    panel_id = panel.get('id', 'без id')
    # Определяем номер раунда из класса (например, round-1)
    round_classes = [c for c in panel.get('class', []) if c.startswith('round-')]
    round_num = round_classes[0].split('-')[1] if round_classes else '?'
    print(f"\nПанель round-{round_num} (id={panel_id}):")
    
    # Ищем все метрики
    metric_blocks = panel.find_all("div", class_="c-stat-metric-compare")
    if not metric_blocks:
        # Альтернативный поиск – внутри c-stat-metric-compare-group
        metric_blocks = panel.select('.c-stat-metric-compare-group .c-stat-metric-compare')
    
    print(f"  Найдено метрик: {len(metric_blocks)}")
    for block in metric_blocks:
        # Пытаемся определить тип метрики по классу
        block_classes = block.get('class', [])
        metric_type = "unknown"
        for cls in block_classes:
            if cls in ['total_strikes', 'takedowns', 'sig_strikes', 'knockdowns', 'sub_attempts', 'rev']:
                metric_type = cls
                break
        
        # Извлекаем числа
        red_num = block.find("span", class_="c-stat-metric-compare__number")
        blue_num = block.find("span", class_="c-stat-metric-compare__value_2 c-stat-metric-compare__number")
        
        red_val = red_num.get_text(strip=True) if red_num else "?"
        blue_val = blue_num.get_text(strip=True) if blue_num else "?"
        print(f"    {metric_type}: red={red_val}, blue={blue_val}")
