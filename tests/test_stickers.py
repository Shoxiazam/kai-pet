"""Стикеры: набор по правилам Telegram и бот против подставного Bot API (без настоящего токена)."""
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import sticker_bot  # noqa: E402

PACK = ROOT / "stickers" / "pack"


def test_pack_follows_telegram_rules():
    pack = json.loads((PACK / "pack.json").read_text(encoding="utf-8"))
    assert len(pack["stickers"]) >= 20
    for s in pack["stickers"]:
        f = PACK / s["file"]
        data = f.read_bytes()
        assert data[:4] == b"\x1aE\xdf\xa3" and len(data) <= 256 * 1024, s     # WebM (EBML), до 256 КБ
        assert s["emoji"]


def test_look_from_words():
    look = sticker_bot.parse_look(["fox", "ginger", "bow", "scarf", "дракон", "rm"])
    assert look["kind"] == "fox" and look["color"] == "ginger" and set(look["acc"]) == {"bow", "scarf"}


def _parts(body: bytes, ctype: str) -> dict:
    boundary = ctype.split("boundary=")[1].encode()
    out = {}
    for part in body.split(b"--" + boundary)[1:-1]:
        head, _, value = part.partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        out[name] = value[:-2]
    return out


def test_bot_creates_pack_after_start(tmp_path, monkeypatch):
    calls = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            method = self.path.rsplit("/", 1)[-1]
            body = self.rfile.read(int(self.headers["Content-Length"]))
            ctype = self.headers["Content-Type"]
            params = _parts(body, ctype) if ctype.startswith("multipart") else json.loads(body or b"{}")
            calls.append((method, params))
            result = {"getMe": {"username": "kai_test_bot"},
                      "getUpdates": [{"update_id": 1, "message": {"text": "/start", "from": {"id": 42}, "chat": {"id": 42}}}]
                      if sum(m == "getUpdates" for m, _ in calls) == 1 else []}.get(method, True)
            ok = method != "getStickerSet"                        # набора ещё нет
            data = json.dumps({"ok": ok, "result": result} if ok else {"ok": False, "description": "STICKERSET_INVALID"})
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())

        def log_message(self, *a):
            pass
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(sticker_bot, "ROOT", tmp_path)
    (tmp_path / "stickers").mkdir()
    bot = sticker_bot.Bot("123:" + "x" * 30, api=f"http://127.0.0.1:{srv.server_port}")
    assert bot.me() == "kai_test_bot"
    link = sticker_bot.create(bot)
    srv.shutdown()
    assert link == "https://t.me/addstickers/kai_pet_by_kai_test_bot"
    created = next(p for m, p in calls if m == "createNewStickerSet")
    stickers = json.loads(created["stickers"])
    assert created["user_id"] == b"42" and created["name"] == b"kai_pet_by_kai_test_bot"
    assert len(stickers) == len([k for k in created if k.startswith("s") and k[1:].isdigit()]) >= 20
    assert all(s["format"] == "video" and s["emoji_list"] for s in stickers)
    assert any(m == "sendMessage" and link in p["text"] for m, p in calls)
    assert (tmp_path / "stickers" / "pack_link.txt").read_text(encoding="utf-8") == link
