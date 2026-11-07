"""Кай: крепление и поворот, музыка, поглаживание, печенька и дружба, сезонные образы, звуки, автозапуск, трей."""
import datetime as dt
import json
import os
import sys
import time
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
    monkeypatch.setattr(pet_module, "battery", lambda: None)
    monkeypatch.setattr(pet_module, "cpu_load", lambda: None)
    monkeypatch.setenv("KAI_PET_USAGE", str(tmp_path / "usage.json"))
    pet_module.save_state("morning_day", __import__("datetime").date.today().isoformat())   # уже здоровался
    pet_module.save_state("report_day", __import__("datetime").date.today().isoformat())   # вечерний отчёт уже был
    monkeypatch.setattr(pet_module, "audible_apps", lambda: {"spotify.exe"})     # звучит музыкальная программа
    monkeypatch.setattr(pet_module, "window_at", lambda x, y, skip: None)      # под Каем — рабочий стол
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
    assert look["acc"] == sorted(["my_bow", "hat", "scarf", ids["галстук"][0]])   # свои вещи сочетаются со всем
    (folder / "head-bow.svg").unlink()
    assert pet_module.normalize_look({"acc": ["my_bow"]})["acc"] == []    # файл убрали — вещь пропала


def test_custom_accessory_goes_to_export(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    big = "".join(f"<circle cx='{i % 256}' cy='{i % 200}' r='3'/>" for i in range(3000))   # > 32 тысяч знаков
    (folder / "head-bow.svg").write_text(f"<svg viewBox='0 0 256 256'>{big}</svg>", encoding="utf-8")
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    started = {}
    monkeypatch.setattr(pet_module, "exporter", lambda: ("python", ["-m", "kai_pet.export"]))

    def start(self):
        file = self.processEnvironment().value("KAI_CUSTOM_FILE")
        started.update(env=self.processEnvironment().value("KAI_CUSTOM"), custom=Path(file).read_text(encoding="utf-8"))
    monkeypatch.setattr(pet_module.QProcess, "start", start)
    look = pet_module.normalize_look({"acc": ["my_bow"]})
    pet._start_export(look, announce=False)
    assert not started["env"] and "circle" in started["custom"] and '"slot": "head"' in started["custom"]
    pet._export_done(look, pet.look_dir(look).with_name("x.tmp"), 1, announce=False)    # файл убирается за собой
    assert not list((tmp_path / "looks").glob("*.custom.json"))


def test_node_that_fails_to_start_does_not_hang_kai(pet, monkeypatch, tmp_path):
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    monkeypatch.setattr(pet_module, "exporter", lambda: (str(tmp_path / "нет-такого.exe"), []))
    pet._start_export(pet_module.normalize_look({"acc": ["scarf"]}), announce=False)
    QApplication.processEvents()
    assert pet._export is None                                   # не «переодевается» вечно
    assert "Не получилось переодеться" in pet.bubble.text.text()


FREEPIK_LIKE = """<?xml version="1.0" encoding="utf-8"?>
<svg version="1.1" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800" style="enable-background:new 0 0 800 800;">
<g id="background"><rect style="fill:#FFFFFF" width="800" height="800"/></g>
<g id="objects"><path d="M200,500 L400,200 L600,500 Z" style="fill:#E00"/>
<rect x="300" y="760" width="200" height="12" style="fill:#333"/></g></svg>"""


def _ink_box(fragment, size=256):
    """Где на кадре 256×256 нарисована вещь: (x0, y0, x1, y1)."""
    from PySide6.QtGui import QImage
    from kai_pet.fit_dialog import preview
    blank = QImage(size, size, QImage.Format_ARGB32)
    blank.fill(0)
    img = preview(blank, fragment, size)
    pts = [(x, y) for y in range(size) for x in range(size) if img.pixelColor(x, y).alpha() > 40]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def test_fit_svg_removes_background_and_signature():
    QApplication.instance() or QApplication([])
    out = pet_module.fit_svg(FREEPIK_LIKE, "head")
    assert "background" not in out and 'width="800"' not in out and 'y="760"' not in out   # без фона и подписи
    x0, y0, x1, y1 = _ink_box(out)
    x, y, w, h, _align = pet_module.SLOT_BOX["head"]
    assert x - 2 <= x0 and x1 <= x + w + 2 and y - 2 <= y0 and abs(y1 - (y + h)) <= 3   # на голове, сидит на макушке
    nx0, ny0, nx1, ny1 = _ink_box(pet_module.fit_svg(FREEPIK_LIKE, "neck"))
    assert ny0 >= pet_module.SLOT_BOX["neck"][1] - 2                                       # на шее — ниже


def test_fit_svg_keeps_kai_sized_and_rejects_garbage():
    own = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256'><circle r='5'/></svg>"
    out = pet_module.fit_svg(own, "head")
    assert "<circle" in out and "transform" not in out                      # рисунок под Кая — как есть
    assert pet_module.fit_svg("это не svg", "head") == ""


# --- подгонка своих вещей ---
def test_normalize_and_place_fit():
    assert pet_module.normalize_fit(None) == pet_module.DEFAULT_FIT
    assert pet_module.normalize_fit({"scale": 99, "dx": -500, "rot": "x", "mirror": 1}) == \
        {"scale": 2.5, "dx": -100, "dy": 0.0, "rot": 0.0, "mirror": True}
    frag = pet_module.fit_svg(FREEPIK_LIKE, "head")
    assert pet_module.place_fragment(frag, "head", {}) == frag                # без подгонки — без лишней обёртки
    QApplication.instance() or QApplication([])
    base = _ink_box(frag)
    big = _ink_box(pet_module.place_fragment(frag, "head", {"scale": 1.5}))
    assert big[2] - big[0] > (base[2] - base[0]) * 1.3                      # больше
    right = _ink_box(pet_module.place_fragment(frag, "head", {"dx": 40}))
    assert abs(right[0] - base[0] - 40) <= 2                                  # сдвиг вправо
    up = _ink_box(pet_module.place_fragment(frag, "head", {"dy": -20}))
    assert abs(up[1] - base[1] + 20) <= 2                                     # выше


def test_fit_dialog_preview_follows_sliders(tmp_path):
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QImage
    from kai_pet.fit_dialog import FitDialog
    frag = pet_module.fit_svg(FREEPIK_LIKE, "head")
    dlg = FitDialog([("my_a", "колпак", "head"), ("my_b", "бант", "head")],
                    lambda item, fit, slot="head": pet_module.place_fragment(frag, slot, fit),
                    {"my_b": {"scale": 1.2}}, QImage(str(pet_module.ASSETS / "look" / "center.png")),
                    pet_module.DEFAULT_FIT, first="my_b")
    assert dlg.current() == "my_b" and dlg.sliders["scale"].value() == 120   # открылась на надетой вещи
    before = dlg.view.pixmap().toImage()
    dlg.sliders["dx"].setValue(30)
    dlg.mirror.setChecked(True)
    assert dlg.fits["my_b"]["dx"] == 30 and dlg.fits["my_b"]["mirror"] is True
    assert dlg.view.pixmap().toImage() != before                               # превью перерисовалось
    dlg.pick.setCurrentIndex(0)
    assert dlg.sliders["dx"].value() == 0                                      # у другой вещи — своя подгонка
    dlg.pick.setCurrentIndex(1)
    dlg.reset()
    assert dlg.fits["my_b"] == pet_module.DEFAULT_FIT


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


@pytest.mark.parametrize("title, mood", [
    ("Lofi beats to study - YouTube", "calm"), ("Metallica — Enter Sandman", "rock"),
    ("Phonk mix 2026", "energetic"), ("Sad piano music", "sad"),          # грусть важнее «пианино»
    ("Грустная песня — YouTube", "sad"), ("Eminem — Lose Yourself (rap)", "hiphop"), ("Русский рэп 2026", "hiphop"),
    ("Вальс цветов — Чайковский", "classical"), ("Techno set", "electronic"), ("Disco hits 80s", "happy"),
    ("Весёлая музыка для детей", "happy"), ("Урок математики", "calm"),   # «урок» — не рок, звук ровный
])
def test_music_mood_by_title(title, mood):
    assert pet_module.music_mood([0.25] * 100, title) == mood


def test_music_mood_by_sound():
    assert pet_module.music_mood([0.25] * 100) == "calm"                 # ровный звук
    assert pet_module.music_mood(_beat(150)) == "energetic"             # быстрый бит
    assert pet_module.tempo_bpm(_beat(120)) == 120
    assert pet_module.music_mood([0.2] * 10) == "normal"                 # мало данных


def test_every_mood_has_real_dances_and_they_rotate():
    for mood, dances in pet_module.MUSIC_MOODS.items():
        for d in dances:
            assert (pet_module.ASSETS / "frames" / d).is_dir(), (mood, d)
    assert len(pet_module.DANCES) >= 11
    for _ in range(20):
        assert pet_module.dance_for("rock", "headbang") == "airguitar"   # другой танец того же настроения
    assert pet_module.dance_for("sad", "sadsway") == "sadsway"           # другого нет — тот же
    assert pet_module.dance_for("неизвестно") in pet_module.MUSIC_MOODS["normal"]


def test_dance_follows_style(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "audio_peak", lambda: 0.3)
    pet._media_title = "Chill piano - YouTube"
    for _ in range(pet_module.MUSIC_SAMPLES):
        pet._listen()
    calm = pet.dance_style
    assert pet.music and pet.music_mood == "calm" and calm in ("sway", "waltz") and pet.current() == calm
    pet._media_title = "Rock radio"
    pet._listen()
    assert pet.dance_style == calm                         # не дёргается: пересматривает раз в 15 с
    pet._style_at -= pet_module.STYLE_EVERY_S + 1
    pet._listen()
    assert pet.music_mood == "rock" and pet.current() in ("headbang", "airguitar")


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


def test_custom_item_in_saved_look_does_not_crash_start(monkeypatch, tmp_path, played):
    """Регресс: надетая своя вещь роняла Кая (и агента) при запуске — сезонные правила знали только встроенные."""
    QApplication.instance() or QApplication([])
    (tmp_path / "acc").mkdir()
    (tmp_path / "acc" / "761053_02.svg").write_text(FREEPIK_LIKE, encoding="utf-8")
    monkeypatch.setenv("KAI_ACCESSORIES", str(tmp_path / "acc"))
    monkeypatch.setenv("KAI_PET_STATE", str(tmp_path / "state.json"))
    pet_module.save_state("look", {"kind": "cat", "color": "gray", "acc": ["my_761053_02"]})
    monkeypatch.setattr(pet_module.dt if hasattr(pet_module, "dt") else pet_module.datetime, "date", Winter)
    for name, value in (("active_window", lambda: ("", "explorer.exe")), ("active_window_rect", lambda: None),
                        ("input_idle_s", lambda: 0.0), ("audio_peak", lambda: 0.0)):
        monkeypatch.setattr(pet_module, name, value)
    p = pet_module.Pet()
    try:
        assert p._effective()["acc"] == ["my_761053_02", "scarf"]        # зимой: колпак свой, шарф сезонный
    finally:
        p.shutdown()


def test_saved_fit_redraws_worn_look_and_forgets_others(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "head-santa.svg").write_text(FREEPIK_LIKE, encoding="utf-8")
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    stale = tmp_path / "looks" / "fox-gray-my_santa"
    (stale / "frames").mkdir(parents=True)                                     # другой образ с этой вещью
    keep = tmp_path / "looks" / "fox-gray-scarf"
    (keep / "frames").mkdir(parents=True)
    pet.look = pet_module.normalize_look({"acc": ["my_santa"]})
    exports = []
    monkeypatch.setattr(pet, "_start_export", lambda look, announce: exports.append(look))
    pet.save_fit("my_santa", {"scale": 1.4, "dy": -12})
    assert load_state()["custom_fit"]["my_santa"]["scale"] == 1.4
    assert exports == [pet.look] and not stale.exists() and keep.exists()


def test_fit_goes_into_export(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "head-santa.svg").write_text(FREEPIK_LIKE, encoding="utf-8")
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    pet_module.save_state("custom_fit", {"my_santa": {"rot": 30}})
    monkeypatch.setattr(pet_module, "exporter", lambda: ("python", ["-m", "kai_pet.export"]))
    got = {}
    monkeypatch.setattr(pet_module.QProcess, "start", lambda self: got.update(
        custom=Path(self.processEnvironment().value("KAI_CUSTOM_FILE")).read_text(encoding="utf-8")))
    look = pet_module.normalize_look({"acc": ["my_santa"]})
    pet._start_export(look, announce=False)
    assert "rotate(30)" in got["custom"]
    pet._export_done(look, pet.look_dir(look).with_name("x.tmp"), 1, announce=False)


def test_menu_offers_fit_and_dialog_saves(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "head-santa.svg").write_text(FREEPIK_LIKE, encoding="utf-8")
    titles = []
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: titles.extend(
        a.text() for m in [menu] + [x.menu() for x in menu.actions() if x.menu()]
        for a in m.actions() + [b for x in m.actions() if x.menu() for b in x.menu().actions()]))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    assert "Подогнать свои вещи…" in titles
    saved = []
    monkeypatch.setattr(pet, "save_fit", lambda item, fit, slot=None: saved.append((item, fit["scale"])))

    def run(dlg):
        dlg.sliders["scale"].setValue(150)
        return True
    monkeypatch.setattr(pet, "_run_dialog", run)
    pet._open_fit()
    assert saved == [("my_santa", 1.5)]                                         # сохраняется только изменённое



# --- танцует только под музыку ---
@pytest.mark.parametrize("apps, title, music", [
    ({"spotify.exe"}, "", True),                                               # музыкальная программа
    ({"discord.exe"}, "Imagine Dragons - Believer", False),                    # звонок — не музыка
    ({"cs2.exe"}, "", False),                                                  # игра
    (set(), "", False),                                                        # никто не звучит
    ({"chrome.exe"}, "(280) ChatGPT vs DeepSeek vs GROK: кто лучше в CS2 - YouTube - Google Chrome", False),
    ({"chrome.exe"}, "Imagine Dragons - Believer - YouTube - Google Chrome", True),
    ({"chrome.exe"}, "Lofi hip hop radio - beats to relax - YouTube", True),
    ({"msedge.exe"}, "Подкаст про ИИ — выпуск 12 - YouTube", False),
    ({"chrome.exe"}, "Как приготовить плов за 30 минут - YouTube", False),
    ({"vlc.exe"}, "Queen - Bohemian Rhapsody - VLC media player", True),
    ({"chrome.exe"}, "Яндекс Музыка — собираем музыку и подкасты для вас - Google Chrome", True),   # сайт, а не подкаст
    ({"chrome.exe"}, "Believer — Imagine Dragons. Яндекс Музыка - Google Chrome", True),
])
def test_is_music(apps, title, music):
    assert pet_module.is_music(apps, title, [0.25] * 60) is music


def test_speech_like_sound_is_not_music():
    speech = [0.3 if i % 4 else 0.0 for i in range(60)]                     # паузы между словами
    assert not pet_module.sustained(speech) and pet_module.sustained([0.25] * 60)
    assert not pet_module.is_music({"chrome.exe"}, "Иван - Привет", speech)   # похоже на песню, но звучит речь


def test_kai_ignores_game_sound(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "audio_peak", lambda: 0.4)
    pet._apps = {"cs2.exe"}
    for _ in range(pet_module.MUSIC_SAMPLES):
        pet._listen()
    assert not pet.music and pet.current() not in pet_module.DANCES
    pet._apps = {"chrome.exe"}
    pet._media_title = "Daft Punk - Get Lucky - YouTube - Google Chrome"   # вкладка с музыкой в фоне
    pet._listen()
    assert pet.music


def test_media_tab_remembered_while_working_elsewhere(pet, monkeypatch):
    windows = iter([("Daft Punk - Get Lucky - YouTube - Google Chrome", "chrome.exe"), ("main.py - VS Code", "Code.exe")])
    monkeypatch.setattr(pet_module, "active_window", lambda: next(windows))
    pet._observe()
    pet._observe()
    assert pet._title == "main.py - VS Code" and pet._media_title.startswith("Daft Punk")


# --- держится за любое окно ---
def test_dropped_on_window_rides_along_and_hides_with_it(pet, monkeypatch):
    rect = [100, 100, 900, 700]
    state = {"min": False, "alive": True}
    monkeypatch.setattr(pet_module, "window_at", lambda x, y, skip: (777, "Документ — Word"))
    monkeypatch.setattr(pet_module, "window_rect", lambda h: tuple(rect) if state["alive"] else None)
    monkeypatch.setattr(pet_module, "window_minimized", lambda h: state["min"])
    pet.show()
    r = pet.devicePixelRatioF()
    pet.move(round(400 / r), round(300 / r))
    pet._dropped()
    assert pet._pin["hwnd"] == 777 and "Word" in pet.bubble.text.text()
    rect[0] += 200
    rect[1] += 50                                                     # окно передвинули
    pet._follow_window()
    assert (round(pet.x() * r), round(pet.y() * r)) == (600, 350)
    state["min"] = True                                               # свернули — Кай прячется
    pet._follow_window()
    assert not pet.isVisible()
    state["min"] = False
    pet._follow_window()
    assert pet.isVisible()
    state["alive"] = False                                            # закрыли — остаётся на месте
    pet._follow_window()
    assert pet._pin is None and "закрылось" in pet.bubble.text.text()


def test_dropped_on_desktop_or_edge_does_not_pin(pet, monkeypatch):
    pet.move(500, 400)
    pet._dropped()
    assert pet._pin is None and pet.dock == "free"                    # рабочий стол — просто сидит
    monkeypatch.setattr(pet_module, "window_at", lambda x, y, skip: (777, "Окно"))
    monkeypatch.setattr(pet_module, "window_rect", lambda h: (0, 0, 5000, 5000))
    area = pet._area()
    pet.move(area.left() + 2, area.top() + 300)
    pet._dropped()
    assert pet._snapped and pet._pin is None                          # у края экрана — липнет к краю, не к окну


def test_unpin_from_menu_and_dock_change(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "window_at", lambda x, y, skip: (777, "Окно"))
    monkeypatch.setattr(pet_module, "window_rect", lambda h: (0, 0, 3000, 3000))
    pet.move(500, 400)
    pet._dropped()
    titles = []
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: titles.extend(
        b.text() for a in menu.actions() if a.menu() for b in a.menu().actions()))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    assert "Держусь за «Окно»" in titles and "Отпустить окно" in titles
    pet.set_dock("corner")
    assert pet._pin is None


def test_window_helpers_never_crash():
    assert pet_module.window_rect(0) is None
    assert pet_module.window_minimized(0) is False
    found = pet_module.window_at(-99999, -99999, set())
    assert found is None


# --- фокус-режим ---
def test_focus_timer_on_sign_and_distraction(pet, monkeypatch):
    pet.start_focus(25)
    assert pet.once == "like"
    pet.once = None
    assert pet.current() == "sign" and pet.board_text().startswith("Фокус 2")
    pet._tick()
    pet.grab()                                                       # таймер рисуется на табличке
    pet._title = "Смешные котики - YouTube - Google Chrome"
    pet._care(time.monotonic(), 0.0, "chrome.exe")
    assert "в фокусе" in pet.bubble.text.text()
    pet.bubble.hide()
    pet._care(time.monotonic(), 0.0, "chrome.exe")
    assert not pet.bubble.isVisible()                                # не чаще раза в 2 минуты
    pet.focus_until = time.monotonic() - 1
    pet._care(time.monotonic(), 0.0, "code.exe")
    assert pet.focus_until is None and "Фокус окончен" in pet.bubble.text.text() and pet.once == "clap"


def test_focus_by_words(pet):
    assert pet.command("фокус на 40 минут") and pet.focus_until
    assert pet.command("хватит фокуса") and pet.focus_until is None


# --- глаза 20-20-20 ---
def test_eye_break_every_20_minutes(pet):
    now = time.monotonic()
    pet._eyes_due = now - 1
    pet._care(now, 0.0, "code.exe")
    assert pet.current() == "calm" and "вдаль" in pet.bubble.text.text()
    pet._care(now + pet_module.EYES_REST_S + 1, 0.0, "code.exe")
    assert pet._eyes_rest is None and "отдохнули" in pet.bubble.text.text()
    pet.away = True
    pet._care(now + 5000, 0.0, "")
    assert pet._eyes_due > now + 5000                                # отошли — отсчёт заново
    pet.away, pet.eyes_on = False, False
    pet._eyes_due = now - 1
    pet._care(now, 0.0, "code.exe")
    assert pet._eyes_rest is None                                    # выключено в настройках


# --- заметка на окне ---
def test_window_note_goes_away_with_window(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "window_at", lambda x, y, skip: (5, "Отчёт.xlsx — Excel"))
    alive = {"v": True}
    monkeypatch.setattr(pet_module, "window_rect", lambda h: (0, 0, 3000, 3000) if alive["v"] else None)
    monkeypatch.setattr(pet_module, "window_minimized", lambda h: False)
    pet.move(500, 400)
    pet._dropped()
    pet.set_window_note("Сдать отчёт до 18:00")
    assert pet.board_text() == "Сдать отчёт до 18:00" and pet.current() == "sign"
    alive["v"] = False
    pet._follow_window()
    assert pet.sign_text == "" and pet._pin is None                  # окно закрыли — заметка ушла
    pet.set_sign("Обычная табличка")
    pet.move(500, 400)
    alive["v"] = True
    pet._dropped()
    pet.unpin()
    assert pet.sign_text == "Обычная табличка"                       # обычная табличка остаётся


# --- батарея и нагрузка ---
def test_battery_and_cpu_care(pet, monkeypatch):
    now = time.monotonic()
    monkeypatch.setattr(pet_module, "battery", lambda: (12, False))
    monkeypatch.setattr(pet_module, "cpu_load", lambda: 20.0)
    pet._battery_and_cpu(now)
    assert "Батарея 12%" in pet.bubble.text.text()
    pet.bubble.hide()
    pet._battery_and_cpu(now + 5)
    assert not pet.bubble.isVisible()                                # не чаще раза в 10 минут
    monkeypatch.setattr(pet_module, "battery", lambda: (13, True))
    pet._battery_and_cpu(now + 6)
    assert "зарядка" in pet.bubble.text.text() and pet.once == "purr"
    monkeypatch.setattr(pet_module, "cpu_load", lambda: 97.0)
    pet._battery_and_cpu(now + 10)
    assert pet._hot_since == now + 10
    pet._battery_and_cpu(now + 10 + pet_module.CPU_HOT_S)
    assert "жарко" in pet.bubble.text.text()


def test_system_readers_never_crash():
    b = pet_module.battery()
    assert b is None or (0 <= b[0] <= 100 and isinstance(b[1], bool))
    pet_module.cpu_load()
    load = pet_module.cpu_load()
    assert load is None or 0 <= load <= 100


# --- отчёт за день ---
def test_usage_counts_and_report(pet, monkeypatch, tmp_path):
    for _ in range(1800):                                            # час в коде (по 2 с)
        pet._care(time.monotonic(), 0.0, "Code.exe")
    for _ in range(600):
        pet._care(time.monotonic(), 0.0, "chrome.exe")
    pet._care(time.monotonic(), 999.0, "chrome.exe")                 # отошли — не считается
    report = pet.today_report()
    assert report.startswith("Сегодня за компьютером 1 ч 20 мин") and "VS Code 1 ч 0 мин" in report
    pet._save_usage()
    saved = json.loads((tmp_path / "usage.json").read_text(encoding="utf-8"))
    assert saved[dt.date.today().isoformat()]["code.exe"] == 3600


def test_usage_keeps_a_week_and_reports_once_in_the_evening(pet, monkeypatch, tmp_path):
    pet._usage = {f"2026-10-{d:02d}": {"a.exe": 60} for d in range(1, 15)}
    pet._save_usage()
    assert len(pet._usage) == 7
    assert pet_module.usage_report({}) .startswith("Сегодня ты почти")

    class Evening(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 6, 21, 30)
    monkeypatch.setattr(pet_module.datetime, "datetime", Evening)
    pet_module.save_state("report_day", "")                          # фикстура уже отметила отчёт
    pet._care(time.monotonic(), 0.0, "code.exe")
    assert "Сегодня" in pet.bubble.text.text()
    pet.bubble.hide()
    pet._care(time.monotonic(), 0.0, "code.exe")
    assert not pet.bubble.isVisible()                                # один раз за вечер


def test_menu_has_care_items(pet, monkeypatch):
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
    for t in ("Фокус 25 минут", "Отчёт за сегодня", "Отдых для глаз (20-20-20)", "Батарея и нагрузка"):
        assert t in titles, t


# --- мелочи от скуки ---
def test_fidgets_only_when_nothing_happens(pet, monkeypatch):
    now = time.monotonic()
    pet._fidget_at = now - 1
    pet._cute(now, 0.0)
    assert pet.once in pet_module.FIDGETS and pet._fidget_at > now + 100      # следующая — через пару минут
    for anim in pet_module.FIDGETS:
        assert (pet_module.ASSETS / "frames" / anim).is_dir()
    pet.once, pet._fidget_at = None, now - 1
    pet.set_sign("Обед")                                                       # держит табличку — не отвлекается
    pet._cute(now, 0.0)
    assert pet.once is None


# --- доброе утро ---
def test_morning_greeting_once_with_weather_and_extra(pet, monkeypatch, played):
    pet_module.save_state("morning_day", "")
    pet.weather, pet.weather_on = (4.0, 61), True
    pet.morning_extra = lambda: "Сегодня напоминаний: 2."
    pet._cute(time.monotonic(), 0.0)
    text = pet.bubble.text.text()
    assert pet.once == "stretch" and "+4°, дождь — возьми зонт" in text and "напоминаний: 2" in text
    assert any(name.startswith("chirp") for name in played)                 # мяу-голос
    pet.bubble.hide()
    pet.once = None
    pet._cute(time.monotonic(), 0.0)
    assert not pet.bubble.isVisible()                                       # один раз за день
    assert pet_module.greeting(8) == "Доброе утро" and pet_module.greeting(20) == "Добрый вечер"


# --- скучал ---
def test_missed_kai_is_sad_then_happy(monkeypatch, tmp_path, played):
    QApplication.instance() or QApplication([])
    monkeypatch.setenv("KAI_PET_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("KAI_PET_USAGE", str(tmp_path / "usage.json"))
    old = (dt.datetime.now() - dt.timedelta(hours=30)).isoformat(timespec="minutes")
    pet_module.save_state("last_care", old)
    pet_module.save_state("morning_day", dt.date.today().isoformat())
    for name, value in (("active_window", lambda: ("", "explorer.exe")), ("active_window_rect", lambda: None),
                        ("input_idle_s", lambda: 0.0), ("audio_peak", lambda: 0.0), ("audible_apps", lambda: None),
                        ("battery", lambda: None), ("cpu_load", lambda: None)):
        monkeypatch.setattr(pet_module, name, value)
    p = pet_module.Pet()
    try:
        p.once = None
        monkeypatch.setattr(p, "_cursor", lambda: QPoint(-5000, -5000))
        assert p.missing and p.current() == "tired"                        # грустит
        p._cute(time.monotonic(), 0.0)
        assert "соскучился" in p.bubble.text.text()
        before = p.friend
        p.petted()
        assert not p.missing and p.once == "heart" and "скучал" in p.bubble.text.text() and p.friend >= before + 2
        assert pet_module._hours_since(pet_module.load_state()["last_care"]) < 1
    finally:
        p.shutdown()


# --- награды за дружбу ---
def test_friendship_unlocks_new_things(pet, monkeypatch):
    pet.friend = 0
    assert pet.locked("bow") == 2 and pet.locked("scarf") == 0
    pet.change_look({"wear": "bow"})
    assert "сердечке" in pet.bubble.text.text() and "bow" not in pet.chosen["acc"]   # пока закрыто
    pet._befriend(pet_module.FRIEND_LEVELS[1])                              # сразу второе сердечко
    assert "Подарок: бантик" in pet.bubble.text.text() and pet.locked("bow") == 0
    monkeypatch.setattr(pet, "_wear", lambda look, announce, greet=False: None)
    pet.change_look({"wear": "bow"})
    assert "bow" in pet.chosen["acc"]
    for _ in range(30):
        pet.change_look({"random": True})
        assert not {"bowtie", "flowers"} & set(pet.chosen["acc"])           # «удиви меня» — только открытое


def test_locked_things_are_greyed_in_menu(pet, monkeypatch):
    pet.friend = 0
    seen = {}

    def walk(menu):
        for a in menu.actions():
            seen[a.text()] = a.isEnabled()
            if a.menu():
                walk(a.menu())
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: walk(menu))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    assert seen["Бантик — на 2-м ♥"] is False and seen["Венок — на 4-м ♥"] is False and seen["Шарфик"] is True


def test_new_things_by_words():
    from kai_pet import commands
    assert commands.parse("надень бантик").look == {"wear": "bow"}
    assert commands.parse("надень бабочку").look == {"wear": "bowtie"}
    assert commands.parse("надень венок").look == {"wear": "flowers"}


# --- праздники ---
def test_holidays():
    assert pet_module.holiday(dt.date(2026, 12, 31)) == "newyear"
    assert pet_module.holiday(dt.date(2027, 1, 5)) == "newyear"
    assert pet_module.holiday(dt.date(2026, 10, 31)) == "halloween"
    assert pet_module.holiday(dt.date(2026, 3, 21), "03-21") == "birthday"
    assert pet_module.holiday(dt.date(2026, 6, 1)) is None


@pytest.mark.parametrize("kind", ["newyear", "halloween", "birthday"])
def test_holiday_decorations_are_drawn(pet, kind):
    from PySide6.QtGui import QImage
    pet._tick()
    plain = pet.grab().toImage()
    img = QImage(plain)
    painter = pet_module.QPainter(img)
    pet._paint_holiday(painter, kind)
    painter.end()
    assert img != plain                                                    # что-то нарисовалось


# --- мяу-голос ---
def test_meow_voice_for_kai_lines_only(pet, played):
    pet.speak("Привет!")
    pet.speak("Это довольно длинная фраза, чтобы Кай побормотал подольше, чем обычно.")
    assert played[-2:] == ["chirp1.wav", "chirp3.wav"]
    played.clear()
    pet.say("Ответ ассистента")                                            # у ассистента свой голос
    assert played == []
    pet.sounds_on = False
    pet.speak("Тихо")
    assert played == []
    for name in ("chirp1", "chirp2", "chirp3"):
        assert (pet_module.ASSETS / "sounds" / f"{name}.wav").is_file()


# --- одежда и костюмы ---
def test_costume_replaces_hat_and_clothes_last_wins():
    n = pet_module.normalize_look
    assert n({"acc": ["hat", "tshirt", "shark"]})["acc"] == ["shark"]               # капюшон вместо шапки и одежды
    assert n({"acc": ["shark", "hat"]})["acc"] == ["hat"]                          # надели шапку — костюм снят
    assert n({"acc": ["shark", "glasses", "scarf"]})["acc"] == ["glasses", "scarf", "shark"]   # очки и шарф — можно
    assert n({"acc": ["hoodie", "tuxedo"]})["acc"] == ["tuxedo"]                    # одна одежда за раз
    assert n({"acc": ["hoodie", "crown"]})["acc"] == ["crown", "hoodie"]
    assert len([k for k, (_ru, slot) in pet_module.ACCESSORIES.items() if slot in ("body", "back", "costume")]) == 12


def test_wardrobe_menu_has_clothes_and_costumes_sections(pet, monkeypatch):
    menus = {}

    def walk(menu, path=""):
        for a in menu.actions():
            if a.menu():
                walk(a.menu(), a.text())
            else:
                menus.setdefault(path, []).append(a.text())
    monkeypatch.setattr(pet, "_show_menu", lambda menu, pos: walk(menu))

    class Ev:
        def globalPos(self):
            return QPoint(0, 0)
    pet.contextMenuEvent(Ev())
    assert "Акулёнок" in menus["Костюмы"] and "Лягушонок" in menus["Костюмы"]
    assert "Худи" in menus["Одежда"] and "Плащ героя" in menus["Одежда"]
    assert "Шарфик" in menus["Аксессуары"] and "Худи" not in menus["Аксессуары"]


@pytest.mark.parametrize("text, op", [
    ("надень костюм акулы", {"wear": "shark"}), ("стань акулёнком", {"wear": "shark"}),
    ("будь пчёлкой", {"wear": "bee"}), ("надень костюм динозавра", {"wear": "dino"}),
    ("сними костюм акулы", {"remove": "shark"}), ("надень худи", {"wear": "hoodie"}),
    ("надень пижаму", {"wear": "pajama"}), ("надень плащ", {"wear": "cape"}), ("стань лисёнком", {"kind": "fox"}),
])
def test_clothes_by_words(text, op):
    from kai_pet import commands
    assert commands.parse(text).look == op


def test_custom_svg_can_go_on_the_body(tmp_path, monkeypatch):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "body-футболка.svg").write_text("<svg/>", encoding="utf-8")
    monkeypatch.setenv("KAI_ACCESSORIES", str(folder))
    mine = pet_module.custom_accessories()
    assert [slot for _n, slot, _f in mine.values()] == ["body"]


TIE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><polygon points="230,20 282,20 300,480 256,510 212,480" fill="#36c"/></svg>"""
BLOB = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><circle cx="256" cy="256" r="200" fill="#c33"/></svg>"""


def test_custom_item_slot_is_guessed_and_can_be_chosen(pet, monkeypatch, tmp_path):
    folder = tmp_path / "acc"
    folder.mkdir()
    (folder / "accessory-man-svgrepo-com.svg").write_text(TIE, encoding="utf-8")     # высокий узкий — галстук
    (folder / "звезда.svg").write_text(BLOB, encoding="utf-8")
    (folder / "мои очки.svg").write_text(BLOB, encoding="utf-8")
    mine = pet_module.custom_accessories()
    slots = {name: slot for name, slot, _f in mine.values()}
    assert slots == {"accessory-man-svgrepo-com": "neck", "звезда": "head", "мои очки": "face"}
    star = next(k for k, (n, _s, _f) in mine.items() if n == "звезда")
    monkeypatch.setattr(pet, "looks_root", lambda: tmp_path / "looks")
    pet.save_fit(star, pet_module.DEFAULT_FIT, "hand")                     # выбрали в окне «Куда надеть»
    assert pet_module.custom_accessories()[star][1] == "hand"
    assert pet_module.all_accessories()[star][1] == "hand"


def test_fit_dialog_changes_place(tmp_path):
    QApplication.instance() or QApplication([])
    from PySide6.QtGui import QImage
    from kai_pet.fit_dialog import FitDialog
    seen = []

    def frag(item, fit, slot):
        seen.append(slot)
        return pet_module.place_fragment(pet_module.fit_svg(BLOB, slot), slot, fit)
    dlg = FitDialog([("my_a", "звезда", "head")], frag, {"my_a": {"dx": 20}},
                    QImage(str(pet_module.ASSETS / "look" / "center.png")), pet_module.DEFAULT_FIT)
    assert dlg.place.currentData() == "head"
    dlg.place.setCurrentIndex(dlg.place.findData("neck"))
    assert dlg.slots["my_a"] == "neck" and seen[-1] == "neck"
    assert dlg.fits["my_a"] == pet_module.DEFAULT_FIT                     # на новом месте — заново вписана
