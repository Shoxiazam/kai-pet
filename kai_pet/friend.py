"""Друг Кая — второй питомец со своим характером. Сидит рядом, болтает с Каем, играет, ссорится и мирится.

Кадры друга рисуются тем же character/export.mjs, но в свою папку (friend/<образ>): уборка образов Кая их не трогает.
"""
from __future__ import annotations

import json
import logging
import random
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QPoint, QProcess, QProcessEnvironment, Qt, QTimer
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QWidget

from .bubble import Bubble

if TYPE_CHECKING:
    from .pet import Pet

log = logging.getLogger(__name__)

SCALE = 0.85                    # друг чуть меньше Кая
SCENE_EVERY_S = (45, 110)       # как часто они что-нибудь затевают
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
    """Окошко друга: только кадры и щелчок; поведением управляет Friends."""

    def __init__(self, folder: Path, size: int, on_click):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(size, size)
        self.dir, self.size_px, self.on_click = folder, size, on_click
        self.cache: dict[str, list[QPixmap]] = {}
        self.anim, self.once, self.frame, self.repeat = "idle", None, 0, 0
        self.flash: tuple[str, float] | None = None
        self._pix: QPixmap | None = None
        self.bubble = Bubble()

    def _frames(self, name: str) -> list[QPixmap]:
        if name not in self.cache:
            files: list[Path] = []
            for kind in ("frames", "moods"):
                files = sorted((self.dir / kind / name).glob("*.png"))
                if files:
                    break
            if not files:
                return self._frames("idle") if name != "idle" else []
            dpr = self.devicePixelRatioF()
            px = round(self.size_px * dpr)
            out = []
            for f in files:
                pix = QPixmap(str(f)).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                pix.setDevicePixelRatio(dpr)
                out.append(pix)
            if len(self.cache) > 8:
                self.cache.pop(next(iter(self.cache)))
            self.cache[name] = out
        return self.cache[name]

    def has(self, name: str) -> bool:
        return any((self.dir / kind / name).is_dir() for kind in ("frames", "moods"))

    def play(self, name: str, times: int = 1) -> None:
        if (self.dir / "frames" / name).is_dir():
            self.once, self.frame, self.repeat = name, 0, times - 1
        elif self.has(name):
            self.flash = (name, time.monotonic() + 3.0 * times)

    def current(self) -> str:
        if self.once:
            return self.once
        if self.flash and time.monotonic() < self.flash[1]:
            return self.flash[0]
        self.flash = None
        return self.anim

    def tick(self) -> None:
        name = self.current()
        frames = self._frames(name)
        if not frames:
            return
        if self.frame >= len(frames):
            self.frame = 0
            if self.once and self.repeat > 0:
                self.repeat -= 1
            elif self.once:
                self.once = None
                frames = self._frames(self.current())
        self._pix = frames[min(self.frame, len(frames) - 1)]
        self.frame += 1
        self.update()

    def paintEvent(self, _event):
        if self._pix is not None:
            QPainter(self).drawPixmap(0, 0, self._pix)

    def moveEvent(self, event):
        super().moveEvent(event)
        self.bubble.place(self.geometry())

    def hideEvent(self, event):
        self.bubble.hide()
        super().hideEvent(event)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.on_click()

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
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._follow = QTimer(self)
        self._follow.timeout.connect(self._stay_near)
        from .pet import load_state
        saved = load_state().get("buddy")
        if isinstance(saved, dict) and saved.get("who") in FRIENDS:
            self.who = saved["who"]
            if saved.get("on"):
                QTimer.singleShot(4000, lambda: self.invite(self.who, greet=False))

    @property
    def name(self) -> str:
        return FRIENDS[self.who]["name"]

    @property
    def here(self) -> bool:
        return self.widget is not None

    def _save(self, on: bool) -> None:
        from .pet import save_state
        save_state("buddy", {"who": self.who, "on": on})

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
        self.widget = FriendPet(folder, size, self._clicked)
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
        target = self._spot()
        if (target - w.pos()).manhattanLength() > 3:
            w.move(target)

    def _clicked(self) -> None:
        if self.widget is None:
            return
        self.widget.play(random.choice(["wave", "jump", "heart"]))
        self.widget.bubble.say(random.choice(CLICK), 4000)

    # --- поведение ---
    def _mirror(self) -> None:
        """Фон друга повторяет настроение Кая: спит, когда Кай спит, танцует, когда Кай танцует."""
        w, shown = self.widget, self.pet.shown
        if shown in ("bed", "sleepy"):
            w.anim = "sleepy" if w.has("sleepy") else "idle"
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
