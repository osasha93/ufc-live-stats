"""Ответ fight/live API → компактное описание боя для картинки и подписи (без сети, легко тестировать)."""
import hashlib
import json
from dataclasses import asdict, dataclass, field

# Бой закончен: во время турнира API сразу ставит "Over" (UFC 333, 24.10), позже — "Final"
FINISHED = ("Final", "Over")

# (подпись, поле «попал», поле «пытался» или None) — в порядке на картинке
METRICS = [
    ("Значимые удары", "SigStrikesLanded", "SigStrikesAttempted"),
    ("Все удары", "TotalStrikesLanded", "TotalStrikesAttempted"),
    ("В голову", "SigHeadStrikesLanded", "SigHeadStrikesAttempted"),
    ("В корпус", "SigBodyStrikesLanded", "SigBodyStrikesAttempted"),
    ("По ногам", "SigLegStrikesLanded", "SigLegStrikesAttempted"),
    ("Тейкдауны", "TakedownsLanded", "TakedownsAttempted"),
    ("Нокдауны", "Knockdowns", None),
    ("Попытки сабмишена", "SubmissionsAttempted", None),
    ("Контроль", "ControlTime", None),
]
ROUND_METRICS = [("Все удары", "TotalStrikesLanded"), ("Знач. удары", "SigStrikesLanded"),
                 ("Тейкдауны", "TakedownsLanded"), ("Нокдауны", "Knockdowns"), ("Контроль", "ControlTime")]


@dataclass
class Corner:
    name: str
    record: str
    outcome: str            # "Win" / "Loss" / "Draw" / "NC" / ""
    fighter_id: int | None


@dataclass
class FightView:
    fight_id: int
    status: str             # "Upcoming" / "Live" / "Final" / …
    weight_class: str
    rounds_scheduled: int
    red: Corner
    blue: Corner
    # Главный блок: во время боя — текущий раунд («РАУНД 2»), после боя — весь бой («СТАТИСТИКА БОЯ»)
    focus_title: str = ""
    focus: list = field(default_factory=list)      # [(подпись, красный, синий, доля красного 0..1 или None)]
    rounds: list = field(default_factory=list)     # [(номер, [(подпись, красный, синий)])]
    result: str = ""                               # "KO/TKO · R2 2:32 · Knee"
    judges: list = field(default_factory=list)     # [(судья, "29-28", "28-29")]
    live_round: int | None = None

    @property
    def finished(self) -> bool:
        return self.status in FINISHED

    @property
    def winner(self) -> Corner | None:
        return next((c for c in (self.red, self.blue) if c.outcome == "Win"), None)

    @property
    def title(self) -> str:
        return f"{self.red.name} vs {self.blue.name}"

    def digest(self) -> str:
        """Отпечаток всего, что видно на картинке: не изменился — не перерисовываем и не редактируем."""
        return hashlib.sha1(json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _seconds(value) -> int:
    if isinstance(value, str) and ":" in value:
        m, s = value.split(":", 1)
        return int(m) * 60 + int(s)
    return 0


def _value(stats: dict, landed: str, attempted: str | None) -> tuple[str, float]:
    """(текст, число для полоски)."""
    if landed == "ControlTime":
        text = stats.get(landed) or "0:00"
        return text, float(_seconds(text))
    got = int(stats.get(landed) or 0)
    if not attempted:
        return str(got), float(got)
    tried = int(stats.get(attempted) or 0)
    pct = f" ({round(100 * got / tried)}%)" if tried else ""
    return f"{got}/{tried}{pct}", float(got)


def _share(a: float, b: float) -> float | None:
    """Доля красного 0..1; у обоих ноль (напр. тейкдауны 0/0 и 0/1) — None, полосок не рисуем."""
    return None if a + b == 0 else a / (a + b)


def _metric_rows(red: dict, blue: dict) -> list:
    """Строки главного блока по METRICS: (подпись, красный, синий, доля красного)."""
    rows = []
    for label, landed, attempted in METRICS:
        (rt, rv), (bt, bv) = _value(red, landed, attempted), _value(blue, landed, attempted)
        rows.append((label, rt, bt, _share(rv, bv)))
    return rows


def _corner(f: dict) -> Corner:
    name = f.get("Name") or {}
    rec = f.get("Record") or {}
    record = f"{rec.get('Wins', 0)}-{rec.get('Losses', 0)}-{rec.get('Draws', 0)}"
    if rec.get("NoContests"):
        record += f" ({rec['NoContests']} NC)"
    return Corner(name=f"{name.get('FirstName', '')} {name.get('LastName', '')}".strip() or "?",
                  record=record, outcome=(f.get("Outcome") or {}).get("Outcome") or "",
                  fighter_id=f.get("FighterId"))


def _by_corner(items: list, fighters: list) -> list[dict]:
    """Статистика в порядке [красный, синий] по FighterId (в ответе порядок не гарантирован)."""
    by_id = {it.get("FighterId"): it for it in items or []}
    if all(f.get("FighterId") in by_id for f in fighters[:2]):
        return [by_id[f["FighterId"]] for f in fighters[:2]]
    return (list(items or []) + [{}, {}])[:2]


def _judges(result: dict, red_id, blue_id) -> list:
    rows = []
    for j in result.get("FightScores") or []:
        scores = {s.get("FighterId"): s.get("Score") for s in j.get("Fighters", [])}
        if red_id in scores and blue_id in scores:
            name = f"{j.get('JudgeFirstName', '')} {j.get('JudgeLastName', '')}".strip()
            rows.append((name, f"{scores[red_id]}-{scores[blue_id]}", f"{scores[blue_id]}-{scores[red_id]}"))
    return rows


def parse_fight(lf: dict, live_round: int | None = None) -> FightView:
    fighters = sorted(lf.get("Fighters") or [], key=lambda f: 0 if f.get("Corner") == "Red" else 1)
    fighters = (fighters + [{}, {}])[:2]
    red, blue = _corner(fighters[0]), _corner(fighters[1])

    rounds = []
    per_round = _by_corner(lf.get("RoundStats"), fighters)
    red_rounds = {r["RoundNumber"]: r for r in per_round[0].get("Rounds", [])}
    blue_rounds = {r["RoundNumber"]: r for r in per_round[1].get("Rounds", [])}
    for num in sorted(set(red_rounds) | set(blue_rounds)):
        r, b = red_rounds.get(num, {}), blue_rounds.get(num, {})
        rounds.append((num, [(label, _value(r, key, None)[0], _value(b, key, None)[0]) for label, key in ROUND_METRICS]))

    # Главный блок: идёт бой и есть раунды — последний (текущий) раунд; иначе — весь бой
    finished = lf.get("Status") in FINISHED
    if not finished and rounds:
        num = rounds[-1][0]
        focus_title = f"РАУНД {num}"
        focus = _metric_rows(red_rounds.get(num, {}), blue_rounds.get(num, {}))
    else:
        stats = _by_corner(lf.get("FightStats"), fighters)
        focus_title = "СТАТИСТИКА БОЯ"
        focus = _metric_rows(stats[0], stats[1])

    res = lf.get("Result") or {}
    result = ""
    if res.get("Method"):
        parts = [res["Method"]]
        if res.get("EndingRound"):
            parts.append(f"R{res['EndingRound']} {res.get('EndingTime') or ''}".strip())
        detail = res.get("EndingSubmission") or res.get("EndingStrike")
        if detail:
            parts.append(detail)
        result = " · ".join(parts)

    return FightView(
        fight_id=lf.get("FightId"), status=lf.get("Status") or "", live_round=live_round,
        weight_class=(lf.get("WeightClass") or {}).get("Description") or "",
        rounds_scheduled=(lf.get("RuleSet") or {}).get("PossibleRounds") or 3,
        red=red, blue=blue, focus_title=focus_title, focus=focus, rounds=rounds, result=result,
        judges=_judges(res, red.fighter_id, blue.fighter_id),
    )


def has_stats(view: FightView) -> bool:
    """Есть что показать: раунды или ненулевая общая статистика (до первого удара — не шлём пустую картинку)."""
    return bool(view.rounds) or any(t[1] not in ("0", "0/0", "0:00") or t[2] not in ("0", "0/0", "0:00")
                                    for t in view.focus)


def caption(view: FightView, event_name: str) -> str:
    if view.finished:
        w = view.winner
        head = f"✅ Победа: {w.name}" if w else "✅ Бой завершён"
        if view.result:
            head += f"\n{view.result}"
    else:
        rnd = f" · Раунд {view.live_round} из {view.rounds_scheduled}" if view.live_round else ""
        head = f"🔴 LIVE{rnd}"
    return f"{head}\n{view.title}\n{view.weight_class} · {event_name}"[:1024]
