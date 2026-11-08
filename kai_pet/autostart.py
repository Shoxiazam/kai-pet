"""Запуск Кая вместе с системой, только по выбору в меню, без прав администратора.

Windows — одно значение в HKCU\\...\\Run. macOS — LaunchAgent ~/Library/LaunchAgents/com.shoxiazam.kaipet.plist.
"""
from __future__ import annotations

import plistlib
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "KaiPet"
MAC_LABEL = "com.shoxiazam.kaipet"


def supported() -> bool:
    return sys.platform in ("win32", "darwin")


def _mac_agent() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def arguments() -> list[str]:
    """Что запускать: сам KaiPet.exe / KaiPet.app или run_kai.pyw (без окна консоли)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    launcher = Path(__file__).resolve().parent.parent / "run_kai.pyw"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.is_file() else sys.executable), str(launcher)]


def command() -> str:
    return " ".join(f'"{a}"' for a in arguments())


def enabled() -> bool:
    if sys.platform == "darwin":
        return _mac_agent().is_file()
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, NAME)
            return True
    except OSError:
        return False


def set_enabled(on: bool) -> None:
    if sys.platform == "darwin":
        agent = _mac_agent()
        if on:
            agent.parent.mkdir(parents=True, exist_ok=True)
            agent.write_bytes(plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": arguments(),
                                              "RunAtLoad": True, "ProcessType": "Interactive"}))
        else:
            agent.unlink(missing_ok=True)
        return
    if sys.platform != "win32":
        return
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass
