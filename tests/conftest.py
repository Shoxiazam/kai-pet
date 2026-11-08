"""Общее для тестов: окна Кая не переживают тест — иначе процесс pytest падает на выходе."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _close_stray_windows():
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    if QCoreApplication.instance() is None:
        return
    from kai_pet.pet import close_kai_windows
    close_kai_windows()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
