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
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from PySide6.QtCore import (QByteArray, QCoreApplication, QEvent, QPoint, QProcess, QProcessEnvironment, QPropertyAnimation, QRect, QRectF,
                            Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QAction, QColor, QCursor, QDesktopServices, QFont, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QInputDialog, QMenu, QWidget

from . import commands, guard, sounds
from .bubble import Bubble
from .config import Config
from .friend import FRIENDS, Friends
from .games import GAMES, Games

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
EAR_MS = 100           # громкость — 10 раз в секунду: хватает, чтобы услышать темп
MUSIC_SAMPLES, MUSIC_NEED = 32, 24         # 32 замера (3,2 с): из них 24 громких — это музыка, а не «дзынь»
STYLE_WINDOW = 100      # 10 с громкости — по ним выбирается танец
STYLE_EVERY_S = 15      # танец пересматривается не чаще, чтобы не дёргался
# Настроение музыки → танцы; внутри настроения танцы сменяются, чтобы не надоедало.
MUSIC_MOODS = {
    "sad": ("sadsway",), "calm": ("sway", "waltz"), "classical": ("waltz", "sway"),
    "rock": ("headbang", "airguitar"), "hiphop": ("hiphop", "groove"), "electronic": ("robot", "bounce"),
    "happy": ("disco", "clapdance", "dance"), "energetic": ("bounce", "disco"), "normal": ("groove", "clapdance", "hiphop"),
}
DANCES = {d for ds in MUSIC_MOODS.values() for d in ds}
# Слова в названии трека, по порядку: «sad piano» — грустная, а не спокойная.
_MOOD_WORDS = [
    ("sad", r"\bsad\b|грустн|печальн|slowed|tears|alone|lonely|одиноч|депресс|melanchol|разбит|плачу|слёз|слез"),
    ("rock", r"\b(?:rock|metal\w*|punk|grunge|рок|метал\w*|панк)\b"),
    ("hiphop", r"\b(?:rap|hip[- ]?hop|drill|trap)\b|рэп|\bреп\b|хип[- ]?хоп"),
    ("classical", r"classical|waltz|orchestra|symphon|вальс|оркестр|симфон|классическ|моцарт|бетховен|чайковск"),
    ("calm", r"lo-?fi|chill|piano|jazz|ambient|sleep|relax|acoustic|колыбел|спокойн|медитац|пианино|джаз"),
    ("electronic", r"\b(?:techno|house|edm|electro\w*|dubstep|trance|synth\w*)\b|техно|электрон"),
    ("happy", r"\b(?:disco|funk|pop|party|summer|happy)\b|диско|вечеринк|весел|весёл|\bлето\b|летн"),
    ("energetic", r"\b(?:dance|phonk|drum|dnb|club|remix|hardstyle|workout)\b|танцев|клубн|фонк|тренировк"),
]
_MOOD_RX = [(m, re.compile(rx)) for m, rx in _MOOD_WORDS]
SIGN_RECT = (44, 194, 168, 42)   # где писать на табличке: x, y, ширина, высота в кадре 256 (character/kai.js, SIGN)
SIGN_MAX = 60
NEWEST_ANIM = "sign"    # в образе нет этих кадров — нарисован старой версией, перерисовать
WEATHER_EVERY_MS = 30 * 60 * 1000
RAIN = set(range(51, 68)) | {80, 81, 82, 95, 96, 99}     # коды погоды WMO (Open-Meteo)
SNOW = set(range(71, 78)) | {85, 86}
PET_DISTANCE, PET_GAP_S = 450, 0.8         # столько провести мышкой по Каю без пауз — погладили
FRIEND_LEVELS = (5, 15, 35, 70, 120)       # очки дружбы до каждого следующего сердечка
SNAP_PX = 48            # ближе к краю экрана — Кай прилипает и поворачивается лапками к этому краю
EDGE_ANGLE = {"bottom": 0, "left": 90, "top": 180, "right": 270}
DOCKS = {"corner": "В углу экрана", "window": "Сверху на активном окне",
         "free": "Где оставлю: на столе или на любом окне"}
PIN_FOLLOW_MS = 150     # как часто Кай догоняет окно, за которое держится
_NOT_WINDOWS = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}   # рабочий стол и панель задач
# Танцевать только под музыку: кто звучит — музыкальная программа, браузер/плеер или что-то другое (звонок, игра).
MUSIC_APPS = {"spotify.exe", "yandexmusic.exe", "яндекс музыка.exe", "aimp.exe", "foobar2000.exe", "winamp.exe",
              "itunes.exe", "applemusic.exe", "music.ui.exe", "musicbee.exe", "tidal.exe", "deezer.exe",
              "audacious.exe", "clementine.exe", "strawberry.exe", "vkmusic.exe", "boom.exe"}
MEDIA_APPS = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "browser.exe", "brave.exe", "vivaldi.exe",
              "arc.exe", "yandex.exe", "vlc.exe", "mpc-hc64.exe", "mpc-hc.exe", "potplayermini64.exe",
              "potplayermini.exe", "wmplayer.exe", "microsoft.media.player.exe"}
_MUSIC_TITLE = re.compile(r"music|музык|spotify|soundcloud|песн|\bsong|lyrics|official (?:music )?video|клип|remix|"
                          r"\bfeat\.|\bft\.|playlist|плейлист|radio|радио|album|альбом|\bmix\b|микс|cover|кавер|"
                          r"lo-?fi|\bbeats?\b|\bost\b|саундтрек|soundtrack|концерт|concert|\bdj\b")
_TALK_TITLE = re.compile(r"podcast|подкаст|interview|интервью|lecture|лекци|урок|tutorial|обзор|review|\bnews\b|"
                         r"новост|стрим|\bstream|vlog|влог|разбор|курс|вебинар|webinar|звонок|meeting|встреча")
# Забота: фокус, глаза, батарея, нагрузка, отчёт за день.
FOCUS_MIN = 25
DISTRACT = re.compile(r"youtube|instagram|tiktok|vk\.com|вконтакте|facebook|twitter|\bx\.com|reddit|twitch|netflix|"
                      r"кинопоиск|pinterest|9gag|shorts")
DISTRACT_EVERY_S = 120   # в фокусе напоминает не чаще
EYES_EVERY_S = 20 * 60   # 20-20-20: каждые 20 минут — 20 секунд вдаль
EYES_REST_S = 20
BATTERY_LOW = 15
CPU_HOT, CPU_HOT_S = 85, 30          # загрузка выше 85 % полминуты — «жарко»
CARE_EVERY_S = 10 * 60               # про батарею и нагрузку — не чаще
REPORT_HOUR = 21                     # вечером — отчёт за день (один раз)
APP_NAMES = {"chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "code.exe": "VS Code",
             "telegram.exe": "Telegram", "explorer.exe": "Проводник", "winword.exe": "Word", "excel.exe": "Excel",
             "powerpnt.exe": "PowerPoint", "figma.exe": "Figma", "spotify.exe": "Spotify", "discord.exe": "Discord",
             "windowsterminal.exe": "Терминал", "pycharm64.exe": "PyCharm", "notepad.exe": "Блокнот",
             "obsidian.exe": "Obsidian", "claude.exe": "Claude", "browser.exe": "Яндекс Браузер"}
DIPS_MAX = 0.12         # у речи между словами тишина — больше 12 % провалов, у музыки звук почти не стихает
_TITLE_TAIL = re.compile(r"\s[-–—]\s(?:youtube|google chrome|mozilla firefox|microsoft\S*\s?edge|яндекс\s?браузер|"
                         r"opera|brave|vivaldi|vlc media player|media player)\b.*$")
_SONG_TITLE = re.compile(r"^[^:?!|/]{1,40}\s[-–—]\s[^:?!|/]{1,60}$")   # «Исполнитель - Песня»

# Гардероб — те же имена, что в character/kai.js (KINDS, PALETTES, ACCESSORIES).
KINDS = {"cat": "Котик", "fox": "Лисёнок", "bunny": "Зайка", "bear": "Мишка"}
COLORS = {"gray": "Серый", "ginger": "Рыжий", "graphite": "Графитовый", "terracotta": "Терракотовый",
          "sky": "Голубой", "mint": "Мятный", "lilac": "Сиреневый", "rose": "Розовый"}
ACCESSORIES = {"scarf": ("Шарфик", "neck"), "hat": ("Шапочка", "head"), "glasses": ("Очки", "face"),
               "headphones": ("Наушники", "ears"), "crown": ("Корона", "head"),
               "sunglasses": ("Тёмные очки", "face"), "umbrella": ("Зонтик", "hand"),
               "bow": ("Бантик", "hair"), "bowtie": ("Бабочка", "chest"), "flowers": ("Венок", "head"),
               # одежда (те же имена, что CLOTHES в character/kai.js)
               "tshirt": ("Футболка", "body"), "hoodie": ("Худи", "body"), "sweater": ("Свитер", "body"),
               "raincoat": ("Дождевик", "body"), "tuxedo": ("Смокинг", "body"), "pajama": ("Пижама", "body"),
               "overalls": ("Комбинезон", "body"), "cape": ("Плащ героя", "back"),
               # костюмы целиком (COSTUMES): капюшон вместо шапки, комбинезон вместо одежды
               "shark": ("Акулёнок", "costume"), "dino": ("Динозаврик", "costume"), "bee": ("Пчёлка", "costume"),
               "frog": ("Лягушонок", "costume")}
WARDROBE_MENUS = {"body": "Одежда", "back": "Одежда", "costume": "Костюмы"}   # остальные места — в «Аксессуарах»
COSTUME_HIDES = ("head", "hair", "ears", "body", "back")      # что костюм-кигуруми закрывает собой
UNLOCKS = {"bow": 2, "bowtie": 3, "flowers": 4}     # награды за дружбу: вещь → на каком сердечке открывается
FIDGETS = ("wash", "chasetail", "stretch", "yawn")  # мелочи от скуки
FIDGET_EVERY_S = (150, 360)                          # раз в 2,5–6 минут, когда ничего не происходит
MISS_AFTER_H = 24                                    # не гладили и не кормили сутки — скучает
DEFAULT_LOOK = {"kind": "cat", "color": "gray", "acc": []}
SLOTS = ("head", "neck", "face", "hand", "body")   # куда можно класть свои SVG
CUSTOM_MAX_BYTES = 2_000_000  # своя вещь — картинка, а не фотоальбом
# Куда ставить скачанную вещь в кадре 256: x, y, ширина, высота, выравнивание (шапка садится на макушку).
SLOT_BOX = {"body": (60, 170, 136, 62, "xMidYMid"), "head": (68, 34, 120, 92, "xMidYMax"), "neck": (66, 166, 124, 44, "xMidYMid"),
            "face": (76, 124, 104, 56, "xMidYMid"), "hand": (164, 140, 84, 92, "xMidYMid")}
SVG_NS, XLINK_NS = "http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"
_BG_ID = re.compile(r"^(?:background|bg|фон)", re.I)
_SHAPES = {"path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "text", "image", "use"}
DEFAULT_FIT = {"scale": 1.0, "dx": 0.0, "dy": 0.0, "rot": 0.0, "mirror": False}   # своя подгонка вещи
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


_sessions: list = [None, 0.0]             # [(программа, индикатор громкости)], когда собрали


def audible_apps() -> set[str] | None:
    """Какие программы сейчас звучат (имена .exe строчными). None — узнать нельзя (не Windows, нет pycaw)."""
    if sys.platform != "win32":
        return None
    try:
        if _sessions[0] is None or time.monotonic() - _sessions[1] > 10:   # новые программы — раз в 10 с
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            found = []
            for s in AudioUtilities.GetAllSessions():
                try:
                    if s.Process is not None:
                        found.append((s.Process.name().lower(), s._ctl.QueryInterface(IAudioMeterInformation)))
                except Exception:                # программа как раз закрылась — без неё
                    continue
            _sessions[0], _sessions[1] = found, time.monotonic()
        return {name for name, meter in _sessions[0] if meter.GetPeakValue() > MUSIC_LEVEL}
    except Exception as e:
        log.debug("Звучащие программы не прочитаны: %s", e)
        _sessions[0] = None
        return None


def sustained(levels, window: int = 50) -> bool:
    """Звук почти не стихает (музыка), а не прерывается паузами (речь). levels — 10 замеров в секунду."""
    recent = list(levels)[-window:]
    if len(recent) < 30:
        return True                            # ещё не наслушались — решит программа и название
    mean = sum(recent) / len(recent)
    return mean > 0 and sum(v < 0.1 * mean for v in recent) / len(recent) <= DIPS_MAX


def media_title(title: str) -> str:
    """Название ролика или трека без «(3)», « - YouTube», « - Google Chrome»."""
    t = re.sub(r"^\(\d+\)\s*", "", title.strip().lower())
    for _ in range(2):                          # « - YouTube - Google Chrome»
        t = _TITLE_TAIL.sub("", t)
    return t


def is_music(apps: set[str] | None, title: str, levels) -> bool:
    """Танцевать ли. Музыкальная программа — да; звонок, игра, система — нет. Браузер и плеер — только если
    по названию это песня (music, клип, lyrics, «Исполнитель - Песня») и звук ровный: обзоры и игры — нет."""
    if apps is not None:
        if apps & MUSIC_APPS:
            return True
        if not apps & MEDIA_APPS:
            return False
    t = media_title(title)
    if _TALK_TITLE.search(t):
        return False
    if _MUSIC_TITLE.search(t):
        return True
    return bool(_SONG_TITLE.match(t)) and sustained(levels)


def window_at(x: int, y: int, skip: set[int]) -> tuple[int, str] | None:
    """Верхнее обычное окно в точке (настоящие пиксели), кроме своих: (hwnd, заголовок). Стол и панель — None."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32

    class _RECT(ctypes.Structure):
        _fields_ = [(n, ctypes.c_long) for n in ("left", "top", "right", "bottom")]

    found: list = []

    def visit(hwnd, _param):
        if not hwnd or hwnd in skip:
            return True
        h = ctypes.c_void_p(hwnd)
        if not user32.IsWindowVisible(h) or user32.IsIconic(h):
            return True
        if user32.GetWindowLongW(h, -20) & 0x80:          # WS_EX_TOOLWINDOW: всплывашки, сам Кай
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value in _NOT_WINDOWS:
            return True
        cloaked = ctypes.c_int(0)                          # скрытые окна приложений Windows
        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        r = _RECT()
        if cloaked.value or not user32.GetWindowRect(h, ctypes.byref(r)):
            return True
        if not (r.left <= x < r.right and r.top <= y < r.bottom):
            return True
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, title, 256)
        if title.value:
            found.append((hwnd, title.value))
            return False                                   # первое сверху — то, что видно
        return True
    proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit)
    user32.EnumWindows(proc, 0)
    return found[0] if found else None


def window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Где окно (настоящие пиксели); None — окно закрыли."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    h = ctypes.c_void_p(hwnd)
    if not user32.IsWindow(h):
        return None

    class _RECT(ctypes.Structure):
        _fields_ = [(n, ctypes.c_long) for n in ("left", "top", "right", "bottom")]

    r = _RECT()
    return (r.left, r.top, r.right, r.bottom) if user32.GetWindowRect(h, ctypes.byref(r)) else None


def battery() -> tuple[int, bool] | None:
    """(заряд %, на зарядке). None — батареи нет или узнать нельзя (настольный компьютер, не Windows)."""
    if sys.platform != "win32":
        return None

    class _SPS(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_ubyte), ("flag", ctypes.c_ubyte), ("percent", ctypes.c_ubyte),
                    ("saver", ctypes.c_ubyte), ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]

    s = _SPS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)) or s.flag & 128 or s.percent > 100:
        return None                              # 128 — батареи нет, 255 — заряд неизвестен
    return int(s.percent), s.ac == 1


_cpu_prev: list = [None]


def cpu_load() -> float | None:
    """Загрузка процессора с прошлого вызова, 0..100. None — первый замер или не Windows."""
    if sys.platform != "win32":
        return None
    idle, kernel, user = (ctypes.c_ulonglong() for _ in range(3))
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return None
    now = (idle.value, kernel.value + user.value)          # kernel уже включает простой
    prev, _cpu_prev[0] = _cpu_prev[0], now
    if prev is None or now[1] <= prev[1]:
        return None
    return max(0.0, min(100.0, 100.0 * (1 - (now[0] - prev[0]) / (now[1] - prev[1]))))


def usage_file() -> Path:
    return Path(os.environ.get("KAI_PET_USAGE") or Path.home() / ".kai-pet-usage.json")


def app_name(process: str) -> str:
    p = process.lower()
    return APP_NAMES.get(p) or (Path(p).stem[:1].upper() + Path(p).stem[1:] if p else "Другое")


def human_time(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60} ч {m % 60} мин" if m >= 60 else f"{max(m, 1)} мин"


def usage_report(day: dict, top: int = 4) -> str:
    """«Сегодня: VS Code 2 ч 10 мин, Chrome 50 мин…» — по секундам на программу."""
    items = sorted(((s, app_name(p)) for p, s in day.items() if s >= 60), reverse=True)
    if not items:
        return "Сегодня ты почти не сидел за компьютером."
    total = sum(s for s, _n in items)
    parts = ", ".join(f"{name} {human_time(s)}" for s, name in items[:top])
    return f"Сегодня за компьютером {human_time(total)}: {parts}."


def window_minimized(hwnd: int) -> bool:
    return sys.platform == "win32" and bool(ctypes.windll.user32.IsIconic(ctypes.c_void_p(hwnd)))


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
    """Курсор относительно центра Кая → куда смотреть: 16 направлений, близко (n) или далеко (a)."""
    if abs(dx) <= half and abs(dy) <= half:
        return "curious"                      # курсор на самом Кае
    dist = math.hypot(dx, dy)
    if dist > radius:
        return None
    i = round(math.atan2(dy, dx) / (math.tau / 16)) % 16   # 0 — вправо, по часовой (y вниз)
    return f"look_{'n' if dist < radius * 0.4 else 'a'}{i:02d}"


def tempo_bpm(levels, hz: int = 10) -> float | None:
    """Темп по громкости (замеры hz раз в секунду): самый похожий на себя сдвиг, 60..200 ударов в минуту."""
    n = len(levels)
    if n < 40:
        return None
    mean = sum(levels) / n
    x = [v - mean for v in levels]
    var = sum(v * v for v in x)
    if var <= 1e-9:
        return None
    best, lag_best = 0.1, None                 # слабее 0,1 — ритма не слышно
    for lag in range(3, 11):                   # 0,3..1,0 с между ударами
        r = sum(x[i] * x[i + lag] for i in range(n - lag)) / var
        if r > best:
            best, lag_best = r, lag
    return 60 * hz / lag_best if lag_best else None


def music_mood(levels, title: str = "") -> str:
    """Настроение музыки: по словам в названии трека, иначе по темпу и силе звука (грусть по звуку не угадать)."""
    t = title.lower()
    for mood, rx in _MOOD_RX:
        if rx.search(t):
            return mood
    if len(levels) < 40:
        return "normal"
    mean = sum(levels) / len(levels)
    if mean <= 0:
        return "normal"
    cv = (sum((v - mean) ** 2 for v in levels) / len(levels)) ** 0.5 / mean   # насколько звук «скачет»
    bpm = tempo_bpm(levels)
    if (bpm and bpm >= 125) or cv >= 0.6:
        return "energetic"
    if cv <= 0.25 or (bpm and bpm <= 80 and cv < 0.4):
        return "calm"
    return "normal"


def dance_for(mood: str, previous: str = "") -> str:
    """Танец под настроение; если вариантов несколько — не тот же, что сейчас."""
    options = MUSIC_MOODS.get(mood, MUSIC_MOODS["normal"])
    fresh = [d for d in options if d != previous] or list(options)
    return random.choice(fresh)


def weather_items(temp: float, code: int) -> list[str]:
    """Что надеть: холодно или снег — шапка и шарф, прохладно — шарф, дождь — зонтик, жара и солнце — тёмные очки."""
    items = []
    if code in RAIN:
        items.append("umbrella")
    if temp <= 3 or code in SNOW:
        items += ["hat", "scarf"]
    elif temp <= 12:
        items.append("scarf")
    if temp >= 24 and code <= 2:
        items.append("sunglasses")
    return items


def weather_words(code: int) -> str:
    if code in SNOW:
        return "снег"
    if code >= 95:
        return "гроза"
    if code in RAIN:
        return "дождь"
    if code in (45, 48):
        return "туман"
    return "ясно" if code <= 1 else "облачно"


def fetch_weather(city: str, geo: dict | None) -> tuple[dict, float, int]:
    """Open-Meteo без ключа: город → координаты (запоминаются), затем погода сейчас. Сетевые ошибки — наружу."""
    if not geo or geo.get("city") != city:
        q = urllib.parse.urlencode({"name": city, "count": 1, "language": "ru"})
        with urllib.request.urlopen(f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=10) as r:
            found = (json.load(r).get("results") or [None])[0]
        if not found:
            raise LookupError(f"город «{city}» не найден")
        geo = {"city": city, "name": found.get("name", city), "lat": found["latitude"], "lon": found["longitude"]}
    q = urllib.parse.urlencode({"latitude": geo["lat"], "longitude": geo["lon"], "current": "temperature_2m,weather_code"})
    with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=10) as r:
        now = json.load(r)["current"]
    return geo, float(now["temperature_2m"]), int(now["weather_code"])


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


def _viewbox(root) -> tuple[float, float, float, float] | None:
    try:
        if root.get("viewBox"):
            x, y, w, h = (float(v) for v in re.split(r"[\s,]+", root.get("viewBox").strip()))
        else:
            x = y = 0.0
            w, h = (float(re.sub(r"[^\d.]", "", root.get(k, ""))) for k in ("width", "height"))
    except ValueError:
        return None
    return (x, y, w, h) if w > 0 and h > 0 else None


def _strip_background(root, vb) -> None:
    """Убрать фон: слой с id «background»/«bg» и прямоугольники на весь холст."""
    parents = {child: parent for parent in root.iter() for child in parent}
    for el in list(root.iter()):
        tag = el.tag.rsplit("}", 1)[-1]
        full = False
        if tag == "rect":
            try:
                w, h = (float(re.sub(r"[^\d.]", "", el.get(k, "0")) or 0) for k in ("width", "height"))
                full = w >= vb[2] * 0.95 and h >= vb[3] * 0.95
            except ValueError:
                pass
        if (full or _BG_ID.match(el.get("id", ""))) and el in parents:
            parents[el].remove(el)


def _content_box(svg_text: str, vb) -> tuple[float, float, float, float]:
    """Где сам рисунок: самое большое связное пятно (без подписи «designed by…» в углу), в координатах viewBox."""
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not renderer.isValid():
        return vb
    n = 128
    img = QImage(n, n, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    renderer.render(painter)                   # растягивает viewBox на всё изображение — пересчёт линейный
    painter.end()
    ink = {(x, y) for y in range(n) for x in range(n) if img.pixelColor(x, y).alpha() > 24}
    if not ink:
        return vb
    grow = {(x + dx, y + dy) for x, y in ink for dx in (-2, 0, 2) for dy in (-2, 0, 2)}   # склеить детали рисунка
    best: set = set()
    seen: set = set()
    for start in grow:
        if start in seen:
            continue
        blob, todo = set(), [start]
        seen.add(start)
        while todo:
            x, y = todo.pop()
            blob.add((x, y))
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in grow and nb not in seen:
                    seen.add(nb)
                    todo.append(nb)
        if len(blob & ink) > len(best & ink):
            best = blob
    pts = best & ink
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts) + 1
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts) + 1
    sx, sy = vb[2] / n, vb[3] / n
    return vb[0] + x0 * sx, vb[1] + y0 * sy, (x1 - x0) * sx, (y1 - y0) * sy


def _drop_outside(root, box) -> None:
    """Убрать то, что вне рисунка (подпись «designed by…», логотипы): по границам каждой фигуры."""
    shapes = [el for el in root.iter() if el.tag.rsplit("}", 1)[-1] in _SHAPES]
    tagged = []
    for i, el in enumerate(shapes):
        if not el.get("id"):
            el.set("id", f"kaifit{i}")
            tagged.append(el)
    renderer = QSvgRenderer(QByteArray(ET.tostring(root, encoding="unicode").encode("utf-8")))
    keep = QRectF(*box)
    if renderer.isValid():
        parents = {child: parent for parent in root.iter() for child in parent}
        for el in shapes:
            sid = el.get("id")
            bounds = renderer.transformForElement(sid).mapRect(renderer.boundsOnElement(sid))
            if not bounds.isEmpty() and not bounds.intersects(keep) and el in parents:
                parents[el].remove(el)
    for el in tagged:
        el.attrib.pop("id", None)


def fit_svg(text: str, slot: str) -> str:
    """Скачанная картинка → SVG-фрагмент вещи Кая (кадр 256×256): без фона и подписей, уменьшена и поставлена
    на своё место. Рисунок в координатах Кая (viewBox 0 0 256 256) ставится как есть. "" — это не SVG."""
    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except ET.ParseError as e:
        log.warning("Своя вещь — не SVG: %s", e)
        return ""
    vb = _viewbox(root)
    if vb is None or vb == (0.0, 0.0, 256.0, 256.0):
        return "".join(ET.tostring(child, encoding="unicode") for child in root)
    _strip_background(root, vb)
    box = _content_box(ET.tostring(root, encoding="unicode"), vb)
    _drop_outside(root, box)
    bx, by, bw, bh = box
    x, y, w, h, align = SLOT_BOX.get(slot, SLOT_BOX["head"])
    k = min(w / bw, h / bh)                    # вписать в место вещи, не искажая
    ox = x + (w - bw * k) / 2 - bx * k
    oy = y + (h - bh * k) * (1.0 if align.endswith("YMax") else 0.5) - by * k
    inner = "".join(ET.tostring(child, encoding="unicode") for child in root)
    return f'<g transform="translate({ox:.2f} {oy:.2f}) scale({k:.5f})">{inner}</g>'


def normalize_fit(fit) -> dict:
    """Подгонка вещи: размер 0,3..2,5, сдвиг ±100, поворот ±180°, отражение."""
    fit = fit if isinstance(fit, dict) else {}
    out = dict(DEFAULT_FIT)
    for key, lo, hi in (("scale", 0.3, 2.5), ("dx", -100, 100), ("dy", -100, 100), ("rot", -180, 180)):
        try:
            out[key] = max(lo, min(hi, float(fit.get(key, out[key]))))
        except (TypeError, ValueError):
            pass
    out["mirror"] = bool(fit.get("mirror", False))
    return out


def place_fragment(fragment: str, slot: str, fit) -> str:
    """Своя подгонка вокруг центра места вещи: сдвиг, поворот, размер, отражение."""
    fit = normalize_fit(fit)
    if not fragment or fit == DEFAULT_FIT:
        return fragment
    x, y, w, h, _align = SLOT_BOX.get(slot, SLOT_BOX["head"])
    cx, cy = x + w / 2, y + h / 2
    sx = -fit["scale"] if fit["mirror"] else fit["scale"]
    return (f'<g transform="translate({cx + fit["dx"]:g} {cy + fit["dy"]:g}) rotate({fit["rot"]:g}) '
            f'scale({sx:g} {fit["scale"]:g}) translate({-cx:g} {-cy:g})">{fragment}</g>')


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
    """Только известные вид, цвет и вещи. Вещи сочетаются, если не лезут на одно место (шапка, корона и венок —
    одно место; бантик, наушники, шарф с бабочкой, одежда с плащом — разные), последняя надетая побеждает."""
    look = look if isinstance(look, dict) else {}
    slots: dict[str, str] = {}
    known = all_accessories()
    for item in look.get("acc") or []:
        if item in known:
            slot = known[item][1]
            if slot == "costume":              # костюм закрывает шапку, бантик, наушники и одежду
                slots = {g: v for g, v in slots.items() if known[v][1] not in COSTUME_HIDES}
            elif slot in COSTUME_HIDES:
                slots.pop("costume", None)
            slots[slot if item in ACCESSORIES else item] = item   # свои вещи из папки сочетаются со всем
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
                   winter_off: str = "", weather: list[str] | None = None) -> dict:
    """Образ с вещами по поводу — только на свободные места: в день рождения корона, по погоде (если известна)
    зонтик, шарф, шапка или тёмные очки, иначе по календарю — зимой шапочка и шарф."""
    look = normalize_look(chosen)
    if not seasonal and weather is None:
        return look
    extra = []
    if seasonal and birthday and day.strftime("%m-%d") == birthday:
        extra.append("crown")
    if weather is not None:
        extra += weather                       # погода знает лучше календаря
    elif season_key(day) and winter_off != season_key(day):
        extra += ["hat", "scarf"]
    known = all_accessories()                  # в образе могут быть и свои вещи из папки
    taken = {known[a][1] for a in look["acc"] if a in known}
    for item in extra:
        if ACCESSORIES[item][1] not in taken:
            look["acc"].append(item)
            taken.add(ACCESSORIES[item][1])
    return normalize_look(look)


def _hours_since(stamp) -> float:
    try:
        return (datetime.datetime.now() - datetime.datetime.fromisoformat(str(stamp))).total_seconds() / 3600
    except ValueError:
        return 0.0


def holiday(day: datetime.date, birthday: str = "") -> str | None:
    """Праздник для украшений вокруг Кая: день рождения, Новый год (20.12–10.01), Хэллоуин (25–31.10)."""
    if birthday and day.strftime("%m-%d") == birthday:
        return "birthday"
    md = (day.month, day.day)
    if md >= (12, 20) or md <= (1, 10):
        return "newyear"
    if (10, 25) <= md <= (10, 31):
        return "halloween"
    return None


def greeting(hour: int) -> str:
    return "Доброе утро" if 5 <= hour < 12 else "Добрый день" if hour < 18 else "Добрый вечер" if hour < 23 else "Доброй ночи"


def weather_tip(temp: float, code: int) -> str:
    """«+5°, дождь — возьми зонт» для утреннего приветствия."""
    tip = {"umbrella": "возьми зонт", "hat": "оденься теплее", "scarf": "не забудь шарф",
           "sunglasses": "жарко, пей воду"}
    items = weather_items(temp, code)
    advice = next((tip[i] for i in ("umbrella", "hat", "scarf", "sunglasses") if i in items), "")
    return f"{temp:+.0f}°, {weather_words(code)}" + (f" — {advice}" if advice else "")


def friend_level(points: int) -> int:
    return sum(points >= x for x in FRIEND_LEVELS)


class Pet(QWidget):
    clicked = Signal()
    quit_requested = Signal()
    _weather_got = Signal(object)              # ответ погоды из фонового потока

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
        self._levels: collections.deque = collections.deque(maxlen=STYLE_WINDOW)   # громкость для выбора танца
        self.dance_style, self.music_mood, self._style_at, self._title = "groove", "normal", 0.0, ""
        self.sign_text = " ".join(str(state.get("sign", "")).split())[:SIGN_MAX]
        self.weather_on = bool(state.get("weather", True))
        self._apps: set[str] | None = audible_apps()      # кто сейчас звучит (обновляется раз в 2 с)
        self._media_title = ""                            # последний ролик/трек, который был впереди
        self._pin: dict | None = None                     # окно, за которое Кай держится, и место на нём
        self._pin_hid = False                             # спрятался, потому что окно свернули
        self.focus_until: float | None = None             # фокус-режим: когда кончится (monotonic)
        self._distract_at = 0.0
        self.eyes_on = bool(state.get("eyes", True))
        self._eyes_due = time.monotonic() + EYES_EVERY_S
        self._eyes_rest: float | None = None              # сейчас отдыхаем глазами — до этого момента
        self.care_on = bool(state.get("care", True))
        self._care_said: dict[str, float] = {}
        self._hot_since: float | None = None
        self._was_charging: bool | None = None
        self._usage: dict = self._load_usage()
        self._usage_saved = time.monotonic()
        self._fidget_at = time.monotonic() + random.uniform(*FIDGET_EVERY_S)
        last_care = state.get("last_care")
        if not last_care:
            save_state("last_care", datetime.datetime.now().isoformat(timespec="minutes"))
        self.missing = _hours_since(last_care) >= MISS_AFTER_H     # долго не гладили — скучает
        self._missing_said = False
        self.city = str(state.get("city", ""))
        self.weather: tuple[float, int] | None = None                         # (температура, код) — когда узнали
        self._weather_announce = False
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
        self._perch.start(PIN_FOLLOW_MS)
        self._ear = QTimer(self)
        self._ear.timeout.connect(self._listen)
        self._ear.start(EAR_MS)
        self._weather_got.connect(self._weather_done)
        self._weather_timer = QTimer(self)
        self._weather_timer.timeout.connect(self.check_weather)
        self._weather_timer.start(3000)          # первый раз — вскоре после запуска, дальше раз в 30 минут
        self.games = Games(self)                  # прятки, догонялки, камень-ножницы-бумага
        self.guard = guard.Guard(self)            # сторож: кто-то трогает ноутбук, пока вас нет
        self.friends = Friends(self)              # второй питомец рядом с Каем
        wanted = self._effective()
        if wanted != self.look:
            QTimer.singleShot(0, lambda: self._wear(wanted, announce=False, greet=True))   # образ из прошлого раза

    def shutdown(self) -> None:
        """Перед выходом: всё остановить и удалить окна, пока Qt ещё жив.

        Иначе Python добирает окна Кая сборщиком мусора уже после закрытия Qt — и процесс падает на выходе.
        """
        for timer in (self._timer, self._watch, self._perch, self._ear, self._weather_timer):
            timer.stop()
        self.games.stop()
        self.guard.disarm(say=False)
        self.friends.shutdown()
        if self._export is not None:
            self._export.finished.disconnect()
            self._export.kill()
            self._export.waitForFinished(2000)
            self._export = None
        if self._run is not None:
            self._run.stop()
        self._save_usage()
        _meter[0] = None                       # отпустить индикатор громкости, пока COM ещё работает
        _sessions[0] = None
        self.bubble.deleteLater()
        self.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    # --- гардероб: вид, цвет, аксессуары, сезонные вещи ---
    def looks_root(self) -> Path:
        return LOOKS_DIR or self.base / "looks"

    def look_dir(self, look: dict) -> Path:
        return self.base if look_id(look) == look_id(DEFAULT_LOOK) else self.looks_root() / look_id(look)

    def _effective(self, chosen: dict | None = None) -> dict:
        state, today = load_state(), datetime.date.today()
        wx = None
        if self.weather_on and self.weather and state.get("weather_off") != today.isoformat():
            wx = weather_items(*self.weather)
        return effective_look(chosen or self.chosen, today, self.cfg.birthday, self.seasonal,
                              state.get("winter_off", ""), wx)

    def change_look(self, op: dict) -> None:
        if op.get("wear") and self.locked(op["wear"]):
            self.speak(f"{ACCESSORIES[op['wear']][0]} откроется на {self.locked(op['wear'])}-м сердечке дружбы. "
                       "Погладь меня почаще!", 7000)
            return
        if op.get("random"):                   # «удиви меня» — только из того, что уже открыто
            look = change_look(self.chosen, op)
            look["acc"] = [a for a in look["acc"] if not self.locked(a)]
            self.set_look(look)
            return
        self._change_look(op)

    def _change_look(self, op: dict) -> None:
        """Команда гардеробу. Снять сезонную вещь — значит не надевать её до конца сезона."""
        removed = op.get("remove")
        seasonal_now = set(self._effective()["acc"]) - set(self.chosen["acc"])
        if removed and (removed == "all" or removed in seasonal_now) and self.weather_on and self.weather:
            save_state("weather_off", datetime.date.today().isoformat())   # снял «погодную» вещь — сегодня без них
        elif removed and (removed == "all" or removed in seasonal_now) and season_key(datetime.date.today()):
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
        if (self.look_dir(look) / "frames" / NEWEST_ANIM).is_dir():   # без новых кадров — перерисовать
            self._apply_look(look, announce)
        else:
            self._start_export(look, announce)

    def _greet_season(self, look: dict) -> None:
        """Сезонную вещь Кай надел сам — один раз скажет почему."""
        today, state = datetime.date.today(), load_state()
        added = set(look["acc"]) - set(self.chosen["acc"])
        if "crown" in added and state.get("birthday_greeted") != today.isoformat():
            save_state("birthday_greeted", today.isoformat())
            self.speak("С днём рождения! Надел корону в твою честь.", 12000)
        elif added & {"hat", "scarf"} and state.get("winter_greeted") != season_key(today):
            save_state("winter_greeted", season_key(today))
            self.speak("Зима пришла! Надел шапочку и шарфик.", 10000)

    def _apply_look(self, look: dict, announce: bool) -> None:
        self.look, self.dir = look, self.look_dir(look)
        self.cache.clear()
        self.shown = ""
        if self.dir != self.base:
            os.utime(self.dir)                  # свежий образ не удалится при уборке
        if announce:
            self.play("wave")
            self.speak(random.choice(DRESSED), 6000)

    def _start_export(self, look: dict, announce: bool) -> None:
        """Кадры нового образа рисуются в фоне (≈20 с): node character/export.mjs с KAI_LOOK и KAI_OUT."""
        node, script = shutil.which("node"), ROOT / "character" / "export.mjs"
        if not node or not script.is_file():
            log.warning("Кай не может переодеться: нет node или %s", script)
            if announce:
                self.speak("Не получается переодеться: нужен Node.js и Edge или Chrome.", 6000)
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
                    svg = place_fragment(self._fragment(item, mine), slot, self.custom_fits().get(item))
                    if svg:
                        custom[item] = {"slot": slot, "svg": svg}
                except OSError as e:
                    log.warning("Своя вещь %s не прочитана: %s", file, e)
        custom_file = tmp.with_name(look_id(look) + ".custom.json")
        if custom:
            # shortcut: образ кэшируется по имени вещи; заменили сам SVG — переименуйте файл (подгонка пересчитает)
            custom_file.write_text(json.dumps(custom), encoding="utf-8")
            env.insert("KAI_CUSTOM_FILE", str(custom_file))
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setProgram(node)
        proc.setArguments([str(script)])
        proc.finished.connect(lambda code, _status: self._export_done(look, tmp, code, announce))
        # node не запустился — finished не придёт; без этого Кай «переодевался» бы вечно
        proc.errorOccurred.connect(lambda err: err == QProcess.FailedToStart and self._export_done(look, tmp, -1, announce))
        self._export, self._export_look = proc, look
        QTimer.singleShot(EXPORT_TIMEOUT_MS, lambda: proc.state() != QProcess.NotRunning and proc.kill())
        proc.start()
        if announce:
            self.speak("Переодеваюсь… минутку", 25000)

    def _export_done(self, look: dict, tmp: Path, code: int, announce: bool) -> None:
        if self._export is None:                # уже обработано (ошибка запуска и конец процесса)
            return
        tmp.with_name(look_id(look) + ".custom.json").unlink(missing_ok=True)
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
            self.speak("Не получилось переодеться. Попробую в другой раз.", 6000)
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
    def _cared(self) -> bool:
        """Погладили или угостили. True — Кай скучал и теперь радуется."""
        save_state("last_care", datetime.datetime.now().isoformat(timespec="minutes"))
        if not self.missing:
            return False
        self.missing = False
        self.play("heart", 2)
        self.speak("Ура! Я так скучал!", 6000)
        self._befriend(2)
        return True

    def petted(self) -> None:
        """Погладили мышкой: мурлычет и жмурится; дружба растёт не чаще раза в минуту."""
        if self.once == "purr":
            return
        self._touch()
        if self._cared():
            return
        self.play("purr", 2)
        self._sound("purr")
        self._tell_friend("petted")
        if time.monotonic() - self._last_pet_friend > 60:
            self._last_pet_friend = time.monotonic()
            self._befriend(1)

    def feed(self) -> None:
        """Печенька — раз в день. Второй раз Кай вежливо откажется."""
        today = datetime.date.today().isoformat()
        if load_state().get("last_fed") == today:
            self.speak("Спасибо, я уже наелся! Давай завтра.", 5000)
            return
        save_state("last_fed", today)
        self._touch()
        self._cared()
        self.play("eat")
        self._sound("munch")
        self.speak("Ням! Спасибо за печеньку!", 5000)
        self._tell_friend("fed")
        self._befriend(3)

    def _befriend(self, points: int) -> None:
        before = friend_level(self.friend)
        self.friend += points
        save_state("friend", self.friend)
        after = friend_level(self.friend)
        if after > before:
            gift = [ACCESSORIES[a][0].lower() for a, lvl in UNLOCKS.items() if before < lvl <= after]
            hearts = f"{'♥' * after}{'♡' * (len(FRIEND_LEVELS) - after)}"
            self.play("heart", 2)
            self.speak(f"Мы стали ещё ближе! Дружба: {hearts}" + (f". Подарок: {', '.join(gift)} — "
                       "загляни во «Внешность»!" if gift else ""), 10000)

    def locked(self, item: str) -> int:
        """На каком сердечке откроется вещь; 0 — уже можно."""
        need = UNLOCKS.get(item, 0)
        return need if friend_level(self.friend) < need else 0

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
        level = audio_peak()
        self._peaks.append(level)
        self._levels.append(level)
        loud = sum(p > MUSIC_LEVEL for p in self._peaks) >= MUSIC_NEED
        self.music = loud and is_music(self._apps, self._media_title, self._levels)   # речь, звонок, игра — нет
        if not self.music:
            self._style_at = 0.0
        elif time.monotonic() - self._style_at > STYLE_EVERY_S:
            self._style_at = time.monotonic()
            self.music_mood = music_mood(list(self._levels), media_title(self._media_title or self._title))
            self.dance_style = dance_for(self.music_mood, self.dance_style)

    # --- API: подключение к своему ассистенту ---
    def set_status(self, status: str) -> None:
        """idle | working | waiting — что сейчас делает ваш ассистент."""
        self._touch()
        self.loop = status if status in ("working", "waiting") else "idle"
        if self.loop == "working" and not self.bubble.asking:
            self.bubble.hide()                 # реплика не должна закрывать экран, пока ассистент кликает

    def speak(self, text: str, hide_after_ms: int = 8000) -> None:
        """Реплика самого Кая: облачко и «мяу-голос» (короткое бормотание по длине фразы)."""
        self.bubble.say(text, hide_after_ms)
        if text.strip() and not self.bubble.asking:
            self._sound("chirp1" if len(text) < 25 else "chirp2" if len(text) < 60 else "chirp3")

    def say(self, text: str, hide_after_ms: int = 12000) -> None:
        """Ответ вашего ассистента облачком — без мяу-голоса, у ассистента свой голос."""
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
        self._tell_friend("done")
        mood = meaning_mood(self.heard, answer)
        self.heard = ""
        if mood and self._has(mood):
            self.flash = (mood, time.monotonic() + FLASH_S)

    def failed(self) -> None:
        self._touch()
        self.play("fail")
        self._tell_friend("failed")

    def _tell_friend(self, event: str) -> None:
        """Друг рядом отзывается на то, что делает Кай."""
        friends = getattr(self, "friends", None)
        if friends is not None:
            friends.kai_event(event)

    def play(self, anim: str, times: int = 1) -> None:
        self.once, self.frame, self.repeat = anim, 0, times - 1

    def gesture(self, name: str, times: int = 2) -> None:
        """Жест (анимация) или эмоция на несколько секунд."""
        self._touch()
        self._tell_friend("gesture:" + name)
        if (self.dir / "frames" / name).is_dir():
            self.play(name, times)
        elif self._has(name):
            self.flash = (name, time.monotonic() + 3.0 * times)

    # --- табличка ---
    def set_sign(self, text: str) -> None:
        """Табличка с вашим текстом; пустой текст — убрать."""
        self.sign_text = " ".join(str(text).split())[:SIGN_MAX]
        save_state("sign", self.sign_text)
        self._touch()
        self.update()

    def _ask_sign(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Табличка")
        dlg.setLabelText(f"Что написать на табличке? (до {SIGN_MAX} знаков, пусто — убрать)")
        dlg.setTextValue(self.sign_text)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec():
            self.set_sign(dlg.textValue())

    # --- погода ---
    def check_weather(self, announce: bool = False) -> None:
        """Раз в 30 минут — погода в вашем городе (в фоне); Кай одевается по ней."""
        self._weather_timer.setInterval(WEATHER_EVERY_MS)
        if not self.weather_on or not self.city:
            return
        self._weather_announce = self._weather_announce or announce
        geo = load_state().get("geo")
        threading.Thread(target=self._weather_job, args=(self.city, geo), daemon=True).start()

    def _weather_job(self, city: str, geo) -> None:
        try:
            self._weather_got.emit({"result": fetch_weather(city, geo if isinstance(geo, dict) else None)})
        except Exception as e:                 # нет сети, город не нашёлся — одеваемся по календарю
            self._weather_got.emit({"error": str(e)})

    def _weather_done(self, reply: dict) -> None:
        announce, self._weather_announce = self._weather_announce, False
        if "error" in reply:
            log.info("Погода не получена: %s", reply["error"])
            if announce:
                self.speak(f"Не получилось узнать погоду: {reply['error']}", 8000)
            return
        geo, temp, code = reply["result"]
        save_state("geo", geo)
        before = weather_items(*self.weather) if self.weather else None
        self.weather = (temp, code)
        now = weather_items(temp, code)
        if announce or (before is not None and set(now) != set(before)):
            wear = ", ".join(ACCESSORIES[i][0].lower() for i in now) or "ничего особенного"
            self.speak(f"{geo.get('name', self.city)}: {temp:+.0f}°, {weather_words(code)}. Надеваю: {wear}.", 9000)
        self._wear(self._effective(), announce=False)

    def _ask_city(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Погода")
        dlg.setLabelText("Ваш город — Кай будет одеваться по погоде (Open-Meteo, без регистрации):")
        dlg.setTextValue(self.city)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec():
            self.city = dlg.textValue().strip()[:60]
            save_state("city", self.city)
            if not self.city:
                self.weather = None
                self._wear(self._effective(), announce=False)
            self.check_weather(announce=True)

    def command(self, text: str) -> bool:
        """Фраза Каю: «передай Антону привет», «покажи сердечко», «надень шарф»… False — это не ему."""
        if self.games.command(text) or self.friends.command(text):
            return True
        on = guard.command(text)
        if on is not None:
            self.guard.arm() if on else self.guard.disarm()
            return True
        act = commands.parse(text)
        if not act:
            return False
        self.gesture(act.anim, act.times)
        self.say(act.say, 6000)
        if act.look:                           # «надень шарф», «стань рыжим», «верни как было»
            self.change_look(act.look)
        if act.sign is not None:               # «покажи табличку Привет», «убери табличку»
            self.set_sign(act.sign)
        if act.focus is not None:              # «фокус на 25 минут», «хватит фокуса»
            self.start_focus(act.focus) if act.focus else self.stop_focus()
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
        process = ""
        try:
            title, process = active_window()
            self._title = title
            self._apps = audible_apps()
            if process.lower() in MEDIA_APPS | MUSIC_APPS:
                self._media_title = title          # музыка играет и в фоне — помним, что за вкладка
            self.app = app_mood(self.cfg.moods, title, process)
        except (OSError, AttributeError) as e:   # окно закрылось на ходу — просто без эмоции программы
            log.debug("Активное окно не прочитано: %s", e)
            self.app = None
        self._care(now, idle, process)
        self._cute(now, idle)
        if datetime.date.today() != self._today:  # наступил новый день: зима, день рождения, счётчик дней
            self._today = datetime.date.today()
            self._mark_day()
            self._wear(self._effective(), announce=False, greet=True)

    def _hint(self, phrases) -> None:
        """Мягкая подсказка облачком. Выключается в меню Кая."""
        self.last_hint = time.monotonic()
        if self.hints and self.isVisible() and not self.bubble.asking:
            self.speak(random.choice(phrases), 15000)

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
        if self._eyes_rest:
            return "calm"                      # глаза закрыты — отдыхаем вместе
        if (self.sign_text or self.focus_until) and self._has("sign"):
            return "sign"                      # держит табличку, пока её не уберут
        c, g = self._cursor(), self.geometry()
        look = look_at(c.x() - g.center().x(), c.y() - g.center().y(), self.cfg.look_radius_px, self.size_px / 2)
        if look:
            return look
        if self.music:
            return self.dance_style if self._has(self.dance_style) else "groove"
        if self._idle_s() > self.cfg.sleep_after_min * 60:
            return "bed" if self._has("bed") else "sleepy"   # уходит спать в кроватку
        hour = datetime.datetime.now().hour
        mood = background_mood(self.app, hour, time.monotonic() - self.session_start, self.cfg.tired_after_min * 60)
        if self.missing and mood == "idle" and self._has("tired"):
            return "tired"                     # давно не гладили — грустит
        return mood if mood == "idle" or self._has(mood) else "idle"

    # --- кадры ---
    def _files(self, name: str) -> tuple[list[Path], int]:
        if name.startswith("look_"):
            file = self.dir / "look" / f"{name[5:]}.png"
            return ([file], 24) if file.is_file() else ([], 24)
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
        if not self.chase_on or self.once or self.loop != "idle" or self._press or self.games.active:
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
        self._tell_friend("hunt")
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
        if self.seasonal:
            kind = holiday(datetime.date.today(), self.cfg.birthday)
            if kind:
                self._paint_holiday(p, kind)
        if self.shown == "sign" and self.board_text():
            self._paint_sign(p)

    def _paint_holiday(self, p: QPainter, kind: str) -> None:
        """Праздник вокруг Кая: падающий снег, тыква у лап, торт со свечкой."""
        s, t = self.size_px, time.monotonic()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#3D3929"))
        if kind == "newyear":
            p.setPen(QColor(110, 150, 200, 230))         # видно и на светлом, и на тёмном столе
            p.setBrush(QColor(225, 238, 252, 240))
            for i in range(8):
                x = (i * 37 % 100) / 100 * s + 5 * math.sin(t * 1.3 + i)
                y = (t * s * 0.12 + i * s / 8) % s
                r = s * (0.02 + 0.008 * (i % 3))
                p.drawEllipse(QRectF(x - r, y - r, 2 * r, 2 * r))
        elif kind == "halloween":
            p.setBrush(QColor("#F28C28"))
            p.drawEllipse(QRectF(s * 0.02, s * 0.80, s * 0.2, s * 0.15))
            p.drawLine(int(s * 0.12), int(s * 0.81), int(s * 0.12), int(s * 0.94))
            p.setBrush(QColor("#4E8B3A"))
            p.drawRect(QRectF(s * 0.11, s * 0.77, s * 0.025, s * 0.04))
        elif kind == "birthday":
            p.setBrush(QColor("#F6C1D0"))
            p.drawRect(QRectF(s * 0.78, s * 0.84, s * 0.19, s * 0.12))
            p.setBrush(QColor("#FFF6E9"))
            p.drawRect(QRectF(s * 0.78, s * 0.84, s * 0.19, s * 0.03))
            p.setBrush(QColor("#7FB3E8"))
            p.drawRect(QRectF(s * 0.865, s * 0.77, s * 0.02, s * 0.07))
            flick = 1 + 0.15 * math.sin(t * 12)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#F2C14E"))
            p.drawEllipse(QRectF(s * 0.862, s * (0.735 - 0.01 * flick), s * 0.026, s * 0.04 * flick))

    def _paint_sign(self, p: QPainter) -> None:
        """Ваш текст на табличке: самый крупный шрифт, при котором он помещается."""
        k = self.size_px / 256
        rect = QRectF(*(v * k for v in SIGN_RECT))
        flags = int(Qt.AlignCenter | Qt.TextWordWrap)
        font = QFont(self.font())
        font.setBold(True)
        for px in range(max(6, int(rect.height() * 0.7)), 5, -1):
            font.setPixelSize(px)
            p.setFont(font)
            box = p.boundingRect(rect, flags, self.board_text())
            if box.height() <= rect.height() and box.width() <= rect.width():
                break
        p.setPen(QColor("#3D3929"))
        p.drawText(rect, flags, self.board_text())

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
        self.unpin()
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

    # --- держится за окно ---
    def _try_pin(self) -> None:
        """Отпустили на окне — держится за него в этом месте; на рабочем столе — просто сидит."""
        self._pin = None
        ratio = self.devicePixelRatioF()
        g = self.geometry()
        feet = (round(g.center().x() * ratio), round((g.top() + g.height() * 0.85) * ratio))
        try:
            found = window_at(*feet, {int(self.winId()), int(self.bubble.winId())})
            rect = window_rect(found[0]) if found else None
        except OSError as e:
            log.debug("Окно под Каем не прочитано: %s", e)
            found = rect = None
        if not found or not rect:
            return
        hwnd, title = found
        self._pin = {"hwnd": hwnd, "title": title,
                     "dx": round(self.x() * ratio) - rect[0], "dy": round(self.y() * ratio) - rect[1]}
        short = title if len(title) <= 28 else title[:27] + "…"
        self.speak(f"Держусь за «{short}»", 4000)

    def unpin(self) -> None:
        self._release_pin()
        if self._pin_hid:
            self._pin_hid = False
            self.show()

    # --- милые мелочи: доброе утро, скучал, занимается своими делами ---
    def morning_extra(self) -> str:
        """Добавка к утреннему приветствию (например, напоминания ассистента). Переопределяется."""
        return ""

    def _cute(self, now: float, idle: float) -> None:
        if self.away or idle >= 3 * 60:
            return
        today = datetime.date.today().isoformat()
        if load_state().get("morning_day") != today and self.loop == "idle" and not self.bubble.asking:
            save_state("morning_day", today)
            parts = [greeting(datetime.datetime.now().hour) + "!"]
            if self.weather and self.weather_on:
                parts.append(weather_tip(*self.weather).capitalize() + ".")
            extra = self.morning_extra()
            if extra:
                parts.append(extra)
            self.play("stretch")
            self.speak(" ".join(parts), 12000)
            return
        if self.missing and not self._missing_said and self.loop == "idle" and not self.once:
            self._missing_said = True
            self.gesture("tired", 3)
            self.speak("Я соскучился… погладишь меня?", 8000)
            return
        busy = (self.once or self.loop != "idle" or self.music or self.sign_text or self.focus_until
                or self._eyes_rest or self._idle_s() > self.cfg.sleep_after_min * 60)
        if now >= self._fidget_at and not busy:
            self._fidget_at = now + random.uniform(*FIDGET_EVERY_S)
            late = datetime.datetime.now().hour >= 22 or datetime.datetime.now().hour < 6
            self.play("yawn" if late and random.random() < 0.6 else random.choice(FIDGETS))

    def _release_pin(self) -> None:
        """Отпустил окно; заметка, приклеенная к нему, уходит вместе с окном."""
        if self._pin and self._pin.get("note"):
            self.set_sign("")
        self._pin = None

    def set_window_note(self, text: str) -> None:
        """Заметка на окне: Кай держится за окно и держит табличку, пока не отпустит его."""
        if not self._pin:
            return
        self._pin["note"] = bool(text.strip())
        self.set_sign(text)

    def _ask_window_note(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Заметка на окне")
        dlg.setLabelText(f"Что напомнить на «{self._pin['title'][:40]}»? Уйдёт, когда отпущу окно.")
        dlg.setTextValue(self.sign_text if self._pin.get("note") else "")
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        if dlg.exec():
            self.set_window_note(dlg.textValue())

    # --- забота: фокус, глаза, батарея, нагрузка, отчёт за день ---
    def board_text(self) -> str:
        """Что на табличке: таймер фокуса важнее заметки."""
        if self.focus_until:
            left = max(0, int(self.focus_until - time.monotonic()))
            return f"Фокус {left // 60:02d}:{left % 60:02d}"
        return self.sign_text

    def start_focus(self, minutes: int = FOCUS_MIN) -> None:
        minutes = max(1, min(180, int(minutes)))
        self.focus_until = time.monotonic() + minutes * 60
        self._distract_at = 0.0
        self._touch()
        self.play("like")
        self.speak(f"Фокус на {minutes} мин. Я присмотрю, чтобы ничего не отвлекало.", 5000)

    def stop_focus(self, done: bool = False) -> None:
        if not self.focus_until:
            return
        self.focus_until = None
        if done:
            self.play("clap", 2)
            self._sound("meow")
            self.speak("Фокус окончен — ты молодец! Отдохни 5 минут.", 12000)
        else:
            self.speak("Фокус выключен.", 3000)

    def _care(self, now: float, idle: float, process: str) -> None:
        """Раз в 2 секунды из _observe: фокус, глаза, батарея, нагрузка, учёт времени."""
        if self.focus_until:
            if now >= self.focus_until:
                self.stop_focus(done=True)
            elif DISTRACT.search(self._title.lower()) and now - self._distract_at >= DISTRACT_EVERY_S:
                self._distract_at = now
                left = int((self.focus_until - now) // 60) + 1
                self.gesture("grumpy", 2)
                self.speak(f"Мы же в фокусе. Осталось {left} мин — потом посмотришь.", 7000)
        if self._eyes_rest and now >= self._eyes_rest:
            self._eyes_rest = None
            self.speak("Спасибо! Глаза отдохнули.", 4000)
        if self.away:
            self._eyes_due = now + EYES_EVERY_S          # отошли — глаза и так отдыхают
        elif self.eyes_on and now >= self._eyes_due and self.loop == "idle" and not self.bubble.asking:
            self._eyes_due = now + EYES_EVERY_S
            self._eyes_rest = now + EYES_REST_S
            self.speak("20 минут прошло — посмотри вдаль 20 секунд. Я тоже закрою глазки.", EYES_REST_S * 1000)
        if self.care_on:
            self._battery_and_cpu(now)
        if not self.away and idle < 60 and process:
            day = self._usage.setdefault(datetime.date.today().isoformat(), {})
            day[process.lower()] = day.get(process.lower(), 0) + 2
            if now - self._usage_saved > 300:
                self._save_usage()
            if (datetime.datetime.now().hour >= REPORT_HOUR and self.hints
                    and load_state().get("report_day") != datetime.date.today().isoformat()):
                save_state("report_day", datetime.date.today().isoformat())
                self.speak(usage_report(day), 15000)

    def _say_once(self, key: str, text: str, now: float) -> None:
        if now - self._care_said.get(key, -1e9) >= CARE_EVERY_S:
            self._care_said[key] = now
            self.speak(text, 8000)

    def _battery_and_cpu(self, now: float) -> None:
        try:
            bat, load = battery(), cpu_load()
        except OSError:
            bat = load = None
        if bat:
            percent, charging = bat
            if charging and self._was_charging is False:
                self.play("purr")
                self._say_once("charge", "Ммм, зарядка! Спасибо.", now)
            elif not charging and percent <= BATTERY_LOW:
                self.gesture("tired", 3)
                self._say_once("battery", f"Батарея {percent}% — подключи зарядку, а то я усну.", now)
            self._was_charging = charging
        if load is not None and load >= CPU_HOT:
            self._hot_since = self._hot_since or now
            if now - self._hot_since >= CPU_HOT_S:
                self.gesture("tired", 2)
                self._say_once("cpu", f"Уф, жарко! Компьютер загружен на {load:.0f}%.", now)
        else:
            self._hot_since = None

    def _load_usage(self) -> dict:
        try:
            data = json.loads(usage_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save_usage(self) -> None:
        """Только имена программ и секунды, только на этом компьютере; хранится неделя."""
        self._usage_saved = time.monotonic()
        keep = sorted(self._usage)[-7:]
        self._usage = {d: self._usage[d] for d in keep}
        try:
            usage_file().write_text(json.dumps(self._usage), encoding="utf-8")
        except OSError as e:
            log.warning("Отчёт за день не сохранён: %s", e)

    def today_report(self) -> str:
        return usage_report(self._usage.get(datetime.date.today().isoformat(), {}))

    def _follow_pin(self) -> None:
        pin = self._pin
        try:
            rect = window_rect(pin["hwnd"])
            minimized = rect is not None and window_minimized(pin["hwnd"])
        except OSError:
            rect, minimized = None, False
        if rect is None:                             # окно закрыли — остаёмся там, где были
            self.unpin()
            self.speak("Окно закрылось — посижу здесь.", 4000)
            return
        if minimized:                                # окно свернули — Кай прячется вместе с ним
            if self.isVisible():
                self._pin_hid = True
                self.hide()
            return
        if self._pin_hid:
            self._pin_hid = False
            self.show()
        ratio = self.devicePixelRatioF()
        target = QPoint(round((rect[0] + pin["dx"]) / ratio), round((rect[1] + pin["dy"]) / ratio))
        if (target - self.pos()).manhattanLength() > 1:
            self.move(target)

    def _follow_window(self) -> None:
        """Режим «на окне»: Кай сидит на верхней кромке окна впереди и ездит вместе с ним."""
        if self._press or self.games.active:
            return
        if self._pin:
            self._follow_pin()
            return
        if self.dock != "window":
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
        """Кая отпустили после перетаскивания: у края экрана прилипает и ложится лапками к краю,
        на окне — держится за это окно, на рабочем столе — сидит, где оставили."""
        self.dock = "free"
        self._release_pin()
        snap = snap_edge(self.x(), self.y(), self.size_px, self._area())
        if snap:
            x, y, edge = snap
            self.move(x, y)
            self.angle, self._snapped = EDGE_ANGLE[edge], True
        else:
            if self._snapped:
                self.angle, self._snapped = 0, False   # оторвали от края — снова стоит ровно
            self._try_pin()
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
        if key == "weather":
            if on:
                self.check_weather(announce=True)
            self._wear(self._effective(), announce=False)

    def contextMenuEvent(self, e):
        menu = QMenu()
        menu.addAction("Сказать Каю…").triggered.connect(lambda _c=False: self._talk())
        gestures = menu.addMenu("Жесты")
        for name, title in GESTURES.items():
            gestures.addAction(title).triggered.connect(lambda _c=False, n=name: self.gesture(n, 2))
        menu.addAction("Угостить печенькой").triggered.connect(lambda _c=False: self.feed())
        play = menu.addMenu("Поиграть")
        for name, title in GAMES.items():
            play.addAction(title).triggered.connect(lambda _c=False, n=name: self.games.start(n))
        play.setEnabled(not self.games.active)
        buddy = menu.addMenu("Друг Кая")
        for key, info in FRIENDS.items():
            action = buddy.addAction(f"{info['name']} — {info['about']}")
            action.setCheckable(True)
            action.setChecked(self.friends.here and self.friends.who == key)
            action.triggered.connect(lambda _c=False, k=key: self.friends.invite(k))
        if self.friends.here:
            buddy.addSeparator()
            buddy.addAction("Поболтать").triggered.connect(lambda _c=False: self.friends.scene("talk"))
            buddy.addAction("Отпустить домой").triggered.connect(lambda _c=False: self.friends.leave())
        if self.guard.armed:
            menu.addAction("Снять охрану").triggered.connect(lambda _c=False: self.guard.disarm())
        else:
            action = menu.addAction("Сторожить ноутбук")
            action.setEnabled(guard.supported())
            action.triggered.connect(lambda _c=False: self.guard.arm())
        menu.addAction("Табличка…").triggered.connect(lambda _c=False: self._ask_sign())
        if self.sign_text:
            menu.addAction("Убрать табличку").triggered.connect(lambda _c=False: self.set_sign(""))
        if self._pin:
            menu.addAction("Заметка на это окно…").triggered.connect(lambda _c=False: self._ask_window_note())
        if self.focus_until:
            menu.addAction("Остановить фокус").triggered.connect(lambda _c=False: self.stop_focus())
        else:
            menu.addAction(f"Фокус {FOCUS_MIN} минут").triggered.connect(lambda _c=False: self.start_focus())
        menu.addAction("Отчёт за сегодня").triggered.connect(lambda _c=False: self.speak(self.today_report(), 15000))
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
        menus = {title: dress.addMenu(title) for title in dict.fromkeys(WARDROBE_MENUS.values())}
        groups = {slot: menus[title] for slot, title in WARDROBE_MENUS.items()}
        things = dress.addMenu("Аксессуары")
        worn = set(self.look["acc"])
        for name, (ru, slot) in all_accessories().items():
            need = self.locked(name)
            action = groups.get(slot, things).addAction(f"{ru} — на {need}-м ♥" if need else ru)
            action.setCheckable(True)
            action.setChecked(name in worn)
            action.setEnabled(not need)
            action.triggered.connect(lambda on, n=name: self.change_look({"wear": n} if on else {"remove": n}))
        things.addSeparator()
        things.addAction("Свои вещи (папка)…").triggered.connect(lambda _c=False: self.open_accessories())
        if custom_accessories():
            things.addAction("Подогнать свои вещи…").triggered.connect(lambda _c=False: self._open_fit())
        dress.addSeparator()
        dress.addAction("Удиви меня").triggered.connect(lambda _c=False: self.change_look({"random": True}))
        dress.addAction("Как было").triggered.connect(lambda _c=False: self.change_look({"reset": True}))
        place = menu.addMenu("Где сидеть")
        for mode, title in DOCKS.items():
            action = place.addAction(title)
            action.setCheckable(True)
            action.setChecked(self.dock == mode and not self._pin)
            action.triggered.connect(lambda _c=False, m=mode: self.set_dock(m))
        if self._pin:
            held = place.addAction(f"Держусь за «{self._pin['title'][:30]}»")
            held.setCheckable(True)
            held.setChecked(True)
            held.setEnabled(False)
            place.addAction("Отпустить окно").triggered.connect(lambda _c=False: self.unpin())
        place.addSeparator()
        place.addAction("Перетащите Кая на любое окно — будет ездить вместе с ним").setEnabled(False)
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
        self._toggle(settings, "Отдых для глаз (20-20-20)", self.eyes_on, lambda on: self._set_flag("eyes", "eyes_on", on))
        self._toggle(settings, "Батарея и нагрузка", self.care_on, lambda on: self._set_flag("care", "care_on", on))
        weather = menu.addMenu("Погода")
        if self.weather and self.city:
            weather.addAction(f"Сейчас: {self.weather[0]:+.0f}°, {weather_words(self.weather[1])}").setEnabled(False)
        weather.addAction(f"Мой город: {self.city}…" if self.city else "Указать город…").triggered.connect(
            lambda _c=False: self._ask_city())
        self._toggle(weather, "Одеваться по погоде", self.weather_on, lambda on: self._set_flag("weather", "weather_on", on))
        menu.addSeparator()
        menu.addAction(self.friendship_text()).setEnabled(False)
        menu.addAction("Выход").triggered.connect(lambda _c=False: self.quit_requested.emit())
        self._show_menu(menu, e.globalPos())

    # --- подгонка своих вещей ---
    def custom_fits(self) -> dict:
        fits = load_state().get("custom_fit")
        return dict(fits) if isinstance(fits, dict) else {}

    def _fragment(self, item: str, mine: dict) -> str:
        """Вещь из папки, вписанная в своё место (без вашей подгонки)."""
        _ru, slot, file = mine[item]
        try:
            if file.stat().st_size > CUSTOM_MAX_BYTES:
                log.warning("Своя вещь %s больше %s байт — пропускаю", file, CUSTOM_MAX_BYTES)
                return ""
            return fit_svg(file.read_text(encoding="utf-8", errors="replace"), slot)
        except OSError as e:
            log.warning("Своя вещь %s не прочитана: %s", file, e)
            return ""

    def save_fit(self, item: str, fit: dict) -> None:
        """Запомнить подгонку и перерисовать: надетый образ — сейчас, остальные с этой вещью — когда наденут."""
        fits = self.custom_fits()
        fits[item] = normalize_fit(fit)
        save_state("custom_fit", fits)
        root = self.looks_root()
        for d in (root.iterdir() if root.is_dir() else []):
            if d.is_dir() and d != self.dir and item in d.name.split("-", 2)[-1].split("+"):
                shutil.rmtree(d, ignore_errors=True)
        if item in self.look["acc"]:
            if self._export is None:
                self._start_export(self.look, announce=True)
            else:
                self.speak("Подгонку запомнил — применю, как только допереодеваюсь.", 6000)

    def _preview_base(self) -> QImage:
        """Кай в нынешнем образе, но без своих вещей — на нём примеряем."""
        plain = {**self.look, "acc": [a for a in self.look["acc"] if a in ACCESSORIES]}
        file = self.look_dir(plain) / "look" / "center.png"
        return QImage(str(file if file.is_file() else self.base / "look" / "center.png"))

    def _open_fit(self) -> None:
        from .fit_dialog import FitDialog
        mine = custom_accessories()
        if not mine:
            return
        cache: dict[str, str] = {}

        def fragment(item: str, fit: dict) -> str:
            if item not in cache:
                cache[item] = self._fragment(item, mine)
            return place_fragment(cache[item], mine[item][1], fit)
        worn = next((a for a in self.look["acc"] if a in mine), None)
        dlg = FitDialog([(k, name, slot) for k, (name, slot, _f) in mine.items()], fragment, self.custom_fits(),
                        self._preview_base(), DEFAULT_FIT, first=worn)
        if self._run_dialog(dlg):
            before = self.custom_fits()
            for item, fit in dlg.fits.items():
                if normalize_fit(fit) != normalize_fit(before.get(item)):
                    self.save_fit(item, fit)

    def _run_dialog(self, dlg) -> bool:
        return bool(dlg.exec())

    def open_accessories(self) -> None:
        """Открыть папку своих вещей; новые SVG появляются в «Аксессуарах» без перезапуска."""
        folder = accessories_dir()
        folder.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.speak("Положи сюда SVG: head-бант.svg, neck-галстук.svg или face-маска.svg", 10000)

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
            elif not self.games.clicked():         # в догонялках щелчок — это «поймал»
                self._touch()
                self.play("wave")
                self._sound("meow")
                self.clicked.emit()
