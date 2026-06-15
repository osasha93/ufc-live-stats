import requests
import json

EVENT_ID = int(os.environ["EVENT_ID"])
FIGHT_ID = 12710

url = f"https://www.ufc.com/api/matchup/{EVENT_ID}/{FIGHT_ID}/stats"
headers = {"User-Agent": "Mozilla/5.0"}
print(f"Пробуем API: {url}")
resp = requests.get(url, headers=headers)
print(f"Статус: {resp.status_code}")
if resp.status_code == 200:
    try:
        data = resp.json()
        print("Ключи в ответе API:")
        print(data.keys() if isinstance(data, dict) else "не словарь")
        # Если есть rounds – покажем первый раунд
        if 'rounds' in data:
            print("Первый раунд:", json.dumps(data['rounds'][0], indent=2))
    except Exception as e:
        print(f"Ошибка парсинга JSON: {e}")
else:
    # Попробуем альтернативный путь
    url2 = f"https://www.ufc.com/api/matchup/{EVENT_ID}/{FIGHT_ID}/post"
    print(f"Пробуем /post: {url2}")
    resp2 = requests.get(url2, headers=headers)
    print(f"Статус: {resp2.status_code}")
    if resp2.status_code == 200:
        try:
            data2 = resp2.json()
            print("Ключи:", data2.keys() if isinstance(data2, dict) else "не словарь")
        except:
            print("Не JSON")
