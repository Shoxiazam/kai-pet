"""Друг Кая — второй питомец со своим характером. Сидит рядом, болтает с Каем, играет, ссорится и мирится.

Кадры друга рисуются тем же kai_pet.export, но в свою папку (friend/<образ>): уборка образов Кая их не трогает.
"""
from __future__ import annotations

import collections
import datetime
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

from . import talks
from .bubble import Bubble

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

SCALE = 0.85                    # друг чуть меньше Кая
FIRST_SCENE_S = (15, 35)        # первая сценка после прихода; дальше паузы — talks.next_pause
JEALOUS_EVERY_S, JEALOUS_CHANCE = 60, 0.5     # гладят друга — Кай иногда ревнует
JEALOUS = ("Эй, а меня погладить?", "А я? Я тоже хороший!", "Хмф. Я тоже тут.")
COPY_GESTURES = {"heart", "like", "wave", "bye", "dance", "hug", "bow", "clap", "jump", "laugh", "spin", "shy",
                 "think", "disco", "robot", "waltz", "hiphop", "bounce", "clapdance", "airguitar", "headbang"}
COPY_MOODS = {"curious", "excited", "playful", "surprised", "proud", "caring", "grumpy", "confused", "inspired"}
# Держатся за лапки: где сидит друг относительно Кая (доли роста Кая) — так кончики лапок встречаются (hold.png).
HOLD_DX, HOLD_DY = 0.60, 0.11
WALK_PX_S = 420                 # скорость, с которой друг бежит к Каю
WALK_FROM_PX = 70               # дальше этого — бежит, ближе — просто пересаживается
DUET_PHASE_S = (5, 9)           # сколько длится одно движение в танце вдвоём
DUET = ("hold", "same", "mix", "clapdance", "spin", "hold", "bounce", "high", "same")
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
        from .host import keep_visible
        keep_visible(self)
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
            while len(self.cache) >= 6:              # память не растёт: дольше всех не нужный набор — вон
                self.cache.pop(next(iter(self.cache)))
            self.cache[name] = out
        else:
            self.cache[name] = self.cache.pop(name)
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
        self.mode = "near"                         # near — рядом, hold — держатся за лапки
        self.duet: str | None = None               # танцуют вдвоём: текущее движение
        self._duet_until = 0.0
        self._walk = None                          # бежит к Каю (QPropertyAnimation)
        self._recent: list[str] = []               # недавние темы — чтобы не повторяться
        from .pet import load_state
        saved = load_state().get("buddy")
        if isinstance(saved, dict) and saved.get("who") in FRIENDS:
            self.who = saved["who"]
            pos = saved.get("pos")
            if isinstance(pos, list) and len(pos) == 2 and all(isinstance(v, int) for v in pos):
                self.free = QPoint(*pos)
            if saved.get("on"):
                self._later(4000, lambda: self.invite(self.who, greet=False))
        guard = getattr(pet, "guard", None)
        if guard is not None:
            guard.alarm.connect(lambda _photo: self.kai_event("alarm"))

    # --- свой голос друга: тот же «мяу-говорок», но выше или ниже (assets/sounds/friends/<кто>/) ---
    def _sound(self, name: str) -> None:
        if not self.pet.sounds_on:
            return
        from . import sounds
        own = self.pet.base / "sounds" / "friends" / self.who / f"{name}.wav"
        sounds.play(own if own.is_file() else self.pet.base / "sounds" / f"{name}.wav")

    def _say(self, text: str, hide_after_ms: int = 4000) -> None:
        """Реплика друга облачком и его голосом (как speak у Кая, но звук свой)."""
        if self.widget is None:
            return
        self.widget.bubble.say(text, hide_after_ms)
        if text.strip() and self.widget.isVisible():
            self._sound("chirp1" if len(text) < 25 else "chirp2" if len(text) < 60 else "chirp3")

    def _later(self, ms: int, fn) -> None:
        """Отложить, но с привязкой к себе: Кая закрыли — таймер умирает вместе с ним."""
        QTimer.singleShot(ms, self, fn)

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
        from .pet import NEWEST_ANIM
        if (folder / "frames" / NEWEST_ANIM).is_dir():
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
            self._say(BYE, 3000)
            self.widget.play("bye")
        w, self.widget = self.widget, None
        self._timer.stop()
        self._follow.stop()
        self._scene = []
        self._release()
        QTimer.singleShot(1800 if say else 0, w, w.close_all)   # окно друга само себя закроет
        self._save(False)

    def shutdown(self) -> None:
        if self._export is not None:
            self._export.kill()
            self._export = None
        if self._walk is not None:
            self._walk.stop()
            self._walk = None
        if self.widget is not None:
            self._timer.stop()
            self._follow.stop()
            self.widget.close_all()
            self.widget = None
        self._release()

    def _draw(self, look: dict, folder: Path, greet: bool) -> None:
        from . import pet as pet_module
        tool = pet_module.exporter()
        if tool is None:
            self.pet.speak("Друг не может прийти: нужен браузер Edge или Chrome.", 6000)
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
            self._say(random.choice(HELLO).format(name=self.name), 6000)
            self._later(2500, lambda: self.pet.play("wave"))
        self._timer.start(1000 // 24)
        self._follow.start(200)
        self._next_scene = time.monotonic() + random.uniform(*FIRST_SCENE_S)

    # --- где сидеть: рядом с Каем, с той стороны, где есть место ---
    def _spot(self) -> QPoint:
        pet, w = self.pet, self.widget
        area = pet._area()
        if self.free is not None:                  # пересадили мышкой — сидит там, пока не позовут к Каю
            return QPoint(min(max(self.free.x(), area.left()), area.right() - w.width()),
                          min(max(self.free.y(), area.top()), area.bottom() - w.height()))
        g, k = pet.geometry(), pet.size_px
        if self.mode == "hold":                    # держатся за лапки — ближе и чуть выше, лапка к лапке
            x = g.left() - round(HOLD_DX * k) if self.side == "left" else g.left() + k + round(HOLD_DX * k) - w.width()
            return QPoint(x, g.top() + round(HOLD_DY * k))
        y = g.bottom() - w.height() + 1
        x = g.left() - w.width() + 18 if self.side == "left" else g.right() - 18
        return QPoint(x, min(max(y, area.top()), area.bottom() - w.height()))

    @property
    def side(self) -> str:
        """С какой стороны от Кая друг: слева, если там хватает места."""
        w, g = self.widget, self.pet.geometry()
        return "left" if g.left() - (w.width() if w else 0) >= self.pet._area().left() else "right"

    def toward_kai(self) -> str:
        """В какую сторону тянуться другу (к Каю): друг слева — вправо."""
        return "R" if self.side == "left" else "L"

    def toward_friend(self) -> str:
        return "L" if self.side == "left" else "R"

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
        if w._press or self._walk is not None:      # друга тащат мышкой или он уже бежит
            return
        target = self._spot()
        dist = (target - w.pos()).manhattanLength()
        if dist > WALK_FROM_PX and self.free is None:
            self.walk_to(target)                     # Кая переставили — друг бежит за ним
        elif dist > 3:
            w.move(target)

    def walk_to(self, target: QPoint, then=None) -> None:
        from PySide6.QtCore import QPropertyAnimation
        w = self.widget
        if w is None:
            return
        dist = (target - w.pos()).manhattanLength()
        w.once, w.frame, w.repeat = ("runRight" if target.x() > w.x() else "runLeft"), 0, 99
        self._walk = QPropertyAnimation(w, b"pos", self)
        self._walk.setDuration(max(250, round(1000 * dist / WALK_PX_S)))
        self._walk.setEndValue(target)

        def arrived():
            self._walk = None
            if self.widget is not None:
                self.widget.once, self.widget.repeat = None, 0
            if then:
                then()
        self._walk.finished.connect(arrived)
        self._walk.start()

    # --- как с Каем: щелчок, поглаживание, печенька, пересадить, меню ---
    def clicked(self) -> None:
        if self.widget is None:
            return
        self.widget.play(random.choice(["wave", "jump", "heart"]))
        self._say(random.choice(CLICK), 4000)
        self._sound("meow")

    def petted(self) -> None:
        """Гладят друга: мурлычет. Кай иногда ревнует."""
        w = self.widget
        if w is None or w.once == "purr":
            return
        w.play("purr", 2)
        self._sound("purr")
        now = time.monotonic()
        if now - self._jealous_at > JEALOUS_EVERY_S and random.random() < JEALOUS_CHANCE and not self.pet.once:
            self._jealous_at = now
            self._later(1500, self._jealous)

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
            self._say("Спасибо, больше не влезет! Давай завтра.", 4000)
            return
        fed[self.who] = today
        save_state("buddy_fed", fed)
        self.widget.play("eat")
        self._sound("munch")
        self._say("Ням! Спасибо!", 4000)
        self._later(2200, lambda: self.pet.speak(f"{self.name}, оставь и мне кусочек!", 4000))

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
        menu.addAction("Взяться за лапки").triggered.connect(lambda _c=False: self.scene("hold"))
        menu.addAction("Дать пять").triggered.connect(lambda _c=False: self.scene("high"))
        menu.addAction("Догонялки вокруг Кая").triggered.connect(lambda _c=False: self.run_around())
        menu.addAction("Сказать нам…").triggered.connect(lambda _c=False: self.pet._talk())
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
            self._say(random.choice(("А мне печеньку?", "Вкусно пахнет!", "Поделишься?")), 4000)
        elif event == "done":
            w.play("clap")
        elif event == "failed":
            w.play("hug")
            self._say(random.choice(("Не грусти, Кай!", "Ничего, в следующий раз получится!")), 4000)
        elif event == "hunt":
            self._later(250, lambda: self.widget and self.widget.play("jump", 2))
        elif event == "hunt_friend":
            if not self.pet.once and self.pet.loop == "idle":
                self._later(250, lambda: self.pet.play("jump"))
        elif event == "dressed":                           # Кай вышел из шкафа в обновке
            w.play(random.choice(("clap", "heart")))
            self._say(random.choice(("Тебе идёт!", "Красавчик!", "Ого, какой модный!", "Мне нравится!")), 3500)
        elif event == "found":
            w.play("clap", 2)
            self._say("Ура, нашёлся!", 3000)
        elif event == "alarm":
            w.flash = ("surprised", time.monotonic() + 6)
            self._say("Чужой! Кай, зови хозяина!", 6000)
        elif event.startswith("gesture:"):               # Каю сказали — делают оба
            name = event[8:]
            if name in ("highL", "highR"):               # Кай дал пять — друг отвечает навстречу
                self._later(150, lambda: self.widget and self.widget.play("high" + self.toward_kai()))
            elif name in COPY_GESTURES:
                self._later(400, lambda: self.widget and self.widget.play(name, 2))
            elif name in COPY_MOODS:
                self._later(400, lambda: self.widget and self.widget.play(name, 1))

    # --- поведение ---
    def _mirror(self) -> None:
        """Фон друга повторяет настроение Кая: спит, когда Кай спит, работает рядом, когда Кай работает."""
        w, shown = self.widget, self.pet.shown
        if self.duet or self.mode == "hold":
            return
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
        if w is None or not w.isVisible():          # друга спрятали — кадры не рисуем
            return
        games = getattr(self.pet, "games", None)
        ears = games.ears if games is not None and games.active == "seek" else None
        w.gaze = ears.geometry().center() if ears is not None else None    # в прятках выдаёт Кая взглядом
        now = time.monotonic()
        self._dance_together(now)
        self._mirror()
        w.tick()
        if self._scene or self.duet:
            return
        busy = (self.pet.loop != "idle" or self.pet.bubble.asking or self.pet.once or not self.pet.isVisible()
                or getattr(self.pet, "games", None) and self.pet.games.active or self.pet.shown in ("bed", "sleepy"))
        if now >= self._next_scene and not busy:
            hour, _ = talks.today()
            self._next_scene = now + talks.next_pause(hour, self.pet._idle_s())   # то болтают подряд, то молчат
            self.scene()
        elif now >= self._fidget_at and not w.once and w.anim == "idle":
            self._fidget_at = now + random.uniform(*FIDGET_EVERY_S)
            w.play(random.choice(FIDGETS))           # от скуки: умывается, гоняется за хвостом, зевает

    # --- танцуют вдвоём, пока играет музыка ---
    def _dance_together(self, now: float) -> None:
        pet, w = self.pet, self.widget
        can = (pet.music and pet.dance_on and pet.loop == "idle" and pet.isVisible() and self.free is None
               and not (getattr(pet, "games", None) and pet.games.active) and not self._scene)
        if not can:
            if self.duet:
                self.duet = None
                self._release()
            return
        if self.duet and now < self._duet_until:
            return
        first = self.duet is None
        choices = [d for d in DUET if d != self.duet]
        self.duet = "hold" if first else random.choice(choices)       # сначала берутся за лапки
        self._duet_until = now + random.uniform(*DUET_PHASE_S)
        if first:
            self._say(random.choice(("Пошли танцевать!", "Ура, музыка!", "Берись за лапку!")), 3000)
        self._duet_step(self.duet)

    def _duet_step(self, step: str) -> None:
        from .pet import DANCES, MUSIC_MOODS
        pet, w = self.pet, self.widget
        mine = pet.dance_style if pet._has(pet.dance_style) else "groove"
        if step == "hold":
            self._hold(True)
            pet.partner_anim, w.anim = "hold" + self.toward_friend(), "hold" + self.toward_kai()
            return
        self._hold(False)
        if step == "high":
            pet.play("high" + self.toward_friend())
            w.play("high" + self.toward_kai())
            pet.partner_anim, w.anim = mine, mine
        elif step == "same":
            pet.partner_anim = w.anim = mine
        elif step == "mix":                       # каждый своё, но под одно настроение музыки
            other = [d for d in MUSIC_MOODS.get(pet.music_mood, ()) if d != mine] or sorted(DANCES - {mine})
            pet.partner_anim, w.anim = mine, random.choice(other)
        else:                                     # clapdance, spin, bounce — одно движение вместе
            pet.partner_anim = w.anim = step
        pet.frame = w.frame = 0                   # в такт: с первого кадра одновременно

    def _hold(self, on: bool) -> None:
        mode = "hold" if on else "near"
        if mode != self.mode:
            self.mode = mode
            if self.widget is not None and self._walk is None:
                self.walk_to(self._spot())

    def _release(self) -> None:
        self.pet.partner_anim = None
        self.mode = "near"
        if self.widget is not None:
            self.widget.anim = "idle"

    # --- сценки ---
    def scene(self, kind: str = "") -> None:
        """Сценка по обстановке: разговор на тему, игра, «за лапки», «дай пять», реплика друга или ссора."""
        if self.widget is None:
            return
        kind = kind or random.choices(["talk", "play", "hold", "high", "solo", "chase", "quarrel"],
                                      weights=[10, 3, 2, 2, 3, 2, 1])[0]
        w, pet = self.widget, self.pet
        if kind == "play":
            k_anim, f_anim, line = random.choice(talks.PLAYS)
            pet.play(k_anim, 2)
            w.play(f_anim, 2)
            self._say(line, 3000)
            return
        if kind == "solo":
            text, anim = random.choice(talks.SOLO[self.who])
            w.play(anim)
            self._say(text, 4500)
            return
        if kind == "chase":                       # друг обегает Кая: на другую сторону и обратно
            self.run_around()
            return
        if kind == "hold":
            lines = [("k", "Возьмёмся за лапки?", "hold"), ("f", "Давай!", "hold"), ("k", "Вот так хорошо.", "hold"),
                     ("f", "Ты мой друг.", "hold")]
        elif kind == "high":
            lines = [("f", "Дай пять!", "high"), ("k", "Есть пять!", "high")]
        else:
            hour, weekday = talks.today()
            weather = pet.weather
            from .pet import RAIN
            topics = ["quarrel"] if kind == "quarrel" else talks.context(
                hour, weekday, pet.music, weather[0] if weather else None, bool(weather and weather[1] in RAIN),
                f"{pet._title} {pet.app or ''}", pet._idle_s(), time.monotonic() - pet.session_start,
                datetime.date.today().month)
            topic, lines = talks.pick(topics, self._recent)
            self._recent = (self._recent + [topic])[-6:]
        self._scene = list(lines)
        self._say_next()

    def run_around(self) -> None:
        """Догонялки вокруг Кая: друг перебегает на другую сторону, Кай подпрыгивает, и обратно."""
        w, pet = self.widget, self.pet
        if w is None or self._walk is not None:
            return
        g, k = pet.geometry(), pet.size_px
        other = QPoint(g.right() - 18 if self.side == "left" else g.left() - w.width() + 18, w.y())
        back = QPoint(w.pos())
        self._say(random.choice(("Догоняй!", "Не поймаешь!", "Я тут!")), 2500)
        pet.play("jump")
        self.walk_to(other, lambda: self._later(600, lambda: self.widget and self.walk_to(back)))

    def _say_next(self) -> None:
        if not self._scene or self.widget is None:
            self._scene = []
            if self.mode == "hold" and not self.duet:
                self._release()
                self._hold(False)
            return
        who, text, anim = self._scene.pop(0)
        text = text.format(name=self.name)
        side = self.toward_friend() if who == "k" else self.toward_kai()
        if anim == "hold":                        # «за лапки»: друг подходит вплотную, оба тянутся друг к другу
            self._hold(True)
            self.pet.partner_anim, self.widget.anim = "hold" + self.toward_friend(), "hold" + self.toward_kai()
            anim = ""
        elif anim == "high":
            anim = "high" + side
        if who == "k":
            if anim:
                self.pet.gesture(anim, 1)
            self.pet.speak(text, LINE_MS)
        else:
            if anim:
                self.widget.play(anim)
            self._say(text, LINE_MS)
        self._later(LINE_MS + random.randint(-300, 700), self._say_next)   # живой темп, а не метроном

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
