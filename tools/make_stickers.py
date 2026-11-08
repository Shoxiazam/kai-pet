"""Стикеры с Каем для Telegram: python tools/make_stickers.py → stickers/pack/*.webm и pack.json.

Кадры рисуются заново в 512×512 прямо из character/kai.js (через Edge/Chrome, как образы), подписи на табличке
и пара «за лапки» — средствами Qt. Видео-стикер по правилам Telegram: WebM VP9 с прозрачностью, 512 px,
до 3 секунд, до 30 к/с, до 256 КБ, без звука. Нужен ffmpeg с libvpx-vp9 (pip install imageio-ffmpeg).
Набор образа «как у меня»: --look '{"kind":"fox","color":"ginger","acc":["bow"]}' --out stickers/my
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter  # noqa: E402

SIZE = 512
MAX_BYTES = 256 * 1024
MAX_S = 3.0
# (имя файла, движение, эмодзи, табличка)
STICKERS = [("hello", "wave", "👋", ""), ("love", "heart", "❤️", ""), ("like", "like", "👍", ""),
            ("yay", "jump", "🎉", ""), ("dance", "dance", "💃", ""), ("laugh", "laugh", "😂", ""),
            ("think", "think", "🤔", ""), ("shy", "shy", "😊", ""), ("spin", "spin", "🌀", ""),
            ("clap", "clap", "👏", ""), ("hug", "hug", "🤗", ""), ("bow", "bow", "🙇", ""),
            ("sad", "fail", "😢", ""), ("sleep", "bed", "😴", ""), ("yum", "eat", "🍪", ""),
            ("sign_hi", "sign", "🙋", "Привет!"), ("sign_thanks", "sign", "🙏", "Спасибо!"),
            ("sign_ok", "sign", "👌", "Ок"), ("disco", "disco", "🕺", ""), ("guitar", "airguitar", "🎸", "")]
DUO = ("duo", "hold", "🤝")
FRIEND_LOOK = {"kind": "fox", "color": "ginger", "acc": ["bow"]}
SIGN_RECT = (44, 194, 168, 42)            # как в kai_pet/pet.py, в кадре 256


def ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        raise SystemExit("Нужен ffmpeg: pip install imageio-ffmpeg")


class Renderer:
    """Кадры из kai.js в нужном размере — тот же браузер без окна, что рисует образы Кая."""

    def __init__(self):
        from kai_pet import export
        self.export = export
        exe = export.find_browser()
        if not exe:
            raise SystemExit("Нужен Edge или Chrome")
        self.port = 9300 + os.getpid() % 600
        self.profile = tempfile.mkdtemp(prefix="kai-st-")
        flags = 0x08000000 if sys.platform == "win32" else 0
        self.browser = subprocess.Popen([exe, "--headless=new", f"--remote-debugging-port={self.port}",
                                         f"--user-data-dir={self.profile}", "--no-first-run", "--disable-gpu",
                                         "--allow-file-access-from-files", "about:blank"],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
        self.ws = export.WebSocket(export._page_ws(self.port))
        self.dt = export.DevTools(self.ws)
        self.dt.send("Page.navigate", url=(export.HERE / "export.html").resolve().as_uri())
        import time
        for _ in range(100):
            try:
                if self.dt.eval("typeof grid") == "function":
                    break
            except RuntimeError:
                pass
            time.sleep(0.1)
        self.anims = self.dt.eval("Object.fromEntries(Object.entries(Kai.ANIMS).map(([k, v]) => [k, [v.frames, v.fps]]))")

    def frames(self, anim: str, look: dict) -> tuple[list[QImage], int]:
        """Кадры движения; «mood:grumpy» — живая эмоция (дыхание и моргание), как у Кая на экране."""
        self.dt.eval(f"Object.assign(Kai.LOOK, {json.dumps(look)}), true")
        if anim.startswith("mood:"):
            state, (n, fps), name = anim[5:], (24, 12), "idle"
        else:
            state, (n, fps), name = None, self.anims[anim], anim
        out = []
        for i in range(n):
            b64 = self.dt.eval(f"grid([Kai.frame({json.dumps(state)}, {json.dumps(name)}, {i / n})], 1, {SIZE})")
            out.append(QImage.fromData(base64.b64decode(b64), "PNG"))
        return out, fps

    def close(self) -> None:
        self.ws.close()
        self.browser.kill()
        shutil.rmtree(self.profile, ignore_errors=True)


FONT_FILES = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
              "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
_family: list[str] = []


def sign_font() -> QFont:
    """Шрифт с кириллицей из файла: без окна (offscreen) Qt системных шрифтов не видит и рисует квадратики."""
    if not _family:
        from PySide6.QtGui import QFontDatabase
        for f in FONT_FILES:
            if Path(f).is_file():
                fid = QFontDatabase.addApplicationFont(f)
                if fid >= 0 and QFontDatabase.applicationFontFamilies(fid):
                    _family.append(QFontDatabase.applicationFontFamilies(fid)[0])
                    break
        _family.append(_family[0] if _family else "Sans Serif")
    font = QFont(_family[0])
    return font


def sign(img: QImage, text: str) -> QImage:
    img = img.convertToFormat(QImage.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    k = SIZE / 256
    x, y, w, h = (v * k for v in SIGN_RECT)
    font = sign_font()
    font.setBold(True)
    font.setPixelSize(round(h * 0.55))
    p.setFont(font)
    p.setPen(QColor("#3B3330"))
    p.drawText(QRectF(x, y, w, h), Qt.AlignCenter, text)
    p.end()
    return img


def duo(kai: list[QImage], friend: list[QImage]) -> list[QImage]:
    """Кай и Мира за лапки в одном квадрате 512 (смещения — как у друга, HOLD_DX/HOLD_DY)."""
    from kai_pet.friend import HOLD_DX, HOLD_DY, SCALE
    k = round(SIZE * 0.6)
    f = round(k * SCALE)
    left = round(HOLD_DX * k)
    w = left + k
    x0, y0 = (SIZE - w) // 2, (SIZE - k) // 2
    out = []
    for a, b in zip(kai, friend):
        img = QImage(SIZE, SIZE, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(x0, y0 + round(HOLD_DY * k), b.scaled(f, f, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.drawImage(x0 + left, y0, a.scaled(k, k, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.end()
        out.append(img)
    return out


def encode(frames: list[QImage], fps: int, out: Path, tool: str) -> int:
    """WebM VP9 с прозрачностью в рамках Telegram: зацикливаем до ~2,5 с, но не дольше 3 с, и ужимаем до 256 КБ."""
    fps = min(fps, 30)
    loops = max(1, int(2.5 * fps // len(frames)))
    seq = (frames * loops)[: int(MAX_S * fps) - 1]
    tmp = Path(tempfile.mkdtemp(prefix="kai-st-"))
    try:
        for i, img in enumerate(seq):
            img.save(str(tmp / f"f{i:03d}.png"))
        for crf in (32, 38, 44, 50, 56):
            subprocess.run([tool, "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(tmp / "f%03d.png"),
                            "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-b:v", "0", "-crf", str(crf),
                            "-deadline", "good", "-row-mt", "1", "-an", str(out)], check=True)
            if out.stat().st_size <= MAX_BYTES:
                return out.stat().st_size
        raise RuntimeError(f"{out.name}: не влезает в 256 КБ")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def make(look: dict, out: Path, with_duo: bool = True) -> list[dict]:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    out.mkdir(parents=True, exist_ok=True)
    tool, r = ffmpeg(), Renderer()
    pack = []
    try:
        for name, anim, emoji, text in STICKERS:
            frames, fps = r.frames(anim, look)
            if text:
                frames = [sign(f, text) for f in frames]
            size = encode(frames, fps, out / f"{name}.webm", tool)
            pack.append({"file": f"{name}.webm", "emoji": emoji})
            print(f"{name}: {size // 1024} КБ", flush=True)
        if with_duo:
            kai, fps = r.frames("holdL", look)
            mira, _ = r.frames("holdR", FRIEND_LOOK)
            size = encode(duo(kai, mira), fps, out / f"{DUO[0]}.webm", tool)
            pack.append({"file": f"{DUO[0]}.webm", "emoji": DUO[2]})
            print(f"{DUO[0]}: {size // 1024} КБ", flush=True)
    finally:
        r.close()
    (out / "pack.json").write_text(json.dumps({"title": "Кай", "look": look, "stickers": pack}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return pack


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--look", default='{"kind":"cat","color":"gray","acc":[]}')
    ap.add_argument("--out", default=str(ROOT / "stickers" / "pack"))
    args = ap.parse_args()
    from kai_pet.pet import normalize_look
    pack = make(normalize_look(json.loads(args.look)), Path(args.out))
    print(f"готово: {len(pack)} стикеров в {args.out}")


if __name__ == "__main__":
    main()
