"""Кай: крепление и поворот, музыка, поглаживание, печенька и дружба, сезонные образы, звуки, автозапуск, трей."""
import datetime as dt
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, QRect, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kai_pet import pet as pet_module  # noqa: E402
from kai_pet.pet import (effective_look, friend_level, load_state, perch_on, season_key,  # noqa: E402
                         snap_edge)


class Winter(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 12, 20)


@pytest.fixture
def played(monkeypatch):
    out = []
    monkeypatch.setattr(pet_module.sounds, "play", lambda path: out.append(path.name))
    return out


@pytest.fixture
def pet(monkeypatch, tmp_path, played):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("KAI_PET_STATE", str(tmp_path / "state.json"))   # память — своя у каждого теста
    monkeypatch.setenv("KAI_ACCESSORIES", str(tmp_path / "acc"))           # и папка своих вещей
    monkeypatch.setattr(pet_module, "active_window", lambda: ("", "explorer.exe"))
    monkeypatch.setattr(pet_module, "active_window_rect", lambda: None)
    monkeypatch.setattr(pet_module, "input_idle_s", lambda: 0.0)
    monkeypatch.setattr(pet_module, "audio_peak", lambda: 0.0)
    monkeypatch.setattr(pet_module, "background_mood", lambda app, *_: app or "idle")
    p = pet_module.Pet()
    p.once = None
    monkeypatch.setattr(p, "_cursor", lambda: QPoint(-5000, -5000))   # курсор далеко
    yield p
    p.shutdown()                       # окна — до закрытия Qt, иначе падение на выходе


# --- крепление и поворот ---
def test_snap_edge_and_perch_rules():
    area = QRect(0, 0, 1536, 824)
    assert snap_edge(20, 300, 150, area) == (0, 300, "left")
    assert snap_edge(600, 10, 150, area) == (600, 0, "top")
    assert snap_edge(600, 300, 150, area) is None
    x, y = perch_on((250, 500, 1500, 1000), 1.25, 150, area)
    assert y == int(400 - 150 * 0.93) and 200 <= x <= 1050
    assert perch_on((0, 0, 1920, 1040), 1.25, 150, area) is None      # развёрнуто во весь экран


def test_rotate_drop_and_dock_are_remembered(pet):
    pet.set_angle(450)
    assert pet.angle == 90
    pet._tick()
    pet.grab()                                            # поворот рисуется без ошибок
    pet.wheelEvent(QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                               Qt.ControlModifier, Qt.NoScrollPhase, False))
    assert pet.angle == 105 and load_state()["angle"] == 105
    area = pet._area()
    pet.move(area.left() + 10, area.top() + 200)
    pet._dropped()
    assert pet.x() == area.left() and pet.angle == 90 and load_state()["dock"] == "free"
    pet.set_dock("window")
    pet._follow_window()                                  # окна нет — в угол
    assert pet.pos() == pet._corner() and pet.angle == 0


# --- музыка ---
def test_dances_only_to_steady_sound(pet, monkeypatch):
    n = pet_module.MUSIC_SAMPLES
    levels = iter([0.3] * 10 + [0.0] * (n - 10) + [0.2] * n)
    monkeypatch.setattr(pet_module, "audio_peak", lambda: next(levels))
    for _ in range(n):
        pet._listen()
    assert not pet.music                                  # короткий «дзынь» — не музыка
    for _ in range(n):
        pet._listen()
    assert pet.music and pet.current() in pet_module.DANCES
    pet.dance_on = False
    pet._listen()
    assert not pet.music                                  # выключили в меню — не танцует


def test_audio_peak_never_crashes(monkeypatch):
    monkeypatch.setattr(pet_module, "_meter", [None, 0.0])
    assert 0.0 <= pet_module.audio_peak() <= 1.0          # на настоящем ноутбуке или без pycaw — число, не ошибка


# --- погладить, угостить, дружба ---
def test_stroking_makes_kai_purr(pet, played):
    pet.show()
    for i in range(40):
        QTest.mouseMove(pet, QPoint(20 + (i % 2) * 100, 60 + (i % 3) * 5))
    assert pet.current() == "purr" and "purr.wav" in played and pet.friend == 1
    assert pet._press is None                             # поглаживание — не перетаскивание


def test_feed_once_a_day_and_friendship(pet, played):
    pet.feed()
    assert pet.current() == "eat" and "munch.wav" in played and pet.friend == 3
    pet.once = None
    pet.feed()
    assert pet.current() != "eat" and "наелся" in pet.bubble.text.text() and pet.friend == 3
    assert load_state()["friend"] == 3 and friend_level(3) == 0 and friend_level(5) == 1
    pet._befriend(2)
    assert "Мы стали ещё ближе" in pet.bubble.text.text()
    assert "дней вместе: 1" in pet.friendship_text()


def test_click_meows_and_sounds_toggle(pet, played):
    QTest.mouseClick(pet, Qt.LeftButton)
    assert played == ["meow.wav"]
    pet._set_flag("sounds", "sounds_on", False)
    QTest.mouseClick(pet, Qt.LeftButton)
    assert played == ["meow.wav"]                          # выключили — тишина
    assert load_state()["sounds"] is False


def test_sound_files_and_new_animations_exist():
    for name in ("meow", "purr", "munch"):
        assert (pet_module.ASSETS / "sounds" / f"{name}.wav").is_file()
    for anim in ("groove", "purr", "eat"):
        assert (pet_module.ASSETS / "frames" / anim).is_dir()


# --- сезонные образы ---
def test_effective_look_seasons():
    winter, summer = dt.date(2026, 12, 20), dt.date(2026, 7, 1)
    assert effective_look({}, winter)["acc"] == ["hat", "scarf"]
    assert effective_look({}, summer)["acc"] == []
    assert effective_look({"acc": ["crown"]}, winter)["acc"] == ["crown", "scarf"]   # голова занята — только шарф
    assert effective_look({}, dt.date(2026, 3, 21), birthday="03-21")["acc"] == ["crown"]
    assert effective_look({}, winter, winter_off=season_key(winter))["acc"] == []
    assert effective_look({}, winter, seasonal=False)["acc"] == []
    assert season_key(dt.date(2027, 2, 1)) == "winter-2026" and season_key(summer) == ""


def test_removing_seasonal_item_keeps_it_off(pet, monkeypatch):
    monkeypatch.setattr(pet_module.datetime, "date", Winter)
    started = []
    monkeypatch.setattr(pet, "_start_export", lambda look, announce: started.append(look))
    assert pet._effective()["acc"] == ["hat", "scarf"]
    pet.change_look({"remove": "hat"})
    assert load_state()["winter_off"] == "winter-2026" and pet._effective()["acc"] == []


def test_season_greeting_once(pet, monkeypatch):
    monkeypatch.setattr(pet_module.datetime, "date", Winter)
    pet._greet_season({"kind": "cat", "color": "gray", "acc": ["hat", "scarf"]})
    assert "Зима" in pet.bubble.text.text()
    pet.bubble.text.setText("")
    pet._greet_season({"kind": "cat", "color": "gray", "acc": ["hat", "scarf"]})
    assert pet.bubble.text.text() == ""                   # второй раз за сезон не повторяет


# --- автозапуск (на тестовом ключе реестра, настоящий не трогаем) и трей ---
@pytest.mark.skipif(sys.platform != "win32", reason="реестр Windows")
def test_autostart_on_off(monkeypatch):
    import winreg
    from kai_pet import autostart
    monkeypatch.setattr(autostart, "RUN_KEY", r"Software\KaiPetTest\Run")
    try:
        autostart.set_enabled(True)
        assert autostart.enabled()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
            value = winreg.QueryValueEx(key, autostart.NAME)[0]
        assert "run_kai.pyw" in value
        autostart.set_enabled(False)
        autostart.set_enabled(False)                      # повторное выключение не падает
        assert not autostart.enabled()
    finally:
        for sub in (r"Software\KaiPetTest\Run", r"Software\KaiPetTest"):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass


def test_tray_builds(pet):
    from kai_pet.__main__ import tray
    icon = tray(QApplication.instance(), pet)
    titles = [a.text() for a in icon.contextMenu().actions()]
    assert "Запускать вместе с Windows" in titles and "Выход" in titles
    icon.hide()


def test_menu_builds_with_everything(pet, monkeypatch):
    """Меню собирается и в нём есть новые пункты (exec подменён, чтобы не ждать клика)."""
    seen = []
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: seen.extend(x.text() for x in menu.actions()))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    for title in ("Угостить печенькой", "Внешность", "Где сидеть", "Повернуть", "Настройки", "Выход"):
        assert title in seen
    assert any(t.startswith("Дружба:") for t in seen)


# --- охота за курсором ---
def test_shaking_rule():
    zigzag = [(i * 0.05, 0 if i % 2 else 200) for i in range(8)]            # 7 рывков по 200 px за 0,35 с
    assert pet_module.shaking(zigzag, 0.4)
    assert not pet_module.shaking([(i * 0.05, i * 100) for i in range(8)], 0.4)   # просто ведут в одну сторону
    assert not pet_module.shaking([(i * 0.05, 0 if i % 2 else 20) for i in range(8)], 0.4)   # дрожь руки
    assert not pet_module.shaking(zigzag, 5.0)                                # это было давно


def test_kai_hunts_shaken_cursor(pet, monkeypatch, played):
    pet.move(500, 500)
    xs = iter([600, 800] * 10)
    monkeypatch.setattr(pet, "_cursor", lambda: QPoint(next(xs), 560))
    for _ in range(8):
        pet._maybe_chase()
    assert pet.once == "jump" and "meow.wav" in played          # в углу — прыгает на месте
    pet.once = None
    pet._maybe_chase()
    assert pet.once is None                                      # и не чаще раза в 6 секунд
    pet.dock, pet._last_chase = "free", 0.0
    xs2 = iter([600, 800] * 10)
    monkeypatch.setattr(pet, "_cursor", lambda: QPoint(next(xs2), 560))
    for _ in range(8):
        pet._maybe_chase()
    assert pet.once == "runRight" and pet._run is not None       # «где оставлю» — подбегает к курсору
    pet._run.stop()
    pet._caught()
    assert pet.once == "jump"
    pet.chase_on, pet.once, pet._last_chase = False, None, 0.0
    for _ in range(8):
        pet._maybe_chase()
    assert pet.once is None                                      # выключено в настройках


# --- свои вещи ---
def test_custom_accessories(tmp_path, monkeypatch):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "head-bow.svg").write_text("<svg/>", encoding="utf-8")
    (folder / "neck-галстук.svg").write_text("<svg/>", encoding="utf-8")
    (folder / "звезда.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("KAI_ACCESSORIES", str(folder))
    mine = pet_module.custom_accessories()
    assert mine["my_bow"][:2] == ("bow", "head")
    ids = {name: (k, slot) for k, (name, slot, _f) in mine.items()}
    assert ids["галстук"][1] == "neck" and ids["звезда"][1] == "head"
    assert all(k.startswith("my_") and k.isascii() for k in mine)          # имя папки образа — латиница
    look = pet_module.normalize_look({"acc": ["my_bow", "hat", "scarf", ids["галстук"][0]]})
    assert look["acc"] == sorted(["hat", ids["галстук"][0]])             # на голове и шее — по одной вещи
    (folder / "head-bow.svg").unlink()
    assert pet_module.normalize_look({"acc": ["my_bow"]})["acc"] == []    # файл убрали — вещь пропала


def test_custom_accessory_goes_to_export(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "head-bow.svg").write_text("<svg><circle r='5'/></svg>", encoding="utf-8")
    started = {}
    monkeypatch.setattr(pet_module.shutil, "which", lambda name: "node")
    monkeypatch.setattr(pet_module.QProcess, "start", lambda self: started.update(
        custom=self.processEnvironment().value("KAI_CUSTOM")))
    pet._start_export(pet_module.normalize_look({"acc": ["my_bow"]}), announce=False)
    assert "circle" in started["custom"] and '"slot": "head"' in started["custom"]
    pet._export.finished.disconnect()
    pet._export = None


def test_menu_lists_custom_things_and_chase_toggle(pet, monkeypatch, tmp_path):
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "face-mask.svg").write_text("<svg/>", encoding="utf-8")
    titles = []

    def walk(menu):
        for a in menu.actions():
            titles.append(a.text())
            if a.menu():
                walk(a.menu())
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: walk(menu))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    assert "mask" in titles and "Свои вещи (папка)…" in titles and "Охотиться за мышкой" in titles


def test_example_accessory_renders():
    """Пример из examples/ — корректный SVG, который можно положить в папку."""
    import xml.etree.ElementTree as ET
    root = ET.parse(Path(__file__).resolve().parent.parent / "examples" / "accessories" / "head-bow.svg").getroot()
    assert root.get("viewBox") == "0 0 256 256"



# --- разные танцы ---
def _beat(bpm, seconds=10, hz=10, base=0.2, kick=0.4):
    period = 60 * hz / bpm
    return [base + (kick if (i % period) < 1 else 0.0) for i in range(seconds * hz)]


def test_music_style_by_title_and_sound():
    steady = [0.25] * 100               # ровный тихий звук
    assert pet_module.music_style(steady, "Lofi beats to study - YouTube") == "sway"
    assert pet_module.music_style(steady, "Metallica — Enter Sandman") == "headbang"
    assert pet_module.music_style(steady, "Phonk mix 2026") == "bounce"
    assert pet_module.music_style(steady, "Урок математики") == "sway"       # «урок» — не рок
    assert pet_module.music_style(steady) == "sway"                     # спокойный звук
    assert pet_module.music_style(_beat(150)) == "bounce"               # быстрый бит
    assert pet_module.tempo_bpm(_beat(120)) == 120
    assert pet_module.music_style([0.2] * 10) == "groove"                # мало данных


def test_dance_follows_style(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "audio_peak", lambda: 0.3)
    pet._title = "Chill piano"
    for _ in range(pet_module.MUSIC_SAMPLES):
        pet._listen()
    assert pet.music and pet.dance_style == "sway" and pet.current() == "sway"
    pet._title = "Rock radio"
    pet._listen()
    assert pet.dance_style == "sway"                       # не дёргается: пересматривает раз в 15 с
    pet._style_at -= pet_module.STYLE_EVERY_S + 1
    pet._listen()
    assert pet.current() == "headbang"


# --- табличка ---
def test_sign_text_shown_and_remembered(pet, monkeypatch):
    pet.set_sign("  Не   беспокоить!  ")
    assert pet.sign_text == "Не беспокоить!" and load_state()["sign"] == "Не беспокоить!"
    assert pet.current() == "sign"
    pet._tick()
    img = pet.grab().toImage()                                     # текст рисуется поверх кадра
    k = pet.size_px / 256
    x, y, w, h = (int(v * k) for v in pet_module.SIGN_RECT)
    dark = sum(img.pixelColor(i, j).lightness() < 90 for i in range(x, x + w) for j in range(y, y + h))
    assert dark > 20
    pet.set_sign("x" * 200)
    assert len(pet.sign_text) == pet_module.SIGN_MAX
    pet.grab()                                                     # длинный текст не ломает отрисовку
    pet.set_sign("")
    assert pet.current() != "sign"


def test_sign_by_words():
    from kai_pet import commands
    act = commands.parse("Покажи табличку: Ушёл на обед")
    assert act.sign == "Ушёл на обед"
    assert commands.parse("напиши на табличке Привет, Олег!").sign == "Привет, Олег!"
    assert commands.parse("убери табличку").sign == ""
    assert commands.parse("напиши Олегу привет") is None                 # сообщение — не табличка
    assert commands.parse("покажи сердечко").sign is None


# --- кровать и новые вещи ---
def test_new_frames_exist():
    for anim in ("sway", "bounce", "headbang", "bed", "sign"):
        assert (pet_module.ASSETS / "frames" / anim).is_dir(), anim
    assert len(list((pet_module.ASSETS / "look").glob("a??.png"))) == 16
    assert len(list((pet_module.ASSETS / "look").glob("n??.png"))) == 16


def test_old_outfit_without_new_frames_is_redrawn(pet, monkeypatch, tmp_path):
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")      # не трогаем настоящий кэш образов
    look = pet_module.normalize_look({"acc": ["scarf"]})
    old = pet.look_dir(look)
    (old / "frames" / "idle").mkdir(parents=True)                        # образ из прошлой версии
    started = []
    monkeypatch.setattr(pet, "_start_export", lambda lk, announce: started.append(lk))
    pet._wear(look, announce=False)
    assert started == [look]


# --- погода ---
def test_weather_items_rules():
    assert pet_module.weather_items(-5, 3) == ["hat", "scarf"]
    assert pet_module.weather_items(8, 61) == ["umbrella", "scarf"]
    assert pet_module.weather_items(15, 2) == []
    assert pet_module.weather_items(29, 0) == ["sunglasses"]
    assert pet_module.weather_items(2, 73) == ["hat", "scarf"]
    assert pet_module.weather_words(61) == "дождь" and pet_module.weather_words(0) == "ясно"


def test_weather_beats_calendar_in_effective_look():
    winter = Winter.today()
    plain = {"kind": "cat", "color": "gray", "acc": []}
    assert effective_look(plain, winter)["acc"] == ["hat", "scarf"]               # без погоды — по календарю
    assert effective_look(plain, winter, weather=["sunglasses"])["acc"] == ["sunglasses"]   # тёплая зима
    assert effective_look(plain, winter, seasonal=False, weather=["umbrella"])["acc"] == ["umbrella"]
    mine = {"kind": "cat", "color": "gray", "acc": ["glasses"]}
    assert effective_look(mine, winter, weather=["sunglasses", "umbrella"])["acc"] == ["glasses", "umbrella"]


def test_weather_fetch_dresses_kai(pet, monkeypatch, played):
    calls = []

    def fake(city, geo):
        calls.append((city, geo))
        return {"city": city, "name": "Осло", "lat": 59.9, "lon": 10.7}, 7.0, 63
    monkeypatch.setattr(pet_module, "fetch_weather", fake)
    worn = []
    monkeypatch.setattr(pet, "_wear", lambda look, announce, greet=False: worn.append(look))
    monkeypatch.setattr(pet_module.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    pet.check_weather()
    assert calls == []                                     # город не указан — в сеть не ходит
    pet.city = "Осло"
    pet.check_weather(announce=True)
    assert pet.weather == (7.0, 63) and calls == [("Осло", None)]
    assert worn[-1]["acc"] == ["scarf", "umbrella"]
    assert "Осло: +7°, дождь" in pet.bubble.text.text()
    pet.check_weather()
    assert calls[-1][1]["lat"] == 59.9                     # координаты запомнены — геокодер второй раз не нужен
    pet.change_look({"remove": "umbrella"})                # сняли зонтик — сегодня без погодных вещей
    assert load_state()["weather_off"] == dt.date.today().isoformat()


def test_weather_error_is_quiet(pet, monkeypatch):
    def boom(city, geo):
        raise OSError("нет сети")
    monkeypatch.setattr(pet_module, "fetch_weather", boom)
    monkeypatch.setattr(pet_module.threading, "Thread",
                        lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    pet.city = "Нигде"
    pet.check_weather()
    assert pet.weather is None and not pet.bubble.isVisible()
    pet.check_weather(announce=True)
    assert "нет сети" in pet.bubble.text.text()


def test_menu_has_sign_and_weather(pet, monkeypatch):
    titles = []

    def walk(menu):
        for a in menu.actions():
            titles.append(a.text())
            if a.menu():
                walk(a.menu())
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: walk(menu))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.set_sign("Привет")
    pet.contextMenuEvent(Ev())
    for t in ("Табличка…", "Убрать табличку", "Погода", "Указать город…", "Одеваться по погоде", "Зонтик", "Тёмные очки"):
        assert t in titles, t
