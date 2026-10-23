"""
HTML карточки боя 1080×1350 по скиллу social-canvas (стиль Technical):
фон #09090b с точечной сеткой и волосяной рамкой, «стеклянные» панели, острые углы, Geist / Geist Mono,
отступы по сетке 4/8px, три зоны (шапка · flex:1 основное · низ без подписи — решение пользователя).
Цвет = смысл, один на значение: красный/синий — только углы; янтарный — «идёт бой»; изумрудный — «итог/победа».
Красный и синий проверены tools/validate_palette.py (порт валидатора dataviz).
"""
import base64
import os
import re
from html import escape

from fight import FightView

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
W, H = 1080, 1350


_FONT_CSS: str | None = None


def _font_css() -> str:
    """@font-face из assets/fonts, шрифты встроены как data: URI — страница из set_content не может
    читать file://, а сеть в момент рендера не нужна. Собирается один раз за запуск."""
    global _FONT_CSS
    if _FONT_CSS is None:
        fonts_dir = os.path.join(ASSETS, "fonts")
        with open(os.path.join(fonts_dir, "fonts.css"), encoding="utf-8") as f:
            css = f.read()

        def inline(m):
            with open(os.path.join(fonts_dir, m.group(1)), "rb") as ff:
                return f"url(data:font/woff2;base64,{base64.b64encode(ff.read()).decode()})"
        _FONT_CSS = re.sub(r"url\(([\w.-]+\.woff2)\)", inline, css)
    return _FONT_CSS


def _img(photo: bytes | None) -> str:
    if not photo:
        return ""
    kind = "png" if photo[:8] == b"\x89PNG\r\n\x1a\n" else "jpeg"
    return f"data:image/{kind};base64,{base64.b64encode(photo).decode()}"


STYLE = """
:root {
  --bg: #09090b; --text: #fafafa; --quiet: #a1a1aa; --muted: #71717a; --line: #27272a;
  --glass-bg: rgba(17,17,19,0.55); --glass-border: rgba(255,255,255,0.12); --glass-blur: 18px;
  --red: #e66767; --blue: #3987e5; --live: #f59e0b; --done: #10b981;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  width: 1080px; height: 1350px; overflow: hidden;
  background-color: var(--bg);
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='24' height='24'><rect x='0' y='0' width='2' height='2' fill='%23ffffff' fill-opacity='0.14'/></svg>");
  background-size: 24px 24px; background-position: 12px 12px;
  border: 1px solid rgba(255,255,255,0.14);
  color: var(--text); font-family: 'Geist', sans-serif;
}
.canvas { width: 100%; height: 100%; padding: 56px 64px 64px; display: flex; flex-direction: column; gap: 32px; }
.mono { font-family: 'Geist Mono', monospace; }
.glass { background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); border: 1px solid var(--glass-border); }

/* зона 1 — шапка */
.eyebrow { display: flex; justify-content: space-between; gap: 24px; font-family: 'Geist Mono', monospace;
  font-size: 18px; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--quiet); }
.eyebrow .event { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.eyebrow .meta { white-space: nowrap; }
.header { display: flex; flex-direction: column; gap: 24px; }
.fighters { display: grid; grid-template-columns: 1fr 56px 1fr; align-items: stretch; }
.vs { display: flex; align-items: center; justify-content: center; font-family: 'Geist Mono', monospace;
  font-size: 20px; font-weight: 700; color: var(--muted); }
.fighter { display: flex; gap: 20px; padding: 20px; align-items: center; border-top-width: 4px; }
.fighter.red { border-top-color: var(--red); }
.fighter.blue { border-top-color: var(--blue); flex-direction: row-reverse; text-align: right; }
.photo { width: 112px; height: 112px; flex: none; background-color: #18181b; background-repeat: no-repeat;
  background-size: 150% auto; background-position: 50% 0; display: flex; align-items: center; justify-content: center;
  font-size: 36px; font-weight: 700; color: var(--quiet); }
.who { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.blue .who { align-items: flex-end; }
.name { font-size: 32px; font-weight: 700; line-height: 1.1; }
.corner { display: flex; align-items: center; gap: 8px; font-family: 'Geist Mono', monospace; font-size: 16px;
  font-weight: 500; letter-spacing: 0.08em; color: var(--quiet); }
.swatch { width: 12px; height: 12px; flex: none; }
.swatch.red { background: var(--red); } .swatch.blue { background: var(--blue); }
.record { font-family: 'Geist Mono', monospace; font-size: 18px; color: var(--quiet); }
.win { margin-top: 4px; padding: 4px 12px; border: 2px solid var(--done); font-family: 'Geist Mono', monospace;
  font-size: 16px; font-weight: 700; letter-spacing: 0.12em; color: var(--text); }
.status { display: flex; align-items: center; gap: 24px; }
.state { display: flex; align-items: center; gap: 14px; font-size: 40px; font-weight: 800; letter-spacing: -0.01em; white-space: nowrap; }
.state .dot { width: 16px; height: 16px; border-radius: 50%; background: var(--live); }
.state.live { color: var(--live); } .state.done { color: var(--done); }
.result { font-size: 28px; font-weight: 500; color: var(--text); padding-left: 24px; border-left: 1px solid var(--line);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

/* зона 2 — основное */
.main { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 24px; }
.panel { padding: 24px 32px; display: flex; flex-direction: column; }
.panel-title { display: flex; justify-content: space-between; align-items: center; padding-bottom: 14px;
  border-bottom: 1px solid var(--line); font-family: 'Geist Mono', monospace; font-size: 18px; font-weight: 700;
  letter-spacing: 0.14em; text-transform: uppercase; }
.panel-title .accent { color: var(--focus); }
.legend { display: flex; gap: 20px; font-weight: 500; letter-spacing: 0.06em; text-transform: none; color: var(--quiet); font-size: 16px; }
.legend span { display: flex; align-items: center; gap: 8px; }
.stats { flex: 1; display: flex; flex-direction: column; justify-content: space-between; padding-top: 12px; }
.stat { display: flex; flex-direction: column; gap: 8px; }
.stat-top { display: grid; grid-template-columns: 1fr auto 1fr; align-items: baseline; }
.v { font-size: 26px; font-weight: 700; font-variant-numeric: tabular-nums; }
.v.r { text-align: right; }
.label { font-size: 20px; color: var(--quiet); text-align: center; padding: 0 16px; }
.bar { position: relative; display: grid; grid-template-columns: 1fr 2px 1fr; height: 8px; }
.bar::before { content: ""; position: absolute; left: 0; right: 0; top: 4px; height: 1px; background: var(--line); }
.bar .l { position: relative; justify-self: end; height: 8px; background: var(--red); }
.bar .rt { position: relative; justify-self: start; height: 8px; background: var(--blue); }
.name.long { font-size: 26px; }
.name.xlong { font-size: 23px; }
.name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }

table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th { font-family: 'Geist Mono', monospace; font-size: 15px; font-weight: 500; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--quiet); text-align: center; padding: 14px 8px 10px; }
th:first-child, td:first-child { text-align: left; width: 88px; }
td { font-size: 24px; font-weight: 700; text-align: center; padding: 10px 8px; border-top: 1px solid var(--line); }
td:first-child { font-family: 'Geist Mono', monospace; font-size: 20px; color: var(--quiet); padding-left: 12px; }
tr.current td { background: rgba(245,158,11,0.08); }
tr.current td:first-child { color: var(--live); box-shadow: inset 4px 0 0 var(--live); }
.sep { color: var(--muted); font-weight: 400; padding: 0 6px; }

.judges { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; padding-top: 16px; }
.judge { display: flex; flex-direction: column; gap: 6px; }
.judge .jn { font-size: 18px; color: var(--quiet); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.judge .js { font-size: 32px; font-weight: 700; font-variant-numeric: tabular-nums; }

/* плотный режим — 4–5 раундов и судьи в итоге */
.dense .canvas { gap: 24px; }
.dense .main { gap: 16px; }
.dense .panel { padding: 18px 28px; }
.dense td { padding: 7px 8px; font-size: 22px; }
.dense th { padding: 10px 8px 6px; }
.dense .judge .js { font-size: 28px; }
/* в плотном режиме строка статистики — в одну линию: значение · полоска · подпись · полоска · значение */
.dense .stats { padding-top: 6px; }
.dense .stat { display: grid; grid-template-columns: 170px 1fr 196px 1fr 170px; align-items: center; gap: 0; }
.dense .stat-top { display: contents; }
.dense .stat-top .v { grid-row: 1; font-size: 22px; }
.dense .stat-top .v:first-child { grid-column: 1; }
.dense .stat-top .label { grid-column: 3; grid-row: 1; font-size: 17px; padding: 0 12px; }
.dense .stat-top .v.r { grid-column: 5; }
.dense .bar { display: contents; }
.dense .bar::before { display: none; }
.dense .bar .l { grid-column: 2; grid-row: 1; }
.dense .bar > div:nth-child(2) { display: none; }
.dense .bar .rt { grid-column: 4; grid-row: 1; }
"""


def _photo(photo: bytes | None, name: str) -> str:
    uri = _img(photo)
    if uri:
        return f'<div class="photo" style="background-image:url({uri})"></div>'
    initials = "".join(p[0] for p in name.split() if p)[:2].upper()
    return f'<div class="photo">{escape(initials)}</div>'


def _fighter(corner, photo, side: str) -> str:
    label = "КРАСНЫЙ УГОЛ" if side == "red" else "СИНИЙ УГОЛ"
    win = '<div class="win">ПОБЕДА</div>' if corner.outcome == "Win" else ""
    long = " xlong" if len(corner.name) > 19 else " long" if len(corner.name) > 15 else ""
    return (f'<div class="fighter glass {side}">{_photo(photo, corner.name)}<div class="who">'
            f'<div class="name{long}">{escape(corner.name)}</div>'
            f'<div class="corner"><span class="swatch {side}"></span>{label}</div>'
            f'<div class="record">{escape(corner.record)}</div>{win}</div></div>')


def _stats(view: FightView) -> str:
    rows = []
    for label, red, blue, share in view.focus:
        if share is None:                                  # у обоих ноль — полосок нет
            lw = rw = 0
        else:
            biggest = max(share, 1 - share)
            lw, rw = round(100 * share / biggest, 1), round(100 * (1 - share) / biggest, 1)
        rows.append(f'<div class="stat"><div class="stat-top"><div class="v">{escape(red)}</div>'
                    f'<div class="label">{escape(label)}</div><div class="v r">{escape(blue)}</div></div>'
                    f'<div class="bar"><div class="l" style="width:{lw}%"></div><div></div>'
                    f'<div class="rt" style="width:{rw}%"></div></div></div>')
    return "".join(rows)


def _rounds(view: FightView) -> str:
    head = "".join(f"<th>{escape(label)}</th>" for label, _, _ in view.rounds[0][1])
    body = []
    for num, cells in view.rounds:
        cls = ' class="current"' if not view.finished and num == view.rounds[-1][0] else ""
        tds = "".join(f'<td>{escape(r)}<span class="sep">:</span>{escape(b)}</td>' for _, r, b in cells)
        body.append(f"<tr{cls}><td>R{num}</td>{tds}</tr>")
    return f"<table><tr><th>РАУНД</th>{head}</tr>{''.join(body)}</table>"


def build_html(view: FightView, event_name: str, photos=(None, None)) -> str:
    rounds_word = "РАУНДА" if view.rounds_scheduled in (2, 3, 4) else "РАУНДОВ"
    if view.finished:
        state = '<div class="state done">ИТОГ</div>'
        result = f'<div class="result">{escape(view.result)}</div>' if view.result else ""
        focus_color = "var(--done)"
    else:
        rnd = f" · РАУНД {view.live_round} ИЗ {view.rounds_scheduled}" if view.live_round else ""
        state = f'<div class="state live"><span class="dot"></span>LIVE{rnd}</div>'
        result = ""
        focus_color = "var(--live)"
    dense = len(view.rounds) >= 4 or (view.judges and len(view.rounds) >= 3)
    # Легенда углов одна — карточки бойцов (■ КРАСНЫЙ УГОЛ / ■ СИНИЙ УГОЛ); в панелях не повторяем (правило 83)
    rounds = (f'<div class="panel glass"><div class="panel-title"><span>ПО РАУНДАМ</span></div>'
              f'{_rounds(view)}</div>') if view.rounds else ""
    judges = ""
    if view.judges:
        cells = "".join(f'<div class="judge"><div class="jn">{escape(n)}</div>'
                        f'<div class="js">{escape(s.replace("-", " : "))}</div></div>' for n, s, _ in view.judges[:3])
        judges = (f'<div class="panel glass"><div class="panel-title"><span>СУДЬИ</span></div>'
                  f'<div class="judges">{cells}</div></div>')
    return f"""<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><style>{_font_css()}{STYLE}</style></head>
<body class="{'dense' if dense else ''}" style="--focus:{focus_color}"><div class="canvas">
  <div class="header">
    <div class="eyebrow"><span class="event">{escape(event_name)}</span>
      <span class="meta">{escape(view.weight_class)} · {view.rounds_scheduled} {rounds_word}</span></div>
    <div class="fighters">{_fighter(view.red, photos[0], "red")}<div class="vs">VS</div>{_fighter(view.blue, photos[1], "blue")}</div>
    <div class="status">{state}{result}</div>
  </div>
  <div class="main">
    <div class="panel glass" style="flex:1;min-height:0"><div class="panel-title"><span class="accent">{escape(view.focus_title)}</span></div>
      <div class="stats">{_stats(view)}</div></div>
    {rounds}{judges}
  </div>
</div></body></html>"""
