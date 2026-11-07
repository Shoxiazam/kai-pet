"""Друг Кая — второй питомец со своим характером. Сидит рядом, болтает с Каем, играет, ссорится и мирится.

Кадры друга рисуются тем же character/export.mjs, но в свою папку (friend/<образ>): уборка образов Кая их не трогает.
"""
from __future__ import annotations

import collections
import json
import logging
import random
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QWidget

from .bubble import Bubble

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

SCALE = 0.85                    # друг чуть меньше Кая
SCENE_EVERY_S = (45, 110)       # как часто они что-нибудь затевают
JEALOUS_EVERY_S, JEALOUS_CHANCE = 60, 0.5     # гладят друга — Кай иногда ревнует
JEALOUS = ("Эй, а меня погладить?", "А я? Я тоже хороший!", "Хмф. Я тоже тут.")
COPY_GESTURES = {"heart", "like", "wave", "bye", "dance", "hug", "bow", "clap", "jump"}
FIDGETS = ("wash", "chasetail", "stretch", "yawn")   # как у Кая: мелочи от скуки
FIDGET_EVERY_S = (120, 300)
LINE_MS = 2600                  # пауза между репликами в разговоре
FRIENDS = {
    "mira": {"name": "Мира", "look": {"kind": "fox", "color": "ginger", "acc": ["bow"]},
             "about": "озорная лисичка, любит спорить и танцевать"},
    "tosha": {"name": "Тоша", "look": {"kind": "bear", "color": "terracotta", "acc": ["glasses"]},
              "about": "спокойный мишка-умник, всё знает и всех мирит"},
    "bunya": {"name": "Буня", "look": {"kind": "bunny", "color": "rose", "acc": ["flowers"]},
              "about": "весёлая зайка, всему радуется и обнимается"},
}
# Сценки: (кто говорит, текст, анимация говорящего). «k» — Кай, «f» — друг. {name} — имя друга.
TALKS = [
    [("f", "Кай, а что ты сегодня делал?", "curious"), ("k", "Помогал хозяину. Он много работает!", "proud"),
     ("f", "Тогда пусть отдохнёт. Давай его отвлечём!", "playful")],
    [("k", "{name}, смотри, какое окно большое!", "excited"), ("f", "Ага. Можно за ним спрятаться.", "playful"),
     ("k", "Чур, я первый!", "jump")],
    [("f", "Мне скучно…", "tired"), ("k", "Хочешь, станцуем?", "playful"), ("f", "Давай!", "dance")],
    [("k", "Как думаешь, печеньки ещё остались?", "curious"), ("f", "Если и остались, то ненадолго.", "playful")],
    [("f", "Кай, у тебя что-то на ухе.", "curious"), ("k", "Где?!", "surprised"), ("f", "Шучу!", "playful")],
]
QUARRELS = [
    [("f", "Это моё место!", "grumpy"), ("k", "Нет, я тут первый сидел!", "grumpy"),
     ("f", "Хмф.", "grumpy"), ("k", "Ладно, давай вместе посидим?", "caring"), ("f", "Мир!", "hug")],
    [("k", "Кто съел мою печеньку?", "cautious"), ("f", "Я? Нет… может быть…", "confused"),
     ("k", "Эх ты!", "grumpy"), ("f", "Прости! Завтра поделюсь.", "caring"), ("k", "Ну ладно.", "heart")],
]
PLAYS = [("jump", "jump", "Прыг-скок!"), ("dance", "disco", "Танцуем!"), ("clap", "clap", "Хлоп-хлоп!"),
         ("hug", "hug", "Обнимашки!")]
HELLO = ("Привет! Я {name}, друг Кая. Можно в гости?", "О, привет! Можно я тут посижу?")
CLICK = ("Хи-хи, щекотно!", "Привет!", "Я тут, я тут!", "Кай хороший, правда?", "Пойдём играть?")
BYE = "Пока! Ещё приду."


def friend_dir(looks_root: Path, look_id: str) -> Path:
    return looks_root.parent / "friend" / look_id


class FriendPet(QWidget):
    """Друг на экране — как сам Кай: следит глазами за мышкой, мурлычет, когда гладят, машет на щелчок,
    подпрыгивает, когда рядом трясут мышкой, его можно перетащить. Решения принимает Friends (ctl)."""

    def __init__(self, folder: Path, size: int, ctl: "Friends"):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(size, size)
        self.setMouseTracking(True)                # поглаживание — движение мыши без нажатия
        self.dir, self.size_px, self.ctl = folder, size, ctl
        self.cache: dict[str, list[QPixmap]] = {}
        self.anim, self.once, self.frame, self.repeat = "idle", None, 0, 0
        self.flash: tuple[str, float] | None = None
        self.gaze: QPoint | None = None            # куда смотреть вместо курсора (в прятках — туда, где Кай)
        self.shown = ""
        self._pix: QPixmap | None = None
        self._press: list | None = None
        self._stroke = [0.0, 0.0, None]
        self._trail: collections.deque = collections.deque(maxlen=30)
        self._last_jump = 0.0
        self.bubble = Bubble()

    # --- кадры ---
    def _files(self, name: str) -> list[Path]:
        if name.startswith("look_"):
            file = self.dir / "look" / f"{name[5:]}.png"
            return [file] if file.is_file() else []
        for kind in ("frames", "moods"):
            files = sorted((self.dir / kind / name).glob("*.png"))
            if files:
                return files
        return []

    def _frames(self, name: str) -> list[QPixmap]:
        if name not in self.cache:
            files = self._files(name)
            if not files:
                return self._frames("idle") if name != "idle" else []
            dpr = self.devicePixelRatioF()
            px = round(self.size_px * dpr)
            out = []
            for f in files:
                pix = QPixmap(str(f)).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pix.setDevicePixelRatio(dpr)
                out.append(pix)
            while len(self.cache) > 12:
                self.cache.pop(next(iter(self.cache)))
            self.cache[name] = out
        return self.cache[name]

    def has(self, name: str) -> bool:
        return bool(self._files(name))

    def play(self, name: str, times: int = 1) -> None:
        if (self.dir / "frames" / name).is_dir():
            self.once, self.frame, self.repeat = name, 0, times - 1
        elif self.has(name):
            self.flash = (name, time.monotonic() + 3.0 * times)

    def _cursor(self) -> QPoint:
        return QCursor.pos()

    def current(self) -> str:
        if self.once:
            return self.once
        if self.flash and time.monotonic() < self.flash[1]:
            return self.flash[0]
        self.flash = None
        if self.anim in ("idle", "curious"):        # спокоен — следит глазами за мышкой, как Кай
            from .pet import look_at
            target, center = self.gaze or self._cursor(), self.geometry().center()
            radius = self.ctl.pet.cfg.look_radius_px * (3 if self.gaze else 1)
            look = look_at(target.x() - center.x(), target.y() - center.y(), radius, self.size_px / 2)
            if look and self.has(look):
                return look
        return self.anim

    def tick(self) -> None:
        self._maybe_jump()
        name = self.current()
        if name != self.shown:
            self.shown, self.frame = name, 0
        frames = self._frames(name)
        if not frames:
            return
        if self.frame >= len(frames):
            self.frame = 0
            if self.once and self.repeat > 0:
                self.repeat -= 1
            elif self.once:
                self.once = None
                self.shown = name = self.current()
                frames = self._frames(name)
        self._pix = frames[min(self.frame, len(frames) - 1)]
        self.frame += 1
        self.update()

    def _maybe_jump(self) -> None:
        """Трясут мышкой рядом — подпрыгивает за курсором, как Кай."""
        from .pet import CHASE_COOLDOWN_S, CHASE_RADIUS, shaking
        if self.once or self._press:
            return
        now, c = time.monotonic(), self._cursor()
        self._trail.append((now, c.x()))
        center = self.geometry().center()
        if (now - self._last_jump < CHASE_COOLDOWN_S
                or abs(c.x() - center.x()) + abs(c.y() - center.y()) > CHASE_RADIUS or not shaking(self._trail, now)):
            return
        self._last_jump = now
        self._trail.clear()
        self.play("jump", 2)
        self.ctl.kai_event("hunt_friend")

    def paintEvent(self, _event):
        if self._pix is not None:
            QPainter(self).drawPixmap(0, 0, self._pix)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.bubble.place(self.geometry())

    def hideEvent(self, event):
        self.bubble.hide()
        super().hideEvent(event)

    # --- мышь: щелчок — помахать, перетащить — пересадить, погладить — мурлыкать, правый — меню ---
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = [e.globalPosition().toPoint(), self.pos(), False]

    def mouseMoveEvent(self, e):
        from .pet import PET_DISTANCE, PET_GAP_S
        if self._press:
            start, origin, _ = self._press
            delta = e.globalPosition().toPoint() - start
            if abs(delta.x()) + abs(delta.y()) > 4:
                self._press[2] = True
            if self._press[2]:
                self.move(origin + delta)
            return
        now, pos = time.monotonic(), e.globalPosition()
        length, last_t, last_pos = self._stroke
        length = 0.0 if last_pos is None or now - last_t > PET_GAP_S else \
            length + abs(pos.x() - last_pos.x()) + abs(pos.y() - last_pos.y())
        self._stroke = [length, now, pos]
        if length > PET_DISTANCE:
            self._stroke = [0.0, now, pos]
            self.ctl.petted()

    def mouseReleaseEvent(self, e):
        if self._press and e.button() == Qt.LeftButton:
            moved = self._press[2]
            self._press = None
            if moved:
                self.ctl.dropped(self.pos())
            else:
                self.ctl.clicked()

    def contextMenuEvent(self, e):
        self.ctl.menu(e.globalPos())

    def close_all(self) -> None:
        self.bubble.hide()
        self.bubble.deleteLater()
        self.hide()
        self.deleteLater()


class Friends(QObject):
    """Позвать друга, отпустить домой и сценки с Каем."""

    def __init__(self, pet: "Pet"):
        super().__init__(pet)
        self.pet = pet
        self.who = "mira"
        self.widget: FriendPet | None = None
        self._export: QProcess | None = None
        self._scene: list = []
        self._next_scene = 0.0
        self._fidget_at = time.monotonic() + random.uniform(*FIDGET_EVERY_S)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._follow = QTimer(self)
        self._follow.timeout.connect(self._stay_near)
        self.free: QPoint | None = None            # куда друга пересадили мышкой; None — рядом с Каем
        self._jealous_at = 0.0
        from .pet import load_state
        saved = load_state().get("buddy")
        if isinstance(saved, dict) and saved.get("who") in FRIENDS:
            self.who = saved["who"]
            pos = saved.get("pos")
            if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int) for v in pos):
                self.free = QPoint(*pos)
            if saved.get("on"):
                QTimer.singleShot(4000, lambda: self.invite(self.who, greet=False))
        guard = getattr(pet, "guard", None)
        if guard is not None:
            guard.alarm.connect(lambda _photo: self.kai_event("alarm"))

    @property
    def name(self) -> str:
        return FRIENDS[self.who]["name"]

    @property
    def here(self) -> bool:
        return self.widget is not None

    def _save(self, on: bool) -> None:
        from .pet import save_state
        pos = [self.free.x(), self.free.y()] if self.free is not None else None
        save_state("buddy", {"who": self.who, "on": on, "pos": pos})

    # --- позвать / отпустить ---
    def invite(self, who: str = "", greet: bool = True) -> None:
        from .pet import look_id, normalize_look
        who = who if who in FRIENDS else self.who
        if self.here and who == self.who:
            self.widget.play("wave")
            return
        self.leave(say=False)
        self.who = who
        self._save(True)
        look = normalize_look(FRIENDS[who]["look"])
        folder = friend_dir(self.pet.looks_root(), look_id(look))
        if (folder / "frames" / "idle").is_dir():
            self._arrive(folder, greet)
        else:
            self._draw(look, folder, greet)

    def leave(self, say: bool = True) -> None:
        if self._export is not None:
            self._export.kill()
            self._export = None
        if not self.here:
            return
        if say:
            self.widget.bubble.say(BYE, 3000)
            self.widget.play("bye")
        w, self.widget = self.widget, None
        self._timer.stop()
        self._follow.stop()
        self._scene = []
        QTimer.singleShot(1800 if say else 0, w.close_all)
        self._save(False)

    def shutdown(self) -> None:
        if self._export is not None:
            self._export.kill()
            self._export = None
        if self.widget is not None:
            self._timer.stop()
            self._follow.stop()
            self.widget.close_all()
            self.widget = None

    def _draw(self, look: dict, folder: Path, greet: bool) -> None:
        from .pet import ROOT
        node, script = shutil.which("node"), ROOT / "character" / "export.mjs"
        if not node or not script.is_file():
            self.pet.speak("Друг не может прийти: нужен Node.js и Edge или Chrome.", 6000)
            return
        tmp = folder.with_name(folder.name + ".tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        env = QProcessEnvironment.systemEnvironment()
        env.insert("KAI_LOOK", json.dumps(look))
        env.insert("KAI_OUT", str(tmp))
        proc = QProcess(self)
        proc.setProcessEnvironment(env)
        proc.setProgram(node)
        proc.setArguments([str(script)])

        def finished(code, _status=None):
            if self._export is not proc:
                return
            self._export = None
            proc.deleteLater()
            if code == 0 and (tmp / "frames" / "idle").is_dir():
                shutil.rmtree(folder, ignore_errors=True)
                tmp.rename(folder)
                self._arrive(folder, greet)
            else:
                shutil.rmtree(tmp, ignore_errors=True)
                log.warning("Друг Кая не нарисовался (код %s)", code)
                self.pet.speak(f"Не получилось позвать друга ({self.name}). Попробуй позже.", 6000)
        proc.finished.connect(finished)
        proc.errorOccurred.connect(lambda err: err == QProcess.FailedToStart and finished(-1))
        self._export = proc
        proc.start()
        self.pet.speak(f"Зову друга: {self.name}… Около 20 секунд.", 20000)

    def _arrive(self, folder: Path, greet: bool) -> None:
        size = round(self.pet.size_px * SCALE)
        self.widget = FriendPet(folder, size, self)
        self._place()
        self.widget.show()
        self.widget.play("wave", 2)
        if greet:
            self.widget.bubble.say(random.choice(HELLO).format(name=self.name), 6000)
            QTimer.singleShot(2500, lambda: self.pet.play("wave"))
        self._timer.start(1000 // 24)
        self._follow.start(200)
        self._next_scene = time.monotonic() + random.uniform(15, 30)

    # --- где сидеть: рядом с Каем, с той стороны, где есть место ---
    def _spot(self) -> QPoint:
        pet, w = self.pet, self.widget
        area = pet._area()
        if self.free is not None:                  # пересадили мышкой — сидит там, пока не позовут к Каю
            return QPoint(min(max(self.free.x(), area.left()), area.right() - w.width()),
                          min(max(self.free.y(), area.top()), area.bottom() - w.height()))
        g = pet.geometry()
        y = g.bottom() - w.height() + 1
        left = g.left() - w.width() + 18
        x = left if left >= area.left() else g.right() - 18
        return QPoint(x, min(max(y, area.top()), area.bottom() - w.height()))

    def _place(self) -> None:
        if self.widget is not None:
            self.widget.move(self._spot())

    def _stay_near(self) -> None:
        w = self.widget
        if w is None:
            return
        if not self.pet.isVisible():          # в прятках друг ждёт на месте, а Кая убрали совсем — уходит с ним
            games = getattr(self.pet, "games", None)
            if not (games and games.active == "seek") and w.isVisible():
                w.hide()
            return
        if not w.isVisible():
            w.show()
        if w._press:                                # друга сейчас тащат мышкой
            return
        target = self._spot()
        if (target - w.pos()).manhattanLength() > 3:
            w.move(target)

    # --- как с Каем: щелчок, поглаживание, печенька, пересадить, меню ---
    def clicked(self) -> None:
        if self.widget is None:
            return
        self.widget.play(random.choice(["wave", "jump", "heart"]))
        self.widget.bubble.say(random.choice(CLICK), 4000)
        self.pet._sound("meow")

    def petted(self) -> None:
        """Гладят друга: мурлычет. Кай иногда ревнует."""
        w = self.widget
        if w is None or w.once == "purr":
            return
        w.play("purr", 2)
        self.pet._sound("purr")
        now = time.monotonic()
        if now - self._jealous_at > JEALOUS_EVERY_S and random.random() < JEALOUS_CHANCE and not self.pet.once:
            self._jealous_at = now
            QTimer.singleShot(1500, self._jealous)

    def _jealous(self) -> None:
        self.pet.gesture("grumpy", 1)
        self.pet.speak(random.choice(JEALOUS), 5000)

    def feed(self) -> None:
        """Печенька другу — раз в день, как Каю."""
        from .pet import load_state, save_state
        if self.widget is None:
            return
        today = time.strftime("%Y-%m-%d")
        fed = load_state().get("buddy_fed")
        fed = fed if isinstance(fed, dict) else {}
        if fed.get(self.who) == today:
            self.widget.bubble.say("Спасибо, я уже наелся! Давай завтра.", 4000)
            return
        fed[self.who] = today
        save_state("buddy_fed", fed)
        self.widget.play("eat")
        self.pet._sound("munch")
        self.widget.bubble.say("Ням! Спасибо!", 4000)
        QTimer.singleShot(2200, lambda: self.pet.speak(f"{self.name}, оставь и мне кусочек!", 4000))

    def dropped(self, pos: QPoint) -> None:
        """Друга отпустили: рядом с Каем — снова сидит с ним, в другом месте — остаётся там."""
        w = self.widget
        near = (pos + QPoint(w.width() // 2, w.height() // 2)
                - self.pet.geometry().center()).manhattanLength() < self.pet.size_px * 1.3
        self.free = None if near else QPoint(pos)
        self._save(True)
        w.play("wave")

    def sit_with_kai(self) -> None:
        self.free = None
        self._save(True)
        self._place()

    def menu(self, pos: QPoint) -> None:
        if self.widget is None:
            return
        menu = QMenu()
        menu.addAction("Погладить").triggered.connect(lambda _c=False: self.petted())
        menu.addAction("Угостить печенькой").triggered.connect(lambda _c=False: self.feed())
        menu.addAction("Поболтать с Каем").triggered.connect(lambda _c=False: self.scene("talk"))
        menu.addAction("Поиграть с Каем").triggered.connect(lambda _c=False: self.scene("play"))
        if self.free is not None:
            menu.addAction("Сесть рядом с Каем").triggered.connect(lambda _c=False: self.sit_with_kai())
        menu.addSeparator()
        menu.addAction(f"{self.name} — {FRIENDS[self.who]['about']}").setEnabled(False)
        menu.addAction("Отпустить домой").triggered.connect(lambda _c=False: self.leave())
        self._show_menu(menu, pos)

    def _show_menu(self, menu: QMenu, pos: QPoint) -> None:
        menu.exec(pos)

    # --- вместе с Каем: друг отзывается на всё, что делает Кай ---
    def kai_event(self, event: str) -> None:
        w = self.widget
        if w is None or self._scene or not w.isVisible():
            return
        if event == "petted":
            if random.random() < 0.3:
                w.play("clap")
        elif event == "fed":
            w.flash = ("curious", time.monotonic() + 3)
            w.bubble.say(random.choice(("А мне печеньку?", "Вкусно пахнет!", "Поделишься?")), 4000)
        elif event == "done":
            w.play("clap")
        elif event == "failed":
            w.play("hug")
            w.bubble.say(random.choice(("Не грусти, Кай!", "Ничего, в следующий раз получится!")), 4000)
        elif event == "hunt":
            QTimer.singleShot(250, lambda: self.widget and self.widget.play("jump", 2))
        elif event == "hunt_friend":
            if not self.pet.once and self.pet.loop == "idle":
                QTimer.singleShot(250, lambda: self.pet.play("jump"))
        elif event == "found":
            w.play("clap", 2)
            w.bubble.say("Ура, нашёлся!", 3000)
        elif event == "alarm":
            w.flash = ("surprised", time.monotonic() + 6)
            w.bubble.say("Чужой! Кай, зови хозяина!", 6000)
        elif event.startswith("gesture:"):               # повторяет жест за Каем
            name = event[8:]
            if name in COPY_GESTURES:
                QTimer.singleShot(500, lambda: self.widget and self.widget.play(name, 2))

    # --- поведение ---
    def _mirror(self) -> None:
        """Фон друга повторяет настроение Кая: спит, когда Кай спит, танцует, когда Кай танцует."""
        w, shown = self.widget, self.pet.shown
        if shown in ("bed", "sleepy"):
            w.anim = shown if w.has(shown) else "idle"          # Кай в кроватке — и друг спит
        elif self.pet.music and w.has(shown):
            w.anim = shown
        elif shown in ("working", "waiting"):
            w.anim = "curious" if w.has("curious") else "idle"
        else:
            w.anim = "idle"

    def _tick(self) -> None:
        w = self.widget
        if w is None:
            return
        games = getattr(self.pet, "games", None)
        ears = games.ears if games is not None and games.active == "seek" else None
        w.gaze = ears.geometry().center() if ears is not None else None    # в прятках выдаёт Кая взглядом
        self._mirror()
        w.tick()
        now = time.monotonic()
        if self._scene:
            return
        busy = (self.pet.loop != "idle" or self.pet.bubble.asking or self.pet.once or not self.pet.isVisible()
                or getattr(self.pet, "games", None) and self.pet.games.active or self.pet.shown in ("bed", "sleepy"))
        if now >= self._next_scene and not busy:
            self._next_scene = now + random.uniform(*SCENE_EVERY_S)
            self.scene()
        elif now >= self._fidget_at and not w.once and w.anim == "idle":
            self._fidget_at = now + random.uniform(*FIDGET_EVERY_S)
            w.play(random.choice(FIDGETS))           # от скуки: умывается, гоняется за хвостом, зевает

    def scene(self, kind: str = "") -> None:
        """Сценка: разговор, игра или ссора с примирением."""
        if self.widget is None:
            return
        kind = kind or random.choices(["talk", "play", "quarrel"], weights=[5, 3, 2])[0]
        if kind == "play":
            k_anim, f_anim, line = random.choice(PLAYS)
            self.pet.play(k_anim, 2)
            self.widget.play(f_anim, 2)
            self.widget.bubble.say(line, 3000)
            return
        lines = random.choice(QUARRELS if kind == "quarrel" else TALKS)
        self._scene = list(lines)
        self._say_next()

    def _say_next(self) -> None:
        if not self._scene or self.widget is None:
            self._scene = []
            return
        who, text, anim = self._scene.pop(0)
        text = text.format(name=self.name)
        if who == "k":
            self.pet.gesture(anim, 1)
            self.pet.speak(text, LINE_MS)
        else:
            self.widget.play(anim)
            self.widget.bubble.say(text, LINE_MS)
        QTimer.singleShot(LINE_MS, self._say_next)

    def command(self, text: str) -> bool:
        low = text.lower()
        words = low.replace(",", " ").split()
        bye = any(w in low for w in ("отпусти", "пока", "уходи", "домой"))
        call = any(w in low for w in ("позови", "пригласи", "зови", "приведи"))
        for key, info in FRIENDS.items():
            stem = info["name"].lower()[:-1]          # Мира, Миру, Мире; Тоша, Тошу; Буня, Буню
            if (call or bye) and any(w.startswith(stem) and len(w) <= len(stem) + 2 for w in words):
                self.leave() if bye else self.invite(key)
                return True
        if any(w in low for w in ("позови друга", "позови подругу", "друга в гости", "подругу в гости")):
            self.invite(self.who)
            return True
        if any(w in low for w in ("отпусти друга", "друг домой", "подруга домой")):
            self.leave()
            return True
        return False
