"""Кай: правила настроения, жесты, облачко, команды."""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kai_pet import config, pet as pet_module  # noqa: E402
from kai_pet.pet import app_mood, background_mood, look_at, meaning_mood  # noqa: E402


# --- правила без Qt ---
def test_app_mood_first_match_wins():
    moods = config.Config().moods
    assert app_mood(moods, "Котики — YouTube — Google Chrome", "chrome.exe") == "playful"
    assert app_mood(moods, "Новая вкладка", "chrome.exe") == "calm"
    assert app_mood(moods, "main.py", "Code.exe") == "focused"
    assert app_mood(moods, "", "explorer.exe") is None


def test_background_mood_rules():
    assert background_mood("focused", 15, 60, 3600) == "focused"
    assert background_mood(None, 15, 60, 3600) == "idle"
    assert background_mood(None, 8, 60, 3600) == "curious"
    assert background_mood(None, 2, 60, 3600) == "sleepy"
    assert background_mood("focused", 2, 60, 3600) == "caring"
    long_work = 3600 + pet_module.TIRED_EVERY_S * 2 + 5
    assert background_mood("focused", 15, long_work, 3600) == "tired"
    assert background_mood("focused", 15, long_work + 60, 3600) == "focused"


def test_look_at_directions():
    assert look_at(0, 0, 240, 75) == "curious"
    assert look_at(-150, 10, 240, 75) == "look_left"
    assert look_at(150, -10, 240, 75) == "look_right"
    assert look_at(10, -150, 240, 75) == "look_up"
    assert look_at(10, 150, 240, 75) == "look_down"
    assert look_at(500, 0, 240, 75) is None


def test_meaning_mood():
    assert meaning_mood("я так устал", "Понимаю") == "caring"
    assert meaning_mood("спасибо!", "Пожалуйста") == "excited"
    assert meaning_mood("удали папку", "Осторожно: это удалит 40 файлов") == "cautious"
    assert meaning_mood("открой что-нибудь", "Что открыть?") == "curious"
    assert meaning_mood("открой почту", "Готово, открыл") == "proud"
    assert meaning_mood("сколько времени", "15:20") is None


def test_every_mood_and_gesture_has_frames():
    a = pet_module.ASSETS
    for mood in set(config.Config().moods.values()):
        assert (a / "moods" / mood).is_dir(), mood
    for g in pet_module.GESTURES:
        assert (a / "frames" / g).is_dir(), g


def test_config_file(tmp_path):
    f = tmp_path / "kai.json"
    f.write_text('{"size": 180, "hints": false, "moods": {"figma": "inspired"}, "nonsense": 1}', encoding="utf-8")
    c = config.load(f)
    assert c.size == 180 and c.hints is False and c.moods == {"figma": "inspired"}
    f.write_text("{broken", encoding="utf-8")
    assert config.load(f) == config.Config()          # битый файл не роняет Кая
    assert config.load(tmp_path / "missing.json") == config.Config()


# --- окно Кая ---
@pytest.fixture
def pet(monkeypatch):
    QApplication.instance() or QApplication([])
    monkeypatch.setattr(pet_module, "active_window", lambda: ("", "explorer.exe"))
    monkeypatch.setattr(pet_module, "input_idle_s", lambda: 0.0)
    monkeypatch.setattr(pet_module, "background_mood", lambda app, *_: app or "idle")
    p = pet_module.Pet()
    p.once = None
    monkeypatch.setattr(p, "_cursor", lambda: QPoint(-5000, -5000))   # курсор далеко
    yield p
    p.hide()


def test_status_flow(pet):
    pet.set_status("working")
    assert pet.current() == "working"
    pet.ask("Удалить?")
    assert pet.current() == "waiting" and pet.bubble.asking
    pet.bubble.yes.click()
    pet.set_status("idle")
    pet.hear("открой почту")
    pet.done("Готово, открыл почту")
    assert pet.current() == "checking"
    pet.once = None
    assert pet.current() == "proud"


def test_fail_then_back_to_background(pet):
    pet.failed()
    pet.done("Не вышло")
    assert pet.current() == "fail"
    for _ in range(len(pet._frames("fail")[0]) + 1):
        pet._tick()
    assert pet.current() == "idle"


def test_gesture_repeats(pet):
    pet.gesture("heart", 2)
    n = len(pet._frames("heart")[0])
    for _ in range(n + 1):
        pet._tick()
    assert pet.current() == "heart"
    for _ in range(n):
        pet._tick()
    assert pet.current() == "idle"


def test_emotion_gesture_is_timed(pet):
    pet.gesture("surprised", 2)
    assert pet.current() == "surprised"
    pet.flash = ("surprised", 0)
    assert pet.current() == "idle"


def test_command_shows_gesture_and_says(pet):
    assert pet.command("Передай Антону привет")
    assert pet.current() == "wave" and pet.bubble.text.text() == "Антон, привет!"
    assert pet.command("покажи сердечко") and pet.current() == "heart"
    assert not pet.command("напиши Антону в телеграм")


def test_program_in_front_sets_mood(pet, monkeypatch):
    monkeypatch.setattr(pet_module, "active_window", lambda: ("main.py", "Code.exe"))
    pet._observe()
    assert pet.current() == "focused"

    def closed():
        raise OSError("окно закрылось")
    monkeypatch.setattr(pet_module, "active_window", closed)
    pet._observe()
    assert pet.current() == "idle"


def test_cursor_and_sleep(pet, monkeypatch):
    c = pet.geometry().center()
    monkeypatch.setattr(pet, "_cursor", lambda: QPoint(c.x() - 150, c.y()))
    assert pet.current() == "look_left"
    pet._tick()
    monkeypatch.setattr(pet, "_cursor", lambda: QPoint(-5000, -5000))
    pet.last_event -= 3600
    monkeypatch.setattr(pet_module, "input_idle_s", lambda: 3600.0)
    assert pet.current() == "sleepy"


def test_hints_break_and_welcome(pet, monkeypatch):
    pet.show()
    pet.session_start -= pet.cfg.tired_after_min * 60 + 10
    pet.last_hint -= pet.cfg.break_hint_every_min * 60 + 10
    pet._observe()
    assert pet.bubble.isVisible() and pet.bubble.text.text() in pet_module.BREAK_HINTS
    pet.bubble.hide()
    monkeypatch.setattr(pet_module, "input_idle_s", lambda: pet.cfg.welcome_after_min * 60 + 5)
    pet._observe()
    monkeypatch.setattr(pet_module, "input_idle_s", lambda: 0.2)
    pet._observe()
    assert pet.current() == "wave" and pet.bubble.text.text() in pet_module.WELCOME_HINTS


def test_click_waves(pet):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    QTest.mouseClick(pet, Qt.LeftButton)
    assert pet.current() == "wave"


def test_cache_bounded(pet):
    for name in ["idle", "wave", "working", "waiting", "checking", "fail", "curious", "calm", "focused",
                 "playful", "sleepy", "tired", "caring", "look_left", "heart", "dance"]:
        pet._frames(name)
    assert len(pet.cache) <= pet_module.CACHE_MAX


def test_missing_assets_raise(tmp_path):
    QApplication.instance() or QApplication([])
    with pytest.raises(FileNotFoundError):
        pet_module.Pet(assets=tmp_path)


def test_work_hides_answer_bubble_but_keeps_question(pet):
    pet.show()
    pet.say("Готово")
    pet.set_status("working")
    assert not pet.bubble.isVisible()
    pet.ask("Отправить?")
    pet.set_status("working")
    assert pet.bubble.isVisible() and pet.bubble.asking
