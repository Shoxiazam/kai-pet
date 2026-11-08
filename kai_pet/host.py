"""Что зависит от системы: папка данных, окна поверх всего на Mac, музыка на Mac.

Windows — основная система Кая. На macOS: окна-инструменты не прячутся при переключении программ, данные лежат в
~/Library/Application Support/KaiPet, танцует под Spotify и «Музыку» Apple (громкость системы на Mac не читается).
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt

MAC = sys.platform == "darwin"
MAC_PLAYERS = ("Spotify", "Music")


def data_dir() -> Path:
    """Папка данных Кая: образы, свои вещи, журнал."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "KaiPet"
    if MAC:
        return Path.home() / "Library" / "Application Support" / "KaiPet"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "KaiPet"


def keep_visible(widget) -> None:
    """На Mac окно-инструмент (Qt.Tool) прячется, как только переключаешься в другую программу — Кай бы исчезал."""
    attr = getattr(Qt, "WA_MacAlwaysShowToolWindow", None)
    if MAC and attr is not None:
        widget.setAttribute(attr)


def _run(args: list[str], timeout: float = 2.0) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def mac_now_playing() -> str | None:
    """Что играет в Spotify или «Музыке» на Mac: «Исполнитель - Песня», "" — ничего, None — узнать нельзя.

    Сначала pgrep: закрытый плеер не трогаем, иначе AppleScript запустил бы его. Первый раз macOS спросит
    разрешение «управлять Spotify / Музыкой» — без него Кай просто не танцует.
    """
    if not MAC:
        return None
    for app in MAC_PLAYERS:
        if not _run(["pgrep", "-x", app]):
            continue
        script = (f'tell application "{app}" to if player state is playing then '
                  f'return (artist of current track) & " - " & (name of current track)')
        out = _run(["osascript", "-e", script])
        if out:
            return out
    return ""


_cg = [None, False]                     # CoreGraphics загружена / уже пробовали


def mac_idle_s() -> float:
    """Сколько секунд на Mac не трогали мышь и клавиатуру — CoreGraphics, без разрешений и без процессов."""
    if not MAC:
        return 0.0
    if not _cg[1]:
        _cg[1] = True
        try:
            lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            fn = lib.CGEventSourceSecondsSinceLastEventType
            fn.restype, fn.argtypes = ctypes.c_double, [ctypes.c_int32, ctypes.c_uint32]
            _cg[0] = fn
        except (OSError, AttributeError):
            _cg[0] = None
    if _cg[0] is None:
        return 0.0
    return max(0.0, float(_cg[0](0, 0xFFFFFFFF)))   # вся сессия, любое событие ввода
