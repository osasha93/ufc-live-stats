"""Сохранить ответы UFC API и страницы ufc.com в tests/fixtures (для офлайн-тестов и повтора турнира).
Турнир 17.10.2026 (ID 1332): главный бой — KO, плюс бой с решением судей."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import ufc_api  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")
EVENT_ID = 1332


def save(name: str, data) -> None:
    mode = "w"
    with open(os.path.join(FIXTURES, name), mode, encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, ensure_ascii=False)
    print("✅", name)


os.makedirs(FIXTURES, exist_ok=True)
event = ufc_api.get_event(EVENT_ID)
save(f"event_{EVENT_ID}.json", event)
ko = next(f for f in event["FightCard"] if f["FightOrder"] == 1)
decision = next(f for f in event["FightCard"] if "Decision" in (f.get("Result") or {}).get("Method", ""))
for fid in (ko["FightId"], decision["FightId"]):
    save(f"fight_{fid}.json", ufc_api.get_fight(fid))
get = lambda url: ufc_api.session.get(url, headers=ufc_api.PAGE_HEADERS, timeout=20).text  # noqa: E731
save("events_page.html", get(f"{ufc_api.UFC}/events"))
save("event_page_ufc333.html", get(f"{ufc_api.UFC}/event/ufc-333"))
save(f"matchup_{decision['FightId']}.html", get(ufc_api.matchup_url(EVENT_ID, decision["FightId"])))
print("бой с решением:", decision["FightId"])
