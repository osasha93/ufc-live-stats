"""Скачать шрифты Geist / Geist Mono (лицензия OFL) в assets/fonts — карточка рендерится без сети.
Берёт woff2 из Google Fonts для подмножеств из SUBSETS и пишет assets/fonts/fonts.css."""
import os
import re

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "fonts")
CSS_URL = ("https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700;800"
           "&family=Geist+Mono:wght@400;500;700&display=swap")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"}
SUBSETS = ("cyrillic", "latin", "latin-ext")    # latin-ext — диакритика в именах (Jiří Procházka)

css = requests.get(CSS_URL, headers=UA, timeout=30).text
os.makedirs(OUT, exist_ok=True)
blocks = re.findall(r"/\*\s*([\w-]+)\s*\*/\s*(@font-face\s*{.*?})", css, re.S)
print("subsets in Google CSS:", sorted({s for s, _ in blocks}))
local_css = []
for subset, block in blocks:
    if subset not in SUBSETS:
        continue
    family = re.search(r"font-family:\s*'([^']+)'", block).group(1)
    weight = re.search(r"font-weight:\s*(\d+)", block).group(1)
    url = re.search(r"url\((https://[^)]+\.woff2)\)", block).group(1)
    name = f"{family.replace(' ', '')}-{weight}-{subset}.woff2"
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(requests.get(url, timeout=60).content)
    local_css.append(block.replace(url, name))
    print(f"✅ {name}")
with open(os.path.join(OUT, "fonts.css"), "w", encoding="utf-8") as f:
    f.write("/* Geist, Geist Mono — SIL Open Font License 1.1 (github.com/vercel/geist-font) */\n" + "\n".join(local_css) + "\n")

# Полные TTF (латиница + кириллица в одном файле) — для запасной карточки Pillow (render_pillow.py):
# Pillow не умеет подставлять глифы из другого файла, а woff2 у Google разбиты по алфавитам.
TTF_URL = ("https://fonts.googleapis.com/css2?family=Geist:wght@400;500;700;800"
           "&family=Geist+Mono:wght@500;700")
ttf_css = requests.get(TTF_URL, headers={"User-Agent": "Mozilla/4.0"}, timeout=30).text   # старый UA → целые .ttf
for block in re.findall(r"@font-face\s*{.*?}", ttf_css, re.S):
    family = re.search(r"font-family:\s*'([^']+)'", block).group(1).replace(" ", "")
    weight = re.search(r"font-weight:\s*(\d+)", block).group(1)
    url = re.search(r"url\((https://[^)]+\.ttf)\)", block).group(1)
    path = os.path.join(OUT, f"{family}-{weight}.ttf")
    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(requests.get(url, timeout=60).content)
    print(f"✅ {os.path.basename(path)}")
