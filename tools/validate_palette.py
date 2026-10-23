"""Проверка цветов карточки по скиллу dataviz (Python-двойник scripts/validate_palette.js: те же формулы и пороги).
Node на этом ПК нет, поэтому проверки перенесены сюда.

  python tools/validate_palette.py "#e66767,#3987e5" --surface "#1a1a19"
"""
import math
import sys

BAND_DARK = (0.48, 0.67)          # OKLCH L для тёмной темы
CHROMA_FLOOR = 0.10
CVD_TARGET, CVD_FLOOR, NORMAL_FLOOR, CONTRAST_MIN = 8.0, 6.0, 15.0, 3.0
MACHADO = {   # Machado, Oliveira & Fernandes (2009), severity 1.0, linear RGB
    "protan": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    "deutan": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    "tritan": [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]],
}


def lin(h):
    h = h.strip().lstrip("#")
    return [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
            for c in (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))]


def oklab_lin(rgb):
    r, g, b = rgb
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def simulate(h, kind):
    r, g, b = lin(h)
    return [max(0.0, min(1.0, row[0] * r + row[1] * g + row[2] * b)) for row in MACHADO[kind]]


def delta_e(a, b, kind=None):
    la = oklab_lin(simulate(a, kind) if kind else lin(a))
    lb = oklab_lin(simulate(b, kind) if kind else lin(b))
    return 100 * math.dist(la, lb)


def contrast(a, b):
    lum = lambda h: sum(w * c for w, c in zip((0.2126, 0.7152, 0.0722), lin(h)))  # noqa: E731
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def validate(palette, surface):
    ok = True
    for c in palette:
        L, a, b = oklab_lin(lin(c))
        C = math.hypot(a, b)
        band = BAND_DARK[0] <= L <= BAND_DARK[1]
        ok &= band and C >= CHROMA_FLOOR
        print(f"  {c}: L={L:.3f} {'PASS' if band else 'FAIL'} band, C={C:.3f} {'PASS' if C >= CHROMA_FLOOR else 'FAIL'} chroma, "
              f"contrast {contrast(c, surface):.2f}:1 {'PASS' if contrast(c, surface) >= CONTRAST_MIN else 'WARN'}")
    pairs = list(zip(palette, palette[1:]))
    cvd = min(delta_e(a, b, k) for a, b in pairs for k in ("protan", "deutan"))
    normal = min(delta_e(a, b) for a, b in pairs)
    tri = min(delta_e(a, b, "tritan") for a, b in pairs)
    cvd_state = "PASS" if cvd >= CVD_TARGET else "WARN" if cvd >= CVD_FLOOR else "FAIL"
    ok &= cvd_state != "FAIL" and normal >= NORMAL_FLOOR
    print(f"  CVD separation ΔE {cvd:.1f} {cvd_state} (tritan {tri:.1f}); normal-vision ΔE {normal:.1f} "
          f"{'PASS' if normal >= NORMAL_FLOOR else 'FAIL'}")
    print("  →", "ALL CHECKS PASS" if ok else "FAILED")
    return ok


if __name__ == "__main__":
    surface = sys.argv[sys.argv.index("--surface") + 1] if "--surface" in sys.argv else "#1a1a19"
    sys.exit(0 if validate([c for c in sys.argv[1].split(",") if c.strip()], surface) else 1)
