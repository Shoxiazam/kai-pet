"""Сборка Кая для Windows: pip install pyinstaller && python build_exe.py → dist/KaiPet/ (папка, быстрый запуск).

python build_exe.py --onefile → dist/KaiPet.exe одним файлом (запускается дольше: распаковывается при каждом старте).
Установщик KaiPet-Setup.exe из папки собирает Inno Setup: iscc installer/KaiPet.iss (так делает GitHub Actions).
Кадры новых образов и друзей рисуются через Edge или Chrome — Node.js не нужен.
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
DATA = ["assets/frames", "assets/moods", "assets/look", "assets/states", "assets/sounds", "character"]


def main() -> None:
    mode = "--onefile" if "--onefile" in sys.argv else "--onedir"
    args = [str(ROOT / "run_kai.pyw"), "--name", "KaiPet", mode, "--windowed", "--noconfirm",
            "--icon", str(ROOT / "assets" / "icon.ico"), "--paths", str(ROOT),
            "--add-data", f"{ROOT / 'assets' / 'icon.ico'}{os.pathsep}assets",
            "--hidden-import", "kai_pet.__main__", "--hidden-import", "kai_pet.export",
            # лишнее из PySide6 — минус десятки мегабайт
            "--exclude-module", "PySide6.QtWebEngineCore", "--exclude-module", "PySide6.QtWebEngineWidgets",
            "--exclude-module", "PySide6.Qt3DCore", "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtQml",
            "--exclude-module", "PySide6.QtPdf", "--exclude-module", "PySide6.QtCharts", "--exclude-module", "PySide6.QtDataVisualization",
            "--exclude-module", "tkinter"]
    for rel in DATA:
        args += ["--add-data", f"{ROOT / rel}{os.pathsep}{rel}"]
    if sys.platform == "win32":
        args += ["--hidden-import", "pycaw.pycaw", "--hidden-import", "comtypes.stream"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
