"""Звуки Кая: короткие WAV из assets/sounds, без зависимостей.

Windows — встроенный winsound, macOS — системный afplay, Linux — paplay или aplay, если есть.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def player() -> list[str] | None:
    """Чем играть WAV вне Windows: afplay есть в каждом macOS."""
    for tool in ("afplay", "paplay", "aplay"):
        found = shutil.which(tool)
        if found:
            return [found] + (["-q"] if tool == "aplay" else [])
    return None


def play(path: Path) -> None:
    if not path.is_file():
        return
    if sys.platform == "win32":
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except RuntimeError as e:               # звуковое устройство занято или отключено — без звука
            log.debug("Звук %s не сыграл: %s", path.name, e)
        return
    cmd = player()
    if cmd:
        try:                                    # не ждём: звук играет сам, Кай не замирает
            subprocess.Popen(cmd + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            log.debug("Звук %s не сыграл: %s", path.name, e)
