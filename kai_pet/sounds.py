"""Звуки Кая: короткие WAV из assets/sounds. Играют через встроенный winsound Windows, без зависимостей.

На других системах Кай просто молчит.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def play(path: Path) -> None:
    if sys.platform != "win32" or not path.is_file():
        return
    try:
        import winsound
        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError as e:                   # звуковое устройство занято или отключено — без звука
        log.debug("Звук %s не сыграл: %s", path.name, e)
