"""Запуск Кая двойным щелчком (без окна консоли) и для автозапуска с Windows."""
import os
import runpy
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
runpy.run_module("kai_pet", run_name="__main__")
