"""
Запасная карточка (Pillow), если Chromium в Actions не поднялся: та же карточка, что card.py (social-canvas,
стиль Technical) — 1080×1350, #09090b + точечная сетка, стеклянные панели с острыми углами, Geist/Geist Mono (TTF
из assets/fonts), те же цвета и порядок блоков. Без браузера, только Pillow.
"""
import io
import os

from PIL import Image, ImageDraw, ImageFont

from fight import FightView

W, H = 1080, 1350
PAD_X, PAD_TOP, PAD_BOTTOM = 64, 56, 64
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

BG = (9, 9, 11)
TEXT = (250, 250, 250)
QUIET = (161, 161, 170)
MUTED = (113, 113, 122)
LINE = (39, 39, 42)
PANEL = (17, 17, 19, 140)            # rgba(17,17,19,0.55)
PANEL_BORDER = (255, 255, 255, 31)   # rgba(255,255,255,0.12)
RED = (230, 103, 103)
BLUE = (57, 135, 229)
LIVE = (245, 158, 11)
DONE = (16, 185, 129)
_fonts: dict = {}


def font(size: int, weight: int = 400, mono: bool = False):
    key = (size, weight, mono)
    if key not in _fonts:
        name = f"GeistMono-{700 if weight >= 600 else 500}.ttf" if mono else f"Geist-{weight}.ttf"
        path = os.path.join(FONTS, name)
        _fonts[key] = ImageFont.truetype(path, size) if os.path.exists(path) else ImageFont.load_default(size)
    return _fonts[key]


def _spaced(d, xy, text, f, fill, spacing: float, anchor="l"):
    """Текст с разрядкой (letter-spacing) — как .eyebrow/.panel-title в card.py. anchor: l / r."""
    widths = [d.textlength(ch, font=f) + spacing for ch in text]
    total = sum(widths) - spacing if widths else 0
    x = xy[0] - total if anchor == "r" else xy[0]
    for ch, w in zip(text, widths):
        d.text((x, xy[1]), ch, font=f, fill=fill)
        x += w
    return total


def _fit(d, text, f, max_w):
    if d.textlength(text, font=f) <= max_w:
        return text
    while text and d.textlength(text + "…", font=f) > max_w:
        text = text[:-1]
    return text + "…"


def _panel(layer, box, top_color=None):
    """Стеклянная панель: полупрозрачная заливка поверх сетки + волосяная рамка; острые углы."""
    ld = ImageDraw.Draw(layer)
    ld.rectangle(box, fill=PANEL, outline=PANEL_BORDER, width=1)
    if top_color:
        ld.rectangle((box[0], box[1], box[2], box[1] + 3), fill=top_color + (255,))


def _photo(photo: bytes | None, name: str, size: int = 112) -> Image.Image:
    """Как в card.py: снимок в полный рост, масштаб 150% по ширине, верх кадра — голова и плечи целиком."""
    tile = Image.new("RGB", (size, size), (24, 24, 27))
    if photo:
        try:
            img = Image.open(io.BytesIO(photo)).convert("RGBA")
            scale = size * 1.5 / img.width
            img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
            left = (img.width - size) // 2
            tile.paste(img.crop((left, 0, left + size, size)), (0, 0), img.crop((left, 0, left + size, size)))
            return tile
        except Exception:
            pass
    ImageDraw.Draw(tile).text((size // 2, size // 2), "".join(p[0] for p in name.split() if p)[:2].upper(),
                              font=font(36, 700), fill=QUIET, anchor="mm")
    return tile


def render(view: FightView, event_name: str, photos=(None, None)) -> bytes:
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    for y in range(12, H, 24):                         # точечная сетка 2×2 через 24px, белый 14%
        for x in range(12, W, 24):
            d.rectangle((x, y, x + 1, y + 1), fill=(44, 44, 46, 255))
    d.rectangle((0, 0, W - 1, H - 1), outline=(44, 44, 47, 255), width=1)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    left, right, cx = PAD_X, W - PAD_X, W // 2
    dense = len(view.rounds) >= 4 or (view.judges and len(view.rounds) >= 3)
    gap = 24 if dense else 32

    # --- шапка: строка турнира, бойцы, статус ---
    y = PAD_TOP
    rounds_word = "РАУНДА" if view.rounds_scheduled in (2, 3, 4) else "РАУНДОВ"
    meta = f"{view.weight_class} · {view.rounds_scheduled} {rounds_word}".upper()
    mw = _spaced(d, (right, y), meta, font(18, 500, True), QUIET, 2.2, "r")
    _spaced(d, (left, y), _fit(d, event_name.upper(), font(18, 500, True), right - left - mw - 80),
            font(18, 500, True), QUIET, 2.2)
    y += 22 + 24
    fh = 172 if any(c.outcome == "Win" for c in (view.red, view.blue)) else 156
    col_w = (right - left - 56) // 2
    cards = []
    for corner, photo, color, x0, side in ((view.red, photos[0], RED, left, "red"),
                                           (view.blue, photos[1], BLUE, right - col_w, "blue")):
        _panel(layer, (x0, y, x0 + col_w, y + fh), top_color=color)
        cards.append((corner, photo, color, x0, side))
    img.alpha_composite(layer)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for corner, photo, color, x0, side in cards:
        py = y + (fh - 112) // 2
        px = x0 + 20 if side == "red" else x0 + col_w - 20 - 112
        img.paste(_photo(photo, corner.name), (px, py))
        tx = px + 132 if side == "red" else px - 20
        anchor = "l" if side == "red" else "r"
        name_size = 23 if len(corner.name) > 19 else 26 if len(corner.name) > 15 else 32
        nf = font(name_size, 700)
        name = _fit(d, corner.name, nf, col_w - 112 - 60)
        lines_h = 36 + 8 + 20 + 8 + 22 + (44 if corner.outcome == "Win" else 0)
        ty = y + (fh - lines_h) // 2
        d.text((tx, ty + 18), name, font=nf, fill=TEXT, anchor=anchor + "m")
        label = "КРАСНЫЙ УГОЛ" if side == "red" else "СИНИЙ УГОЛ"
        lf = font(16, 500, True)
        lw = sum(d.textlength(ch, font=lf) + 1.3 for ch in label)
        sx = tx if side == "red" else tx - lw - 20
        d.rectangle((sx, ty + 48, sx + 11, ty + 59), fill=color)
        _spaced(d, (sx + 20, ty + 45), label, lf, QUIET, 1.3)
        d.text((tx, ty + 84), corner.record, font=font(18, 500, True), fill=QUIET, anchor=anchor + "m")
        if corner.outcome == "Win":
            wf = font(16, 700, True)
            ww = sum(d.textlength(ch, font=wf) + 1.9 for ch in "ПОБЕДА") + 24
            bx = tx if side == "red" else tx - ww
            d.rectangle((bx, ty + 104, bx + ww, ty + 136), outline=DONE, width=2)
            _spaced(d, (bx + 12, ty + 110), "ПОБЕДА", wf, TEXT, 1.9)
    d.text((cx, y + fh // 2), "VS", font=font(20, 700, True), fill=MUTED, anchor="mm")
    y += fh + 24

    sf = font(40, 800)
    if view.finished:
        d.text((left, y + 24), "ИТОГ", font=sf, fill=DONE, anchor="lm")
        if view.result:
            rx = left + d.textlength("ИТОГ", font=sf) + 24
            d.line((rx, y + 4, rx, y + 44), fill=LINE, width=1)
            d.text((rx + 24, y + 24), _fit(d, view.result, font(28, 500), right - rx - 24), font=font(28, 500),
                   fill=TEXT, anchor="lm")
    else:
        rnd = f" · РАУНД {view.live_round} ИЗ {view.rounds_scheduled}" if view.live_round else ""
        d.ellipse((left, y + 16, left + 16, y + 32), fill=LIVE)
        d.text((left + 30, y + 24), "LIVE" + rnd, font=sf, fill=LIVE, anchor="lm")
    y += 48 + gap

    # --- высоты нижних панелей (снизу вверх), главная панель забирает остаток (flex: 1) ---
    bottom = H - PAD_BOTTOM
    pad_y = 18 if dense else 24
    row_h = 40 if dense else 48
    judges_h = (pad_y * 2 + 32 + 16 + 70) if view.judges else 0
    rounds_h = (pad_y * 2 + 32 + 40 + row_h * len(view.rounds)) if view.rounds else 0
    panels_gap = 16 if dense else 24
    focus_bottom = bottom - (judges_h + panels_gap if judges_h else 0) - (rounds_h + panels_gap if rounds_h else 0)
    boxes = [("focus", (left, y, right, focus_bottom))]
    yy = focus_bottom + panels_gap
    if rounds_h:
        boxes.append(("rounds", (left, yy, right, yy + rounds_h)))
        yy += rounds_h + panels_gap
    if judges_h:
        boxes.append(("judges", (left, yy, right, yy + judges_h)))
    for _, box in boxes:
        _panel(layer, box)
    img.alpha_composite(layer)
    d = ImageDraw.Draw(img)
    tf = font(18, 700, True)
    px0, px1 = left + (28 if dense else 32), right - (28 if dense else 32)

    def title(box, text, color=TEXT):
        _spaced(d, (px0, box[1] + pad_y), text, tf, color, 2.5)
        d.line((px0, box[1] + pad_y + 32, px1, box[1] + pad_y + 32), fill=LINE, width=1)
        return box[1] + pad_y + 32

    for kind, box in boxes:
        if kind == "focus":
            top = title(box, view.focus_title.upper(), DONE if view.finished else LIVE)
            rows = view.focus
            area_top, area_bottom = top + (6 if dense else 12), box[3] - pad_y
            step = (area_bottom - area_top) / len(rows)
            half = (px1 - px0) // 2
            for i, (label, red, blue, share) in enumerate(rows):
                both_zero = red in ("0", "0/0", "0:00") and blue in ("0", "0/0", "0:00")
                biggest = max(share, 1 - share) or 1
                ry = area_top + step * i
                if dense:                                   # одна линия: значение · полоска · подпись · полоска · значение
                    mid = ry + step / 2
                    d.text((px0, mid), red, font=font(22, 700), fill=TEXT, anchor="lm")
                    d.text((px1, mid), blue, font=font(22, 700), fill=TEXT, anchor="rm")
                    d.text((cx, mid), label, font=font(17), fill=QUIET, anchor="mm")
                    bl, br = px0 + 170, cx - 98                # колонки как в card.py: 170 · 1fr · 196 · 1fr · 170
                    span = br - bl
                    if not both_zero:
                        lw = int(span * share / biggest)
                        rw = int(span * (1 - share) / biggest)
                        if lw:
                            d.rectangle((br - lw, mid - 4, br, mid + 3), fill=RED)
                        if rw:
                            d.rectangle((cx + 98, mid - 4, cx + 98 + rw, mid + 3), fill=BLUE)
                else:                                       # две строки: цифры и подпись, под ними полоска от центра
                    d.text((px0, ry + 6), red, font=font(26, 700), fill=TEXT)
                    d.text((px1, ry + 6), blue, font=font(26, 700), fill=TEXT, anchor="ra")
                    d.text((cx, ry + 10), label, font=font(20), fill=QUIET, anchor="ma")
                    by = ry + 46
                    d.line((px0, by + 4, px1, by + 4), fill=LINE, width=1)
                    if not both_zero:
                        lw = int(half * share / biggest)
                        rw = int(half * (1 - share) / biggest)
                        if lw:
                            d.rectangle((cx - 1 - lw, by, cx - 1, by + 7), fill=RED)
                        if rw:
                            d.rectangle((cx + 1, by, cx + 1 + rw, by + 7), fill=BLUE)
        elif kind == "rounds":
            top = title(box, "ПО РАУНДАМ")
            labels = [label for label, _, _ in view.rounds[0][1]]
            c0 = 88
            cw = (px1 - px0 - c0) / len(labels)
            hf = font(15, 500, True)
            hy = top + 14
            _spaced(d, (px0 + 8, hy), "РАУНД", hf, QUIET, 1.2)
            for i, label in enumerate(labels):
                text = label.upper()
                tw = sum(d.textlength(ch, font=hf) + 1.2 for ch in text)
                _spaced(d, (px0 + c0 + cw * i + cw / 2 - tw / 2, hy), text, hf, QUIET, 1.2)
            ry = top + 40
            for num, cells in view.rounds:
                current = not view.finished and num == view.rounds[-1][0]
                if current:
                    d.rectangle((px0, ry, px1, ry + row_h), fill=(30, 24, 14))
                    d.rectangle((px0, ry, px0 + 3, ry + row_h), fill=LIVE)
                d.line((px0, ry, px1, ry), fill=LINE, width=1)
                mid = ry + row_h / 2
                d.text((px0 + 12, mid), f"R{num}", font=font(20, 500, True), fill=LIVE if current else QUIET,
                       anchor="lm")
                vf = font(22 if dense else 24, 700)
                for i, (_, r, b) in enumerate(cells):
                    ccx = px0 + c0 + cw * i + cw / 2
                    d.text((ccx - 10, mid), r, font=vf, fill=TEXT, anchor="rm")
                    d.text((ccx, mid), ":", font=font(20), fill=MUTED, anchor="mm")
                    d.text((ccx + 10, mid), b, font=vf, fill=TEXT, anchor="lm")
                ry += row_h
        else:
            top = title(box, "СУДЬИ")
            jw = (px1 - px0 - 32) / 3
            for i, (name, score, _) in enumerate(view.judges[:3]):
                jx = px0 + (jw + 16) * i
                d.text((jx, top + 16), _fit(d, name, font(18), jw), font=font(18), fill=QUIET)
                d.text((jx, top + 44), score.replace("-", " : "), font=font(28 if dense else 32, 700), fill=TEXT)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
