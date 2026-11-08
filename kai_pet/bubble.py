"""Облачко-реплика Кая: реплика, вопрос «да или нет», мягкая подсказка."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

_STYLE = """
QLabel { color: #3B3330; font-size: 13px; }
QPushButton { border: none; border-radius: 9px; padding: 5px 16px; font-weight: 600; color: #fff; }
QPushButton#yes { background: #2f9e61; }
QPushButton#no { background: #c9463d; }
"""
_WIDTH = 300
_TAIL = 10            # хвостик облачка вниз, к Каю
_MAX_CHARS = 420      # длиннее — обрезается многоточием


class Bubble(QWidget):
    answered = Signal(bool)

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        from .host import keep_visible
        keep_visible(self)
        self.asking = False
        self.anchor = QRect()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(_STYLE)
        self.setFixedWidth(_WIDTH)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.yes = QPushButton("Да")
        self.yes.setObjectName("yes")
        self.no = QPushButton("Нет")
        self.no.setObjectName("no")
        for b, value in ((self.yes, True), (self.no, False)):
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _c=False, v=value: self._answer(v))
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.no)
        row.addWidget(self.yes)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10 + _TAIL)
        layout.setSpacing(8)
        layout.addWidget(self.text)
        layout.addLayout(row)
        self._buttons(False)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def _buttons(self, on: bool) -> None:
        self.yes.setVisible(on)
        self.no.setVisible(on)

    def _show(self, text: str) -> None:
        self.text.setText(text if len(text) <= _MAX_CHARS else text[:_MAX_CHARS - 1].rstrip() + "…")
        self.show()
        self.place(self.anchor)

    # --- слоты ---
    def say(self, text: str, hide_after_ms: int = 12000) -> None:
        """Реплика. Вопрос «да или нет» она не перебивает."""
        if self.asking or not text.strip():
            return
        self._buttons(False)
        self._show(text.strip())
        self._timer.start(hide_after_ms)

    def ask(self, question: str) -> None:
        self.asking = True
        self._timer.stop()
        self._buttons(True)
        self._show(question)

    def close_question(self) -> None:
        if self.asking:
            self.asking = False
            self._buttons(False)
            self.hide()

    def _answer(self, yes: bool) -> None:
        self.close_question()
        self.answered.emit(yes)

    def place(self, anchor: QRect) -> None:
        """Над Каем, правым краем к нему; у края экрана — сдвигается внутрь."""
        self.anchor = QRect(anchor)
        if not self.isVisible() or anchor.isNull():
            return
        self.adjustSize()
        area = QGuiApplication.primaryScreen().availableGeometry()
        x = min(max(anchor.center().x() - self.width() + 40, area.left() + 8), area.right() - self.width() - 8)
        y = max(anchor.top() - self.height() + 14, area.top() + 8)
        self.move(x, y)
        self.update()

    def mousePressEvent(self, _e):
        if not self.asking:     # клик по реплике — закрыть её
            self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(2, 2, -2, -2 - _TAIL)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        tip_x = min(max(self.anchor.center().x() - self.x(), 30), self.width() - 30)
        tail = QPainterPath()
        tail.moveTo(QPointF(tip_x - 10, r.bottom() - 1))
        tail.lineTo(QPointF(tip_x, r.bottom() + _TAIL))
        tail.lineTo(QPointF(tip_x + 10, r.bottom() - 1))
        tail.closeSubpath()
        p.setPen(QPen(QColor("#3B3330"), 2))
        p.setBrush(QColor("#F5EFE6"))
        p.drawPath(path.united(tail))
