"""Настройки Кая. Всё необязательно: без файла работают значения ниже.

Свой файл: ~/.kai-pet.json (или путь в переменной KAI_PET_CONFIG), например
{"size": 180, "hints": false, "moods": {"figma": "inspired", "chrome": "calm"}}
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

# Кусок имени программы или заголовка окна → эмоция. Первое совпадение побеждает,
# поэтому сайты (youtube) стоят выше браузеров (chrome).
DEFAULT_MOODS = {
    "youtube": "playful", "netflix": "playful", "twitch": "playful", "spotify": "playful",
    "steam": "excited", "minecraft": "excited", "javaw": "excited", "roblox": "excited",
    "telegram": "curious", "whatsapp": "curious", "discord": "curious",
    "code.exe": "focused", "cursor.exe": "focused", "pycharm": "focused", "devenv": "focused",
    "windowsterminal": "focused", "powershell": "focused", "cmd.exe": "focused",
    "winword": "focused", "excel": "focused", "powerpnt": "focused",
    "chrome": "calm", "msedge": "calm", "firefox": "calm",
}


@dataclass
class Config:
    size: int = 150                    # размер Кая в логических пикселях
    sleep_after_min: float = 10        # без мыши и клавиатуры столько минут — засыпает
    away_after_min: float = 5          # перерыв не короче — при возвращении машет
    tired_after_min: float = 60        # непрерывная работа дольше — иногда устаёт (намёк на перерыв)
    look_radius_px: int = 240          # курсор ближе — Кай смотрит на него
    welcome_after_min: float = 30      # перерыв не короче — здоровается облачком
    break_hint_every_min: float = 60   # подсказка про перерыв не чаще раза в столько минут
    hints: bool = True                 # мягкие подсказки облачком
    sounds: bool = True                # «мяу» на клик, мурчание, хруст печеньки (меняется и в меню)
    dance_to_music: bool = True        # играет музыка — кивает в такт
    seasonal: bool = True              # зимой сам надевает шапочку и шарф, в день рождения — корону
    birthday: str = ""                 # ваш день рождения, "MM-DD", например "03-21"
    moods: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MOODS))


def load(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("KAI_PET_CONFIG") or Path.home() / ".kai-pet.json")
    if not path.is_file():
        return Config()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log.warning("Настройки Кая не прочитаны (%s): %s — беру значения по умолчанию", path, e)
        return Config()
    known = {f.name for f in fields(Config)}
    for key in set(data) - known:
        log.warning("Неизвестная настройка Кая: %s", key)
    return Config(**{k: v for k, v in data.items() if k in known})
