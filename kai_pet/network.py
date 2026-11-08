"""Сеть Каев: Кай ходит в гости к Каю друга через интернет и носит открытки.

Посредник — бесплатный ntfy.sh (HTTPS, без регистрации): у каждого Кая свой ящик kaipet-<id>, адрес — код
дружбы KAI-<id>. Сообщения короткие: имя, наряд, текст открытки. Ящик слушается, только если вы сами завели
сеть (добавили друга или показали свой код). Принимается только от друзей; чужой запрос дружбы Кай спрашивает
у хозяина. Всё входящее проверяется: известные вещи наряда, длина имени и текста, не чаще нескольких раз в минуту.
"""
from __future__ import annotations

import collections
import json
import logging
import random
import re
import secrets
import shutil
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QProcess, QProcessEnvironment, QTimer, Signal
from PySide6.QtWidgets import QApplication, QInputDialog, QMenu, QMessageBox

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

SERVER = "https://ntfy.sh"
PREFIX = "kaipet-"
CODE_RX = re.compile(r"^\s*(?:KAI-)?([A-Za-z0-9_-]{8,32})\s*$", re.I)
NAME_MAX, TEXT_MAX = 24, 60
RATE_PER_MIN = 6               # от одного друга не больше стольких сообщений в минуту
VISIT_S = (70, 110)            # сколько гость гостит
AWAY_MAX_S = 240               # хозяйский Кай ждёт «вернулся» не дольше
GUESTS_KEEP = 6
TYPES = {"hello", "hello_ok", "visit", "visit_done", "card"}
GUEST_LINES = [("g", "Привет! Я Кай от {who}. Пришёл в гости!", "wave"), ("k", "Ура, гости! Заходи!", "jump"),
               ("g", "У тебя тут уютно.", "curious"), ("k", "Давай потанцуем?", "playful"),
               ("g", "Давай!", "dance")]
GUEST_BYE = ("Мне пора домой. Спасибо, было здорово!", "Пока-пока! Ещё приду!", "Пора бежать. Обнимаю!")


def clean_text(text, limit: int) -> str:
    """Чужой текст: без управляющих символов и переносов, не длиннее limit."""
    text = re.sub(r"[\x00-\x1f\x7f​-‏ -‮]", " ", str(text or ""))
    return " ".join(text.split())[:limit]


def parse_code(code: str) -> str | None:
    m = CODE_RX.match(code or "")
    return m.group(1) if m else None


def safe_look(raw) -> dict:
    """Наряд гостя: только виды, цвета и вещи, которые знает этот Кай (свои SVG друга сюда не попадают)."""
    from .pet import ACCESSORIES, COLORS, KINDS, normalize_look
    raw = raw if isinstance(raw, dict) else {}
    acc = [a for a in raw.get("acc", []) if isinstance(a, str) and a in ACCESSORIES] if isinstance(raw.get("acc"), list) else []
    return normalize_look({"kind": raw.get("kind") if raw.get("kind") in KINDS else "cat",
                           "color": raw.get("color") if raw.get("color") in COLORS else "gray", "acc": acc[:8]})


def _lines(resp):
    """Строки потока ntfy сразу, как пришли (read1 не ждёт заполнения буфера)."""
    buf = b""
    read = resp.read1 if hasattr(resp, "read1") else resp.read
    while True:
        chunk = read(65536)
        if not chunk:
            if buf.strip():
                yield buf
            return
        buf += chunk
        *lines, buf = buf.split(b"\n")
        yield from (line for line in lines if line.strip())


class Transport:
    """ntfy.sh: отправить в чужой ящик и слушать свой (поток с переподключением)."""

    def __init__(self, server: str = SERVER):
        self.server = server
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._resp = None

    def publish(self, box: str, message: dict) -> bool:
        data = json.dumps(message, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(f"{self.server}/{PREFIX}{box}", data=data, method="POST",
                                     headers={"User-Agent": "KaiPet", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return 200 <= r.status < 300
        except OSError as e:
            log.info("Сеть Каев: не отправилось: %s", e)
            return False

    def listen(self, box: str, since: str, on_message: Callable[[dict, str], None]) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, args=(box, since, on_message), daemon=True)
        self._thread.start()

    def _loop(self, box: str, since: str, on_message) -> None:
        backoff = 2
        while not self._stop.is_set():
            url = f"{self.server}/{PREFIX}{box}/json?since={urllib.parse.quote(since or '12h')}"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "KaiPet"})
                with urllib.request.urlopen(req, timeout=90) as resp:
                    self._resp, backoff = resp, 2
                    for line in _lines(resp):           # по мере прихода: «for line in resp» копит буфер ~40 с
                        if self._stop.is_set():
                            return
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get("event") == "message":
                            since = event.get("id") or since
                            try:
                                body = json.loads(event.get("message") or "")
                            except ValueError:
                                continue
                            if isinstance(body, dict):
                                on_message(body, since)
            except (OSError, ValueError, AttributeError) as e:  # закрыли ответ из другого потока — это выход
                if self._stop.is_set():
                    return
                log.info("Сеть Каев: переподключаюсь через %d с (%s)", backoff, e)
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 120)

    def stop(self) -> None:
        self._stop.set()
        try:
            if self._resp is not None:
                self._resp.close()
        except OSError:
            pass


class GuestCtl(QObject):
    """Гость из сети: окно как у друга (FriendPet), но приходит ненадолго и говорит от имени хозяина."""

    def __init__(self, net: "Network", folder: Path, who: str, sender: str):
        super().__init__(net)
        from .friend import FriendPet, SCALE
        self.net, self.pet, self.who, self.sender = net, net.pet, who, sender
        self.widget = FriendPet(folder, round(self.pet.size_px * SCALE), self)
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._frame)
        self._lines = list(GUEST_LINES)

    def start(self, stay_s: float) -> None:
        self.widget.move(self._spot())
        self.widget.show()
        self.widget.play("wave", 2)
        self._tick.start(1000 // 24)
        QTimer.singleShot(1200, self, self._say_next)
        QTimer.singleShot(round(stay_s * 1000), self, self.leave)

    def _spot(self) -> QPoint:
        """С той стороны Кая, где нет друга."""
        pet, w = self.pet, self.widget
        g, area = pet.geometry(), pet._area()
        friend_left = pet.friends.here and pet.friends.side == "left"
        right = QPoint(g.right() - 18, g.bottom() - w.height() + 1)
        left = QPoint(g.left() - w.width() + 18, g.bottom() - w.height() + 1)
        spot = right if friend_left or g.left() - w.width() < area.left() else left
        if spot.x() + w.width() > area.right():
            spot = left
        return spot

    def _frame(self) -> None:
        if self.widget is not None:
            if self.widget.pos() != self._spot() and not self.widget._press:
                self.widget.move(self._spot())
            self.widget.tick()

    def _say_next(self) -> None:
        if not self._lines or self.widget is None:
            return
        who, text, anim = self._lines.pop(0)
        text = text.format(who=self.who)
        if who == "g":
            self.widget.play(anim)
            self.widget.bubble.say(text, 2800)
            self.pet._sound("chirp2")
        else:
            self.pet.gesture(anim, 1)
            self.pet.speak(text, 2800)
        if anim == "dance":                                   # танцуют вдвоём
            self.pet.play("dance", 3)
            self.widget.play("dance", 3)
        QTimer.singleShot(3000 + random.randint(0, 600), self, self._say_next)

    def leave(self) -> None:
        if self.widget is None:
            return
        self.widget.bubble.say(random.choice(GUEST_BYE), 3000)
        self.widget.play("bye")
        self.pet.gesture("wave", 2)
        w, self.widget = self.widget, None
        self._tick.stop()
        QTimer.singleShot(2500, w, w.close_all)
        self.net.guest_left(self)

    # окну FriendPet нужны эти отклики
    def petted(self) -> None:
        if self.widget is not None:
            self.widget.play("purr", 2)
            self.pet._sound("purr")

    def clicked(self) -> None:
        if self.widget is not None:
            self.widget.play("wave")
            self.widget.bubble.say(f"Я в гостях! Мой хозяин — {self.who}.", 3000)

    def dropped(self, _pos) -> None:
        pass

    def menu(self, _pos) -> None:
        pass

    def kai_event(self, _event: str) -> None:
        pass


class Network(QObject):
    got = Signal(dict, str)                 # сообщение из потока → в поток интерфейса

    def __init__(self, pet: "Pet", transport: Transport | None = None):
        super().__init__(pet)
        self.pet = pet
        self.transport = transport or Transport()
        self.guest: GuestCtl | None = None
        self.away: str | None = None        # мой Кай сейчас в гостях у…
        self._sign_before = ""
        self._export: QProcess | None = None
        self._recent: dict[str, collections.deque] = {}
        self._asking = False
        self.got.connect(self._handle)
        st = self._state()
        if st.get("on") and st.get("id"):
            QTimer.singleShot(3000, self, self.start)

    # --- состояние ---
    def _state(self) -> dict:
        from .pet import load_state
        st = load_state().get("net")
        return dict(st) if isinstance(st, dict) else {}

    def _save(self, **changes) -> dict:
        from .pet import save_state
        st = self._state()
        st.update(changes)
        save_state("net", st)
        return st

    @property
    def my_id(self) -> str:
        st = self._state()
        if not st.get("id"):
            st = self._save(id=secrets.token_urlsafe(9).replace("-", "x").replace("_", "y"))
        return st["id"]

    @property
    def code(self) -> str:
        return f"KAI-{self.my_id}"

    @property
    def friends(self) -> dict[str, str]:
        f = self._state().get("friends")
        return {k: v for k, v in f.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(f, dict) else {}

    def my_name(self, ask: bool = True) -> str:
        name = clean_text(self._state().get("name", ""), NAME_MAX)
        if name or not ask:
            return name
        dlg = QInputDialog()
        dlg.setWindowTitle("Сеть Каев")
        dlg.setLabelText("Как тебя зовут? Это имя увидят друзья, к которым придёт твой Кай.")
        if dlg.exec() and clean_text(dlg.textValue(), NAME_MAX):
            self._save(name=clean_text(dlg.textValue(), NAME_MAX))
        return clean_text(self._state().get("name", ""), NAME_MAX)

    # --- включить, выключить ---
    def start(self) -> None:
        self._save(on=True)
        self.transport.listen(self.my_id, self._state().get("since", "12h"), lambda m, since: self.got.emit(m, since))

    def stop(self, forget: bool = False) -> None:
        self.transport.stop()
        self._save(on=False)

    def shutdown(self) -> None:
        self.transport.stop()
        if self._export is not None:
            self._export.kill()
            self._export = None
        if self.guest and self.guest.widget is not None:
            self.guest.widget.close_all()
            self.guest.widget = None

    # --- отправка ---
    def send(self, to: str, kind: str, **fields) -> bool:
        msg = {"v": 1, "type": kind, "from": self.my_id, "name": self.my_name(ask=False) or "друг", **fields}
        ok = self.transport.publish(to, msg)
        if not ok:
            self.pet.speak("Не получилось достучаться до сети. Проверь интернет.", 5000)
        return ok

    def add_friend(self, code: str) -> bool:
        box = parse_code(code)
        if not box or box == self.my_id:
            self.pet.speak("Это не похоже на код дружбы. Он выглядит так: KAI-…", 5000)
            return False
        if not self.my_name():
            return False
        self.start()
        pending = self._state().get("pending")
        pending = dict(pending) if isinstance(pending, dict) else {}
        pending[box] = int(time.time())
        self._save(pending=pending)
        if self.send(box, "hello"):
            self.pet.speak("Отправил запрос дружбы! Как только друг ответит — сможем ходить в гости.", 7000)
            return True
        return False

    def visit(self, box: str) -> None:
        name = self.friends.get(box)
        if not name or self.away:
            return
        if self.send(box, "visit", look=self.pet.look):
            self.away = name
            self._sign_before = self.pet.sign_text
            self.pet.play("bye")
            self.pet.speak(f"Пошёл в гости к {name}!", 5000)
            self.pet.sign_text = clean_text(f"В гостях у {name}", 60)   # не сохраняем — это ненадолго
            self.pet.update()
            QTimer.singleShot(AWAY_MAX_S * 1000, self, lambda: self._back(name, quiet=True))

    def card(self, box: str, text: str) -> None:
        text = clean_text(text, TEXT_MAX)
        if text and self.send(box, "card", text=text):
            self.pet.gesture("heart", 1)
            self.pet.speak(f"Открытку отправил: «{text}»", 5000)

    def _back(self, name: str, quiet: bool = False) -> None:
        if self.away != name:
            return
        self.away = None
        self.pet.sign_text = self._sign_before
        self.pet.update()
        if not quiet:
            self.pet.play("jump")
            self.pet.speak(f"Я вернулся от {name}! Мы танцевали — было весело.", 7000)

    # --- приём ---
    def _allowed(self, sender: str) -> bool:
        now = time.monotonic()
        q = self._recent.setdefault(sender, collections.deque(maxlen=RATE_PER_MIN))
        if len(q) == RATE_PER_MIN and now - q[0] < 60:
            return False
        q.append(now)
        return True

    def _handle(self, msg: dict, since: str) -> None:
        self._save(since=since)
        kind, sender = msg.get("type"), msg.get("from")
        if kind not in TYPES or not isinstance(sender, str) or not parse_code(sender) or sender == self.my_id:
            return
        if not self._allowed(sender):
            log.info("Сеть Каев: слишком часто от %s — пропускаю", sender)
            return
        name = clean_text(msg.get("name"), NAME_MAX) or "друг"
        friends = self.friends
        if kind == "hello":
            if sender in friends:
                self.send(sender, "hello_ok")
            else:
                self._ask_friendship(sender, name)
            return
        if kind == "hello_ok":
            pending = self._state().get("pending")
            pending = dict(pending) if isinstance(pending, dict) else {}
            if sender not in friends and sender in pending:   # только ответ на наш собственный запрос
                pending.pop(sender)
                friends[sender] = name
                self._save(friends=friends, pending=pending)
                self.pet.gesture("heart", 2)
                self.pet.speak(f"{name} теперь в друзьях! Правый клик → «Друзья по сети».", 7000)
            return
        if sender not in friends:                              # гости и открытки — только от друзей
            return
        if kind == "visit":
            self._guest_comes(sender, friends[sender], safe_look(msg.get("look")))
        elif kind == "visit_done":
            self._back(friends[sender])
        elif kind == "card":
            text = clean_text(msg.get("text"), TEXT_MAX)
            if text:
                self.pet.gesture("heart", 2)
                self.pet._sound("meow")
                self.pet.speak(f"Открытка от {friends[sender]} 💌", 8000)
                before = self.pet.sign_text
                self.pet.sign_text = text
                self.pet.update()
                QTimer.singleShot(90_000, self, lambda: self._unsign(text, before))

    def _unsign(self, text: str, before: str) -> None:
        if self.pet.sign_text == text:
            self.pet.sign_text = before
            self.pet.update()

    def _ask_friendship(self, sender: str, name: str) -> None:
        if self._asking:
            return
        self._asking = True
        try:
            box = QMessageBox(QMessageBox.Question, "Сеть Каев",
                              f"{name} хочет дружить с твоим Каем по сети. Добавить в друзья?",
                              QMessageBox.Yes | QMessageBox.No)
            if self._run_box(box) == QMessageBox.Yes:
                friends = self.friends
                friends[sender] = name
                self._save(friends=friends)
                if not self.my_name():
                    return
                self.send(sender, "hello_ok")
                self.pet.speak(f"Теперь мы дружим с {name}!", 5000)
        finally:
            self._asking = False

    def _run_box(self, box: QMessageBox) -> int:
        return box.exec()

    # --- гость ---
    def guests_dir(self) -> Path:
        return self.pet.looks_root().parent / "guests"

    def _guest_comes(self, sender: str, who: str, look: dict) -> None:
        from .pet import NEWEST_ANIM, look_id
        if self.guest is not None or not self.pet.isVisible():
            return                                             # один гость за раз; спрятанный Кай гостей не принимает
        folder = self.guests_dir() / look_id(look)
        if (folder / "frames" / NEWEST_ANIM).is_dir():
            self._arrive(sender, who, folder)
            return
        from . import pet as pet_module
        tool = pet_module.exporter()
        if tool is None:
            return
        tmp = folder.with_name(folder.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("KAI_LOOK", json.dumps(look))
        env.insert("KAI_OUT", str(tmp))
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setProgram(tool[0])
        proc.setArguments(tool[1])
        self.pet.speak(f"Кто-то стучится… Это Кай от {who}!", 6000)

        def done(code, _status=None):
            if self._export is not proc:
                return
            self._export = None
            proc.deleteLater()
            if code == 0 and (tmp / "frames" / "idle").is_dir():
                shutil.rmtree(folder, ignore_errors=True)
                tmp.rename(folder)
                self._prune()
                self._arrive(sender, who, folder)
            else:
                shutil.rmtree(tmp, ignore_errors=True)
        proc.finished.connect(done)
        proc.errorOccurred.connect(lambda err: err == QProcess.FailedToStart and done(-1))
        self._export = proc
        proc.start()

    def _arrive(self, sender: str, who: str, folder: Path) -> None:
        self.guest = GuestCtl(self, folder, who, sender)
        self.guest.start(random.uniform(*VISIT_S))

    def guest_left(self, guest: GuestCtl) -> None:
        if self.guest is guest:
            self.guest = None
            self.send(guest.sender, "visit_done")

    def _prune(self) -> None:
        root = self.guests_dir()
        dirs = sorted((d for d in root.iterdir() if d.is_dir() and not d.name.endswith(".tmp")),
                      key=lambda d: d.stat().st_mtime, reverse=True)
        for d in dirs[GUESTS_KEEP:]:
            shutil.rmtree(d, ignore_errors=True)

    # --- меню ---
    def fill_menu(self, menu: QMenu) -> None:
        menu.addAction(f"Мой код: {self.code} (скопировать)").triggered.connect(lambda _c=False: self.copy_code())
        menu.addAction("Добавить друга по коду…").triggered.connect(lambda _c=False: self._ask_code())
        friends = self.friends
        if friends:
            menu.addSeparator()
        for box, name in friends.items():
            sub = menu.addMenu(name)
            go = sub.addAction("Сходить в гости")
            go.setEnabled(self.away is None)
            go.triggered.connect(lambda _c=False, b=box: self.visit(b))
            sub.addAction("Отправить открытку…").triggered.connect(lambda _c=False, b=box: self._ask_card(b))
            sub.addAction("Удалить из друзей").triggered.connect(lambda _c=False, b=box: self.remove(b))
        menu.addSeparator()
        on = bool(self._state().get("on"))
        menu.addAction("Выключить сеть" if on else "Включить сеть").triggered.connect(
            lambda _c=False: self.stop() if on else self.start())
        menu.addAction("Работает через ntfy.sh: только имя, наряд и открытки").setEnabled(False)

    def copy_code(self) -> None:
        QApplication.clipboard().setText(self.code)
        self.start()                                           # показал код — значит, ждём друзей
        self.pet.speak(f"Мой код {self.code} скопирован. Отправь его другу — пусть добавит меня.", 9000)

    def _ask_code(self) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Сеть Каев")
        dlg.setLabelText("Код дружбы друга (KAI-…):")
        if dlg.exec():
            self.add_friend(dlg.textValue())

    def _ask_card(self, box: str) -> None:
        dlg = QInputDialog()
        dlg.setWindowTitle("Открытка")
        dlg.setLabelText(f"Что написать на табличке у {self.friends.get(box, 'друга')}? (до {TEXT_MAX} знаков)")
        if dlg.exec():
            self.card(box, dlg.textValue())

    def remove(self, box: str) -> None:
        friends = self.friends
        friends.pop(box, None)
        self._save(friends=friends)
