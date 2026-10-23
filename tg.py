"""Telegram: картинка боя — новым сообщением, дальше редактируем её же (editMessageMedia)."""
import json
import os
import time

import requests

NOT_MODIFIED = "message is not modified"
GONE = ("message to edit not found", "message can't be edited", "MESSAGE_ID_INVALID")


class TelegramSender:
    def __init__(self, token: str, chat_id: str, thread_id: str | None = None):
        self.api = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.thread_id = int(thread_id) if thread_id else None
        self.session = requests.Session()

    def _call(self, method: str, data: dict, photo: bytes, attempts: int = 4) -> dict | None:
        """Ответ Telegram при успехе; {"gone": True}, если сообщения больше нет; None — не вышло."""
        for attempt in range(1, attempts + 1):
            try:
                resp = self.session.post(f"{self.api}/{method}", data=data,
                                         files={"photo": ("fight.png", photo, "image/png")}, timeout=60)
                body = resp.json()
            except (requests.RequestException, ValueError) as e:
                print(f"⚠️ Telegram {method}, попытка {attempt}: {e}")
                time.sleep(3 * attempt)
                continue
            if body.get("ok"):
                return body
            desc = body.get("description") or ""
            if NOT_MODIFIED in desc:
                return body
            if any(g in desc for g in GONE):
                return {"gone": True}
            retry_after = (body.get("parameters") or {}).get("retry_after")
            print(f"⚠️ Telegram {method}, попытка {attempt}: {desc}")
            if retry_after:
                time.sleep(retry_after + 1)
            elif resp.status_code < 500:
                return None
            else:
                time.sleep(3 * attempt)
        return None

    def send(self, photo: bytes, caption: str, button: tuple[str, str] | None) -> int | None:
        """Новое сообщение с картинкой → message_id."""
        data = {"chat_id": self.chat_id, "caption": caption}
        if self.thread_id:
            data["message_thread_id"] = self.thread_id
        if button:
            data["reply_markup"] = _keyboard(button)
        body = self._call("sendPhoto", data, photo)
        return body["result"]["message_id"] if body and body.get("result") else None

    def edit(self, message_id: int, photo: bytes, caption: str, button: tuple[str, str] | None) -> bool | None:
        """True — обновлено, None — сообщения больше нет (надо прислать заново), False — ошибка."""
        data = {"chat_id": self.chat_id, "message_id": message_id,
                "media": json.dumps({"type": "photo", "media": "attach://photo", "caption": caption})}
        if button:
            data["reply_markup"] = _keyboard(button)
        body = self._call("editMessageMedia", data, photo)
        if body and body.get("gone"):
            return None
        return bool(body)


class DryRunSender:
    """Вместо Telegram — картинки в папку out/ (каждый кадр отдельным файлом: msg1_01.png, msg1_02.png…)."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir
        self.next_id = 1
        self.frames: dict[int, int] = {}

    def _save(self, message_id: int, photo: bytes, caption: str, verb: str) -> None:
        os.makedirs(self.out_dir, exist_ok=True)
        self.frames[message_id] = self.frames.get(message_id, 0) + 1
        path = os.path.join(self.out_dir, f"msg{message_id}_{self.frames[message_id]:02d}.png")
        with open(path, "wb") as f:
            f.write(photo)
        print(f"[{verb} {message_id}] {caption.splitlines()[0]} → {path}")

    def send(self, photo, caption, button):
        message_id, self.next_id = self.next_id, self.next_id + 1
        self._save(message_id, photo, caption, "новое")
        return message_id

    def edit(self, message_id, photo, caption, button):
        self._save(message_id, photo, caption, "правка")
        return True


def _keyboard(button: tuple[str, str]) -> str:
    text, url = button
    return json.dumps({"inline_keyboard": [[{"text": text, "url": url}]]})
