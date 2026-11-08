"""Письма через Кая: переписка с друзьями по сети — история и окно ответа на каждого друга.

История хранится у вас (state «net_chat», последние HISTORY_MAX писем на друга), непрочитанные — «net_unread».
"""
from __future__ import annotations

import html
import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextBrowser, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from .network import Network

HISTORY_MAX = 60
LETTER_MAX = 200
STYLE = """
QWidget { background: #FBF6EE; color: #3B3330; font-size: 14px; }
QTextBrowser { background: #FFFDF9; border: 1px solid #E7DACA; border-radius: 12px; padding: 6px; }
QLineEdit { background: #FFFDF9; border: 1px solid #E7DACA; border-radius: 10px; padding: 8px 10px; }
QLineEdit:focus { border-color: #B5532F; }
QPushButton { border: none; border-radius: 10px; padding: 8px 14px; font-weight: 600; color: #fff; background: #B5532F; }
QPushButton:hover { background: #9E4627; }
QPushButton:disabled { background: #D9C7B8; }
QPushButton#kai { background: #2E8C6E; }
QPushButton#kai:hover { background: #24715A; }
QLabel#hint { color: #6E625B; font-size: 12px; }
"""


def history(net: "Network", box: str) -> list[dict]:
    chat = net._state().get("chat") or {}
    items = chat.get(box) if isinstance(chat, dict) else None
    return [m for m in items if isinstance(m, dict)] if isinstance(items, list) else []


def add(net: "Network", box: str, mine: bool, text: str, via_kai: bool = False) -> None:
    chat = net._state().get("chat")
    chat = dict(chat) if isinstance(chat, dict) else {}
    items = history(net, box) + [{"me": mine, "t": text, "ts": int(time.time()), "kai": via_kai}]
    chat[box] = items[-HISTORY_MAX:]
    unread = net._state().get("unread")
    unread = dict(unread) if isinstance(unread, dict) else {}
    if not mine:
        window = net.windows.get(box)
        unread[box] = 0 if window is not None and window.isVisible() else int(unread.get(box, 0)) + 1
    net._save(chat=chat, unread=unread)
    window = net.windows.get(box)
    if window is not None:
        window.refresh()


def unread(net: "Network", box: str) -> int:
    u = net._state().get("unread")
    return int(u.get(box, 0)) if isinstance(u, dict) else 0


def mark_read(net: "Network", box: str) -> None:
    u = net._state().get("unread")
    u = dict(u) if isinstance(u, dict) else {}
    if u.get(box):
        u[box] = 0
        net._save(unread=u)


class ChatWindow(QWidget):
    """Переписка с одним другом. Пока у вас гостит его Кай с письмом — ответ уходит с ним."""

    def __init__(self, net: "Network", box: str, name: str, send: Callable[[str], None], send_kai: Callable[[str], None]):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.net, self.box, self.name = net, box, name
        self._send, self._send_kai = send, send_kai
        self.setWindowTitle(f"Письма — {name}")
        self.setStyleSheet(STYLE)
        self.resize(380, 460)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.hint = QLabel()
        self.hint.setObjectName("hint")
        self.hint.setWordWrap(True)
        self.edit = QLineEdit()
        self.edit.setMaxLength(LETTER_MAX)
        self.edit.setPlaceholderText("Написать… (Enter — отправить)")
        self.edit.returnPressed.connect(self.send)
        self.edit.textChanged.connect(self._buttons)
        self.button = QPushButton("Отправить")
        self.button.clicked.connect(self.send)
        self.kai = QPushButton("Отправить с Каем 🐾")
        self.kai.setObjectName("kai")
        self.kai.setToolTip("Ваш Кай сам отнесёт письмо и принесёт ответ")
        self.kai.clicked.connect(self.send_with_kai)
        row = QHBoxLayout()
        row.addWidget(self.edit, 1)
        row.addWidget(self.button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.hint)
        layout.addLayout(row)
        layout.addWidget(self.kai)
        self.refresh()
        self._buttons()

    def _buttons(self, *_args) -> None:
        has = bool(self.edit.text().strip())
        self.button.setEnabled(has)
        self.kai.setEnabled(has and self.net.away is None and self.net.guest_from != self.box)

    def refresh(self) -> None:
        rows = []
        for m in history(self.net, self.box):
            who = "Вы" if m.get("me") else html.escape(self.name)
            paw = " 🐾" if m.get("kai") else ""
            align, bg = ("right", "#F6DED2") if m.get("me") else ("left", "#DDF1E8")
            rows.append(f'<table width="100%"><tr><td align="{align}"><div style="background:{bg};padding:6px 10px;'
                        f'border-radius:10px"><b>{who}{paw}</b><br>{html.escape(str(m.get("t", "")))}</div></td></tr></table>')
        self.view.setHtml("".join(rows) or '<p style="color:#6E625B">Пока писем нет. Напишите первым!</p>')
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        guest = self.net.guest_from == self.box
        self.hint.setText(f"Кай от {self.name} ждёт ответ — он унесёт его с собой." if guest else
                          ("Ваш Кай сейчас в гостях." if self.net.away else ""))
        self._buttons()
        if self.isVisible():
            mark_read(self.net, self.box)

    def showEvent(self, event):
        super().showEvent(event)
        mark_read(self.net, self.box)
        self.refresh()
        self.edit.setFocus()

    def send(self) -> None:
        text = self.edit.text().strip()[:LETTER_MAX]
        if text:
            self.edit.clear()
            self._send(text)

    def send_with_kai(self) -> None:
        text = self.edit.text().strip()[:LETTER_MAX]
        if text:
            self.edit.clear()
            self._send_kai(text)
