"""
UFC LIVE → Telegram: статистика боёв турнира UFC в прямом эфире.
На каждый бой — одна картинка: во время боя — статистика текущего раунда (обновление каждые 5 с),
по окончании — общая статистика боя, метод победы и судьи; между боями проверка каждые 30 с.
Турнир определяется сам (schedule.json от tapology-bot или ufc.com/events), ничего вручную не вводится.

  python main.py --auto                     # как в GitHub Actions: идёт турнир — цикл до его конца, иначе выход
  python main.py --auto --dry-run           # то же без Telegram: картинки в out/
  python main.py --find                     # какой турнир бот определил бы сейчас
  python main.py --replay 13046             # повтор боя 17.10 «как в эфире» в тестовую группу tapology-bot
  python main.py --replay 13046 --dry-run   # то же в out/
  python main.py --replay 13046 --pillow    # то же запасной картинкой (как если Chromium не поднялся)
  python main.py --target prod              # в боевой чат (секреты из secret.Py этой папки)
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader

import fight
import render
import replay
import state
import ufc_api
from tg import DryRunSender, TelegramSender

INTERVAL = timedelta(seconds=30)                 # между боями — ждём начала следующего
LIVE_INTERVAL = timedelta(seconds=5)             # пока идёт бой — статистика раунда почти в реальном времени
WINDOW_BEFORE = timedelta(minutes=30)            # турнир «идёт» с start − 30 мин…
EVENT_HOURS = timedelta(hours=7)                 # …самые долгие турниры — до 7 ч (UFC 332: 6 ч 56 мин)
WINDOW_AFTER = EVENT_HOURS + timedelta(hours=1)  # …до start + 8 ч (запас на задержки)
JOB_BUDGET = timedelta(hours=5, minutes=40)      # лимит job в Actions — 6 ч; дальше продолжит part2 (live.yml)
LIVE_GRACE = timedelta(minutes=12)               # идущий бой можно дотянуть сверх JOB_BUDGET (timeout job 355 мин)
BUTTON_TEXT = "📊 Статистика на UFC.com"
TAPOLOGY_SECRET = r"H:\СКРИПТЫ\tapology-bot\config\secret.py"
OUT_DIR = os.path.join(state.HERE, "out")
SKIP_STATUSES = ("Upcoming", "Canceled", "")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def telegram_target(target: str) -> tuple[str, str, str | None]:
    """В Actions — из переменных окружения. Локально: test — тестовая группа tapology-bot, prod — secret.Py."""
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        return (os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"],
                os.environ.get("TELEGRAM_THREAD_ID") or None)
    path = TAPOLOGY_SECRET if target == "test" else os.path.join(state.HERE, "secret.Py")
    if not os.path.exists(path):
        raise RuntimeError(f"Нет файла с секретами для --target {target}: {path}")
    secret = SourceFileLoader(f"secret_{target}", path).load_module()
    token, chat = getattr(secret, "BOT_TOKEN", ""), getattr(secret, "CHAT_ID", "")
    if not token or not chat:
        raise RuntimeError(f"В {path} не заполнены BOT_TOKEN / CHAT_ID")
    return token, str(chat), getattr(secret, "THREAD_ID", None) or None


# ---------- Один проход по турниру ----------
class Tracker:
    """Шлёт/правит картинки боёв турнира. fights — состояние {ID боя: {"msg", "digest", "final"}}."""

    def __init__(self, sender, event_id: int, fights: dict,
                 get_event=ufc_api.get_event, get_fight=ufc_api.get_fight,
                 get_photos=ufc_api.fighter_photos, draw=render.render):
        self.sender, self.event_id, self.fights = sender, event_id, fights
        self.get_event, self.get_fight, self.get_photos, self.draw = get_event, get_fight, get_photos, draw
        self.photos: dict[str, list] = {}
        self.event_name = ""

    def tick(self) -> tuple[bool, bool, bool]:
        """(турнир закончился и все итоги отправлены, изменилось состояние для сохранения,
        сейчас идёт бой — итог которого ещё не отправлен → проверять чаще)."""
        ev = self.get_event(self.event_id)
        if not ev:
            return False, False, False
        self.event_name = ev.get("Name") or self.event_name
        live_id, live_round = ev.get("LiveFightId"), ev.get("LiveRoundNumber")
        changed = False
        # ранние прелимы идут первыми — у них самый большой FightOrder
        for card in sorted(ev.get("FightCard", []), key=lambda f: -(f.get("FightOrder") or 0)):
            fid = card["FightId"]
            st = self.fights.get(str(fid), {})
            if st.get("final") or (card.get("Status") in SKIP_STATUSES and fid != live_id):
                continue
            changed |= self._update(fid, live_round if fid == live_id else None)
        cards = ev.get("FightCard", [])
        live = any(not self.fights.get(str(f["FightId"]), {}).get("final")
                   and (f["FightId"] == live_id or f.get("Status") not in SKIP_STATUSES + ("Final",))
                   for f in cards)
        done = ev.get("Status") == "Final" and all(
            self.fights.get(str(f["FightId"]), {}).get("final") or f.get("Status") == "Canceled" for f in cards)
        return done, changed, live

    def _update(self, fid: int, live_round: int | None) -> bool:
        lf = self.get_fight(fid)
        if not lf:
            return False
        view = fight.parse_fight(lf, live_round)
        if not view.finished and not fight.has_stats(view):
            return False                              # бой открыт, но ещё ни одного действия — ждём
        st = self.fights.setdefault(str(fid), {})
        digest = view.digest()
        if digest == st.get("digest"):
            return False                              # цифры те же — Telegram не трогаем
        if str(fid) not in self.photos:
            self.photos[str(fid)] = self.get_photos(self.event_id, fid)
        png = self.draw(view, self.event_name, self.photos[str(fid)])
        caption = fight.caption(view, self.event_name)
        button = (BUTTON_TEXT, ufc_api.matchup_url(self.event_id, fid))
        new_message = False
        ok = self.sender.edit(st["msg"], png, caption, button) if st.get("msg") else None
        if ok is None:                                # сообщения ещё нет или его удалили
            msg = self.sender.send(png, caption, button)
            if not msg:
                return False
            st["msg"], new_message = msg, True
        elif not ok:
            return False
        st["digest"] = digest
        if view.finished:
            st["final"] = True
        print(f"{'🆕' if new_message else '✏️'} {view.title}: {'итог' if view.finished else f'раунд {live_round}'}")
        return new_message or view.finished


# ---------- Какой турнир сейчас ----------
def scheduled_event(schedule: dict, live_state: dict, now: datetime) -> dict | None:
    """Турнир из schedule.json, который идёт сейчас и ещё не отмечен завершённым."""
    for ev in sorted(schedule.get("events", []), key=lambda e: e["start_utc"]):
        start = ufc_api.parse_time(ev["start_utc"])
        if ev["start_utc"] not in live_state.get("done", []) and \
                start - WINDOW_BEFORE <= now <= start + WINDOW_AFTER:
            return ev
    return None


def resolve_event(now: datetime, schedule: dict, live_state: dict,
                  find=ufc_api.find_event_id, discover=ufc_api.discover_from_ufc_com,
                  get_event=ufc_api.get_event) -> tuple[int, str] | None:
    """(ID турнира в UFC API, ключ для done) или None. Сначала расписание tapology-bot, затем ufc.com/events."""
    sched = scheduled_event(schedule, live_state, now)
    if sched:
        key = sched["start_utc"]
        ids = live_state.setdefault("event_ids", {})
        if key not in ids:
            event_id = find(ufc_api.parse_time(key), live_state.get("last_event_id"))
            if event_id is None:
                print(f"UFC API: «{sched['title']}» пока не найден по времени старта, пробую ufc.com/events.")
            else:
                ids[key] = live_state["last_event_id"] = event_id
        if key in ids:
            return ids[key], key
    event_id = discover(now)
    ev = event_id and get_event(event_id)
    if not ev:
        return None
    key = ev["StartTime"]
    start = ufc_api.parse_time(key)
    if key in live_state.get("done", []) or not (start - WINDOW_BEFORE <= now <= start + WINDOW_AFTER):
        return None
    live_state["last_event_id"] = event_id
    return event_id, key


def run_auto(sender, save: bool = True, now=now_utc, sleep=time.sleep,
             resolve=resolve_event, tracker_cls=Tracker) -> None:
    live_state = state.load_json(state.STATE_FILE, {})
    found = resolve(now(), state.load_json(state.SCHEDULE_FILE, {}), live_state)
    if not found:
        print("Сейчас турнира UFC нет — выхожу.")
        return
    event_id, key = found
    deadline = now() + JOB_BUDGET
    window_end = ufc_api.parse_time(key) + WINDOW_AFTER
    fights = live_state.setdefault("fights", {}).setdefault(str(event_id), {})
    tracker = tracker_cls(sender, event_id, fights)
    print(f"🥊 Турнир ID {event_id} (старт {key}): проверка каждые {int(INTERVAL.total_seconds())} с, "
          f"во время боя — каждые {int(LIVE_INTERVAL.total_seconds())} с")
    was_live = False
    while True:
        done, changed, live = tracker.tick()
        if live != was_live:
            print(f"⏱ {'Бой идёт — обновление каждые 5 с' if live else 'Боя нет — проверка каждые 30 с'}")
            was_live = live
        interval = LIVE_INTERVAL if live else INTERVAL
        done = done or now() >= window_end
        if done:
            live_state.setdefault("done", []).append(key)
        if save and (changed or done):
            state.save_json(state.STATE_FILE, live_state)
            state.git_push(f"{'Done' if done else 'Live'}: {tracker.event_name or event_id}")
        if done:
            print("✅ Турнир закончился, итоги всех боёв отправлены — выхожу.")
            return
        # лимит job: между боями уходим сразу, а идущий бой дотягиваем (до +12 мин, job живёт 355 мин),
        # чтобы передача part1 → part2 (1–2 мин на запуск) не пришлась на середину раунда
        if now() + interval > deadline + (LIVE_GRACE if live else timedelta(0)):
            if save:
                state.save_json(state.STATE_FILE, live_state)
                state.git_push(f"Pause: {tracker.event_name or event_id}")
            print("⏸ Лимит времени job — продолжит следующий job.")
            return
        sleep(interval.total_seconds())


def run_replay(sender, fight_id: int, event_id: int, pause: float) -> None:
    """Повтор прошедшего боя «как в эфире»: снимок после каждого раунда, затем итог."""
    event = ufc_api.get_event(event_id)
    final = ufc_api.get_fight(fight_id)
    if not event or not final:
        print(f"❌ Нет данных UFC API для турнира {event_id} / боя {fight_id}")
        sys.exit(1)
    fights: dict = {}
    photos = ufc_api.fighter_photos(event_id, fight_id)
    shots = replay.snapshots(final)
    for i, (lf, live_round) in enumerate(shots):
        Tracker(sender, event_id, fights,
                get_event=lambda _id, lf=lf, r=live_round: replay.fake_event(event, fight_id, lf, r),
                get_fight=lambda _id, lf=lf: lf,
                get_photos=lambda *_: photos).tick()
        if i < len(shots) - 1:
            time.sleep(pause)


def main():
    p = argparse.ArgumentParser(description="UFC LIVE → Telegram")
    p.add_argument("--auto", action="store_true", help="цикл по турниру, который идёт сейчас (GitHub Actions)")
    p.add_argument("--find", action="store_true", help="показать, какой турнир определён, и выйти")
    p.add_argument("--replay", type=int, metavar="FIGHT_ID", help="повтор прошедшего боя «как в эфире»")
    p.add_argument("--event", type=int, default=1332, help="ID турнира для --replay (по умолчанию 17.10.2026)")
    p.add_argument("--pause", type=float, default=5, help="пауза между снимками --replay, с")
    p.add_argument("--dry-run", action="store_true", help="не отправлять, картинки в out/")
    p.add_argument("--pillow", action="store_true", help="рисовать запасной вариант (как если Chromium не поднялся)")
    p.add_argument("--target", choices=["test", "prod"], default="test",
                   help="локально: test — тестовая группа tapology-bot (по умолчанию), prod — secret.Py")
    args = p.parse_args()

    if args.find:
        live_state = state.load_json(state.STATE_FILE, {})
        found = resolve_event(now_utc(), state.load_json(state.SCHEDULE_FILE, {}), live_state)
        nearest = ufc_api.discover_from_ufc_com(now_utc())
        ev = nearest and ufc_api.get_event(nearest)
        print(f"Идёт сейчас: {found or 'нет'}")
        print(f"Ближайший по ufc.com/events: {nearest} {ev and ev['Name']} {ev and ev['StartTime']}")
        return

    if args.dry_run:
        sender = DryRunSender(OUT_DIR)
    else:
        try:
            sender = TelegramSender(*telegram_target(args.target))
        except RuntimeError as e:
            print(f"❌ {e}")
            sys.exit(1)
    print(f"🎯 {'GitHub Actions' if state.IN_ACTIONS else args.target}{' (dry-run)' if args.dry_run else ''}")
    if args.pillow:
        render._disabled = True

    if args.replay:
        run_replay(sender, args.replay, args.event, args.pause)
    elif args.auto:
        run_auto(sender, save=not args.dry_run)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
