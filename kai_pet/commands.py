"""Команды самому Каю: передать привет, попрощаться, показать жест или эмоцию.

Разбираются локально, без нейросети. Просьбы написать или отправить кому-то сообщение
Кай не перехватывает — их можно отдать своему ассистенту.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass


@dataclass
class KaiAction:
    anim: str       # анимация или эмоция Кая (имя из kai/out/frames или kai/out/moods)
    say: str        # реплика облачком и голосом
    times: int = 2  # сколько раз проиграть анимацию


_MESSENGER = re.compile(r"телеграм|telegram|ватсап|whatsapp|вотсап|дискорд|discord|инстаграм|instagram|"
                        r"напиши|отправь|сообщени|смс|sms|почт|письм|позвони")
_ADDRESS = re.compile(r"^\s*(?:кай|котик|котёнок|котенок)[\s,!.]+", re.IGNORECASE)
_FROM_ME = re.compile(r"\s+(?:от меня|пожалуйста|плиз)\b.*$", re.IGNORECASE)

# дательный падеж («передай Антону») и творительный («попрощайся с Антоном») → именительный, на глаз
_FIXED = {"всем": "всем", "маме": "мама", "папе": "папа", "бабушке": "бабушка", "дедушке": "дедушка",
          "брату": "брат", "сестре": "сестра", "другу": "друг", "подруге": "подруга", "мамой": "мама",
          "папой": "папа", "сестрой": "сестра", "братом": "брат", "всеми": "всем", "друзьям": "друзья",
          "друзьями": "друзья"}
_YA = {"ан", "тан", "ван", "сон", "сан", "ман", "ол", "юл", "кол", "вал", "гал", "кат", "нат", "наст", "дим", "мит"}


def _nominative(word: str) -> str:
    low = word.lower().replace("ё", "е")
    if low in _FIXED:
        return _FIXED[low].capitalize() if word[:1].isupper() else _FIXED[low]
    if low.endswith("ии"):                                    # Марии
        base = low[:-2] + "ия"
    elif low.endswith(("ой", "ей")) and len(low) > 3:         # Машей, Олей (творительный)
        stem = low[:-2]
        base = stem + ("я" if stem in _YA else "а")
    elif low.endswith(("ом", "ем")) and len(low) > 3:          # Антоном, Андреем
        stem = low[:-2]
        base = stem + "й" if stem[-1] in "аеиоуяю" else stem
    elif low.endswith("е") and len(low) > 2:                  # Маше, Оле
        stem = low[:-1]
        base = stem + ("я" if stem in _YA else "а")
    elif low.endswith("у") and len(low) > 2:                  # Антону
        base = low[:-1]
    elif low.endswith("ю") and len(low) > 2:                  # Андрею, Игорю
        stem = low[:-1]
        base = stem + ("й" if stem[-1] in "аеиоуяю" else "ь")
    else:
        base = low
    return base.capitalize()


def _names(raw: str) -> str:
    """«Антону и Маше» → «Антон и Маша»."""
    raw = _FROM_ME.sub("", raw).strip(" ,.!?")
    words = raw.split()
    if not words or len(words) > 5:
        return ""
    return " ".join(w if w.lower() == "и" else _nominative(w.strip(",")) for w in words)


def _pick(*phrases: str) -> str:
    return random.choice(phrases)


_VERB = r"(?:покажи|сделай|изобрази)"   # «поставь лайк под видео» — задача ассистенту, не жест
# Жест — сразу после глагола и в конце фразы: «покажи сердечко», «покажи мне лайк».
# «Покажи расписание класса» или «покажи класс в расписании» — не жест, это работа ассистента.
_SHOW = rf"\b{_VERB}\s+(?:(?:мне|нам|ещё|еще|свой|своё|свое|какой[- ]нибудь|какое[- ]нибудь)\s+)*"
_END = r"\w*(?:\s+(?:пожалуйста|кай|лапкой|лапками))*[\s!.?,]*$"
# (регулярка, анимация, реплики). Существительные — только вместе с «покажи/сделай», повелительные — сами.
_GESTURES = [
    (rf"{_SHOW}(?:сердечк|сердц|сердеч){_END}|\bлюблю\s+тебя", "heart",
     ("Держи сердечко!", "Это тебе, от всего сердца.", "Сердечко для тебя!")),
    (rf"{_SHOW}(?:лайк|класс|палец вверх|большой палец){_END}", "like",
     ("Класс!", "Лайк!", "Полностью одобряю!")),
    (rf"\b(?:станцуй|потанцуй|танцуй)\b|{_SHOW}танец{_END}", "dance",
     ("Танцую!", "Смотри, как умею!", "Музыку бы ещё!")),
    (r"\b(?:прыгни|подпрыгни|попрыгай)\b", "jump", ("Хоп!", "Оп-па!", "Высоко?")),
    (r"\b(?:обними|обнимашки)\b", "hug", ("Обнимаю!", "Иди сюда, обниму.", "Крепко-крепко!")),
    (r"\b(?:поклонись|поклон)\b", "bow", ("С уважением!", "Благодарю.", "К вашим услугам.")),
    (r"\b(?:похлопай|хлопай|поаплодируй|аплодируй|аплодисменты|браво)\b", "clap",
     ("Браво!", "Аплодирую!", "Отлично получилось!")),
    (r"\b(?:помаши|махни)\b", "wave", ("Привет-привет!", "Машу лапкой!")),
    (r"\bподмигни\b", "playful", ("Подмигиваю!", "Хе-хе.")),
]
_EMOTIONS = [
    (r"\bудивись\b", "surprised", ("Ого!", "Вот это да!")),
    (r"\b(?:обрадуйся|порадуйся|радуйся)\b", "excited", ("Ура!", "Как здорово!")),
    (r"\b(?:рассердись|разозлись|поворчи|поругайся|злись)\b", "grumpy", ("Хмф. Ладно, ворчу.", "Ну во-о-от…")),
    (r"\b(?:загрусти|погрусти|грусти)\b", "tired", ("Эх…", "Немножко грустно.")),
    (r"\b(?:задумайся|призадумайся)\b", "confused", ("Хм…", "Дай подумать…")),
    (r"\b(?:засыпай|поспи|усни|иди спать|ложись спать|спокойной ночи)\b", "sleepy",
     ("Спокойной ночи…", "Ухожу баиньки.")),
    (r"\b(?:проснись|просыпайся)\b", "wave", ("Я тут!", "Доброе утро!")),
    (r"\b(?:гордись|похвали меня|похвали)\b", "proud", ("Я тобой горжусь!", "Ты молодец!")),
    (r"\bвдохновись\b", "inspired", ("О, идея!", "Чувствую вдохновение!")),
    (r"\b(?:успокойся|расслабься)\b", "calm", ("Всё хорошо, я спокоен.", "Выдыхаем…")),
    (r"\b(?:испугайся|насторожись)\b", "cautious", ("Ой… что там?", "Я начеку.")),
]
_ANY_GESTURE = re.compile(rf"{_VERB}\s+(?:какой[- ]нибудь\s+|любой\s+|свой\s+|какой[- ]то\s+)?жест")


def parse(text: str) -> KaiAction | None:
    """Команда Каю или None, если это не ему (например, просьба отправить сообщение)."""
    original = _ADDRESS.sub("", text.strip())          # имена с заглавной берём из исходной фразы
    t = original.lower().replace("ё", "е")
    if not t or len(t) > 120 or _MESSENGER.search(t):
        return None

    m = re.search(r"\b(?:передай|скажи)\s+привет\s+(.+)$", t) or re.search(r"\b(?:передай|скажи)\s+(.+?)\s+привет\b", t)
    if m:
        who = _names(original[m.start(1):m.end(1)])
        if not who or who.lower() == "всем":
            return KaiAction("wave", "Всем привет!")
        return KaiAction("wave", f"{who[:1].upper()}{who[1:]}, привет!")   # фраза начинается с имени
    if re.search(r"\b(?:передай|скажи)\s+привет\b", t):
        return KaiAction("wave", "Всем привет!")
    m = re.search(r"\bпоздоровайся(?:\s+со?\s+(.+))?$", t)
    if m:
        who = _names(original[m.start(1):m.end(1)]) if m.group(1) else ""
        return KaiAction("wave", f"{who[:1].upper()}{who[1:]}, привет!" if who else _pick("Привет!", "Здравствуй!", "Приветик!"))

    m = re.search(r"\bпопрощайся(?:\s+со?\s+(.+))?$", t) or re.search(r"\bскажи\s+(?:пока|до свидания)(?:\s+(.+))?$", t)
    if m:
        who = _names(original[m.start(1):m.end(1)]) if m.group(1) else ""
        return KaiAction("bye", f"Пока, {who}!" if who else _pick("Пока-пока!", "До встречи!", "До скорого!"))
    if re.fullmatch(r"(?:пока|до свидания|до встречи)[\s!.]*", t):
        return KaiAction("bye", _pick("Пока-пока!", "До встречи!"))

    if _ANY_GESTURE.search(t):
        anim, phrases = random.choice([(a, p) for _r, a, p in _GESTURES if a in ("heart", "like", "clap", "dance")])
        return KaiAction(anim, random.choice(phrases), 3 if anim in ("heart", "dance") else 2)
    for rx, anim, phrases in _GESTURES + _EMOTIONS:
        if re.search(rx, t):
            return KaiAction(anim, random.choice(phrases), 3 if anim in ("heart", "dance") else 2)
    return None
