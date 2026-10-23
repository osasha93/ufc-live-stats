# UFC LIVE — контекст для Claude Code

Папка — рабочая копия публичного репозитория `osasha93/ufc-live-stats` (ветка main, минуты Actions бесплатны).
Во время турнира UFC бот шлёт в Telegram на каждый бой ОДНУ карточку и дальше только правит её:
пока бой идёт — главный блок «РАУНД N» (цифры текущего раунда) + таблица раундов, обновление каждые 5 с;
после боя — «СТАТИСТИКА БОЯ» (весь бой), метод/раунд/время и оценки судей; между боями проверка каждые 30 с.
Работает в GitHub Actions (`.github/workflows/live.yml`).
Карточка 1080×1350 — HTML по скиллу social-canvas (`~/.claude/skills/social-canvas`, стиль Technical: #09090b +
точечная сетка, стеклянные панели, острые углы, Geist/Geist Mono из `assets/fonts`, встроены data: URI) →
PNG через Playwright/Chromium (`card.py` + `render.py`, браузер один на весь цикл, ~0.2 с на кадр).
Бренд Fractal AI из скилла НЕ используется; подписи внизу нет (решение пользователя).
Цвет = одно значение: красный/синий — углы (проверены `tools/validate_palette.py`, порт валидатора dataviz),
янтарный — идёт бой, изумрудный — итог/победа. Chromium не поднялся → запасная карточка `render_pillow.py`
в том же дизайне (TTF Geist из `assets/fonts`, `--pillow` — посмотреть её вручную).
Таблица раундов: Все удары · Знач. удары · Тейкдауны · Нокдауны · Контроль (как есть из API).
Проверка рендера на GitHub: Actions → Live Fight Stats → Run workflow, `replay_fight` = 13046 →
повтор без Telegram, кадры в Artifacts «render-check» (part2 и цикл турнира при этом не запускаются).
ОС: Windows, UTC+7. Python: `.venv\Scripts\python.exe`. Git: `C:\Users\Александр\AppData\Local\hermes\tools\git-2.53.0+3-win32-x64\cmd\git.exe`.
Коммитить и пушить только по просьбе пользователя. Actions сам коммитит live_state.json — перед push делать pull --rebase.

## Откуда данные (ufc.com рисует статистику из того же API)
- `https://d29dxerjsp82wz.cloudfront.net/api/v3/event/live/<ID турнира>.json` — кард, статусы боёв,
  `LiveFightId` / `LiveRoundNumber` (какой бой и раунд идут).
- `…/fight/live/<ID боя>.json` — FightStats (итог), RoundStats (по раундам), Result (метод, FightScores судей).
- Адрес CloudFront при 403/ошибке соединения берётся заново с главной ufc.com (`ufc_api.refresh_api`).
- Страница боя на ufc.com: `https://www.ufc.com/matchup/<ID турнира>/<ID боя>/post` — оттуда фото бойцов и кнопка под картинкой.

## Как определяется турнир (ничего не вводится руками)
1. `schedule.json` + cron в live.yml пишет tapology-bot (`utils/ufc_schedule.py`, боевой запуск по понедельникам или
   `main.py --schedule-only`); турнир в UFC API ищется по времени старта (`ufc_api.find_event_id`).
2. Иначе — `ufc.com/events` → первая страница турнира → тикер `data-fmid` = ID турнира (`discover_from_ufc_com`).
- Окно: [старт−30 мин, старт+8 ч]; job — до 5 ч 40 мин (идущий бой дотягивает ещё до 12 мин), part2 продолжает.
- Стоп: турнир Final и итог каждого боя отправлен (`live_state.json`: fights[турнир][бой] = msg/digest/final, done).

## Секреты
- `--target test` (по умолчанию) — тестовый бот из `H:\СКРИПТЫ\tapology-bot\config\secret.py`;
  `--target prod` — `secret.Py` этой папки (в .gitignore). В Actions — секреты репозитория `TELEGRAM_*`.
- Токен GitHub — в `H:\СКРИПТЫ\ufc-scorecards-bot\secret.Py`. Значения не выводить.
- `H:\СКРИПТЫ\UFC live\app.Py` (ручной dispatch live.yml каждые 30 с) больше не нужен — не запускать.

## Модули
`ufc_api.py` (API, определение турнира, фото) · `fight.py` (ответ API → FightView, подпись, digest) ·
`card.py` (HTML карточки) · `render.py` (Playwright → PNG, фолбэк) · `render_pillow.py` (запасной рисунок) · `tg.py` (sendPhoto/editMessageMedia, DryRunSender → out/) ·
`state.py` (json, git push) · `replay.py` (повтор прошедшего боя по раундам) · `main.py` (Tracker, цикл, CLI).

## Как проверять
```
.venv\Scripts\python.exe tests\test_offline.py            # офлайн: определение турнира, разбор, картинка, «эфир», 2 job
.venv\Scripts\python.exe tools\preview.py --photos         # картинки по fixtures в out/
.venv\Scripts\python.exe tools\save_fixtures.py            # обновить tests/fixtures (турнир 17.10, ID 1332)
.venv\Scripts\python.exe tools\fetch_fonts.py              # заново скачать Geist в assets/fonts
.venv\Scripts\python.exe -m playwright install chromium    # Chromium для рендера (один раз на ПК)
.venv\Scripts\python.exe main.py --find                    # какой турнир определён сейчас
.venv\Scripts\python.exe main.py --replay 13046            # повтор боя «как в эфире» в тестовую группу
.venv\Scripts\python.exe main.py --auto --dry-run          # как в Actions, картинки в out/
```
