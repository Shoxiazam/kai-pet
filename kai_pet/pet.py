"""Кай — питомец на рабочем столе.

Что показывает, по важности:
1. разовая реакция или жест (машет, сердечко, лайк, танец…);
2. статус, если Кая подключили к ассистенту (работает, ждёт ответа);
3. эмоция по смыслу ненадолго;
4. курсор рядом — смотрит на него, на самом Кае — любопытство;
5. долго никого нет — спит;
6. фон: программа впереди, усталость после долгой работы, время суток.
Всё считается локально: имя программы, заголовок окна и время без ввода. Клавиши и экран не читаются.
"""
from __future__ import annotations

import ctypes
import datetime
import logging
import os
import random
import sys
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget

from . import commands
from .bubble import Bubble
from .config import Config

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent.parent / "assets"   # кадры: node character/export.mjs
FPS = {"moods": 12}     # живые эмоции дышат медленнее, остальное 24 к/с
CACHE_MAX = 10          # наборов кадров в памяти; одна эмоция ≈ 3 МБ
TIRED_EVERY_S, TIRED_FOR_S = 15 * 60, 20   # после долгой работы: раз в 15 минут устаёт на 20 секунд
FLASH_S = 8             # эмоция по смыслу держится после кивка
GESTURES = {"heart": "Сердечко", "like": "Лайк", "wave": "Помахать", "bye": "Попрощаться", "dance": "Станцевать",
            "hug": "Обнять", "bow": "Поклониться", "clap": "Похлопать", "jump": "Подпрыгнуть"}

# Эмоция по смыслу: ваша фраза и ответ ассистента. Без нейросети.
_CARE = ("устал", "грустн", "плохо", "надоел", "болит", "тяжело", "стресс", "не могу", "tired", "sad")
_THANKS = ("спасибо", "молодец", "круто", "класс", "отлично", "супер", "thank", "great")
_HELLO = ("привет", "здравств", "доброе утро", "добрый", "hello")
_CAUTION = ("осторожн", "внимани", "опасн", "не рекоменд", "warning")
_DONE = ("готово", "сделал", "отправил", "открыл", "сохранил", "нашёл", "нашел", "скачал", "done")

BREAK_HINTS = ("Ты уже долго работаешь. Может, пару минут отдохнём?",
               "Я тут подумал: как насчёт перерыва на чай?",
               "Глаза не устали? Можно ненадолго отвлечься, я подожду.")
WELCOME_HINTS = ("С возвращением! Продолжим?", "Рад тебя видеть. Чем займёмся?", "О, привет! Я соскучился.")


# --- что видно о пользователе (только Windows; на других системах эти сигналы просто молчат) ---
def input_idle_s() -> float:
    """Сколько секунд не было мыши и клавиатуры (сами клавиши не видны)."""
    if sys.platform != "win32":
        return 0.0

    class _LII(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    lii = _LII(ctypes.sizeof(_LII), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000


def active_window() -> tuple[str, str]:
    """(заголовок, имя программы) окна впереди."""
    if sys.platform != "win32":
        return "", ""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p,
                                                    ctypes.POINTER(ctypes.c_ulong)]
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    hwnd = ctypes.c_void_p(hwnd)
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    name = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        size = ctypes.c_ulong(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            name = os.path.basename(buf.value)
        kernel32.CloseHandle(handle)
    return title.value, name


# --- правила (без Qt, легко проверять) ---
def app_mood(moods: dict[str, str], title: str, process: str) -> str | None:
    text = f"{process} {title}".lower()
    for key, mood in moods.items():
        if key.lower() in text:
            return mood
    return None


def background_mood(app: str | None, hour: int, active_s: float, tired_after_s: float) -> str:
    """Фоновое настроение, когда ничего не происходит и курсор далеко."""
    if active_s > tired_after_s and active_s % TIRED_EVERY_S < TIRED_FOR_S:
        return "tired"
    if hour < 6 or hour >= 23:            # ночь: сонный, а если вы работаете — заботливый
        return "caring" if app else "sleepy"
    if app:
        return app
    return "curious" if hour < 11 else "idle"   # утром бодрый и любопытный


def look_at(dx: float, dy: float, radius: float, half: float) -> str | None:
    """Курсор относительно центра Кая → куда смотреть."""
    if abs(dx) <= half and abs(dy) <= half:
        return "curious"                      # курсор на самом Кае
    if dx * dx + dy * dy > radius * radius:
        return None
    if abs(dx) >= abs(dy):
        return "look_left" if dx < 0 else "look_right"
    return "look_up" if dy < 0 else "look_down"


def meaning_mood(heard: str, answer: str) -> str | None:
    """Что почувствовать Каю по вашей фразе и ответу."""
    h, a = heard.lower(), answer.lower()
    if any(w in h for w in _CARE):
        return "caring"
    if any(w in h for w in _THANKS):
        return "excited"
    if any(w in h for w in _HELLO):
        return "wave"
    if any(w in a for w in _CAUTION):
        return "cautious"
    if a.rstrip().endswith("?"):
        return "curious"
    if any(w in a for w in _DONE):
        return "proud"
    return None


class Pet(QWidget):
    clicked = Signal()
    quit_requested = Signal()

    def __init__(self, cfg: Config | None = None, assets: Path = ASSETS):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        if not (assets / "frames" / "idle").is_dir():
            raise FileNotFoundError(f"нет кадров Кая в {assets} — запустите node character/export.mjs")
        self.dir, self.cfg = assets, cfg or Config()
        self.size_px = self.cfg.size
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.size_px, self.size_px)
        self.cache: dict = {}
        self.loop, self.once, self.frame = "idle", None, 0   # статус и разовая реакция поверх фона
        self.repeat = 0                                       # сколько ещё раз повторить разовую реакцию
        self.last_event = time.monotonic()
        self.app: str | None = None                           # эмоция по программе впереди
        self.session_start = time.monotonic()                 # начало непрерывной работы
        self.away = False
        self.away_since = 0.0
        self.hints = self.cfg.hints
        self.last_hint = time.monotonic()
        self.heard = ""
        self.flash: tuple[str, float] | None = None          # эмоция ненадолго: (имя, до какого момента)
        self.bubble = Bubble()
        self.shown = ""
        self._pix = None
        self._press = None
        self._warned: set[str] = set()
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - self.size_px - 16, area.bottom() - self.size_px - 8)
        self.play("wave")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // 24)
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._observe)
        self._watch.start(2000)

    # --- API: подключение к своему ассистенту ---
    def set_status(self, status: str) -> None:
        """idle | working | waiting — что сейчас делает ваш ассистент."""
        self._touch()
        self.loop = status if status in ("working", "waiting") else "idle"
        if self.loop == "working" and not self.bubble.asking:
            self.bubble.hide()                 # реплика не должна закрывать экран, пока ассистент кликает

    def say(self, text: str, hide_after_ms: int = 12000) -> None:
        self.bubble.say(text, hide_after_ms)

    def ask(self, question: str) -> None:
        """Вопрос «да или нет»: ответ придёт сигналом self.bubble.answered(bool)."""
        self.set_status("waiting")
        self.bubble.ask(question)

    def hear(self, text: str) -> None:
        """Что сказал пользователь — для эмоции по смыслу в done()."""
        self.heard = text

    def done(self, answer: str = "") -> None:
        """Ассистент ответил: Кай кивает и ненадолго показывает эмоцию по смыслу."""
        self._touch()
        if self.once:           # огорчение или жест не перебиваем кивком
            return
        self.play("checking")
        mood = meaning_mood(self.heard, answer)
        self.heard = ""
        if mood and self._has(mood):
            self.flash = (mood, time.monotonic() + FLASH_S)

    def failed(self) -> None:
        self._touch()
        self.play("fail")

    def play(self, anim: str, times: int = 1) -> None:
        self.once, self.frame, self.repeat = anim, 0, times - 1

    def gesture(self, name: str, times: int = 2) -> None:
        """Жест (анимация) или эмоция на несколько секунд."""
        self._touch()
        if (self.dir / "frames" / name).is_dir():
            self.play(name, times)
        elif self._has(name):
            self.flash = (name, time.monotonic() + 3.0 * times)

    def command(self, text: str) -> bool:
        """Фраза Каю: «передай Антону привет», «покажи сердечко», «станцуй»… False — это не ему."""
        act = commands.parse(text)
        if not act:
            return False
        self.gesture(act.anim, act.times)
        self.say(act.say, 6000)
        return True

    # --- что делаете вы ---
    def _touch(self) -> None:
        self.last_event = time.monotonic()

    def _observe(self) -> None:
        """Раз в 2 секунды: программа впереди и ритм работы."""
        now = time.monotonic()
        idle = input_idle_s()
        if idle >= self.cfg.away_after_min * 60:
            if not self.away:
                self.away, self.away_since = True, now - idle
        elif self.away and idle < 3:
            self.away = False                  # вернулись после перерыва — радуемся
            self.session_start = now
            if not self.once and self.loop == "idle":
                self.play("wave")
                if now - self.away_since >= self.cfg.welcome_after_min * 60:
                    self._hint(WELCOME_HINTS)
        elif (self.loop == "idle" and now - self.session_start > self.cfg.tired_after_min * 60
              and now - self.last_hint >= self.cfg.break_hint_every_min * 60):
            self._hint(BREAK_HINTS)
        try:
            title, process = active_window()
            self.app = app_mood(self.cfg.moods, title, process)
        except (OSError, AttributeError) as e:   # окно закрылось на ходу — просто без эмоции программы
            log.debug("Активное окно не прочитано: %s", e)
            self.app = None

    def _hint(self, phrases) -> None:
        """Мягкая подсказка облачком. Выключается в меню Кая."""
        self.last_hint = time.monotonic()
        if self.hints and self.isVisible() and not self.bubble.asking:
            self.bubble.say(random.choice(phrases), 15000)

    def _idle_s(self) -> float:
        return min(input_idle_s(), time.monotonic() - self.last_event)

    def _cursor(self) -> QPoint:
        return QCursor.pos()

    def current(self) -> str:
        if self.once:
            return self.once
        if self.loop != "idle":
            return self.loop
        if self.flash:
            if time.monotonic() < self.flash[1]:
                return self.flash[0]
            self.flash = None
        c, g = self._cursor(), self.geometry()
        look = look_at(c.x() - g.center().x(), c.y() - g.center().y(), self.cfg.look_radius_px, self.size_px / 2)
        if look:
            return look
        if self._idle_s() > self.cfg.sleep_after_min * 60:
            return "sleepy"
        hour = datetime.datetime.now().hour
        mood = background_mood(self.app, hour, time.monotonic() - self.session_start, self.cfg.tired_after_min * 60)
        return mood if mood == "idle" or self._has(mood) else "idle"

    # --- кадры ---
    def _files(self, name: str) -> tuple[list[Path], int]:
        if name.startswith("look_"):
            return [self.dir / "look" / f"{name[5:]}.png"], 24
        for kind in ("frames", "moods"):
            files = sorted((self.dir / kind / name).glob("*.png"))
            if files:
                return files, FPS.get(kind, 24)
        return [], 24

    def _has(self, name: str) -> bool:
        if self._files(name)[0]:
            return True
        if name not in self._warned:           # опечатка в настройках не должна ронять Кая
            self._warned.add(name)
            log.warning("У Кая нет эмоции «%s» — проверьте moods в настройках", name)
        return False

    def _frames(self, name: str) -> tuple[list[QPixmap], int]:
        dpr = self.devicePixelRatioF()
        key = (name, dpr)
        if key not in self.cache:
            files, fps = self._files(name)
            if not files:
                return self._frames("idle")
            px = round(self.size_px * dpr)   # в настоящих пикселях экрана — без растягивания и мыла
            frames = []
            for f in files:
                pix = QPixmap(str(f)).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pix.setDevicePixelRatio(dpr)
                frames.append(pix)
            while len(self.cache) >= CACHE_MAX:   # самый старый набор — вон, память не растёт
                self.cache.pop(next(iter(self.cache)))
            self.cache[key] = (frames, fps)
        return self.cache[key]

    def _tick(self) -> None:
        name = self.current()
        if name != self.shown:
            self.shown, self.frame = name, 0
        frames, fps = self._frames(name)
        if self.frame >= len(frames):
            self.frame = 0
            if self.once and self.repeat > 0:   # жест — ещё раз
                self.repeat -= 1
            elif self.once:         # разовая реакция доиграла — к фону
                self.once = None
                self.shown = name = self.current()
                frames, fps = self._frames(name)
        self._pix = frames[self.frame]
        self.frame += 1
        self._timer.setInterval(1000 // fps)
        self.update()

    def paintEvent(self, _event):
        if self._pix is not None:
            QPainter(self).drawPixmap(0, 0, self._pix)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.bubble.place(self.geometry())       # облачко ездит за Каем

    def hideEvent(self, event):
        super().hideEvent(event)
        self.bubble.hide()

    # --- меню и мышь: клик — помахать, перетаскивание — переставить ---
    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.addAction("Сказать Каю…").triggered.connect(lambda _c=False: self._talk())
        gestures = menu.addMenu("Жесты")
        for name, title in GESTURES.items():
            gestures.addAction(title).triggered.connect(lambda _c=False, n=name: self.gesture(n, 2))
        menu.addSeparator()
        hints = QAction("Подсказки", menu)
        hints.setCheckable(True)
        hints.setChecked(self.hints)
        hints.toggled.connect(lambda on: setattr(self, "hints", on))
        menu.addAction(hints)
        menu.addAction("Выход").triggered.connect(lambda _c=False: self.quit_requested.emit())
        menu.exec(e.globalPos())

    def _talk(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Кай")
        dlg.setLabelText("Что сказать Каю? Например: «передай Антону привет», «покажи сердечко», «станцуй»")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec() and dlg.textValue().strip() and not self.command(dlg.textValue()):
            self.gesture("confused", 1)
            self.say("Я пока такого не умею. Попробуй «покажи сердечко» или «станцуй».", 6000)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = [e.globalPosition().toPoint(), self.pos(), False]

    def mouseMoveEvent(self, e):
        if self._press:
            start, origin, _ = self._press
            delta = e.globalPosition().toPoint() - start
            if abs(delta.x()) + abs(delta.y()) > 4:
                self._press[2] = True
            if self._press[2]:
                self.move(origin + QPoint(delta.x(), delta.y()))

    def mouseReleaseEvent(self, e):
        if self._press and e.button() == Qt.LeftButton:
            moved = self._press[2]
            self._press = None
            if not moved:
                self._touch()
                self.play("wave")
                self.clicked.emit()
