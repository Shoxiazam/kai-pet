"""Кадры нового образа через Edge/Chrome без Node.js: python -m kai_pet.export (или KaiPet.exe --export).

То же, что character/export.mjs в режиме образа: KAI_LOOK — образ (JSON), KAI_OUT — куда сложить кадры,
KAI_CUSTOM_FILE — свои вещи (JSON). Браузер запускается без окна, говорим с ним по DevTools Protocol
через маленький WebSocket-клиент на стандартной библиотеке — ставить ничего не нужно.
"""
from __future__ import annotations

import base64
import json
import os
import random
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "character"
BROWSERS = [os.environ.get("KAI_BROWSER", ""),
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            str(Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"),
            "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Arc.app/Contents/MacOS/Arc",
            str(Path.home() / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]


def find_browser() -> str | None:
    for path in BROWSERS:
        if path and Path(path).is_file():
            return path
    return shutil.which("msedge") or shutil.which("chrome") or shutil.which("chromium")


class WebSocket:
    """Минимальный клиент WebSocket (RFC 6455): текстовые кадры туда и обратно — всё, что нужно DevTools."""

    def __init__(self, url: str, timeout: float = 60):
        rest = url.split("://", 1)[1]
        hostport, path = rest.split("/", 1)
        host, port = hostport.rsplit(":", 1)
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(1)
            if not chunk:
                raise ConnectionError("браузер закрыл соединение")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.decode(errors="replace"))

    def _read(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("браузер закрыл соединение")
            buf += chunk
        return bytes(buf)

    def send(self, text: str) -> None:
        data, mask = text.encode(), os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                                bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536 else
                                bytes([0x80 | 127]) + struct.pack(">Q", n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self) -> str:
        message = bytearray()
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else b""
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            op = b1 & 0x0F
            if op == 8:
                raise ConnectionError("браузер закрыл соединение")
            if op == 9:                                      # ping — ответить pong
                continue
            if op in (0, 1, 2):
                message += payload
                if b1 & 0x80:
                    return message.decode()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class DevTools:
    def __init__(self, ws: WebSocket):
        self.ws, self.n = ws, 0

    def send(self, method: str, **params) -> dict:
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.n:
                return reply

    def eval(self, expression: str):
        r = self.send("Runtime.evaluate", expression=expression, awaitPromise=True, returnByValue=True)
        if "error" in r or r["result"].get("exceptionDetails"):
            raise RuntimeError(json.dumps(r.get("error") or r["result"]["exceptionDetails"])[:500])
        return r["result"]["result"].get("value")


def _page_ws(port: int) -> str:
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
                pages = [t for t in json.load(r) if t.get("type") == "page"]
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("Браузер не ответил по DevTools")


def export(look: dict, out: Path, custom: dict | None = None, attempts: int = 2) -> None:
    """Нарисовать все кадры образа. Браузер изредка рвёт соединение посреди работы — тогда ещё раз с новым."""
    for left in range(attempts, 0, -1):
        try:
            _export_once(look, out, custom)
            return
        except (ConnectionError, OSError, RuntimeError):
            if left == 1:
                raise
            time.sleep(1)


def _export_once(look: dict, out: Path, custom: dict | None) -> None:
    exe = find_browser()
    if not exe:
        raise RuntimeError("Не найден Edge или Chrome")
    port = 9300 + random.randrange(600)
    profile = tempfile.mkdtemp(prefix="kai-")
    flags = 0x08000000 if sys.platform == "win32" else 0          # без окна консоли
    browser = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
                                "--no-first-run", "--disable-gpu", "--allow-file-access-from-files", "about:blank"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    ws = None
    try:
        ws = WebSocket(_page_ws(port))
        dt = DevTools(ws)
        dt.send("Page.navigate", url=(HERE / "export.html").resolve().as_uri())
        for _ in range(100):
            try:
                if dt.eval("typeof grid") == "function":
                    break
            except RuntimeError:
                pass
            time.sleep(0.1)
        dt.eval(f"Object.assign(Kai.LOOK, {json.dumps(look)}), true")
        if custom:
            dt.eval(f"Object.assign(Kai.CUSTOM, {json.dumps(custom)}), true")
        for d in ("frames", "states", "moods", "look"):
            shutil.rmtree(out / d, ignore_errors=True)

        def save(rel: str, expr: str) -> None:
            file = out / rel
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(base64.b64decode(dt.eval(expr)))

        anims = dt.eval("Object.fromEntries(Object.entries(Kai.ANIMS).map(([k, v]) => [k, v.frames]))")
        for name, frames in anims.items():
            for i in range(frames):
                save(f"frames/{name}/{name}_{i:03d}.png", f"grid([Kai.frame(null, {json.dumps(name)}, {i / frames})], 1)")
        states = [s for s in dt.eval("Object.keys(Kai.STATES)") if s != "neutral"]
        for s in states:
            save(f"states/{s}.png", f"grid([Kai.frame({json.dumps(s)}, 'idle', 0)], 1)")
            for i in range(24):                                 # живые эмоции: дыхание и моргание
                save(f"moods/{s}/{s}_{i:03d}.png", f"grid([Kai.frame({json.dumps(s)}, 'idle', {i / 24})], 1)")
        for d in dt.eval("Object.keys(Kai.LOOKS)"):
            save(f"look/{d}.png", f"grid([Kai.svg({{ look: Kai.LOOKS.{d} }})], 1)")
    finally:
        if ws is not None:
            ws.close()
        browser.kill()
        try:
            browser.wait(10)
        except subprocess.TimeoutExpired:
            pass
        shutil.rmtree(profile, ignore_errors=True)


def main() -> int:
    look = json.loads(os.environ.get("KAI_LOOK") or "{}")
    out = Path(os.environ["KAI_OUT"])
    custom = None
    if os.environ.get("KAI_CUSTOM_FILE"):
        custom = json.loads(Path(os.environ["KAI_CUSTOM_FILE"]).read_text(encoding="utf-8"))
    try:
        export(look, out, custom)
    except Exception as e:                                      # причина — в stderr, её прочитает питомец
        if sys.stderr:                                          # у pythonw и окна .exe консоли может не быть
            print(f"Кадры не нарисованы: {e}", file=sys.stderr)
        return 1
    if sys.stdout:
        print("PNG сохранены в", out)
    return 0


def command() -> tuple[str, list[str]]:
    """Как запустить экспорт отдельным процессом: из исходников — этот файл по пути, из .exe — KaiPet.exe --export.

    По пути, а не «python -m kai_pet.export»: в голосовом агенте kai_pet подключён через sys.path, и новый процесс
    модуль не нашёл бы. Файлу пакет не нужен — только стандартная библиотека.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ["--export"]
    return sys.executable, [str(Path(__file__).resolve())]   # pythonw — без мелькающего окна консоли


if __name__ == "__main__":
    raise SystemExit(main())
