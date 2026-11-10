"""Достижения Кая: счётчики того, что вы делаете вместе, и награды за круглые числа.

Счётчики и полученные достижения хранятся в общем состоянии Кая (load_state/save_state):
«ach_counts» — сколько раз что было, «ach_done» — ключи полученных достижений.
"""
from __future__ import annotations

import datetime

# ключ → (значок, название, за что, счётчик, сколько нужно)
ACHIEVEMENTS: dict[str, tuple[str, str, str, str, int]] = {
    "first_cookie": ("🍪", "Первая печенька", "угостить Кая", "fed", 1),
    "gourmet": ("🧁", "Гурман", "угощать Кая 10 дней", "fed", 10),
    "first_pet": ("🤲", "Мур", "погладить Кая", "petted", 1),
    "cuddles": ("💞", "Обнимашки", "погладить 50 раз", "petted", 50),
    "week": ("📅", "Неделя вместе", "7 дней с Каем", "days", 7),
    "month": ("🗓️", "Месяц вместе", "30 дней с Каем", "days", 30),
    "year": ("🎂", "Год вместе", "365 дней с Каем", "days", 365),
    "player": ("🎲", "Игрок", "сыграть 10 игр", "games", 10),
    "champion": ("🏆", "Чемпион", "выиграть у Кая 10 раз", "wins", 10),
    "dancer": ("💃", "Танцор", "станцевать под 10 песен", "dances", 10),
    "disco": ("🪩", "Дискотека", "станцевать под 100 песен", "dances", 100),
    "fashion": ("👗", "Модник", "переодеть Кая 20 раз", "dressed", 20),
    "traveler": ("🧳", "Путешественник", "сходить в гости по сети", "visits", 1),
    "host": ("🏠", "Гостеприимный", "принять гостя из сети", "guests", 1),
    "postman": ("💌", "Почтальон", "отправить 5 открыток", "cards", 5),
    "buddy": ("🐾", "Компания", "позвать друга Кая", "buddies", 1),
    "owl": ("🦉", "Сова", "работать после полуночи 3 ночи", "nights", 3),
    "lark": ("🌅", "Жаворонок", "начать день до 7 утра 3 раза", "mornings", 3),
    "helper": ("🤖", "Напарник", "100 задач ассистента рядом с Каем", "tasks", 100),
}
DAILY = {"nights", "mornings", "fed"}     # такие счётчики растут не чаще раза в день


class Achievements:
    def __init__(self, pet, load_state, save_state):
        self.pet = pet
        self._load, self._save = load_state, save_state

    def counts(self) -> dict[str, int]:
        c = self._load().get("ach_counts")
        return c if isinstance(c, dict) else {}

    def done(self) -> list[str]:
        d = self._load().get("ach_done")
        return [k for k in d if k in ACHIEVEMENTS] if isinstance(d, list) else []

    def bump(self, counter: str, n: int = 1) -> list[str]:
        """+n к счётчику; новые достижения — Кай празднует. Возвращает ключи полученных сейчас."""
        if counter in DAILY:
            today = datetime.date.today().isoformat()
            days = self._load().get("ach_days") or {}
            if days.get(counter) == today:
                return []
            days[counter] = today
            self._save("ach_days", days)
        counts = self.counts()
        counts[counter] = int(counts.get(counter, 0)) + n
        self._save("ach_counts", counts)
        return self._check(counts)

    def set_at_least(self, counter: str, value: int) -> list[str]:
        """Счётчик, который знает своё значение сам (дни вместе)."""
        counts = self.counts()
        if int(counts.get(counter, 0)) >= value:
            return []
        counts[counter] = value
        self._save("ach_counts", counts)
        return self._check(counts)

    def _check(self, counts: dict[str, int]) -> list[str]:
        have = self.done()
        new = [k for k, (_, _, _, c, goal) in ACHIEVEMENTS.items() if k not in have and counts.get(c, 0) >= goal]
        if new:
            self._save("ach_done", have + new)
            for k in new:
                self.pet.achieved(k)
        return new

    def summary(self) -> str:
        return f"🏆 Достижения: {len(self.done())}/{len(ACHIEVEMENTS)}"

    def lines(self) -> list[str]:
        have, counts = set(self.done()), self.counts()
        out = []
        for k, (icon, title, about, c, goal) in ACHIEVEMENTS.items():
            if k in have:
                out.append(f"{icon} {title} — {about}")
            else:
                out.append(f"🔒 {title} — {about} ({min(counts.get(c, 0), goal)}/{goal})")
        return out


def time_badges(now: datetime.datetime) -> str | None:
    """Ночь (0–4 ч) → «nights», раннее утро (5–6 ч) → «mornings»."""
    if 0 <= now.hour < 5:
        return "nights"
    if 5 <= now.hour < 7:
        return "mornings"
    return None


def bump(pet, counter: str, n: int = 1) -> None:
    """Для игр, сети и друга: у тестового «питомца» достижений может не быть."""
    ach = getattr(pet, "ach", None)
    if ach is not None:
        ach.bump(counter, n)
