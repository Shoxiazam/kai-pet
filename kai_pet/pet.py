"""Кай — питомец на рабочем столе.

Что показывает, по важности:
1. разовая реакция или жест (машет, мурлычет, ест, сердечко, танец…);
2. статус, если Кая подключили к ассистенту (работает, ждёт ответа);
3. эмоция по смыслу ненадолго;
4. курсор рядом — смотрит на него, на самом Кае — любопытство;
5. играет музыка — кивает в такт;
6. долго никого нет — спит;
7. фон: программа впереди, усталость после долгой работы, время суток.
Всё считается локально: имя программы, заголовок и место окна, время без ввода, громкость звука.
Клавиши и экран не читаются.
"""
from __future__ import annotations

import collections
import ctypes
import datetime
import hashlib
import json
import logging
import math
import os
import random
import re
import shutil
import sys
import time
from pathlib import Path

from PySide6.QtCore import (QCoreApplication, QEvent, QPoint, QProcess, QProcessEnvironment, QPropertyAnimation, QRect,
                            Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QCursor, QDesktopServices, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget

from . import commands, sounds
from .bubble import Bubble
from .config import Config

log = logging.getLogger(__name__)

FROZEN = bool(getattr(sys, "frozen", False))
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
ASSETS = ROOT / "assets"                     # кадры: node character/export.mjs
# В KaiPet.exe папка с кадрами только для чтения — новые образы Кай рисует в профиль пользователя.
LOOKS_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "KaiPet" / "looks" if FROZEN else None
FPS = {"moods": 12}     # живые эмоции дышат медленнее, остальное 24 к/с
CACHE_MAX = 10          # наборов кадров в памяти; одна эмоция ≈ 3 МБ
TIRED_EVERY_S, TIRED_FOR_S = 15 * 60, 20   # после долгой работы: раз в 15 минут устаёт на 20 секунд
FLASH_S = 8             # эмоция по смыслу держится после кивка
MUSIC_LEVEL = 0.02      # громкость выше — звучит что-то
MUSIC_SAMPLES, MUSIC_NEED = 8, 6           # 8 замеров по 0,4 с: из них 6 громких — это музыка, а не «дзынь»
PET_DISTANCE, PET_GAP_S = 450, 0.8         # столько провести мышкой по Каю без пауз — погладили
FRIEND_LEVELS = (5, 15, 35, 70, 120)       # очки дружбы до каждого следующего сердечка
SNAP_PX = 48            # ближе к краю экрана — Кай прилипает и поворачивается лапками к этому краю
EDGE_ANGLE = {"bottom": 0, "left": 90, "top": 180, "right": 270}
DOCKS = {"corner": "В углу экрана", "window": "Сверху на активном окне", "free": "Где оставлю (липнет к краям)"}

# Гардероб — те же имена, что в character/kai.js (KINDS, PALETTES, ACCESSORIES).
KINDS = {"cat": "Котик", "fox": "Лисёнок", "bunny": "Зайка", "bear": "Мишка"}
COLORS = {"gray": "Серый", "ginger": "Рыжий", "graphite": "Графитовый", "terracotta": "Терракотовый",
          "sky": "Голубой", "mint": "Мятный", "lilac": "Сиреневый", "rose": "Розовый"}
ACCESSORIES = {"scarf": ("Шарфик", "neck"), "hat": ("Шапочка", "head"), "glasses": ("Очки", "face"),
               "headphones": ("Наушники", "head"), "crown": ("Корона", "head")}
DEFAULT_LOOK = {"kind": "cat", "color": "gray", "acc": []}
SLOTS = ("head", "neck", "face")
CUSTOM_MAX_BYTES = 200_000   # своя вещь — картинка, а не фотоальбом
CHASE_COOLDOWN_S = 6    # охотится за курсором не чаще
CHASE_RADIUS = 500      # трясти мышкой надо рядом с Каем
CHASE_STEP = 220        # на сколько пикселей подбегает (только если сидит «где оставлю»)
LOOKS_KEEP = 6          # готовых образов на диске; один ≈ 20 МБ
EXPORT_TIMEOUT_MS = 180_000
DRESSED = ("Как я тебе?", "Ну как, идёт?", "Новый образ готов!")

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


# --- память между запусками: образ, место, дружба, переключатели ---
def state_file() -> Path:
    """Путь можно сменить переменной KAI_PET_STATE."""
    return Path(os.environ.get("KAI_PET_STATE") or Path.home() / ".kai-pet-state.json")


def load_state() -> dict:
    try:
        data = json.loads(state_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(key: str, value) -> None:
    data = load_state()
    data[key] = value
    try:
        state_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError as e:                       # не записалось — Кай работает, просто не вспомнит
        log.warning("Состояние Кая не сохранено: %s", e)


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


def _foreground():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    hwnd = user32.GetForegroundWindow()
    return ctypes.c_void_p(hwnd) if hwnd else None


def active_window() -> tuple[str, str]:
    """(заголовок, имя программы) окна впереди."""
    if sys.platform != "win32":
        return "", ""
    user32 = ctypes.windll.user32
    hwnd = _foreground()
    if not hwnd:
        return "", ""
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    return title.value, os.path.basename(_exe_of(hwnd))


def _exe_of(hwnd) -> str:
    """Полный путь программы, которой принадлежит окно; "" — не удалось."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p,
                                                    ctypes.POINTER(ctypes.c_ulong)]
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    path = ""
    handle = kernel32.OpenProcess(0x1000, False, pid.value)   # PROCESS_QUERY_LIMITED_INFORMATION
    if handle:
        size = ctypes.c_ulong(1024)
        buf = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            path = buf.value
        kernel32.CloseHandle(handle)
    return path


def active_exe() -> str:
    """Полный путь программы окна впереди (для её значка)."""
    if sys.platform != "win32":
        return ""
    hwnd = _foreground()
    return _exe_of(hwnd) if hwnd else ""


def active_window_rect() -> tuple[int, int, int, int] | None:
    """(left, top, right, bottom) окна впереди в настоящих пикселях экрана."""
    if sys.platform != "win32":
        return None
    hwnd = _foreground()
    if not hwnd:
        return None

    class _RECT(ctypes.Structure):
        _fields_ = [(n, ctypes.c_long) for n in ("left", "top", "right", "bottom")]

    r = _RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    return r.left, r.top, r.right, r.bottom


_meter = [None, 0.0]                         # индикатор громкости и когда его открыли


def audio_peak() -> float:
    """Насколько громко сейчас что-то играет (0..1). Не Windows или нет pycaw — 0: Кай просто не танцует."""
    if sys.platform != "win32":
        return 0.0
    try:
        if _meter[0] is None or time.monotonic() - _meter[1] > 120:   # раз в 2 минуты: вдруг сменили наушники
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            dev = AudioUtilities.GetSpeakers()
            dev = getattr(dev, "_dev", dev)
            # QueryInterface, а не cast: cast не считает ссылку, и COM-объект освобождался дважды —
            # Python падал с access violation, когда сборщик мусора убирал старый индикатор.
            unknown = dev.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
            _meter[0] = unknown.QueryInterface(IAudioMeterInformation)
            _meter[1] = time.monotonic()
        return float(_meter[0].GetPeakValue())
    except Exception as e:                   # нет pycaw, нет устройства вывода — без танцев, без падения
        log.debug("Громкость не прочитана: %s", e)
        _meter[0] = None
        return 0.0


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


def snap_edge(x: int, y: int, size: int, area: QRect) -> tuple[int, int, str] | None:
    """Кая отпустили у края экрана → (x, y, край) вплотную к краю; далеко от краёв — None."""
    left, top = area.left(), area.top()
    right, bottom = left + area.width(), top + area.height()
    gaps = {"left": x - left, "right": right - (x + size), "top": y - top, "bottom": bottom - (y + size)}
    edge = min(gaps, key=gaps.get)
    if gaps[edge] > SNAP_PX:
        return None
    x, y = min(max(x, left), right - size), min(max(y, top), bottom - size)
    if edge == "left":
        x = left
    elif edge == "right":
        x = right - size
    elif edge == "top":
        y = top
    else:
        y = bottom - size
    return x, y, edge


def perch_on(rect, ratio: float, size: int, area: QRect) -> tuple[int, int] | None:
    """Окно впереди (настоящие пиксели) → где Каю сидеть на его верхней кромке; негде — None."""
    if not rect:
        return None
    left, top, right, bottom = (v / ratio for v in rect)
    if right - left < size * 2 or bottom - top < size or top - area.top() < size * 0.8:
        return None                           # окна нет, оно маленькое или развёрнуто во весь экран
    x = right - size - 160                    # правее середины, но не над кнопками «свернуть/закрыть»
    x = min(max(x, left + 8), area.left() + area.width() - size)
    return int(x), int(top - size * 0.93)     # лапки как раз на кромке окна


def accessories_dir() -> Path:
    """Папка своих вещей: KAI_ACCESSORIES или %LOCALAPPDATA%/KaiPet/accessories (~/.kai-pet/accessories)."""
    if os.environ.get("KAI_ACCESSORIES"):
        return Path(os.environ["KAI_ACCESSORIES"])
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "KaiPet" / "accessories" if base else Path.home() / ".kai-pet" / "accessories"


def custom_accessories(folder: Path | None = None) -> dict[str, tuple[str, str, Path]]:
    """Свои вещи: <место>-<название>.svg (head-bow.svg, neck-tie.svg, face-mask.svg) → {id: (название, место, файл)}.

    Без места в имени — на голову. Рисовать в координатах Кая 256×256 (голова — около 128,120).
    """
    folder = folder or accessories_dir()
    try:
        files = sorted(folder.glob("*.svg"))
    except OSError:
        return {}
    found = {}
    for f in files:
        slot, _, name = f.stem.partition("-")
        if slot not in SLOTS or not name:
            slot, name = "head", f.stem
        slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        if not slug or slug != name.lower():           # кириллица, пробелы — плюс короткий хэш, чтобы имена не совпали
            slug = (slug + "_" if slug else "") + hashlib.md5(name.encode()).hexdigest()[:6]
        found["my_" + slug] = (name, slot, f)
    return found


def all_accessories() -> dict[str, tuple[str, str]]:
    return {**ACCESSORIES, **{k: (ru, slot) for k, (ru, slot, _f) in custom_accessories().items()}}


def shaking(trail, now: float, window: float = 1.0, turns_needed: int = 4, travel: int = 600) -> bool:
    """Мышкой быстро трясут из стороны в сторону: ≥4 разворота и ≥600 px пути за секунду. trail — [(t, x)]."""
    pts = [(t, x) for t, x in trail if now - t <= window]
    turns, dist, last = 0, 0, 0
    for (_t0, x0), (_t1, x1) in zip(pts, pts[1:]):
        dx = x1 - x0
        if abs(dx) < 3:
            continue
        way = 1 if dx > 0 else -1
        dist += abs(dx)
        turns += bool(last and way != last)
        last = way
    return turns >= turns_needed and dist >= travel


def normalize_look(look) -> dict:
    """Только известные вид, цвет и вещи; на каждом месте (голова, шея, лицо) — одна вещь, последняя побеждает."""
    look = look if isinstance(look, dict) else {}
    slots: dict[str, str] = {}
    known = all_accessories()
    for item in look.get("acc") or []:
        if item in known:
            slots[known[item][1]] = item
    return {"kind": look.get("kind") if look.get("kind") in KINDS else "cat",
            "color": look.get("color") if look.get("color") in COLORS else "gray",
            "acc": sorted(slots.values())}


def look_id(look: dict) -> str:
    look = normalize_look(look)
    return f"{look['kind']}-{look['color']}-{'+'.join(look['acc']) or 'none'}"


def change_look(look: dict, op: dict) -> dict:
    """Команда гардеробу: {"kind"}, {"color"}, {"wear"}, {"remove": вещь | "all"}, {"reset"}, {"random"}."""
    look = normalize_look(look)
    if op.get("reset"):
        return normalize_look(DEFAULT_LOOK)
    if op.get("random"):
        acc = random.sample(sorted(ACCESSORIES), random.randint(0, 2))
        return normalize_look({"kind": random.choice(list(KINDS)), "color": random.choice(list(COLORS)), "acc": acc})
    if op.get("kind"):
        look["kind"] = op["kind"]
    if op.get("color"):
        look["color"] = op["color"]
    if op.get("wear"):
        look["acc"] = look["acc"] + [op["wear"]]
    if op.get("remove"):
        look["acc"] = [] if op["remove"] == "all" else [a for a in look["acc"] if a != op["remove"]]
    return normalize_look(look)


def season_key(day: datetime.date) -> str:
    """«winter-2026» с декабря 2026 по февраль 2027; вне зимы — пусто."""
    if day.month == 12:
        return f"winter-{day.year}"
    return f"winter-{day.year - 1}" if day.month in (1, 2) else ""


def effective_look(chosen: dict, day: datetime.date, birthday: str = "", seasonal: bool = True,
                   winter_off: str = "") -> dict:
    """Образ с сезонными вещами: зимой шапочка и шарф, в день рождения корона — только на свободные места."""
    look = normalize_look(chosen)
    if not seasonal:
        return look
    extra = []
    if birthday and day.strftime("%m-%d") == birthday:
        extra.append("crown")
    if season_key(day) and winter_off != season_key(day):
        extra += ["hat", "scarf"]
    taken = {ACCESSORIES[a][1] for a in look["acc"]}
    for item in extra:
        if ACCESSORIES[item][1] not in taken:
            look["acc"].append(item)
            taken.add(ACCESSORIES[item][1])
    return normalize_look(look)


def friend_level(points: int) -> int:
    return sum(points >= x for x in FRIEND_LEVELS)


class Pet(QWidget):
    clicked = Signal()
    quit_requested = Signal()

    def __init__(self, cfg: Config | None = None, assets: Path = ASSETS):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        if not (assets / "frames" / "idle").is_dir():
            raise FileNotFoundError(f"нет кадров Кая в {assets} — запустите node character/export.mjs")
        self.dir, self.cfg = assets, cfg or Config()
        self.base = assets                         # кадры обычного Кая; новые образы — в looks/<id>
        self._export: QProcess | None = None
        self._export_look: dict | None = None      # что сейчас готовится
        self._pending_look: dict | None = None     # что попросили, пока готовилось другое
        self.look = normalize_look(DEFAULT_LOOK)   # надетый образ (с сезонными вещами)
        state = load_state()
        self.chosen = normalize_look(state.get("look"))   # что выбрали вы
        self.size_px = self.cfg.size
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.size_px, self.size_px)
        self.setMouseTracking(True)                # поглаживание — движение мыши без нажатия
        self.cache: dict = {}
        self.loop, self.once, self.frame = "idle", None, 0   # статус и разовая реакция поверх фона
        self.repeat = 0                                       # сколько ещё раз повторить разовую реакцию
        self.last_event = time.monotonic()
        self.app: str | None = None                           # эмоция по программе впереди
        self.session_start = time.monotonic()                 # начало непрерывной работы
        self.away = False
        self.away_since = 0.0
        self.hints = bool(state.get("hints", self.cfg.hints))
        self.sounds_on = bool(state.get("sounds", self.cfg.sounds))
        self.dance_on = bool(state.get("dance", self.cfg.dance_to_music))
        self.seasonal = bool(state.get("seasonal", self.cfg.seasonal))
        self.chase_on = bool(state.get("chase", True))
        self._trail: collections.deque = collections.deque(maxlen=30)   # где был курсор: (время, x)
        self._last_chase = 0.0
        self._run: QPropertyAnimation | None = None
        self.friend = int(state.get("friend", 0) or 0)
        self.last_hint = time.monotonic()
        self.heard = ""
        self.flash: tuple[str, float] | None = None          # эмоция ненадолго: (имя, до какого момента)
        self.bubble = Bubble()
        self.shown = ""
        self.music = False
        self._peaks: collections.deque = collections.deque(maxlen=MUSIC_SAMPLES)
        self._stroke = [0.0, 0.0, None]                       # длина поглаживания, когда последнее движение, где
        self._last_pet_friend = 0.0
        self._pix = None
        self._press = None
        self._warned: set[str] = set()
        self._today = datetime.date.today()
        self.dock = state.get("dock") if state.get("dock") in DOCKS else "corner"
        try:
            self.angle = int(state.get("angle", 0)) % 360
        except (TypeError, ValueError):
            self.angle = 0
        self._snapped = False
        self._place_saved(str(state.get("pos", "")))
        self._mark_day()
        self.play("wave")
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // 24)
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._observe)
        self._watch.start(2000)
        self._perch = QTimer(self)
        self._perch.timeout.connect(self._follow_window)
        self._perch.start(400)
        self._ear = QTimer(self)
        self._ear.timeout.connect(self._listen)
        self._ear.start(400)
        wanted = self._effective()
        if wanted != self.look:
            QTimer.singleShot(0, lambda: self._wear(wanted, announce=False, greet=True))   # образ из прошлого раза

    def shutdown(self) -> None:
        """Перед выходом: всё остановить и удалить окна, пока Qt ещё жив.

        Иначе Python добирает окна Кая сборщиком мусора уже после закрытия Qt — и процесс падает на выходе.
        """
        for timer in (self._timer, self._watch, self._perch, self._ear):
            timer.stop()
        if self._export is not None:
            self._export.finished.disconnect()
            self._export.kill()
            self._export.waitForFinished(2000)
            self._export = None
        if self._run is not None:
            self._run.stop()
        _meter[0] = None                       # отпустить индикатор громкости, пока COM ещё работает
        self.bubble.deleteLater()
        self.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # --- гардероб: вид, цвет, аксессуары, сезонные вещи ---
    def looks_root(self) -> Path:
        return LOOKS_DIR or self.base / "looks"

    def look_dir(self, look: dict) -> Path:
        return self.base if look_id(look) == look_id(DEFAULT_LOOK) else self.looks_root() / look_id(look)

    def _effective(self, chosen: dict | None = None) -> dict:
        return effective_look(chosen or self.chosen, datetime.date.today(), self.cfg.birthday, self.seasonal,
                              load_state().get("winter_off", ""))

    def change_look(self, op: dict) -> None:
        """Команда гардеробу. Снять сезонную вещь — значит не надевать её до конца сезона."""
        removed = op.get("remove")
        seasonal_now = set(self._effective()["acc"]) - set(self.chosen["acc"])
        if removed and (removed == "all" or removed in seasonal_now) and season_key(datetime.date.today()):
            save_state("winter_off", season_key(datetime.date.today()))
        self.set_look(change_look(self.chosen, op))

    def set_look(self, look: dict, announce: bool = True) -> None:
        self.chosen = normalize_look(look)
        save_state("look", self.chosen)
        self._wear(self._effective(), announce)

    def _wear(self, look: dict, announce: bool, greet: bool = False) -> None:
        look = normalize_look(look)
        if self._export is not None:            # уже переодевается — этот образ следующим
            self._pending_look = look if look != self._export_look else None
            return
        if look == self.look:
            return
        if greet:
            self._greet_season(look)
        if (self.look_dir(look) / "frames" / "idle").is_dir():
            self._apply_look(look, announce)
        else:
            self._start_export(look, announce)

    def _greet_season(self, look: dict) -> None:
        """Сезонную вещь Кай надел сам — один раз скажет почему."""
        today, state = datetime.date.today(), load_state()
        added = set(look["acc"]) - set(self.chosen["acc"])
        if "crown" in added and state.get("birthday_greeted") != today.isoformat():
            save_state("birthday_greeted", today.isoformat())
            self.bubble.say("С днём рождения! Надел корону в твою честь.", 12000)
        elif added & {"hat", "scarf"} and state.get("winter_greeted") != season_key(today):
            save_state("winter_greeted", season_key(today))
            self.bubble.say("Зима пришла! Надел шапочку и шарфик.", 10000)

    def _apply_look(self, look: dict, announce: bool) -> None:
        self.look, self.dir = look, self.look_dir(look)
        self.cache.clear()
        self.shown = ""
        if self.dir != self.base:
            os.utime(self.dir)                  # свежий образ не удалится при уборке
        if announce:
            self.play("wave")
            self.bubble.say(random.choice(DRESSED), 6000)

    def _start_export(self, look: dict, announce: bool) -> None:
        """Кадры нового образа рисуются в фоне (≈20 с): node character/export.mjs с KAI_LOOK и KAI_OUT."""
        node, script = shutil.which("node"), ROOT / "character" / "export.mjs"
        if not node or not script.is_file():
            log.warning("Кай не может переодеться: нет node или %s", script)
            if announce:
                self.bubble.say("Не получается переодеться: нужен Node.js и Edge или Chrome.", 6000)
            return
        tmp = self.look_dir(look).with_name(look_id(look) + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("KAI_LOOK", json.dumps(look))
        env.insert("KAI_OUT", str(tmp))
        mine = custom_accessories()
        custom = {}
        for item in look["acc"]:
            if item in mine:
                _ru, slot, file = mine[item]
                try:
                    if file.stat().st_size <= CUSTOM_MAX_BYTES:
                        custom[item] = {"slot": slot, "svg": file.read_text(encoding="utf-8", errors="replace")}
                except OSError as e:
                    log.warning("Своя вещь %s не прочитана: %s", file, e)
        if custom:
            # shortcut: готовый образ кэшируется по имени вещи; поправили SVG — переименуйте файл
            env.insert("KAI_CUSTOM", json.dumps(custom))
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setProgram(node)
        proc.setArguments([str(script)])
        proc.finished.connect(lambda code, _status: self._export_done(look, tmp, code, announce))
        self._export, self._export_look = proc, look
        QTimer.singleShot(EXPORT_TIMEOUT_MS, lambda: proc.state() != QProcess.NotRunning and proc.kill())
        proc.start()
        if announce:
            self.bubble.say("Переодеваюсь… минутку", 25000)

    def _export_done(self, look: dict, tmp: Path, code: int, announce: bool) -> None:
        proc, self._export, self._export_look = self._export, None, None
        if proc is not None:
            proc.deleteLater()
        final = self.look_dir(look)
        if code == 0 and (tmp / "frames" / "idle").is_dir():
            shutil.rmtree(final, ignore_errors=True)
            tmp.rename(final)                   # половину кадров Кай никогда не увидит: папка появляется целиком
            self._prune_looks(keep=final)
            if self._pending_look is None:
                self._apply_look(look, announce)
        else:
            shutil.rmtree(tmp, ignore_errors=True)
            err = bytes(proc.readAllStandardError()).decode(errors="replace")[-300:] if proc else ""
            log.warning("Кай не переоделся (код %s): %s", code, err)
            self.bubble.say("Не получилось переодеться. Попробую в другой раз.", 6000)
        pending, self._pending_look = self._pending_look, None
        if pending is not None:
            self._wear(pending, announce)

    def _prune_looks(self, keep: Path) -> None:
        """На диске — не больше LOOKS_KEEP образов: самые давние удаляются, надетый и новый — никогда."""
        root = self.looks_root()
        dirs = sorted((d for d in root.iterdir() if d.is_dir() and not d.name.endswith(".tmp")),
                      key=lambda d: d.stat().st_mtime, reverse=True)
        for d in dirs[LOOKS_KEEP:]:
            if d not in (keep, self.dir):
                shutil.rmtree(d, ignore_errors=True)

    # --- погладить, угостить, дружба ---
    def petted(self) -> None:
        """Погладили мышкой: мурлычет и жмурится; дружба растёт не чаще раза в минуту."""
        if self.once == "purr":
            return
        self._touch()
        self.play("purr", 2)
        self._sound("purr")
        if time.monotonic() - self._last_pet_friend > 60:
            self._last_pet_friend = time.monotonic()
            self._befriend(1)

    def feed(self) -> None:
        """Печенька — раз в день. Второй раз Кай вежливо откажется."""
        today = datetime.date.today().isoformat()
        if load_state().get("last_fed") == today:
            self.bubble.say("Спасибо, я уже наелся! Давай завтра.", 5000)
            return
        save_state("last_fed", today)
        self._touch()
        self.play("eat")
        self._sound("munch")
        self.bubble.say("Ням! Спасибо за печеньку!", 5000)
        self._befriend(3)

    def _befriend(self, points: int) -> None:
        before = friend_level(self.friend)
        self.friend += points
        save_state("friend", self.friend)
        after = friend_level(self.friend)
        if after > before:
            self.bubble.say(f"Мы стали ещё ближе! Дружба: {'♥' * after}{'♡' * (len(FRIEND_LEVELS) - after)}", 8000)

    def friendship_text(self) -> str:
        lvl = friend_level(self.friend)
        days = int(load_state().get("days", 1) or 1)
        return f"Дружба: {'♥' * lvl}{'♡' * (len(FRIEND_LEVELS) - lvl)} · дней вместе: {days}"

    def _mark_day(self) -> None:
        today = datetime.date.today().isoformat()
        state = load_state()
        if state.get("last_day") != today:
            save_state("days", int(state.get("days", 0) or 0) + 1)
            save_state("last_day", today)

    def _sound(self, name: str) -> None:
        if self.sounds_on:
            sounds.play(self.base / "sounds" / f"{name}.wav")

    # --- музыка ---
    def _listen(self) -> None:
        if not self.dance_on:
            self.music = False
            return
        self._peaks.append(audio_peak())
        self.music = sum(p > MUSIC_LEVEL for p in self._peaks) >= MUSIC_NEED

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
        """Фраза Каю: «передай Антону привет», «покажи сердечко», «надень шарф»… False — это не ему."""
        act = commands.parse(text)
        if not act:
            return False
        self.gesture(act.anim, act.times)
        self.say(act.say, 6000)
        if act.look:                           # «надень шарф», «стань рыжим», «верни как было»
            self.change_look(act.look)
        return True

    # --- что делаете вы ---
    def _touch(self) -> None:
        self.last_event = time.monotonic()

    def _observe(self) -> None:
        """Раз в 2 секунды: программа впереди, ритм работы, новый день."""
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
        if datetime.date.today() != self._today:  # наступил новый день: зима, день рождения, счётчик дней
            self._today = datetime.date.today()
            self._mark_day()
            self._wear(self._effective(), announce=False, greet=True)

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
        if self.music:
            return "groove"
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
        self._maybe_chase()
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

    def _maybe_chase(self) -> None:
        """Мышкой трясут рядом с Каем — он охотится: подбегает к курсору и прыгает."""
        if not self.chase_on or self.once or self.loop != "idle" or self._press:
            return
        now, c = time.monotonic(), self._cursor()
        self._trail.append((now, c.x()))
        center = self.geometry().center()
        if (now - self._last_chase < CHASE_COOLDOWN_S
                or abs(c.x() - center.x()) + abs(c.y() - center.y()) > CHASE_RADIUS or not shaking(self._trail, now)):
            return
        self._last_chase = now
        self._trail.clear()
        self.hunt(c.x() - center.x())

    def hunt(self, dx: int) -> None:
        """Подбежать к курсору (если сидит «где оставлю») и прыгнуть на него."""
        self._touch()
        self._sound("meow")
        step = max(-CHASE_STEP, min(CHASE_STEP, dx))
        area = self._area()
        x = max(area.left(), min(area.right() - self.size_px, self.x() + step))
        if self.dock != "free" or abs(x - self.x()) < 30:
            self.play("jump", 2)
            return
        self.play("runRight" if step > 0 else "runLeft")
        self._run = QPropertyAnimation(self, b"pos", self)
        self._run.setDuration(700)
        self._run.setEndValue(QPoint(x, self.y()))
        self._run.finished.connect(self._caught)
        self._run.start()

    def _caught(self) -> None:
        self._run = None
        self._save_place()
        self.play("jump")

    def paintEvent(self, _event):
        if self._pix is None:
            return
        p = QPainter(self)
        if self.angle:
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            rad = math.radians(self.angle)
            k = 1 / (abs(math.cos(rad)) + abs(math.sin(rad)))   # повёрнутый Кай целиком влезает в окошко
            half = self.size_px / 2
            p.translate(half, half)
            p.rotate(self.angle)
            p.scale(k, k)
            p.translate(-half, -half)
        p.drawPixmap(0, 0, self._pix)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.bubble.place(self.geometry())       # облачко ездит за Каем

    def hideEvent(self, event):
        super().hideEvent(event)
        self.bubble.hide()

    # --- где сидит и как повёрнут ---
    def _area(self) -> QRect:
        screen = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _corner(self) -> QPoint:
        area = QGuiApplication.primaryScreen().availableGeometry()
        return QPoint(area.right() - self.size_px - 16, area.bottom() - self.size_px - 8)

    def _place_saved(self, pos: str) -> None:
        """Место из прошлого запуска, если тот экран всё ещё подключён; иначе — угол."""
        if self.dock == "free":
            try:
                x, y = (int(v) for v in pos.split(","))
            except ValueError:
                x = y = None
            if x is not None and any(s.availableGeometry().intersects(QRect(x, y, self.size_px, self.size_px))
                                     for s in QGuiApplication.screens()):
                self.move(x, y)
                return
        self.move(self._corner())

    def _save_place(self) -> None:
        save_state("dock", self.dock)
        save_state("angle", self.angle)
        save_state("pos", f"{self.x()},{self.y()}")

    def set_dock(self, mode: str) -> None:
        self.dock = mode if mode in DOCKS else "corner"
        if self.dock != "free":
            self.angle, self._snapped = 0, False   # в углу и на окне Кай стоит на лапках
        if self.dock == "corner":
            self.move(self._corner())
        self._follow_window()
        self._save_place()
        self.update()

    def set_angle(self, angle: int) -> None:
        self.angle = angle % 360
        self._save_place()
        self.update()

    def _follow_window(self) -> None:
        """Режим «на окне»: Кай сидит на верхней кромке окна впереди и ездит вместе с ним."""
        if self.dock != "window" or self._press:
            return
        try:
            rect = active_window_rect()
        except OSError as e:                         # окно закрылось на ходу — посидим в углу
            log.debug("Окно для Кая не прочитано: %s", e)
            rect = None
        ratio = 1.0 if sys.platform == "darwin" else self.devicePixelRatioF()   # окна Windows — в настоящих пикселях
        spot = perch_on(rect, ratio, self.size_px, self._area())
        target = QPoint(*spot) if spot else self._corner()
        if (target - self.pos()).manhattanLength() > 2:
            self.move(target)

    def _dropped(self) -> None:
        """Кая отпустили после перетаскивания: у края прилипает и ложится лапками к краю."""
        self.dock = "free"
        snap = snap_edge(self.x(), self.y(), self.size_px, self._area())
        if snap:
            x, y, edge = snap
            self.move(x, y)
            self.angle, self._snapped = EDGE_ANGLE[edge], True
        elif self._snapped:
            self.angle, self._snapped = 0, False   # оторвали от края — снова стоит ровно
        self._save_place()
        self.update()

    def wheelEvent(self, e):
        if e.modifiers() & Qt.ControlModifier:       # Ctrl + колёсико — плавный поворот
            self.set_angle(self.angle + (15 if e.angleDelta().y() < 0 else -15))
            e.accept()
        else:
            e.ignore()

    # --- меню ---
    def _toggle(self, menu: QMenu, title: str, checked: bool, slot) -> None:
        action = QAction(title, menu)
        action.setCheckable(True)
        action.setChecked(checked)
        action.toggled.connect(slot)
        menu.addAction(action)

    def _set_flag(self, key: str, attr: str, on: bool) -> None:
        setattr(self, attr, on)
        save_state(key, on)
        if key == "seasonal":
            self._wear(self._effective(), announce=True)

    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.addAction("Сказать Каю…").triggered.connect(lambda _c=False: self._talk())
        gestures = menu.addMenu("Жесты")
        for name, title in GESTURES.items():
            gestures.addAction(title).triggered.connect(lambda _c=False, n=name: self.gesture(n, 2))
        menu.addAction("Угостить печенькой").triggered.connect(lambda _c=False: self.feed())
        menu.addSeparator()
        dress = menu.addMenu("Внешность")
        current = self._pending_look or self._export_look or self.chosen
        for title, options, key in (("Вид", KINDS, "kind"), ("Цвет", COLORS, "color")):
            sub = dress.addMenu(title)
            for name, ru in options.items():
                action = sub.addAction(ru)
                action.setCheckable(True)
                action.setChecked(current[key] == name)
                action.triggered.connect(lambda _c=False, k=key, n=name: self.change_look({k: n}))
        things = dress.addMenu("Аксессуары")
        worn = set(self.look["acc"])
        for name, (ru, _slot) in all_accessories().items():
            action = things.addAction(ru)
            action.setCheckable(True)
            action.setChecked(name in worn)
            action.triggered.connect(lambda on, n=name: self.change_look({"wear": n} if on else {"remove": n}))
        things.addSeparator()
        things.addAction("Свои вещи (папка)…").triggered.connect(lambda _c=False: self.open_accessories())
        dress.addSeparator()
        dress.addAction("Удиви меня").triggered.connect(lambda _c=False: self.change_look({"random": True}))
        dress.addAction("Как было").triggered.connect(lambda _c=False: self.change_look({"reset": True}))
        place = menu.addMenu("Где сидеть")
        for mode, title in DOCKS.items():
            action = place.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.dock == mode)
            action.triggered.connect(lambda _c=False, m=mode: self.set_dock(m))
        turn = menu.addMenu("Повернуть")
        for title, delta in (("По часовой ↻", 90), ("Против часовой ↺", -90), ("Вверх лапками", 180)):
            turn.addAction(title).triggered.connect(lambda _c=False, d=delta: self.set_angle(self.angle + d))
        turn.addAction("Ровно").triggered.connect(lambda _c=False: self.set_angle(0))
        turn.addSeparator()
        turn.addAction("Плавно: Ctrl + колёсико мыши").setEnabled(False)
        settings = menu.addMenu("Настройки")
        self._toggle(settings, "Подсказки", self.hints, lambda on: self._set_flag("hints", "hints", on))
        self._toggle(settings, "Звуки", self.sounds_on, lambda on: self._set_flag("sounds", "sounds_on", on))
        self._toggle(settings, "Танцевать под музыку", self.dance_on, lambda on: self._set_flag("dance", "dance_on", on))
        self._toggle(settings, "Сезонные образы", self.seasonal, lambda on: self._set_flag("seasonal", "seasonal", on))
        self._toggle(settings, "Охотиться за мышкой", self.chase_on, lambda on: self._set_flag("chase", "chase_on", on))
        menu.addSeparator()
        menu.addAction(self.friendship_text()).setEnabled(False)
        menu.addAction("Выход").triggered.connect(lambda _c=False: self.quit_requested.emit())
        self._show_menu(menu, e.globalPos())

    def open_accessories(self) -> None:
        """Открыть папку своих вещей; новые SVG появляются в «Аксессуарах» без перезапуска."""
        folder = accessories_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.bubble.say("Положи сюда SVG: head-бант.svg, neck-галстук.svg или face-маска.svg", 10000)

    def _show_menu(self, menu: QMenu, pos: QPoint) -> None:
        menu.exec(pos)

    def _talk(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Кай")
        dlg.setLabelText("Что сказать Каю? Например: «передай Антону привет», «покажи сердечко», «надень шарф»")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec() and dlg.textValue().strip() and not self.command(dlg.textValue()):
            self.gesture("confused", 1)
            self.say("Я пока такого не умею. Попробуй «покажи сердечко» или «станцуй».", 6000)

    # --- мышь: клик — помахать, перетаскивание — переставить, поглаживание — мурлыкать ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            if self._run is not None:              # схватили на бегу — бег не тянет Кая из рук
                self._run.stop()
                self._run = None
            self._press = [e.globalPosition().toPoint(), self.pos(), False]

    def mouseMoveEvent(self, e):
        if self._press:
            start, origin, _ = self._press
            delta = e.globalPosition().toPoint() - start
            if abs(delta.x()) + abs(delta.y()) > 4:
                self._press[2] = True
            if self._press[2]:
                self.move(origin + QPoint(delta.x(), delta.y()))
            return
        now, pos = time.monotonic(), e.globalPosition()
        length, last_t, last_pos = self._stroke
        if last_pos is None or now - last_t > PET_GAP_S:
            length = 0.0
        else:
            length += abs(pos.x() - last_pos.x()) + abs(pos.y() - last_pos.y())
        self._stroke = [length, now, pos]
        if length > PET_DISTANCE:
            self._stroke = [0.0, now, pos]
            self.petted()

    def mouseReleaseEvent(self, e):
        if self._press and e.button() == Qt.LeftButton:
            moved = self._press[2]
            self._press = None
            if moved:
                self._dropped()
            else:
                self._touch()
                self.play("wave")
                self._sound("meow")
                self.clicked.emit()
