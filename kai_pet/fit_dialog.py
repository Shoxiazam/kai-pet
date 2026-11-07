"""Окно «Подогнать свои вещи»: размер, сдвиг, поворот и отражение скачанной вещи с живым превью."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QSlider, QVBoxLayout)

PREVIEW_PX = 300
# ключ подгонки → (подпись, от, до, множитель для значения)
SLIDERS = {"scale": ("Размер, %", 30, 250, 0.01), "dx": ("Влево / вправо", -100, 100, 1),
           "dy": ("Вверх / вниз", -100, 100, 1), "rot": ("Поворот, °", -180, 180, 1)}


def preview(base: QImage, fragment: str, size: int = PREVIEW_PX) -> QImage:
    """Кай (картинка) и вещь поверх — так же, как её нарисует character/kai.js (кадр 256×256)."""
    img = base.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_ARGB32)
    doc = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
           f'viewBox="0 0 256 256" width="256" height="256">{fragment}</svg>')
    renderer = QSvgRenderer(QByteArray(doc.encode("utf-8")))
    painter = QPainter(img)
    if renderer.isValid():
        renderer.render(painter)
    painter.end()
    return img


SLOT_NAMES = {"head": "На голову", "neck": "На шею", "face": "На лицо", "hand": "В лапку", "body": "На тело"}


class FitDialog(QDialog):
    """items — [(id, название, место)]; fragment(id, подгонка, место) → SVG-фрагмент вещи уже с подгонкой."""

    def __init__(self, items: list[tuple[str, str, str]], fragment: Callable[[str, dict], str], fits: dict,
                 base: QImage, default: dict, first: str | None = None):
        super().__init__()
        self.setWindowTitle("Подогнать свои вещи")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self._fragment, self._base, self._default = fragment, base, dict(default)
        self.fits = {k: dict(default, **fits.get(k, {})) for k, _n, _s in items}
        self.slots = {k: s for k, _n, s in items}           # куда надета каждая вещь
        self.view = QLabel()
        self.view.setFixedSize(PREVIEW_PX, PREVIEW_PX)
        self.pick = QComboBox()
        for item, name, _slot in items:
            self.pick.addItem(name, item)
        if first in self.fits:
            self.pick.setCurrentIndex(self.pick.findData(first))
        form = QFormLayout()
        form.addRow("Вещь", self.pick)
        self.place = QComboBox()                              # куда надеть: шея, голова, лицо…
        for slot, title in SLOT_NAMES.items():
            self.place.addItem(title, slot)
        self.place.setAccessibleName("Куда надеть")
        self.place.currentIndexChanged.connect(self._moved)
        form.addRow("Куда надеть", self.place)
        self.sliders: dict[str, QSlider] = {}
        for key, (title, lo, hi, _k) in SLIDERS.items():
            s = QSlider(Qt.Horizontal)
            s.setRange(lo, hi)
            s.setAccessibleName(title)
            s.valueChanged.connect(self._changed)
            self.sliders[key] = s
            form.addRow(title, s)
        self.mirror = QCheckBox("Отразить")
        self.mirror.toggled.connect(self._changed)
        form.addRow("", self.mirror)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        buttons.button(QDialogButtonBox.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
        buttons.button(QDialogButtonBox.Reset).setText("Как было")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Reset).clicked.connect(self.reset)
        side = QVBoxLayout()
        side.addLayout(form)
        side.addStretch()
        side.addWidget(QLabel("Нажмите «Сохранить» — Кай перерисуется за ~20 секунд."))
        side.addWidget(buttons)
        row = QHBoxLayout(self)
        row.addWidget(self.view)
        row.addLayout(side)
        self.pick.currentIndexChanged.connect(self._load)
        self._load()

    def current(self) -> str:
        return self.pick.currentData()

    def _load(self, *_args) -> None:
        """Ползунки — по подгонке выбранной вещи."""
        fit = self.fits[self.current()]
        for key, s in self.sliders.items():
            s.blockSignals(True)
            s.setValue(round(fit[key] / SLIDERS[key][3]))
            s.blockSignals(False)
        self.mirror.blockSignals(True)
        self.mirror.setChecked(bool(fit["mirror"]))
        self.mirror.blockSignals(False)
        self.place.blockSignals(True)
        self.place.setCurrentIndex(max(0, self.place.findData(self.slots[self.current()])))
        self.place.blockSignals(False)
        self._draw()

    def _moved(self, *_args) -> None:
        """Другое место — вещь вписывается заново, прежние сдвиги к нему не подходят."""
        item = self.current()
        self.slots[item] = self.place.currentData()
        self.fits[item] = dict(self._default)
        self._load()

    def _changed(self, *_args) -> None:
        fit = self.fits[self.current()]
        for key, s in self.sliders.items():
            fit[key] = s.value() * SLIDERS[key][3]
        fit["mirror"] = self.mirror.isChecked()
        self._draw()

    def reset(self) -> None:
        self.fits[self.current()] = dict(self._default)
        self._load()

    def _draw(self) -> None:
        item = self.current()
        self.view.setPixmap(QPixmap.fromImage(preview(self._base, self._fragment(item, self.fits[item], self.slots[item]))))
