def get_event_data():
    """Парсит страницу события и возвращает event_id и список fight_id"""
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(EVENT_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Сначала ищем все ссылки, ведущие на /matchup/...
    matchup_links = soup.find_all("a", href=re.compile(r"/matchup/\d+/\d+"))
    if not matchup_links:
        # Иногда ссылки могут быть на /matchup/ID1/ID2/post, но чаще без /post
        matchup_links = soup.find_all("a", href=re.compile(r"/matchup/\d+/\d+/post"))

    if not matchup_links:
        raise Exception("Не найдены ссылки на бои (matchup)")

    # Берём первый попавшийся URL и извлекаем event_id и fight_id (но нам нужен только event_id)
    first_href = matchup_links[0]["href"]
    match = re.search(r"/matchup/(\d+)/\d+", first_href)
    if not match:
        raise Exception("Не удалось извлечь Event ID из ссылки")
    event_id = int(match.group(1))

    # 2. Собираем все fight_id из хэшей (#12711)
    fight_ids = set()
    for a in soup.find_all("a", href=re.compile(r'#\d+')):
        href = a["href"]
        if href.startswith("#"):
            try:
                fid = int(href[1:])
                fight_ids.add(fid)
            except:
                pass
    if not fight_ids:
        raise Exception("Не найдены ID боёв")

    fight_ids = sorted(list(fight_ids))  # сохраняем порядок (обычно от первого к главному)

    return event_id, fight_ids
