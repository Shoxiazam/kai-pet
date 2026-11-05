"""Запуск: python -m kai_pet"""
import logging
import sys

from PySide6.QtWidgets import QApplication

from . import config
from .pet import Pet


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = Pet(config.load())
    pet.quit_requested.connect(app.quit)
    pet.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
