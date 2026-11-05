"""Сборка KaiPet.exe одним файлом: pip install pyinstaller && python build_exe.py → dist/KaiPet.exe.

В .exe — готовые кадры, звуки и character/ (для новых образов нужен Node.js на компьютере).
"""
import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
DATA = ["assets/frames", "assets/moods", "assets/look", "assets/states", "assets/sounds", "character"]


def main() -> None:
    args = [str(ROOT / "run_kai.pyw"), "--name", "KaiPet", "--onefile", "--windowed", "--noconfirm",
            "--icon", str(ROOT / "assets" / "icon.ico"), "--paths", str(ROOT),
            "--add-data", f"{ROOT / 'assets' / 'icon.ico'}{os.pathsep}assets",
            "--hidden-import", "kai_pet.__main__"]
    for rel in DATA:
        args += ["--add-data", f"{ROOT / rel}{os.pathsep}{rel}"]
    if sys.platform == "win32":
        args += ["--hidden-import", "pycaw.pycaw", "--hidden-import", "comtypes.stream"]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
