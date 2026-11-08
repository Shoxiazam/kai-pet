"""Сборка Кая: pip install pyinstaller && python build_exe.py

Windows → dist/KaiPet/ (папка, быстрый запуск); установщик KaiPet-Setup.exe собирает Inno Setup:
iscc installer/KaiPet.iss. python build_exe.py --onefile → dist/KaiPet.exe одним файлом (стартует дольше).
macOS → dist/KaiPet.app (нужен Pillow для иконки); .dmg и подпись делает GitHub Actions (release.yml).
Кадры новых образов и друзей рисуются через Edge или Chrome — Node.js не нужен.
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
DATA = ["assets/frames", "assets/moods", "assets/look", "assets/states", "assets/sounds", "character"]
MAC = sys.platform == "darwin"


def main() -> None:
    mode = "--onefile" if "--onefile" in sys.argv and not MAC else "--onedir"
    icon = ROOT / "assets" / ("icon.png" if MAC else "icon.ico")
    args = [str(ROOT / "run_kai.pyw"), "--name", "KaiPet", mode, "--windowed", "--noconfirm",
            "--icon", str(icon), "--paths", str(ROOT),
            "--add-data", f"{ROOT / 'assets' / 'icon.ico'}{os.pathsep}assets",
            "--add-data", f"{ROOT / 'assets' / 'icon.png'}{os.pathsep}assets",
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
    if MAC:
        args += ["--osx-bundle-identifier", "com.shoxiazam.kaipet"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
