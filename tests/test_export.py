"""Кадры нового образа без Node.js: kai_pet.export говорит с Edge/Chrome по DevTools сам."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kai_pet import export  # noqa: E402


def test_command_runs_module_from_sources_and_flag_from_exe(monkeypatch):
    exe, args = export.command()
    assert args == ["-m", "kai_pet.export"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert export.command() == (sys.executable, ["--export"])


@pytest.mark.skipif(not export.find_browser(), reason="нет Edge или Chrome")
def test_real_export_draws_every_animation(tmp_path):
    export.export({"kind": "bunny", "color": "mint", "acc": ["hat"]}, tmp_path)
    anims = {d.name for d in (tmp_path / "frames").iterdir()}
    assert {"idle", "wave", "holdL", "holdR", "highR", "spin"} <= anims
    assert len(list((tmp_path / "frames" / "idle").glob("*.png"))) == 48
    assert (tmp_path / "moods" / "curious").is_dir() and (tmp_path / "look").is_dir()
    png = (tmp_path / "frames" / "idle" / "idle_000.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 2000
