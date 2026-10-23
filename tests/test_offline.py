"""
Офлайн-тесты без сети и без настоящего Telegram: автоопределение турнира (ufc.com/events, UFC API, расписание),
разбор статистики, картинка, «эфир» боя (новое сообщение → правки → итог), цикл --auto с двумя job.

  python tests/test_offline.py
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fight  # noqa: E402
import main  # noqa: E402
import render  # noqa: E402
import replay  # noqa: E402
import state  # noqa: E402
import ufc_api  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PASSED = []
T0 = datetime(2026, 10, 17, 21, 0, tzinfo=timezone.utc)   # старт турнира 1332
START = "2026-10-17T21:00:00Z"


def test(fn):
    PASSED.append(fn)
    return fn


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fx_json(name: str):
    return json.loads(fixture(name))


EVENT = fx_json("event_1332.json")
KO, DECISION = fx_json("fight_13002.json"), fx_json("fight_13046.json")


class FakeSender:
    def __init__(self, gone_after=None):
        self.log, self.next_id, self.gone_after = [], 100, gone_after

    def send(self, photo, caption, button):
        assert photo.startswith(b"\x89PNG") and button[1].startswith("https://www.ufc.com/matchup/")
        self.next_id += 1
        self.log.append(("send", self.next_id, caption.splitlines()[0]))
        return self.next_id

    def edit(self, message_id, photo, caption, button):
        if self.gone_after is not None and len(self.log) >= self.gone_after:
            self.log.append(("gone", message_id, ""))
            return None
        self.log.append(("edit", message_id, caption.splitlines()[0]))
        return True


def tmp_state(fn):
    def wrapper():
        old = (state.STATE_FILE, state.SCHEDULE_FILE)
        with tempfile.TemporaryDirectory() as tmp:
            state.STATE_FILE, state.SCHEDULE_FILE = (os.path.join(tmp, n) for n in ("live.json", "schedule.json"))
            try:
                fn()
            finally:
                state.STATE_FILE, state.SCHEDULE_FILE = old
    wrapper.__name__ = fn.__name__
    return wrapper


# ---------- автоопределение турнира ----------
@test
def test_ufc_com_events_page():
    links = ufc_api.parse_events_page(fixture("events_page.html"))
    assert links[0] == "/event/ufc-333", links[:3]
    assert ufc_api.parse_event_page_id(fixture("event_page_ufc333.html")) == 1336
    assert ufc_api.api_from_html(fixture("event_page_ufc333.html")) == "https://d29dxerjsp82wz.cloudfront.net/api/v3"


@test
def test_discover_from_ufc_com():
    pages = {f"{ufc_api.UFC}/events": fixture("events_page.html"),
             f"{ufc_api.UFC}/event/ufc-333": fixture("event_page_ufc333.html")}
    upcoming = {"EventId": 1336, "StartTime": "2026-10-24T14:00Z", "Status": "Upcoming",
                "Organization": {"OrganizationId": 1}}
    found = ufc_api.discover_from_ufc_com(datetime(2026, 10, 22, tzinfo=timezone.utc),
                                          fetch_page=lambda url: pages.get(url, ""),
                                          fetch_event=lambda i: upcoming if i == 1336 else None)
    assert found == 1336
    cancelled = {**upcoming, "Status": "Canceled"}
    assert ufc_api.discover_from_ufc_com(datetime(2026, 10, 22, tzinfo=timezone.utc),
                                         fetch_page=lambda url: pages.get(url, ""),
                                         fetch_event=lambda i: cancelled) is None


@test
def test_find_event_id_by_start():
    others = {1330: {"EventId": 1330, "StartTime": "2026-08-25T23:00Z", "Organization": {"OrganizationId": 67}}}
    fetch = lambda i: EVENT if i == 1332 else others.get(i)  # noqa: E731
    assert ufc_api.find_event_id(T0, hint=1325, fetch=fetch) == 1332
    assert ufc_api.find_event_id(T0 + timedelta(days=7), hint=1325, fetch=fetch) is None


@test
def test_resolve_event_schedule_then_ufc_com():
    sched = {"events": [{"title": "UFC Edmonton", "start_utc": START, "url": "t"}]}
    live_state = {}
    hit = main.resolve_event(T0 + timedelta(hours=1), sched, live_state,
                             find=lambda s, h: 1332, discover=lambda now: None)
    assert hit == (1332, START) and live_state["event_ids"][START] == 1332
    # расписания нет — ufc.com/events; турнир ещё не начался → None, идёт → найден
    ev = {"EventId": 1336, "StartTime": "2026-10-24T14:00Z"}
    kw = dict(find=lambda s, h: None, discover=lambda now: 1336, get_event=lambda i: ev)
    assert main.resolve_event(datetime(2026, 10, 22, tzinfo=timezone.utc), {}, {}, **kw) is None
    assert main.resolve_event(datetime(2026, 10, 24, 15, tzinfo=timezone.utc), {}, {}, **kw) == (1336, ev["StartTime"])
    assert main.resolve_event(datetime(2026, 10, 24, 15, tzinfo=timezone.utc), {}, {"done": [ev["StartTime"]]}, **kw) is None


# ---------- статистика и картинка ----------
@test
def test_parse_fight_decision():
    v = fight.parse_fight(DECISION)
    assert v.finished and v.winner.name == "Jasmine Jasudavicius" and v.red.name == "Erin Blanchfield"
    assert v.focus_title == "СТАТИСТИКА БОЯ"      # бой завершён — общая статистика
    assert v.focus[0] == ("Значимые удары", "62/134 (46%)", "43/138 (31%)", 62 / 105)
    assert [r[0] for r in v.rounds] == [1, 2, 3]
    assert v.result.startswith("Decision - Unanimous · R3 5:00")
    assert len(v.judges) == 3 and all(red == "28-29" for _, red, _ in v.judges)


@test
def test_parse_fight_ko_and_caption():
    v = fight.parse_fight(KO)
    assert v.result == "KO/TKO · R2 2:32 · Knee" and v.winner.name == "Mike Malott" and v.judges == []
    cap = fight.caption(v, EVENT["Name"])
    assert cap.startswith("✅ Победа: Mike Malott\nKO/TKO") and len(cap) <= 1024
    live = fight.parse_fight(replay.snapshots(KO)[0][0], live_round=2)
    assert fight.caption(live, EVENT["Name"]).startswith("🔴 LIVE · Раунд 2 из 5")


@test
def test_render_png():
    for lf in (KO, DECISION, replay.snapshots(DECISION)[0][0]):
        png = render.render(fight.parse_fight(lf), EVENT["Name"], (None, None))
        assert png.startswith(b"\x89PNG") and len(png) > 10_000


@test
def test_card_html_live_and_final():
    import card
    live_html = card.build_html(fight.parse_fight(replay.snapshots(DECISION)[2][0], live_round=2), EVENT["Name"])
    assert "LIVE · РАУНД 2 ИЗ 3" in live_html and "РАУНД 2</span>" in live_html and "СУДЬИ" not in live_html
    assert 'class="current"' in live_html and "ИТОГ" not in live_html
    final_html = card.build_html(fight.parse_fight(DECISION), EVENT["Name"])
    assert "ИТОГ" in final_html and "СТАТИСТИКА БОЯ" in final_html and "СУДЬИ" in final_html
    assert 'class="dense"' in final_html and "ПОБЕДА" in final_html
    assert "data:font/woff2;base64," in final_html          # шрифты встроены — рендер без сети и file://
    assert "linear-gradient" not in card.STYLE               # social-canvas: без градиентов
    assert "border-radius: 50%" in card.STYLE and card.STYLE.count("border-radius") == 1   # острые углы, кроме точки


@test
def test_no_bars_when_both_landed_zero():
    """Тейкдауны 0/0 против 0/1 — попаданий нет ни у кого, полосок быть не должно (было: обе полные)."""
    import card
    live = fight.parse_fight(replay.snapshots(DECISION)[2][0], live_round=2)
    td = next(row for row in live.focus if row[0] == "Тейкдауны")
    assert td[1] == "0/0" and td[2].startswith("0/") and td[3] is None
    html = card._stats(live)
    row = html[html.index("Тейкдауны"):]
    assert 'class="l" style="width:0%"' in row[:400] and 'class="rt" style="width:0%"' in row[:400]


@test
def test_render_falls_back_to_pillow():
    old = render._get_page, render._disabled
    render._get_page = lambda: (_ for _ in ()).throw(RuntimeError("no chromium"))
    render._disabled = False
    try:
        png = render.render(fight.parse_fight(KO), EVENT["Name"], (None, None))
        assert png.startswith(b"\x89PNG") and render._disabled
        from PIL import Image
        import io
        assert Image.open(io.BytesIO(png)).size == (1080, 1350)   # запасная карточка — тот же формат
        for lf, rnd in replay.snapshots(DECISION):                 # все состояния рисуются без ошибок
            assert render.render(fight.parse_fight(lf, rnd), EVENT["Name"]).startswith(b"\x89PNG")
    finally:
        render._get_page, render._disabled = old


@test
def test_rounds_table_all_strikes():
    v = fight.parse_fight(DECISION)
    labels = [label for label, _, _ in v.rounds[0][1]]
    assert labels[:2] == ["Все удары", "Знач. удары"]               # сначала все удары, потом значимые
    red = fight._by_corner(DECISION["RoundStats"], sorted(
        DECISION["Fighters"], key=lambda f: 0 if f.get("Corner") == "Red" else 1))[0]
    r1 = red["Rounds"][0]
    assert v.rounds[0][1][0][1] == str(r1["TotalStrikesLanded"])    # как есть из API, без пересчёта


@test
def test_replay_snapshots_like_live():
    shots = replay.snapshots(DECISION)
    assert [r for _, r in shots] == [1, 1, 2, 2, 3, None]       # середина/конец каждого раунда, потом итог
    mid_r1, end_r1 = shots[0][0], shots[1][0]
    red_id = end_r1["FightStats"][0]["FighterId"]
    red_r1 = next(s for s in DECISION["RoundStats"] if s["FighterId"] == red_id)["Rounds"][0]
    assert end_r1["FightStats"][0]["SigStrikesLanded"] == red_r1["SigStrikesLanded"]
    assert mid_r1["FightStats"][0]["SigStrikesLanded"] == red_r1["SigStrikesLanded"] // 2
    assert all(s["Status"] == "Live" and s["Result"] == {} for s, _ in shots[:-1])


@test
def test_live_shows_current_round_final_shows_whole_fight():
    """Во время боя главный блок — текущий раунд, по окончании — весь бой; судьи и метод — только в итоге."""
    mid_r2, _ = replay.snapshots(DECISION)[2]
    live = fight.parse_fight(mid_r2, live_round=2)
    assert live.focus_title == "РАУНД 2" and [r[0] for r in live.rounds] == [1, 2]
    assert live.result == "" and live.judges == [] and live.winner is None
    r2_red = live.rounds[1][1][1][1]                             # «Знач. удары» красного в таблице за R2
    assert live.focus[0][1].startswith(r2_red + "/")              # главный блок = цифры R2, а не всего боя
    final = fight.parse_fight(DECISION)
    assert final.focus_title == "СТАТИСТИКА БОЯ" and final.judges and final.result


@test
def test_no_empty_picture_before_first_action():
    empty = json.loads(json.dumps(DECISION))
    empty.update(Status="Live", Result={}, RoundStats=[], FightStats=[])
    assert not fight.has_stats(fight.parse_fight(empty))


# ---------- «эфир» боя ----------
def run_broadcast(sender, fights):
    lives = []
    for lf, live_round in replay.snapshots(DECISION):
        tr = main.Tracker(sender, 1332, fights,
                          get_event=lambda _i, lf=lf, r=live_round: replay.fake_event(EVENT, 13046, lf, r),
                          get_fight=lambda _i, lf=lf: lf, get_photos=lambda *_: (None, None))
        done, _, live = tr.tick()
        lives.append(live)
        tr.tick()                                # повтор без изменений — Telegram не трогаем
    return done, lives


@test
def test_broadcast_send_edit_final():
    s, fights = FakeSender(), {}
    done, lives = run_broadcast(s, fights)
    assert done                                  # турнир (из одного боя) завершён
    assert [a for a, _, _ in s.log] == ["send"] + ["edit"] * 5   # одна карточка, дальше только правки
    assert s.log[-1][2].startswith("✅ Победа") and fights["13046"]["final"]
    assert lives == [True] * 5 + [False]         # 5 с во время боя, после итога — снова 30 с


@test
def test_broadcast_message_deleted_resent():
    s, fights = FakeSender(gone_after=1), {}
    run_broadcast(s, fights)
    assert [a for a, _, _ in s.log][:3] == ["send", "gone", "send"]


# ---------- цикл --auto ----------
class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


@test
@tmp_state
def test_run_auto_two_jobs_cover_7h():
    """Турнир 7 ч: part1 упирается в лимит job, part2 продолжает с сохранённого состояния и доводит до конца."""
    clock = Clock(T0)
    end = T0 + timedelta(hours=7)
    ticks = []

    class FakeTracker:
        def __init__(self, sender, event_id, fights):
            self.event_name, self.fights = "UFC Edmonton", fights

        def tick(self):
            ticks.append(clock.t)
            self.fights.setdefault("13046", {"msg": 1})
            return clock.t >= end, len(ticks) == 1, False

    resolve = lambda now, sched, st: (1332, START) if START not in st.get("done", []) else None  # noqa: E731
    main.run_auto(FakeSender(), now=clock.now, sleep=clock.sleep, resolve=resolve, tracker_cls=FakeTracker)
    assert T0 + timedelta(hours=5, minutes=30) <= clock.t <= T0 + main.JOB_BUDGET
    assert state.load_json(state.STATE_FILE, {})["fights"]["1332"]["13046"]["msg"] == 1   # состояние для part2
    clock.t += timedelta(minutes=2)
    main.run_auto(FakeSender(), now=clock.now, sleep=clock.sleep, resolve=resolve, tracker_cls=FakeTracker)
    assert clock.t >= end and state.load_json(state.STATE_FILE, {})["done"] == [START]
    assert max(b - a for a, b in zip(ticks, ticks[1:])) <= timedelta(minutes=3)   # без дыр между job
    n = len(ticks)
    main.run_auto(FakeSender(), now=clock.now, sleep=clock.sleep, resolve=resolve, tracker_cls=FakeTracker)
    assert len(ticks) == n                       # запасной запуск после конца — сразу выход


@test
@tmp_state
def test_run_auto_interval_30_5_30():
    """Между боями — 30 с, как только бой пошёл — 5 с, после итога — снова 30 с."""
    clock = Clock(T0 + timedelta(minutes=10))
    fight_start, fight_end = clock.t + timedelta(minutes=2), clock.t + timedelta(minutes=17)
    ticks = []

    class FakeTracker:
        def __init__(self, sender, event_id, fights):
            self.event_name = "UFC Edmonton"

        def tick(self):
            ticks.append(clock.t)
            return clock.t >= fight_end + timedelta(minutes=3), False, fight_start <= clock.t < fight_end

    main.run_auto(FakeSender(), now=clock.now, sleep=clock.sleep,
                  resolve=lambda *a: (1332, START), tracker_cls=FakeTracker)
    gaps = [(a, b - a) for a, b in zip(ticks, ticks[1:])]
    assert all(g == timedelta(seconds=30) for t, g in gaps if t < fight_start - timedelta(seconds=30))
    assert all(g == timedelta(seconds=5) for t, g in gaps if fight_start <= t < fight_end)
    assert all(g == timedelta(seconds=30) for t, g in gaps if t >= fight_end)


if __name__ == "__main__":
    failed = 0
    for fn in PASSED:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(PASSED) - failed}/{len(PASSED)} пройдено")
    sys.exit(1 if failed else 0)
