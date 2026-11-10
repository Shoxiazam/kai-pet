"""Достижения: счётчики, раз в день, праздник за новое."""
import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kai_pet import achievements as A  # noqa: E402


class FakePet:
    def __init__(self):
        self.got = []

    def achieved(self, key):
        self.got.append(key)


def make():
    store = {}
    pet = FakePet()
    return A.Achievements(pet, lambda: dict(store), store.__setitem__), pet, store


def test_counts_and_unlocks():
    ach, pet, _ = make()
    assert ach.bump("petted") == ["first_pet"]
    for _ in range(48):
        ach.bump("petted")
    assert "cuddles" not in pet.got
    ach.bump("petted")
    assert pet.got == ["first_pet", "cuddles"]
    assert ach.bump("petted") == []                      # дважды не празднуем
    assert ach.summary() == f"🏆 Достижения: 2/{len(A.ACHIEVEMENTS)}"


def test_daily_counters_once_a_day():
    ach, pet, _ = make()
    ach.bump("fed")
    ach.bump("fed")
    assert ach.counts()["fed"] == 1 and pet.got == ["first_cookie"]


def test_days_and_lines():
    ach, pet, _ = make()
    ach.set_at_least("days", 8)
    assert pet.got == ["week"]
    ach.set_at_least("days", 3)                            # назад не откатывается
    assert ach.counts()["days"] == 8
    lines = ach.lines()
    assert any(l.startswith("📅 Неделя") for l in lines) and any("(8/30)" in l for l in lines)


def test_time_badges():
    assert A.time_badges(datetime.datetime(2026, 1, 1, 2)) == "nights"
    assert A.time_badges(datetime.datetime(2026, 1, 1, 6)) == "mornings"
    assert A.time_badges(datetime.datetime(2026, 1, 1, 14)) is None


def test_bump_without_achievements_is_quiet():
    A.bump(object(), "games")
