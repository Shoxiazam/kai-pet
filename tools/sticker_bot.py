"""Бот стикеров Кая для Telegram — без библиотек, только Bot API через urllib.

1. В Telegram у @BotFather: /newbot → токен. Положите его в stickers/bot_token.txt (в git не попадает)
   или в переменную KAI_BOT_TOKEN.
2. python tools/sticker_bot.py create — напишите своему боту /start: он загрузит набор stickers/pack
   (python tools/make_stickers.py) и пришлёт ссылку t.me/addstickers/… — её можно раздавать всем.
3. python tools/sticker_bot.py serve — бот работает, пока запущен: /start — ссылка на набор,
   /my fox ginger bow scarf — личный набор с Каем в таком наряде (рисуется около минуты).
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "stickers" / "pack"
TOKEN_FILE = ROOT / "stickers" / "bot_token.txt"
API = os.environ.get("KAI_TG_API", "https://api.telegram.org")
PERSONAL_EVERY_S = 600                     # личный набор — не чаще раза в 10 минут на человека
FIRST_BATCH, MAX_SET = 50, 120              # Telegram: набор создаётся до 50 стикерами, всего до 120
PERSONAL = ["hello", "love", "like", "yay", "dance", "laugh", "hug", "sign_hi", "sign_thanks", "sleep"]


def token() -> str:
    t = os.environ.get("KAI_BOT_TOKEN") or (TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.is_file() else "")
    if not re.fullmatch(r"\d+:[\w-]{20,}", t or ""):
        raise SystemExit(f"Нет токена бота: положите его в {TOKEN_FILE} или KAI_BOT_TOKEN (выдаёт @BotFather).")
    return t


class Bot:
    def __init__(self, tok: str, api: str = API):
        self.base = f"{api}/bot{tok}"
        self.username = ""

    def call(self, method: str, files: dict[str, Path] | None = None, http_timeout: float = 60, **params):
        if files:
            body, ctype = multipart(params, files)
        else:
            body, ctype = json.dumps(params, ensure_ascii=False).encode("utf-8"), "application/json"
        req = urllib.request.Request(f"{self.base}/{method}", data=body, headers={"Content-Type": ctype})
        try:
            with urllib.request.urlopen(req, timeout=http_timeout) as r:
                reply = json.load(r)
        except urllib.error.HTTPError as e:
            reply = json.loads(e.read() or b"{}")
        if not reply.get("ok"):
            raise RuntimeError(f"{method}: {reply.get('description', reply)}")
        return reply["result"]

    def me(self) -> str:
        self.username = self.call("getMe")["username"]
        return self.username

    def set_name(self, prefix: str) -> str:
        return f"{prefix}_by_{self.username}"

    def updates(self, offset: int, wait: int = 30) -> list[dict]:
        """Долгий опрос: Telegram держит запрос до wait секунд, пока не придёт сообщение."""
        return self.call("getUpdates", http_timeout=wait + 15, offset=offset, timeout=wait, allowed_updates=["message"])

    def say(self, chat: int, text: str) -> None:
        self.call("sendMessage", chat_id=chat, text=text, disable_web_page_preview=False)

    def upload_set(self, user_id: int, name: str, title: str, folder: Path, only: list[str] | None = None) -> str:
        """Создать набор (или дополнить существующий) из folder/pack.json. Ссылка на него."""
        pack = json.loads((folder / "pack.json").read_text(encoding="utf-8"))["stickers"]
        if only:
            pack = [s for s in pack if Path(s["file"]).stem in only]
        pack = pack[:MAX_SET]
        try:
            have = len(self.call("getStickerSet", name=name)["stickers"])      # набор уже есть — догружаем остаток
        except RuntimeError:
            have = 0
        if have == 0:
            first = pack[:FIRST_BATCH]                     # createNewStickerSet принимает не больше 50 сразу
            stickers = [{"sticker": f"attach://s{i}", "format": "video", "emoji_list": [s["emoji"]]} for i, s in enumerate(first)]
            files = {f"s{i}": folder / s["file"] for i, s in enumerate(first)}
            self.call("createNewStickerSet", files=files, http_timeout=600, user_id=user_id, name=name, title=title,
                      stickers=json.dumps(stickers, ensure_ascii=False))
            have = len(first)
        for i, s in enumerate(pack[have:], start=have):
            self.call("addStickerToSet", files={"s0": folder / s["file"]}, http_timeout=120, user_id=user_id, name=name,
                      sticker=json.dumps({"sticker": "attach://s0", "format": "video", "emoji_list": [s["emoji"]]},
                                         ensure_ascii=False))
            print(f"  добавлен {i + 1}/{len(pack)}", flush=True)
        return f"https://t.me/addstickers/{name}"


def multipart(fields: dict, files: dict[str, Path]) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        if v is None:
            continue
        v = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + v.encode("utf-8") + b"\r\n"
    for k, path in files.items():
        out += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{path.name}"\r\n'
                f"Content-Type: video/webm\r\n\r\n").encode() + path.read_bytes() + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return bytes(out), f"multipart/form-data; boundary={boundary}"


def wait_start(bot: Bot) -> dict:
    """Ждём /start от хозяина — набор создаётся от имени того, кто написал боту."""
    offset = 0
    print(f"Напишите своему боту @{bot.username} команду /start …", flush=True)
    while True:
        for u in bot.updates(offset):
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            if (msg.get("text") or "").startswith("/start"):
                return msg


def create(bot: Bot) -> str:
    if not (PACK / "pack.json").is_file():
        raise SystemExit("Сначала нарисуйте стикеры: python tools/make_stickers.py")
    msg = wait_start(bot)
    user, chat = msg["from"]["id"], msg["chat"]["id"]
    bot.say(chat, "Загружаю стикеры Кая… это пара минут.")
    link = bot.upload_set(user, bot.set_name("kai_pet"), "Кай и друзья", PACK)
    bot.say(chat, f"Готово! Стикеры Кая: {link}\nДелитесь ссылкой — добавить может любой.")
    (ROOT / "stickers" / "pack_link.txt").write_text(link, encoding="utf-8")
    return link


def parse_look(words: list[str]) -> dict:
    """«/my fox ginger bow scarf» → наряд из того, что знает Кай; остальное — мимо."""
    sys.path.insert(0, str(ROOT))
    from kai_pet.pet import ACCESSORIES, COLORS, KINDS, normalize_look
    look = {"kind": "cat", "color": "gray", "acc": []}
    for w in (x.lower() for x in words):
        if w in KINDS:
            look["kind"] = w
        elif w in COLORS:
            look["color"] = w
        elif w in ACCESSORIES and len(look["acc"]) < 6:
            look["acc"].append(w)
    return normalize_look(look)


def serve(bot: Bot) -> None:
    main_link = (ROOT / "stickers" / "pack_link.txt").read_text(encoding="utf-8").strip() \
        if (ROOT / "stickers" / "pack_link.txt").is_file() else ""
    last: dict[int, float] = {}
    offset = 0
    print(f"@{bot.username} работает. Ctrl+C — остановить.", flush=True)
    while True:
        try:
            batch = bot.updates(offset)
        except (OSError, RuntimeError) as e:
            print("Telegram недоступен:", e, flush=True)
            time.sleep(10)
            continue
        for u in batch:
            offset = u["update_id"] + 1
            msg = u.get("message") or {}
            text, chat, user = (msg.get("text") or "").strip(), msg.get("chat", {}).get("id"), msg.get("from", {}).get("id")
            if not chat or not user:
                continue
            try:
                if text.startswith("/start"):
                    bot.say(chat, "Привет! Я бот Кая 🐾\n" + (f"Стикеры: {main_link}\n" if main_link else "") +
                            "Свой набор: /my fox ginger bow — вид (cat fox bunny bear), цвет (gray ginger graphite "
                            "terracotta sky mint lilac rose) и вещи (hat scarf glasses crown bow …).\n"
                            "Сам Кай: https://shoxiazam.github.io/kai-pet/")
                elif text.startswith("/my"):
                    if time.time() - last.get(user, 0) < PERSONAL_EVERY_S:
                        bot.say(chat, "Твой набор уже рисовался недавно — попробуй через 10 минут.")
                        continue
                    last[user] = time.time()
                    look = parse_look(text.split()[1:])
                    bot.say(chat, f"Рисую Кая: {look['kind']}, {look['color']}, {', '.join(look['acc']) or 'без вещей'}… около минуты.")
                    sys.path.insert(0, str(ROOT / "tools"))
                    from make_stickers import STICKERS, make
                    keep = [s for s in STICKERS if s[0] in PERSONAL]
                    import make_stickers
                    make_stickers.STICKERS = keep
                    try:
                        folder = Path(tempfile.mkdtemp(prefix="kai-my-"))
                        make(look, folder, with_duo=False)
                    finally:
                        make_stickers.STICKERS = STICKERS
                    name = bot.set_name(f"kai_{user}_{int(time.time()) % 100000}")
                    link = bot.upload_set(user, name, "Мой Кай", folder)
                    bot.say(chat, f"Твой Кай готов: {link}")
            except (OSError, RuntimeError) as e:
                print("Ошибка:", e, flush=True)
                bot.say(chat, "Не получилось 😿 Попробуй ещё раз позже.")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("create", "serve"):
        raise SystemExit(__doc__)
    bot = Bot(token())
    bot.me()
    if sys.argv[1] == "create":
        print("Набор:", create(bot))
    else:
        serve(bot)


if __name__ == "__main__":
    main()
