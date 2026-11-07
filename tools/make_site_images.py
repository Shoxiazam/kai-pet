"""Картинки для сайта (site/img): ленты кадров для CSS-анимации и Кай с другом за лапки.

python tools/make_site_images.py  (после node character/export.mjs и с нарисованным другом в assets/friend)
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "img"
CELL = 220


def frames(folder: Path, name: str, step: int = 1) -> list[QImage]:
    files = sorted((folder / "frames" / name).glob("*.png"))[::step]
    return [QImage(str(f)).scaled(CELL, CELL, Qt.KeepAspectRatio, Qt.SmoothTransformation) for f in files]


def strip(images: list[QImage], file: str, width: int = CELL, height: int = CELL) -> None:
    out = QImage(width * len(images), height, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    p = QPainter(out)
    for i, im in enumerate(images):
        p.drawImage(i * width, 0, im)
    p.end()
    out.save(str(OUT / file), "PNG", 9)
    print(file, len(images), "кадров")


def duo(kai: Path, friend: Path, file: str, step: int = 2) -> None:
    """Кай справа (holdL), друг слева (holdR) — смещения как в kai_pet/friend.py (HOLD_DX, HOLD_DY)."""
    from kai_pet.friend import HOLD_DX, HOLD_DY, SCALE
    k, f = CELL, round(CELL * SCALE)
    left = round(HOLD_DX * k)
    w, h = left + k + 10, k + round(HOLD_DY * k) + 4
    ks = sorted((kai / "frames" / "holdL").glob("*.png"))[::step]
    fs = sorted((friend / "frames" / "holdR").glob("*.png"))[::step]
    images = []
    for kf, ff in zip(ks, fs):
        im = QImage(w, h, QImage.Format_ARGB32)
        im.fill(Qt.transparent)
        p = QPainter(im)
        p.drawImage(0, round(HOLD_DY * k), QImage(str(ff)).scaled(f, f, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.drawImage(left, 0, QImage(str(kf)).scaled(k, k, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.end()
        images.append(im)
    strip(images, file, w, h)


def main() -> None:
    sys.path.insert(0, str(ROOT))
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    a = ROOT / "assets"
    strip(frames(a, "wave"), "kai-wave.png")
    strip(frames(a, "dance", 2), "kai-dance.png")
    strip(frames(a, "heart"), "kai-heart.png")
    mira = next((a / "friend").glob("fox-*"), None)
    if mira:
        duo(a, mira, "duo-hold.png")


if __name__ == "__main__":
    main()
