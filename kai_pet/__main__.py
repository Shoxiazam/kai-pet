"""Запуск: python -m kai_pet (или двойной щелчок по run_kai.pyw / KaiPet.exe)."""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import autostart, config
from .pet import ASSETS, FROZEN, Pet


def _logging() -> None:
    if FROZEN:      # у .exe нет консоли — ошибки пишутся в профиль пользователя
        folder = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "KaiPet"
        folder.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=folder / "kai.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def tray(app: QApplication, pet: Pet) -> QSystemTrayIcon:
    """Значок у часов: показать или спрятать Кая, запуск вместе с Windows, выход."""
    icon = QSystemTrayIcon(QIcon(str(ASSETS / "icon.ico")), app)
    icon.setToolTip("Кай")
    menu = QMenu()
    toggle = menu.addAction("Спрятать Кая")

    def show_hide():
        pet.setVisible(not pet.isVisible())
        toggle.setText("Спрятать Кая" if pet.isVisible() else "Показать Кая")
    toggle.triggered.connect(lambda _c=False: show_hide())
    start = QAction("Запускать вместе с Windows", menu)
    start.setCheckable(True)
    start.setChecked(autostart.enabled())
    start.setEnabled(autostart.supported())
    start.toggled.connect(autostart.set_enabled)
    menu.addAction(start)
    menu.addSeparator()
    menu.addAction("Выход").triggered.connect(lambda _c=False: app.quit())
    icon.setContextMenu(menu)
    icon.activated.connect(lambda reason: show_hide() if reason == QSystemTrayIcon.Trigger else None)
    icon.show()
    icon._menu = menu                      # держим ссылку, иначе меню соберёт сборщик мусора
    return icon


def main() -> int:
    _logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet(config.load())
    pet.quit_requested.connect(app.quit)
    pet.show()
    if QSystemTrayIcon.isSystemTrayAvailable():
        app._tray = tray(app, pet)
    code = app.exec()
    if getattr(app, "_tray", None):
        app._tray.hide()
    pet.shutdown()                         # окна — до закрытия Qt, иначе падение на выходе
    return code


if __name__ == "__main__":
    raise SystemExit(main())
