"""Повтор прошедшего боя «как в прямом эфире»: из итогового ответа API — снимки после каждого раунда.
Нужен для проверки в тестовой группе и в офлайн-тестах (сообщение создаётся, правится, в конце — итог)."""
import copy


def _add(a, b):
    if isinstance(a, str) or isinstance(b, str):        # время "m:ss"
        def sec(v):
            if isinstance(v, str) and ":" in v:
                m, s = v.split(":", 1)
                return int(m) * 60 + int(s)
            return 0
        total = sec(a) + sec(b)
        return f"{total // 60}:{total % 60:02d}"
    return (a or 0) + (b or 0)


def _sum_rounds(rounds: list[dict], fighter_id) -> dict:
    total = {"FighterId": fighter_id}
    for r in rounds:
        for k, v in r.items():
            if k in ("RoundNumber", "SigStrikesAccuracy", "TakedownsAccuracy"):
                continue
            total[k] = _add(total.get(k, "0:00" if isinstance(v, str) else 0), v)
    return total


def _half(r: dict) -> dict:
    """Раунд «на середине»: все счётчики и время пополам (так выглядит идущий раунд в API)."""
    out = {}
    for k, v in r.items():
        if k in ("RoundNumber", "SigStrikesAccuracy", "TakedownsAccuracy"):
            out[k] = v
        elif isinstance(v, str) and ":" in v:
            m, s = v.split(":", 1)
            sec = (int(m) * 60 + int(s)) // 2
            out[k] = f"{sec // 60}:{sec % 60:02d}"
        elif isinstance(v, (int, float)):
            out[k] = int(v) // 2
        else:
            out[k] = v
    return out


def _live(final: dict, upto: int, half_last: bool) -> dict:
    """Ответ API во время боя: раунды 1..upto (последний — наполовину), без результата."""
    lf = copy.deepcopy(final)
    lf["Status"] = "Live"
    lf["Result"] = {}
    for f in lf["Fighters"]:
        f["Outcome"] = {}
    for side in lf["RoundStats"]:
        rounds = [r for r in side["Rounds"] if r["RoundNumber"] <= upto]
        if half_last and rounds:
            rounds[-1] = _half(rounds[-1])
        side["Rounds"] = rounds
    lf["FightStats"] = [_sum_rounds(side["Rounds"], side["FighterId"]) for side in lf["RoundStats"]]
    return lf


def snapshots(final: dict) -> list[tuple[dict, int | None]]:
    """[(ответ fight API, номер идущего раунда)]: середина R1, конец R1, середина R2, …, затем итог."""
    rounds = max((len(s.get("Rounds", [])) for s in final.get("RoundStats", [])), default=0)
    result = []
    for num in range(1, rounds + 1):
        result.append((_live(final, num, half_last=True), num))
        if num < rounds:
            result.append((_live(final, num, half_last=False), num))
    result.append((final, None))
    return result


def fake_event(event: dict, fight_id: int, live: dict, live_round: int | None) -> dict:
    """Ответ event API, в котором идёт только этот бой (остальные — «не начались»)."""
    ev = copy.deepcopy(event)
    ev["Status"] = live["Status"]
    ev["LiveFightId"] = fight_id if live["Status"] != "Final" else None
    ev["LiveRoundNumber"] = live_round
    ev["FightCard"] = [{**f, "Status": live["Status"] if f["FightId"] == fight_id else "Canceled"}
                       for f in ev["FightCard"]]
    return ev
