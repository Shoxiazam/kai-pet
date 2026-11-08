"""Запуск: python -m kai_pet (или двойной щелчок по run_kai.pyw / KaiPet.exe)."""
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import __version__, autostart, config, update
from .pet import ASSETS, FROZEN, Pet


def _logging() -> None:
    if FROZEN:      # у .exe и .app нет консоли — ошибки пишутся в папку данных Кая
        from .host import data_dir
        folder = data_dir()
        folder.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=folder / "kai.log", level=logging.INFO,
                            format="%(asctime)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def tray(app: QApplication, pet: Pet) -> QSystemTrayIcon:
    """Значок у часов: показать или спрятать Кая, запуск вместе с Windows, выход."""
    icon = QSystemTrayIcon(QIcon(str(ASSETS / ("icon.png" if sys.platform == "darwin" else "icon.ico"))), app)
    icon.setToolTip("Кай")
    menu = QMenu()
    toggle = menu.addAction("Спрятать Кая")

    def show_hide():
        pet.setVisible(not pet.isVisible())
        toggle.setText("Спрятать Кая" if pet.isVisible() else "Показать Кая")
    toggle.triggered.connect(lambda _c=False: show_hide())
    start = QAction("Запускать вместе с Windows" if sys.platform == "win32" else "Запускать при входе в систему", menu)
    start.setCheckable(True)
    start.setChecked(autostart.enabled())
    start.setEnabled(autostart.supported())
    start.toggled.connect(autostart.set_enabled)
    menu.addAction(start)
    if update.supported():
        upgrade = menu.addAction("Обновить Кая")
        upgrade.setVisible(False)
        upgrade.triggered.connect(lambda _c=False: app._updater.install())

        def fresh():
            got = app._updater.available
            upgrade.setVisible(bool(got))
            if got:
                upgrade.setText(f"Обновить до {got[0].lstrip('v')}")
        menu.aboutToShow.connect(fresh)
        menu.addAction("Проверить обновления").triggered.connect(lambda _c=False: app._updater.check(force=True))
        icon.messageClicked.connect(lambda: app._updater.install())
    menu.addSeparator()
    menu.addAction(f"Кай {__version__}").setEnabled(False)
    menu.addAction("Выход").triggered.connect(lambda _c=False: app.quit())
    icon.setContextMenu(menu)
    icon.activated.connect(lambda reason: show_hide() if reason == QSystemTrayIcon.Trigger else None)
    icon.show()
    icon._menu = menu                      # держим ссылку, иначе меню соберёт сборщик мусора
    return icon


def updates(app: QApplication, pet: Pet) -> update.Updater:
    """Новая версия на GitHub — видно сразу: Кай говорит облачком, у часов уведомление, в меню «Обновить до …».
    Windows: скачал установщик, запустил тихо, вышел. Mac: открывает скачивание нового .dmg."""
    from .pet import load_state, save_state
    up = update.Updater(app)
    manual = [False]

    def install() -> None:
        if not up.available:
            return
        version, url = up.available
        if sys.platform == "darwin":
            QDesktopServices.openUrl(QUrl(url))
            pet.speak("Качаю новую версию! Открой KaiPet-macOS.dmg и перетащи меня в «Программы» с заменой.", 15000)
        else:
            pet.speak("Скачиваю обновление…", 60000)
            up.download(url)

    def found(version: str, url: str) -> None:
        v = version.lstrip("v")
        pet.speak(f"Вышла новая версия меня — {v}! Правый клик по мне → «Обновить».", 15000)
        icon = getattr(app, "_tray", None)
        if icon is not None:
            icon.showMessage("Кай", f"Доступна версия {v} (у вас {__version__}). Нажмите, чтобы обновить.",
                             QSystemTrayIcon.Information, 10000)
        if not manual[0] and load_state().get("update_offered") == version:
            return                                   # окно про эту версию уже было — дальше только облачко и меню
        manual[0] = False
        save_state("update_offered", version)
        box = QMessageBox(QMessageBox.Question, "Кай", f"Вышла новая версия Кая — {v} "
                          f"(у вас {__version__}). Обновить сейчас? Это займёт меньше минуты.",
                          QMessageBox.Yes | QMessageBox.No)
        box.setWindowIcon(QIcon(str(ASSETS / ("icon.png" if sys.platform == "darwin" else "icon.ico"))))
        if box.exec() == QMessageBox.Yes:
            install()

    def downloaded(path: str) -> None:
        if path and update.run_installer(path):
            pet.speak("Обновляюсь! Сейчас вернусь.", 5000)
            QTimer.singleShot(1500, app.quit)
        else:
            pet.speak("Не получилось скачать обновление. Попробую позже.", 6000)

    def nothing() -> None:
        if manual[0]:
            manual[0] = False
            pet.speak(f"У меня последняя версия — {__version__}.", 5000)

    up.found.connect(found)
    up.downloaded.connect(downloaded)
    up.nothing.connect(nothing)
    up.install = install
    check = up.check

    def check_any(force: bool = False) -> None:
        manual[0] = force
        check(force)
    up.check = check_any
    QTimer.singleShot(20_000, up.check)                       # после запуска — не мешая старту
    often = QTimer(app)
    often.timeout.connect(up.check)
    often.start(3600 * 1000)                                  # раз в час спрашивает себя; на GitHub — раз в 6 часов
    up._often = often
    return up


def link_arg() -> str:
    """Ссылка kaipet://… из приглашения на сайте (браузер запускает KaiPet.exe с ней)."""
    return next((a for a in sys.argv[1:] if a.lower().startswith("kaipet:")), "")


def forward_link(url: str) -> bool:
    """Кай уже запущен (сам или внутри голосового агента) — отдать ссылку ему, второго Кая не открывать."""
    from PySide6.QtNetwork import QLocalSocket
    from .network import link_server
    sock = QLocalSocket()
    sock.connectToServer(link_server())
    if not sock.waitForConnected(1500):
        return False
    sock.write(url.encode("utf-8") + b"\n")
    sock.flush()
    sock.waitForBytesWritten(1500)
    sock.waitForReadyRead(3000)                     # «ok» от Кая: ссылка дошла, теперь можно отключаться
    sock.disconnectFromServer()
    return True


def register_links() -> None:
    """Windows: ссылки kaipet:// открывает этот KaiPet.exe (HKCU, без прав администратора)."""
    if sys.platform != "win32" or not FROZEN:
        return
    try:
        import winreg
        base = r"Software\Classes\kaipet"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:Кай")
            winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base + r"\shell\open\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{sys.executable}" "%1"')
    except OSError as e:
        logging.warning("Ссылки kaipet:// не зарегистрированы: %s", e)


class _MacLinks(QObject):
    """macOS присылает ссылку kaipet:// событием FileOpen самому приложению."""

    def __init__(self, pet: Pet):
        super().__init__()
        self.pet = pet

    def eventFilter(self, obj, event):
        if event.type() == QEvent.FileOpen and event.url().scheme() == "kaipet":
            self.pet.network.handle_url(event.url().toString())
            return True
        return False


def main() -> int:
    if "--export" in sys.argv:              # KaiPet.exe --export: нарисовать кадры образа и выйти (kai_pet.export)
        from .export import main as export_main
        return export_main()
    _logging()
    url = link_arg()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if url and forward_link(url):           # ссылку принял уже работающий Кай
        return 0
    register_links()
    pet = Pet(config.load())
    if url:
        QTimer.singleShot(1500, lambda: pet.network.handle_url(url))
    app._links = _MacLinks(pet)
    app.installEventFilter(app._links)
    pet.quit_requested.connect(app.quit)
    pet.show()
    if update.supported():
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
