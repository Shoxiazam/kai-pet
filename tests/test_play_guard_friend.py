"""Мини-игры, Кай-сторож и друг Кая."""
import shutil
import time

from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest

from kai_pet import friend as friend_module
from kai_pet import guard as guard_module
from kai_pet import talks
from kai_pet.games import GAME_POINTS_DAY, game_for, rps_result
from kai_pet.pet import ASSETS, load_state
from test_features import pet, played  # noqa: F401  (фикстуры)


# --- игры ---
def test_rps_rules():
    assert rps_result("rock", "scissors") == 1
    assert rps_result("rock", "paper") == -1
    assert rps_result("paper", "paper") == 0


def test_game_phrases():
    assert game_for("давай поиграем в прятки") == "seek"
    assert game_for("догони меня") == "catch"
    assert game_for("сыграем в камень ножницы бумага") == "rps"
    assert game_for("давай поиграем") in ("seek", "catch", "rps")
    assert game_for("открой почту") is None


def test_game_friendship_has_daily_cap(pet):
    before = pet.friend
    for _ in range(10):
        pet.games.reward(2)
    assert pet.friend - before == GAME_POINTS_DAY


def test_catch_click_wins_and_counts_score(pet):
    pet.games.catch()
    assert pet.games.active == "catch"
    assert pet.games.clicked()                       # щелчок по Каю — поймали
    assert pet.games.active is None
    assert load_state()["score_catch"] == [1, 0]
    assert not pet.games.clicked()                   # без игры щелчок — обычное «помахать»


def test_catch_timeout_kai_wins(pet, monkeypatch):
    pet.games.catch()
    pet.games.started = time.monotonic() - 999
    pet.games._tick()
    assert pet.games.active is None and load_state()["score_catch"] == [0, 1]


def test_seek_hides_kai_and_found_by_ears(pet):
    pet.show()
    home = pet.pos()
    pet.games.seek()
    pet.games._hide_now()
    assert not pet.isVisible() and pet.games.ears.isVisible()
    pet.games.ears.on_found()
    assert pet.isVisible() and pet.games.active is None
    assert load_state()["score_seek"] == [1, 0]
    assert pet.games.home == home


def test_seek_gives_up_and_returns_home(pet):
    pet.show()
    home = pet.pos()
    pet.games.seek()
    pet.games._hide_now()
    pet.games.started = time.monotonic() - 999
    pet.games._tick()
    assert pet.isVisible() and pet.pos() == home and load_state()["score_seek"] == [0, 1]


def test_games_by_words(pet):
    assert pet.command("давай в догонялки")
    assert not pet.command("какая сегодня погода")


# --- сторож ---
def test_guard_phrases():
    assert guard_module.command("охраняй ноутбук") is True
    assert guard_module.command("я вернулся") is False
    assert guard_module.command("привет") is None


def test_guard_trips_on_touch_and_sends_photo(pet, monkeypatch, tmp_path):
    monkeypatch.setattr(guard_module, "supported", lambda: True)
    monkeypatch.setattr(guard_module, "photos_dir", lambda: tmp_path)
    shots = []

    def fake_take(path, callback, parent=None):
        path.write_bytes(b"jpg")
        shots.append(path)
        callback(str(path))
    monkeypatch.setattr(guard_module.camera, "take", fake_take)
    alarms = []
    pet.guard.alarm.connect(alarms.append)
    idle = [999.0]
    monkeypatch.setattr(pet.guard, "_idle_s", lambda: idle[0])
    pet.guard.arm()
    pet.guard.since -= guard_module.GRACE_S + 1     # время уйти прошло
    pet.guard._check()
    assert not alarms                                # тихо — тревоги нет
    idle[0] = 0.5                                    # кто-то тронул мышь
    pet.guard._check()
    pet.guard._check()                               # одна тревога, а не по фото на каждую проверку
    assert alarms == [str(shots[0])] and pet.guard.alarms == 1
    idle[0] = guard_module.REARM_IDLE_S + 1          # ушёл — сторожит дальше
    pet.guard._check()
    assert not pet.guard.tripped
    pet.guard.disarm()
    assert not pet.guard.armed


def test_guard_by_words(pet, monkeypatch):
    monkeypatch.setattr(guard_module, "supported", lambda: True)
    assert pet.command("посторожи, я ухожу")
    assert pet.guard.armed
    assert pet.command("сними охрану")
    assert not pet.guard.armed


# --- друг ---
def _fake_friend(monkeypatch, tmp_path):
    folder = tmp_path / "friend-frames"
    for anim in ("idle", "wave", "jump", "purr", "clap", "eat", "hug", "heart", "holdL", "holdR", "highL", "highR", "laugh"):
        shutil.copytree(ASSETS / "frames" / anim, folder / "frames" / anim)
    shutil.copytree(ASSETS / "look", folder / "look")
    monkeypatch.setattr(friend_module, "friend_dir", lambda root, look_id: folder)
    return folder


def test_friend_comes_sits_near_and_leaves(pet, monkeypatch, tmp_path):
    _fake_friend(monkeypatch, tmp_path)
    pet.show()
    pet.friends.invite("tosha")
    w = pet.friends.widget
    assert w is not None and w.isVisible()
    assert abs(w.geometry().bottom() - pet.geometry().bottom()) <= 1          # сидят на одной линии
    assert load_state()["buddy"] == {"who": "tosha", "on": True, "pos": None}
    pet.friends.leave(say=False)
    assert not pet.friends.here and load_state()["buddy"]["on"] is False


def test_friend_scene_talks_in_turns(pet, monkeypatch, tmp_path):
    _fake_friend(monkeypatch, tmp_path)
    pet.show()
    pet.friends.invite("mira", greet=False)
    pet.friends.scene("quarrel")
    first = pet.friends._scene[:]
    assert first                                      # реплики ждут своей очереди
    pet.friends._say_next()
    assert len(pet.friends._scene) == len(first) - 1


def test_friend_by_words(pet, monkeypatch, tmp_path):
    _fake_friend(monkeypatch, tmp_path)
    pet.show()
    assert pet.command("позови Буню")
    assert pet.friends.here and pet.friends.who == "bunya"
    assert pet.command("отпусти друга домой")
    assert not pet.friends.here


def test_friend_hides_with_kai(pet, monkeypatch, tmp_path):
    _fake_friend(monkeypatch, tmp_path)
    pet.show()
    pet.friends.invite("mira", greet=False)
    pet.hide()
    pet.friends._stay_near()
    assert not pet.friends.widget.isVisible()
    pet.show()
    pet.friends._stay_near()
    assert pet.friends.widget.isVisible()
    pet.move(QPoint(500, 500))
    pet.friends._stay_near()
    assert pet.friends._walk is not None                 # Кая переставили — друг бежит к нему
    QTest.qWait(1500)
    assert pet.friends._walk is None and pet.friends.widget.pos() == pet.friends._spot()


def test_guard_ignores_own_assistant_and_remote(pet, monkeypatch):
    monkeypatch.setattr(guard_module, "supported", lambda: True)
    monkeypatch.setattr(pet.guard, "_idle_s", lambda: 0.1)          # мышь двигается
    trips = []
    monkeypatch.setattr(pet.guard, "_trip", lambda: trips.append(1))
    pet.guard.arm()
    pet.guard.since -= guard_module.GRACE_S + 1
    pet.set_status("working")                                        # это кликает ассистент
    pet.guard._check()
    pet.set_status("idle")
    pet.guard._check()                                               # и ещё несколько секунд после него
    assert not trips
    pet.guard.quiet_until = 0
    pet.guard._check()
    assert trips == [1]


def _friend(pet, monkeypatch, tmp_path):
    _fake_friend(monkeypatch, tmp_path)
    pet.show()
    pet.friends.invite("mira", greet=False)
    w = pet.friends.widget
    w.once = None
    return w


def test_friend_follows_mouse_with_eyes(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    c = w.geometry().center()
    monkeypatch.setattr(w, "_cursor", lambda: QPoint(c.x() + 150, c.y()))
    assert w.current().startswith("look_")              # смотрит на курсор, как Кай
    monkeypatch.setattr(w, "_cursor", lambda: QPoint(-5000, -5000))
    assert w.current() == "idle"
    w.gaze = QPoint(c.x(), c.y() - 400)                  # в прятках смотрит туда, где ушки Кая
    assert w.current().startswith("look_")


def test_friend_petted_and_kai_gets_jealous(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    monkeypatch.setattr(friend_module.random, "random", lambda: 0.0)
    pet.friends.petted()
    assert w.once == "purr"
    pet.friends._jealous()
    assert pet.bubble.text.text() in friend_module.JEALOUS


def test_friend_cookie_once_a_day(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    pet.friends.feed()
    assert w.once == "eat"
    w.once = None
    pet.friends.feed()
    assert w.once is None                                 # второй раз — «уже наелся»


def test_friend_can_be_moved_and_called_back(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    far = pet.pos() + QPoint(-600, -300)
    pet.friends.dropped(far)
    assert pet.friends.free == far and load_state()["buddy"]["pos"] == [far.x(), far.y()]
    pet.friends.sit_with_kai()
    assert pet.friends.free is None and w.pos() == pet.friends._spot()


def test_friend_reacts_to_kai(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    pet.done("Готово")
    assert w.once == "clap"                               # Кай справился — друг хлопает
    w.once = None
    pet.failed()
    assert w.once == "hug"                                # Каю не повезло — обнимает
    w.once = None
    monkeypatch.setattr(friend_module.random, "random", lambda: 0.0)
    pet.petted()
    assert w.once == "clap"


def test_dance_together_holds_paws_then_changes_moves(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    pet.music, pet.dance_on, pet.dance_style = True, True, "groove"
    pet.friends._dance_together(time.monotonic())
    assert pet.friends.duet == "hold" and pet.friends.mode == "hold"     # сначала берутся за лапки
    assert pet.partner_anim == "hold" + pet.friends.toward_friend()
    assert w.anim == "hold" + pet.friends.toward_kai()
    assert pet.current() == pet.partner_anim                            # Кай танцует с другом, а не смотрит на мышку
    pet.friends._duet_until = 0
    pet.friends._dance_together(time.monotonic())
    assert pet.friends.duet != "hold" or pet.friends.mode == "hold"
    pet.music = False                                                    # музыка кончилась — отпускают лапки
    pet.friends._dance_together(time.monotonic())
    assert pet.friends.duet is None and pet.partner_anim is None and pet.friends.mode == "near"


def test_hold_spot_puts_paws_together(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    pet.friends.mode = "hold"
    spot, g, k = pet.friends._spot(), pet.geometry(), pet.size_px
    if pet.friends.side == "left":
        assert spot.x() == g.left() - round(friend_module.HOLD_DX * k)
    assert spot.y() == g.top() + round(friend_module.HOLD_DY * k)


def test_hold_scene_and_release(pet, monkeypatch, tmp_path):
    _friend(pet, monkeypatch, tmp_path)
    pet.friends.scene("hold")
    assert pet.friends.mode == "hold" and pet.partner_anim
    while pet.friends._scene:
        pet.friends._say_next()
    pet.friends._say_next()                                              # разговор кончился — отпускают
    assert pet.friends.mode == "near" and pet.partner_anim is None


def test_every_talk_uses_existing_moves():
    known = {d.name for d in (ASSETS / "frames").iterdir()} | {d.name for d in (ASSETS / "moods").iterdir()}
    known |= {"high", "hold"}
    for topic, dialogs in talks.TOPICS.items():
        assert len(dialogs) >= 1
        for dialog in dialogs:
            for who, text, anim in dialog:
                assert who in ("k", "f") and text and anim in known, (topic, text, anim)
    for lines in talks.SOLO.values():
        assert all(anim in known for _t, anim in lines)
    for k_anim, f_anim, _line in talks.PLAYS:
        assert k_anim in known and f_anim in known
    assert sum(len(d) for d in talks.TOPICS.values()) >= 75                  # разговоров много


def test_talk_topics_follow_situation():
    assert "music" in talks.context(14, 2, True, None, False, "", 0, 0)
    assert "code" in talks.context(14, 2, False, None, False, "Visual Studio Code", 0, 0)
    assert "night" in talks.context(2, 2, False, None, False, "", 0, 0)
    assert "rain" in talks.context(14, 2, False, 10, True, "", 0, 0)
    assert "cold" in talks.context(14, 2, False, -5, False, "", 0, 0)
    assert "winter" in talks.context(14, 2, False, None, False, "", 0, 0, month=12)
    topic, _ = talks.pick(["jokes", "food"], ["jokes"])
    assert topic == "food"                                                 # недавнюю тему не повторяют


def test_pauses_are_random_and_alive():
    import random
    rng = random.Random(1)
    pauses = [talks.next_pause(14, 60, rng) for _ in range(400)]
    assert min(pauses) < 30 and max(pauses) > 400                          # то болтают подряд, то надолго молчат
    assert len({round(p) for p in pauses}) > 150
    night = sum(talks.next_pause(2, 60, random.Random(i)) for i in range(200))
    day = sum(talks.next_pause(14, 60, random.Random(i)) for i in range(200))
    assert night > day


def test_kai_command_makes_both_do_it(pet, monkeypatch, tmp_path):
    w = _friend(pet, monkeypatch, tmp_path)
    assert pet.command("посмейся")
    QTest.qWait(600)
    assert w.once == "laugh" or w.flash                                   # сказали одному — делают оба
    w.once = None
    assert pet.command("дай пять")
    QTest.qWait(300)
    assert pet.once == "high" + pet.friends.toward_friend()
    assert w.once == "high" + pet.friends.toward_kai()
