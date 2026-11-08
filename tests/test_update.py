"""Обновление в один клик: сравнение версий и выбор установщика из выпуска."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kai_pet import update  # noqa: E402


def test_versions():
    assert update.newer("v1.3.1", "1.3.0")
    assert update.newer("v1.10.0", "1.9.9")              # не строками: 10 > 9
    assert not update.newer("v1.3.0", "1.3.0")
    assert not update.newer("garbage", "1.0.0")


def test_latest_picks_installer(monkeypatch):
    rel = {"tag_name": "v9.0.0", "assets": [{"name": "KaiPet-portable.zip", "browser_download_url": "z"},
                                              {"name": "KaiPet-Setup.exe", "browser_download_url": "https://x/Setup.exe"}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda req, timeout=0: Resp(json.dumps(rel).encode()))
    assert update.latest() == ("v9.0.0", "https://x/Setup.exe")


def test_only_installed_kai_updates_itself(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not update.installed()                         # из исходников — git pull
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(update.sys, "platform", "win32")
    assert update.installed()
    monkeypatch.setattr(update.sys, "platform", "darwin")
    assert not update.installed()                         # на Mac — из .dmg, без установщика Windows


def test_mac_gets_dmg_and_checks_every_few_hours(monkeypatch):
    rel = {"tag_name": "v9.0.0", "assets": [{"name": "KaiPet-Setup.exe", "browser_download_url": "w"},
                                              {"name": "KaiPet-macOS.dmg", "browser_download_url": "https://x/Kai.dmg"}]}

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    monkeypatch.setattr(update.urllib.request, "urlopen", lambda req, timeout=0: Resp(json.dumps(rel).encode()))
    monkeypatch.setattr(update.sys, "platform", "darwin")
    assert update.latest() == ("v9.0.0", "https://x/Kai.dmg")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert update.supported()                             # Mac тоже узнаёт о новой версии
    assert update.due("2026-01-01")                       # старый формат (дата) — проверить
    assert update.due(None)
    assert not update.due(1000.0, now=1000.0 + 3600)
    assert update.due(1000.0, now=1000.0 + update.EVERY_S)
