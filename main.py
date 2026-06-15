import requests
from bs4 import BeautifulSoup
import os
import time

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710   # второй бой

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# 1. Ищем все элементы, которые могут содержать data-value или data-percent
print("=== ЭЛЕМЕНТЫ С data-value / data-percent ===")
data_elements = soup.select('[data-value], [data-percent]')
for el in data_elements[:20]:  # первые 20 штук
    value = el.get('data-value')
    percent = el.get('data-percent')
    if value or percent:
        print(f"  tag={el.name}, class={el.get('class')}, data-value={value}, data-percent={percent}")

# 2. Ищем старые метрики (span.c-stat-metric-compare__number)
print("\n=== СТАРЫЕ МЕТРИКИ (span.c-stat-metric-compare__number) ===")
old_numbers = soup.select('span.c-stat-metric-compare__number')
for num in old_numbers[:10]:
    print(f"  {num.get_text(strip=True)}")

# 3. Выводим весь HTML первого контейнера с data-value
if data_elements:
    first = data_elements[0]
    # Поднимаемся до ближайшего div
    parent = first.find_parent('div')
    if parent:
        print("\n=== HTML БЛОКА С ПЕРВЫМ data-value ===")
        print(parent.prettify()[:3000])

if __name__ == "__main__":
    pass
