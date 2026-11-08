"""Шкаф для переодевания: Кай забегает внутрь, дверцы закрываются, шкаф шуршит и покачивается, пока рисуется
новый образ, потом дверцы открываются — и Кай выходит уже в обновке.

Кай не прячется (hide), а становится прозрачным: для агента и друга он остаётся «на экране».
"""
from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QEasingCurve, QObject, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from .pet import Pet

INK, WOOD, WOOD_DARK, INSIDE, GOLD = "#3B3330", "#B07A4C", "#8A5A35", "#4A3426", "#F2C14E"
CLOTHES = ("#E05A47", "#4FA3A5", "#F2C14E", "#7C6CF2")
FADE_MS = 260
RUN_MS = 420
MIN_INSIDE_S = 1.6           # даже готовый образ — пару секунд «шуршит», иначе не видно, что переоделся
RUSTLE_EVERY_MS = 1500


class Closet(QWidget):
    """Сам шкаф: рисуется кодом, дверцы открыты или закрыты, может покачиваться."""

    def __init__(self, size: int):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        from .host import keep_visible
        keep_visible(self)                                       # на Mac окна-инструменты иначе прячутся
        self.w, self.h = round(size * 0.78), round(size * 1.02)
        self.pad = round(self.w * 0.24)                          # место распахнутым дверцам
        self.setFixedSize(self.w + 2 * self.pad, self.h + 8)
        self.open = True
        self.wobble = 0.0

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.pad + self.wobble * 2.5, 4)
        p.translate(self.w / 2, self.h)
        p.rotate(self.wobble * 1.6)                              # качается от основания
        p.translate(-self.w / 2, -self.h)
        w, h = self.w, self.h
        pen = QPen(QColor(INK), 3)
        p.setPen(pen)
        body = QRectF(2, h * 0.08, w - 4, h * 0.88)
        p.setBrush(QColor(WOOD))
        p.drawRoundedRect(body, 10, 10)
        p.setBrush(QColor(WOOD_DARK))
        p.drawRoundedRect(QRectF(-2, h * 0.02, w + 4, h * 0.09), 6, 6)        # карниз
        for x in (w * 0.15, w * 0.85):                                       # ножки
            p.drawRect(QRectF(x - 5, h * 0.95, 10, h * 0.05))
        inner = body.adjusted(8, 8, -8, -8)
        mid = inner.center().x()
        if self.open:
            p.setBrush(QColor(INSIDE))
            p.drawRect(inner)
            p.drawLine(QPointF(inner.left() + 6, inner.top() + 14), QPointF(inner.right() - 6, inner.top() + 14))
            step = inner.width() / (len(CLOTHES) + 1)
            for i, color in enumerate(CLOTHES):                               # одежда на вешалках
                x = inner.left() + step * (i + 1)
                p.drawLine(QPointF(x, inner.top() + 14), QPointF(x, inner.top() + 22))
                path = QPainterPath(QPointF(x - step * 0.38, inner.top() + 30))
                path.lineTo(x, inner.top() + 22)
                path.lineTo(x + step * 0.38, inner.top() + 30)
                path.lineTo(x + step * 0.3, inner.top() + 30 + inner.height() * 0.38)
                path.lineTo(x - step * 0.3, inner.top() + 30 + inner.height() * 0.38)
                path.closeSubpath()
                p.setBrush(QColor(color))
                p.drawPath(path)
            p.setBrush(QColor(WOOD))
            for side in (-1, 1):                                              # распахнутые дверцы
                edge = inner.left() if side < 0 else inner.right()
                door = QPainterPath(QPointF(edge, inner.top()))
                door.lineTo(edge + side * w * 0.2, inner.top() - 6)
                door.lineTo(edge + side * w * 0.2, inner.bottom() + 6)
                door.lineTo(edge, inner.bottom())
                door.closeSubpath()
                p.drawPath(door)
        else:
            p.setBrush(QColor(WOOD))
            for left in (True, False):
                r = QRectF(inner.left() if left else mid, inner.top(), inner.width() / 2, inner.height())
                p.drawRect(r)
                p.drawRoundedRect(r.adjusted(7, 9, -7, -9), 5, 5)
            p.setBrush(QColor(GOLD))
            for x in (mid - 9, mid + 9):
                p.drawEllipse(QPointF(x, inner.center().y()), 4.5, 4.5)
        p.end()


class Wardrobe(QObject):
    """Сценарий переодевания вокруг шкафа. enter() — зашёл, leave(then) — вышел и сделал then()."""

    def __init__(self, pet: "Pet"):
        super().__init__(pet)
        self.pet = pet
        self.closet: Closet | None = None
        self.inside = False
        self.busy = False                     # пока идёт сценка, Кая не двигают ни окно, ни игры
        self.home = QPoint()
        self._entered = 0.0
        self._anims: list = []
        self._shake = QTimer(self)
        self._shake.timeout.connect(self._wobble)
        self._rustle = QTimer(self)
        self._rustle.timeout.connect(lambda: self.pet._sound("rustle"))
        self._t0 = time.monotonic()

    def _later(self, ms: int, fn) -> None:
        QTimer.singleShot(ms, self, fn)

    def can(self) -> bool:
        games = getattr(self.pet, "games", None)
        return (self.pet.isVisible() and not self.busy and not (games and games.active)
                and self.pet.windowOpacity() > 0.99)

    def _spot(self) -> QPoint:
        """Шкаф — рядом с Каем, там, где хватает места (лучше справа), на одной линии по низу."""
        pet, c = self.pet, self.closet
        area, g = pet._area(), pet.geometry()
        x = g.right() - round(pet.size_px * 0.08) - c.pad          # сам шкаф — вплотную к Каю, дверцы шире
        if x + c.width() - c.pad > area.right():
            x = g.left() - c.w - c.pad + round(pet.size_px * 0.08)
        y = min(max(g.bottom() - c.height() + 2, area.top()), area.bottom() - c.height())
        return QPoint(x, y)

    def _animate(self, target, prop: bytes, end, ms: int, done: Callable | None = None, curve=QEasingCurve.OutCubic):
        a = QPropertyAnimation(target, prop, self)
        a.setDuration(ms)
        a.setEndValue(end)
        a.setEasingCurve(curve)
        if done:
            a.finished.connect(done)
        a.finished.connect(lambda: a in self._anims and self._anims.remove(a))
        self._anims.append(a)
        a.start()
        return a

    # --- зайти ---
    def enter(self) -> None:
        if self.inside or self.busy or not self.can():
            return
        pet = self.pet
        self.busy, self.home = True, pet.pos()
        self.closet = Closet(pet.size_px)
        self.closet.move(self._spot())
        self.closet.setWindowOpacity(0.0)
        self.closet.show()
        self._animate(self.closet, b"windowOpacity", 1.0, FADE_MS)
        self._later(FADE_MS + 80, self._run_in)

    def _run_in(self) -> None:
        pet, c = self.pet, self.closet
        if c is None:
            return
        target = c.geometry().center() - QPoint(pet.width() // 2, pet.height() // 2)
        target.setY(pet.y())
        pet.play("runRight" if target.x() > pet.x() else "runLeft", 3)
        self._animate(pet, b"pos", target, RUN_MS, self._shut, QEasingCurve.InOutQuad)

    def _shut(self) -> None:
        if self.closet is None:
            return
        self.pet.setWindowOpacity(0.0)                      # Кай внутри
        self.closet.open = False
        self.closet.update()
        self.pet._sound("door")
        self.inside, self._entered = True, time.monotonic()
        self._shake.start(40)
        self._rustle.start(RUSTLE_EVERY_MS)
        self._later(250, lambda: self.inside and self.pet._sound("rustle"))

    def _wobble(self) -> None:
        if self.closet is None:
            return
        t = time.monotonic() - self._entered
        self.closet.wobble = math.sin(t * 9) * (0.6 + 0.4 * math.sin(t * 1.7))
        self.closet.update()

    # --- выйти ---
    def leave(self, then: Callable | None = None) -> None:
        """Выйти из шкафа (не раньше, чем через MIN_INSIDE_S), потом then() — показать обновку."""
        if not self.busy:
            if then:
                then()
            return
        if not self.inside:                                  # ещё бежит к шкафу — выйдем, когда добежит
            self._later(200, lambda: self.leave(then))
            return
        wait = MIN_INSIDE_S - (time.monotonic() - self._entered)
        if wait > 0:
            self._later(round(wait * 1000), lambda: self.leave(then))
            return
        self._shake.stop()
        self._rustle.stop()
        c, pet = self.closet, self.pet
        c.wobble, c.open = 0.0, True
        c.update()
        pet._sound("door")
        self.inside = False
        pet.setWindowOpacity(1.0)                            # вышел — уже в новом образе
        pet.play("runRight" if self.home.x() > pet.x() else "runLeft", 3)
        self._animate(pet, b"pos", self.home, RUN_MS, lambda: self._out(then), QEasingCurve.InOutQuad)

    def _out(self, then: Callable | None) -> None:
        self.pet.once = None
        if then:
            then()
        c = self.closet
        if c is not None:
            self._animate(c, b"windowOpacity", 0.0, FADE_MS, lambda: self._remove(c))
        self.busy = False

    def _remove(self, c: Closet) -> None:
        if self.closet is c:
            self.closet = None
        c.hide()
        c.deleteLater()

    def close(self) -> None:
        """Выход из Кая посреди переодевания: всё убрать, Кая вернуть видимым."""
        self._shake.stop()
        self._rustle.stop()
        for a in list(self._anims):
            a.stop()
        self._anims.clear()
        if self.closet is not None:
            self.closet.hide()
            self.closet.deleteLater()
            self.closet = None
        self.pet.setWindowOpacity(1.0)
        self.inside = self.busy = False
