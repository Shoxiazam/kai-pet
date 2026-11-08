"""Обновление Кая в один клик: раз в день смотрит последний выпуск на GitHub и, если он новее, предлагает обновиться.

Только у установленного Кая (KaiPet.exe из KaiPet-Setup.exe): скачивает новый установщик и запускает его тихо —
галочки прошлой установки сохраняются, Кай перезапускается сам. Из исходников обновляются через git pull.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from . import __version__

log = logging.getLogger(__name__)

REPO = "Shoxiazam/kai-pet"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
SETUP = "KaiPet-Setup.exe"
SILENT = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]


def parse(version: str) -> tuple[int, ...]:
    """«v1.2.10» → (1, 2, 10); мусор → (0,)."""
    nums = re.findall(r"\d+", version or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def newer(remote: str, local: str = __version__) -> bool:
    return parse(remote) > parse(local)


def installed() -> bool:
    """Обновлять установщиком можно только установленного Кая на Windows (KaiPet.exe из KaiPet-Setup.exe).
    На Mac новую версию ставят перетаскиванием из .dmg — проверку обновлений там не показываем."""
    return bool(getattr(sys, "frozen", False)) and sys.platform == "win32"


def latest(timeout: float = 10) -> tuple[str, str] | None:
    """(версия, ссылка на установщик) последнего выпуска или None."""
    req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "KaiPet-updater"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.load(r)
    url = next((a.get("browser_download_url") for a in rel.get("assets", []) if a.get("name") == SETUP), None)
    return (str(rel.get("tag_name", "")), url) if url else None


class Updater(QObject):
    found = Signal(str, str)         # версия, ссылка — есть новее
    nothing = Signal()               # проверили: это последняя версия (или проверить не вышло)
    downloaded = Signal(str)         # путь к скачанному установщику ("" — не скачалось)

    def check(self, force: bool = False) -> None:
        """Раз в день в фоне; force — по кнопке «Проверить обновления»."""
        from .pet import load_state, save_state
        today = datetime.date.today().isoformat()
        if not force and load_state().get("update_checked") == today:
            return
        save_state("update_checked", today)
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self) -> None:
        try:
            got = latest()
        except (OSError, ValueError) as e:
            log.info("Обновления не проверены: %s", e)
            got = None
        if got and newer(got[0]):
            self.found.emit(*got)
        else:
            self.nothing.emit()

    def download(self, url: str) -> None:
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url: str) -> None:
        target = Path(tempfile.gettempdir()) / SETUP
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KaiPet-updater"})
            with urllib.request.urlopen(req, timeout=60) as r, open(target, "wb") as f:
                while chunk := r.read(1 << 16):
                    f.write(chunk)
            self.downloaded.emit(str(target) if target.stat().st_size > 1_000_000 else "")
        except OSError as e:
            log.warning("Обновление не скачалось: %s", e)
            self.downloaded.emit("")


def run_installer(path: str) -> bool:
    """Тихо запустить новый установщик: он закроет этого Кая и запустит обновлённого."""
    return QProcess.startDetached(path, SILENT)[0]
