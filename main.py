import requests
from bs4 import BeautifulSoup
import os
import time
import json
import re

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/matchup/{EVENT_ID}/{FIGHT_ID}/post?t={int(time.time())}"
headers = {"User-Agent": "Mozilla/5.0"}
resp = requests.get(url, headers=headers, timeout=15)
soup = BeautifulSoup(resp.text, "html.parser")

# Ищем скрипты с JSON
for script in soup.find_all('script'):
    if script.string and ('drupalSettings' in script.string or 'matchup' in script.string):
        print("=== НАЙДЕН СКРИПТ С ДАННЫМИ ===")
        # Пытаемся извлечь JSON
        match = re.search(r'(\{.*\})', script.string, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1))
                # Ищем статистику
                if 'matchup' in data:
                    print("Ключи внутри matchup:")
                    print(data['matchup'].keys())
                    # Попробуем найти раунды
                    if 'stats' in data['matchup']:
                        print("Статистика по раундам:")
                        print(json.dumps(data['matchup']['stats'], indent=2)[:2000])
                break
            except Exception as e:
                print(f"Не удалось разобрать JSON: {e}")
