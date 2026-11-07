"""Запуск: python -m kai_pet (или двойной щелчок по run_kai.pyw / KaiPet.exe)."""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, autostart, config, update
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
    if update.installed():
        menu.addAction("Проверить обновления").triggered.connect(lambda _c=False: app._updater.check(force=True))
    menu.addSeparator()
    menu.addAction(f"Кай {__version__}").setEnabled(False)
    menu.addAction("Выход").triggered.connect(lambda _c=False: app.quit())
    icon.setContextMenu(menu)
    icon.activated.connect(lambda reason: show_hide() if reason == QSystemTrayIcon.Trigger else None)
    icon.show()
    icon._menu = menu                      # держим ссылку, иначе меню соберёт сборщик мусора
    return icon


def updates(app: QApplication, pet: Pet) -> update.Updater:
    """Новая версия на GitHub — Кай спрашивает и обновляется сам: скачал установщик, запустил тихо, вышел."""
    up = update.Updater(app)
    manual = [False]

    def found(version: str, url: str) -> None:
        box = QMessageBox(QMessageBox.Question, "Кай", f"Вышла новая версия Кая — {version.lstrip('v')} "
                          f"(у вас {__version__}). Обновить сейчас? Это займёт меньше минуты.",
                          QMessageBox.Yes | QMessageBox.No)
        box.setWindowIcon(QIcon(str(ASSETS / "icon.ico")))
        if box.exec() == QMessageBox.Yes:
            pet.speak("Скачиваю обновление…", 60000)
            up.download(url)

    def downloaded(path: str) -> None:
        if path and update.run_installer(path):
            pet.speak("Обновляюсь! Сейчас вернусь.", 5000)
            QTimer.singleShot(1500, app.quit)
        else:
            pet.speak("Не получилось скачать обновление. Попробую завтра.", 6000)

    def nothing() -> None:
        if manual[0]:
            manual[0] = False
            pet.speak(f"У меня последняя версия — {__version__}.", 5000)

    up.found.connect(found)
    up.downloaded.connect(downloaded)
    up.nothing.connect(nothing)
    check = up.check

    def check_any(force: bool = False) -> None:
        manual[0] = force
        check(force)
    up.check = check_any
    QTimer.singleShot(30_000, up.check)                       # после запуска — не мешая старту
    daily = QTimer(app)
    daily.timeout.connect(up.check)
    daily.start(6 * 3600 * 1000)                              # сам решит, проверял ли сегодня
    up._daily = daily
    return up


def main() -> int:
    if "--export" in sys.argv:              # KaiPet.exe --export: нарисовать кадры образа и выйти (kai_pet.export)
        from .export import main as export_main
        return export_main()
    _logging()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet(config.load())
    pet.quit_requested.connect(app.quit)
    pet.show()
    if update.installed():
        app._updater = updates(app, pet)
    if QSystemTrayIcon.isSystemTrayAvailable():
        app._tray = tray(app, pet)
    code = app.exec()
    if getattr(app, "_tray", None):
        app._tray.hide()
    pet.shutdown()                         # окна — до закрытия Qt, иначе падение на выходе
    return code


if __name__ == "__main__":
    raise SystemExit(main())
