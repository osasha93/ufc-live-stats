"""Нарисовать картинки по fixtures в out/ (посмотреть вид без Telegram).
  python tools/preview.py            # итог KO и решения + «живой» вариант на середине 2-го раунда
  python tools/preview.py --photos   # с фото бойцов с ufc.com (нужна сеть)"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import fight  # noqa: E402
import render  # noqa: E402
import replay  # noqa: E402
import ufc_api  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
OUT = os.path.join(ROOT, "out")
os.makedirs(OUT, exist_ok=True)
event = json.load(open(os.path.join(FIX, "event_1332.json"), encoding="utf-8"))

for fid in (13002, 13046):
    lf = json.load(open(os.path.join(FIX, f"fight_{fid}.json"), encoding="utf-8"))
    photos = ufc_api.fighter_photos(1332, fid) if "--photos" in sys.argv else (None, None)
    mid_r2, live_round = replay.snapshots(lf)[2]          # середина 2-го раунда, как в эфире
    for name, data, rnd in ((f"{fid}_final", lf, None), (f"{fid}_live_r2", mid_r2, live_round)):
        view = fight.parse_fight(data, live_round=rnd)
        path = os.path.join(OUT, f"{name}.png")
        with open(path, "wb") as f:
            f.write(render.render(view, event["Name"], photos))
        print(path, "|", fight.caption(view, event["Name"]).replace("\n", " | "))
