"""Мини-игры с Каем: прятки, догонялки, «камень-ножницы-бумага». Победы растят дружбу (не больше GAME_POINTS_DAY в день)."""
from __future__ import annotations

import datetime
import logging
import random
import sys
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QPropertyAnimation, QRect, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

GAME_POINTS_DAY = 6          # сколько очков дружбы можно выиграть за день: игры не заменяют заботу
SEEK_HINT_S = 15             # ушки шевелятся — подсказка
SEEK_GIVE_UP_S = 90          # не нашли — Кай вылезает сам
EARS_PART = 0.42             # какая часть Кая торчит из-за окна
CATCH_S = 20                 # догонялки: сколько секунд ловить
FLEE_PX = 140                # курсор ближе — Кай убегает
FLEE_COOLDOWN_S = 0.55
RPS = {"rock": ("Камень", "✊"), "scissors": ("Ножницы", "✌"), "paper": ("Бумага", "✋")}
BEATS = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
GAMES = {"seek": "Прятки", "catch": "Догонялки", "rps": "Камень-ножницы-бумага"}
_WORDS = {"seek": ("прятк", "спрячься"), "catch": ("догонялк", "догони", "поймай меня", "лови меня"),
          "rps": ("камень", "ножниц", "цу-е-фа", "цуефа")}


def rps_result(you: str, kai: str) -> int:
    """1 — вы выиграли, -1 — Кай, 0 — ничья."""
    if you == kai:
        return 0
    return 1 if BEATS[you] == kai else -1


def game_for(text: str) -> str | None:
    """«давай поиграем в прятки» → seek; просто «поиграем» → любая игра."""
    low = text.lower()
    for game, words in _WORDS.items():
        if any(w in low for w in words):
            return game
    if "поигра" in low or "играть" in low or "сыграем" in low:
        return random.choice(list(GAMES))
    return None


def hiding_spots(area: QRect, ratio: float, skip: set[int], size: int) -> list[tuple[QRect, str]]:
    """Окна, за верхней кромкой которых можно спрятаться: (прямоугольник в точках Qt, заголовок)."""
    from .pet import window_at, window_rect
    if sys.platform != "win32":
        return []
    found: dict[int, tuple[QRect, str]] = {}
    for gx in range(1, 6):
        for gy in range(1, 5):
            px, py = area.left() + area.width() * gx // 6, area.top() + area.height() * gy // 5
            try:
                hit = window_at(round(px * ratio), round(py * ratio), skip)
                rect = hit and window_rect(hit[0])
            except OSError:
                continue
            if not hit or not rect or hit[0] in found:
                continue
            r = QRect(round(rect[0] / ratio), round(rect[1] / ratio),
                      round((rect[2] - rect[0]) / ratio), round((rect[3] - rect[1]) / ratio))
            if r.width() > size * 1.5 and r.top() - size * EARS_PART > area.top() and r.top() < area.bottom() - 40:
                found[hit[0]] = (r, hit[1])
    return list(found.values())


class Ears(QWidget):
    """Ушки Кая из-за окна: щёлкнули — нашли."""

    def __init__(self, pix: QPixmap, on_found):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.pix, self.on_found = pix, on_found
        dpr = pix.devicePixelRatioF() or 1.0
        w, h = round(pix.width() / dpr), round(pix.height() / dpr)
        self.setFixedSize(w, round(h * EARS_PART))
        self.setCursor(Qt.PointingHandCursor)
        self._wiggle: QPropertyAnimation | None = None

    def paintEvent(self, _event):
        QPainter(self).drawPixmap(0, 0, self.pix)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_found()

    def wiggle(self) -> None:
        start = self.pos()
        self._wiggle = QPropertyAnimation(self, b"pos", self)
        self._wiggle.setDuration(600)
        self._wiggle.setKeyValueAt(0.25, start + QPoint(0, -8))
        self._wiggle.setKeyValueAt(0.5, start)
        self._wiggle.setKeyValueAt(0.75, start + QPoint(0, -8))
        self._wiggle.setEndValue(start)
        self._wiggle.start()


class Games(QObject):
    def __init__(self, pet: "Pet"):
        super().__init__(pet)
        self.pet = pet
        self.active: str | None = None
        self.started = 0.0
        self.home = QPoint()
        self.ears: Ears | None = None
        self.spot_title = ""
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._hinted = 0.0
        self._fled = 0.0
        self._run: QPropertyAnimation | None = None

    # --- общее ---
    def start(self, game: str) -> None:
        if self.active or not self.pet.isVisible():
            return
        if game == "rps":
            self.rps()
        elif game == "seek":
            self.seek()
        elif game == "catch":
            self.catch()

    def command(self, text: str) -> bool:
        game = game_for(text)
        if not game:
            return False
        if self.active:
            self.pet.speak("Мы уже играем!", 4000)
        else:
            QTimer.singleShot(300, lambda: self.start(game))    # сначала закроется окно, где писали
        return True

    def stop(self) -> None:
        self._timer.stop()
        if self._run is not None:
            self._run.stop()
            self._run = None
        if self.ears is not None:
            self.ears.hide()
            self.ears.deleteLater()
            self.ears = None
        if self.active and not self.pet.isVisible():
            self.pet.show()
        self.active = None

    def reward(self, points: int) -> None:
        """Очки дружбы за победу — с дневным пределом."""
        from .pet import load_state, save_state
        today = datetime.date.today().isoformat()
        state = load_state()
        got = int(state.get("game_points", 0) or 0) if state.get("game_day") == today else 0
        give = max(0, min(points, GAME_POINTS_DAY - got))
        save_state("game_day", today)
        save_state("game_points", got + give)
        if give:
            self.pet._befriend(give)

    def score(self, key: str, won: bool) -> tuple[int, int]:
        from .pet import load_state, save_state
        raw = load_state().get("score_" + key)
        you, kai = raw if isinstance(raw, list) and len(raw) == 2 else (0, 0)
        you, kai = (you + 1, kai) if won else (you, kai + 1)
        save_state("score_" + key, [you, kai])
        return you, kai

    def _go_home(self, delay_ms: int = 3500) -> None:
        home = QPoint(self.home)
        QTimer.singleShot(delay_ms, lambda: self.active is None and self.pet.move(home))

    # --- камень-ножницы-бумага ---
    def rps(self) -> None:
        pet = self.pet
        pet._touch()
        pet.play("lookAround")
        box = QMessageBox()
        box.setWindowTitle("Кай")
        box.setText("Камень, ножницы, бумага… раз, два, три!")
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        buttons = {box.addButton(f"{icon} {ru}", QMessageBox.AcceptRole): key for key, (ru, icon) in RPS.items()}
        box.addButton("Не сейчас", QMessageBox.RejectRole)
        box.exec()
        you = buttons.get(box.clickedButton())
        if not you:
            return
        kai = random.choice(list(RPS))
        result = rps_result(you, kai)
        shown = f"У меня {RPS[kai][1]} {RPS[kai][0].lower()}!"
        if result == 0:
            pet.gesture("surprised", 1)
            pet.speak(f"{shown} Ничья. Ещё разок?", 6000)
            return
        you_n, kai_n = self.score("rps", result > 0)
        if result > 0:
            pet.gesture("grumpy", 1)
            pet.speak(f"{shown} Эх, ты выиграл… Счёт {you_n}:{kai_n}.", 7000)
            self.reward(1)
        else:
            pet.play("jump", 2)
            pet.speak(f"{shown} Я победил! Счёт {you_n}:{kai_n}.", 7000)

    # --- прятки ---
    def seek(self) -> None:
        pet = self.pet
        area = pet._area()
        size = pet.size_px
        spots = hiding_spots(area, pet.devicePixelRatioF(), {int(pet.winId()), int(pet.bubble.winId())}, size)
        if spots:
            rect, self.spot_title = random.choice(spots)
            x = random.randint(rect.left() + 10, max(rect.left() + 10, rect.right() - size - 10))
            y = rect.top() - round(size * EARS_PART) + 6
        else:                               # окон нет — прячется за нижним краем экрана
            self.spot_title = ""
            x = random.randint(area.left() + 20, max(area.left() + 20, area.right() - size - 20))
            y = area.bottom() - round(size * EARS_PART) + 6
        frames, _fps = pet._frames("idle")
        self.ears = Ears(frames[0], self._found)
        self.ears.move(x, y)
        self.active, self.home, self.started, self._hinted = "seek", pet.pos(), time.monotonic(), time.monotonic()
        pet.speak("Закрой глаза… Я прячусь! Ищи мои ушки за окнами.", 5000)
        pet._sound("meow")
        QTimer.singleShot(1200, self._hide_now)

    def _hide_now(self) -> None:
        if self.active != "seek" or self.ears is None:
            return
        self.pet.bubble.hide()
        self.pet.hide()
        self.ears.show()
        self._timer.start(500)

    def _found(self) -> None:
        if self.active != "seek":
            return
        took = int(time.monotonic() - self.started)
        spot = self.ears.pos() if self.ears else self.home
        self.stop()
        pet = self.pet
        area = pet._area()
        pet.move(QPoint(min(max(spot.x(), area.left()), area.right() - pet.size_px),
                        min(max(spot.y(), area.top()), area.bottom() - pet.size_px)))
        pet.show()
        pet.play("jump")
        pet._sound("meow")
        you, kai = self.score("seek", True)
        pet.speak(f"Нашёл! За {took} с. Счёт {you}:{kai}.", 7000)
        pet._tell_friend("found")
        self.reward(2)
        self._go_home()

    def _seek_tick(self, now: float) -> None:
        if now - self.started > SEEK_GIVE_UP_S:
            where = f" Я был за «{self.spot_title[:30]}»." if self.spot_title else " Я был внизу экрана."
            self.stop()
            self.pet.move(self.home)
            self.pet.play("jump", 2)
            you, kai = self.score("seek", False)
            self.pet.speak(f"Ку-ку! Не нашёл?{where} Счёт {you}:{kai}.", 9000)
        elif now - self._hinted > SEEK_HINT_S and self.ears is not None:
            self._hinted = now
            self.ears.wiggle()
            self.pet._sound("chirp1")

    # --- догонялки: Кай убегает от курсора, поймайте его щелчком ---
    def catch(self) -> None:
        pet = self.pet
        self.active, self.home, self.started = "catch", pet.pos(), time.monotonic()
        pet.speak(f"Догони меня! Щёлкни по мне за {CATCH_S} секунд.", 5000)
        pet.play("jump")
        self._timer.start(50)

    def clicked(self) -> bool:
        """Щелчок по Каю во время игры. True — щелчок съела игра."""
        if self.active != "catch":
            return False
        took = time.monotonic() - self.started
        self.stop()
        pet = self.pet
        pet.gesture("surprised", 1)
        pet.play("heart")
        you, kai = self.score("catch", True)
        pet.speak(f"Поймал! За {took:.1f} с. Счёт {you}:{kai}.", 7000)
        self.reward(2)
        self._go_home()
        return True

    def _catch_tick(self, now: float) -> None:
        pet = self.pet
        if now - self.started > CATCH_S:
            self.stop()
            pet.play("jump", 2)
            you, kai = self.score("catch", False)
            pet.speak(f"Не догнал! Я быстрее. Счёт {you}:{kai}.", 7000)
            self._go_home()
            return
        if now - self._fled < FLEE_COOLDOWN_S or (self._run and self._run.state() == QPropertyAnimation.Running):
            return
        c, center = QCursor.pos(), pet.geometry().center()
        if abs(c.x() - center.x()) + abs(c.y() - center.y()) > FLEE_PX:
            return
        self._fled = now
        area, size = pet._area(), pet.size_px
        for _ in range(12):                 # подальше от курсора
            target = QPoint(random.randint(area.left(), area.right() - size), random.randint(area.top(), area.bottom() - size))
            if abs(target.x() + size // 2 - c.x()) + abs(target.y() + size // 2 - c.y()) > 3 * FLEE_PX:
                break
        pet.play("runRight" if target.x() > pet.x() else "runLeft")
        self._run = QPropertyAnimation(pet, b"pos", self)
        self._run.setDuration(380)
        self._run.setEndValue(target)
        self._run.start()

    def _tick(self) -> None:
        now = time.monotonic()
        if self.active == "seek":
            self._seek_tick(now)
        elif self.active == "catch":
            self._catch_tick(now)
        else:
            self._timer.stop()
