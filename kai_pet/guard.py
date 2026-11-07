"""Кай-сторож: вы ушли, а кто-то трогает ноутбук — Кай пугается, фотографирует с камеры и зовёт вас.

Сам Кай только снимает и сообщает сигналом alarm(путь к фото или ""). На телефон сообщение отправляет тот,
кто подключил Кая (голосовой агент через пульт). Без него фото лежит в «Изображения/Кай-сторож».
"""
from __future__ import annotations

import datetime
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal

from . import camera

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

GRACE_S = 20            # столько дать, чтобы спокойно уйти от ноутбука
TOUCH_IDLE_S = 2.0      # мышь или клавиатура были меньше этого назад — кто-то трогает
REARM_IDLE_S = 120      # после тревоги снова тихо 2 минуты — сторожит дальше
PHOTOS_KEEP = 30
ALARM_TEXT = "Кай-сторож: кто-то за ноутбуком!"
_ON = ("охраняй", "сторожи", "посторожи", "охрана вкл", "я ушёл", "я ушел", "я ухожу")
_OFF = ("сними охрану", "хватит охранять", "не охраняй", "не сторожи", "охрана выкл", "я вернулся", "я вернулась")


def photos_dir() -> Path:
    pictures = QStandardPaths.writableLocation(QStandardPaths.PicturesLocation) or str(Path.home() / "Pictures")
    return Path(pictures) / "Кай-сторож"


def supported() -> bool:
    return sys.platform == "win32"          # время последнего касания мыши и клавиатуры знаем только на Windows


def command(text: str) -> bool | None:
    """True — включить охрану, False — снять, None — фраза не об этом."""
    low = text.lower()
    if any(w in low for w in _OFF):
        return False
    if any(w in low for w in _ON):
        return True
    return None


class Guard(QObject):
    alarm = Signal(str)             # тревога: путь к фото ("" — снять не вышло)
    changed = Signal(bool)          # охрана включена / снята

    def __init__(self, pet: "Pet"):
        super().__init__(pet)
        self.pet = pet
        self.armed = False
        self.tripped = False        # тревога уже была — ждём тишины, чтобы сторожить дальше
        self.since = 0.0
        self.last_photo = ""
        self.alarms = 0
        self.quiet_until = 0.0      # до этого момента касания не считаются: мышью двигает свой агент или пульт
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)

    def arm(self) -> None:
        if not supported():
            self.pet.speak("Сторожить я умею только на Windows.", 5000)
            return
        if self.armed:
            self.pet.speak("Я и так сторожу!", 4000)
            return
        self.armed, self.tripped, self.since, self.alarms = True, False, time.monotonic(), 0
        self._timer.start(500)
        self.pet.gesture("focused", 3)
        self.pet.speak(f"Сторожу! Уходи спокойно, через {GRACE_S} секунд начну следить.", 7000)
        self.changed.emit(True)

    def disarm(self, say: bool = True) -> None:
        if not self.armed:
            return
        self.armed = self.tripped = False
        self._timer.stop()
        if say:
            seen = f" Тревог было: {self.alarms}, фото в папке «Кай-сторож»." if self.alarms else " Всё было спокойно."
            self.pet.play("wave")
            self.pet.speak("Охрану снял." + seen, 9000)
        self.changed.emit(False)

    def pause(self, seconds: float = 5.0) -> None:
        """Мышь и клавиатуру сейчас трогает не чужой, а ваш ассистент или пульт с телефона."""
        self.quiet_until = max(self.quiet_until, time.monotonic() + seconds)

    def _idle_s(self) -> float:
        from .pet import input_idle_s
        return input_idle_s()

    def _check(self) -> None:
        now = time.monotonic()
        if self.pet.loop != "idle":            # ассистент работает и сам кликает
            self.pause()
        if now - self.since < GRACE_S or now < self.quiet_until:
            return
        idle = self._idle_s()
        if self.tripped:
            if idle >= REARM_IDLE_S:
                self.tripped = False        # ушли — сторожим дальше
            return
        if idle < TOUCH_IDLE_S:
            self._trip()

    def _trip(self) -> None:
        self.tripped = True
        self.alarms += 1
        pet = self.pet
        if not pet.isVisible():
            pet.show()
        pet.gesture("surprised", 3)
        pet._sound("meow")
        pet.speak("Ой! Кто здесь?! Я всё вижу и уже зову хозяина!", 10000)
        folder = photos_dir()
        name = folder / datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S.jpg")
        camera.take(name, self._photo, self)

    def _photo(self, path: str) -> None:
        self.last_photo = path
        if path:
            log.info("Кай-сторож: фото %s", path)
            self._prune()
        else:
            log.warning("Кай-сторож: фото не получилось")
        self.alarm.emit(path)

    def _prune(self) -> None:
        try:
            photos = sorted(photos_dir().glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return
        for old in photos[PHOTOS_KEEP:]:
            old.unlink(missing_ok=True)
