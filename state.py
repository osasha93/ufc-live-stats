"""Файлы состояния в репозитории и их сохранение (в GitHub Actions — коммит и push сразу)."""
import json
import os
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "live_state.json")      # турнир, сообщения по боям, завершённые турниры
SCHEDULE_FILE = os.path.join(HERE, "schedule.json")     # пишет tapology-bot: турниры UFC недели

IN_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        print(f"⚠️ Не читается {os.path.basename(path)} ({e}), начинаю с пустого.")
        return default


def save_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def git_push(message: str, files: tuple[str, ...] = (STATE_FILE,)) -> None:
    """В Actions — закоммитить и запушить состояние (следующий job продолжит с него). Локально — ничего."""
    if not IN_ACTIONS:
        return
    existing = [p for p in files if os.path.exists(p)]
    subprocess.run(["git", "add", *existing], check=True)
    if subprocess.run(["git", "diff", "--staged", "--quiet"]).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", message], check=True)
    for _ in range(3):   # пока шёл цикл, tapology-bot мог обновить schedule.json
        if subprocess.run(["git", "pull", "-q", "--rebase"]).returncode == 0 and \
                subprocess.run(["git", "push", "-q"]).returncode == 0:
            return
        time.sleep(10)
    print("⚠️ Не удалось запушить состояние — повторю при следующем сохранении.")
