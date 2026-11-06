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
    look: dict | None = None  # команда гардеробу: {"kind"}, {"color"}, {"wear"}, {"remove"}, {"reset"}, {"random"}
    sign: str | None = None   # текст таблички; "" — убрать, None — табличку не трогать
    focus: int | None = None  # фокус-режим: минуты; 0 — выключить, None — не трогать


# Гардероб: основа слова → имя в kai.js. Кай рисует только свои образы.
_ITEMS = {"шарф": "scarf", "шапк": "hat", "шапочк": "hat", "очк": "glasses", "очеч": "glasses",
          "наушник": "headphones", "корон": "crown", "темн": "sunglasses", "солнечн": "sunglasses",
          "солнцезащитн": "sunglasses", "зонт": "umbrella", "бант": "bow", "бабочк": "bowtie", "галстук": "bowtie",
          "венок": "flowers", "венк": "flowers", "цветоч": "flowers", "цветы": "flowers",
          "футболк": "tshirt", "майк": "tshirt", "худи": "hoodie", "толстовк": "hoodie", "кофт": "sweater",
          "свитер": "sweater", "дождевик": "raincoat", "смокинг": "tuxedo", "фрак": "tuxedo", "пижам": "pajama",
          "комбинезон": "overalls", "плащ": "cape", "накидк": "cape", "акул": "shark", "динозавр": "dino",
          "дино": "dino", "пчел": "bee", "пчёл": "bee", "лягуш": "frog", "жаб": "frog"}
_ITEM_RU = {"scarf": "шарфик", "hat": "шапочку", "glasses": "очки", "headphones": "наушники", "crown": "корону",
            "sunglasses": "тёмные очки", "umbrella": "зонтик", "bow": "бантик", "bowtie": "бабочку", "flowers": "венок",
            "tshirt": "футболку", "hoodie": "худи", "sweater": "свитер", "raincoat": "дождевик", "tuxedo": "смокинг",
            "pajama": "пижаму", "overalls": "комбинезон", "cape": "плащ героя", "shark": "костюм акулёнка",
            "dino": "костюм динозаврика", "bee": "костюм пчёлки", "frog": "костюм лягушонка"}
_COSTUMES = {"shark", "dino", "bee", "frog"}
_KINDS = {"лис": "fox", "зай": "bunny", "зайч": "bunny", "кролик": "bunny", "миш": "bear", "медвед": "bear",
          "кот": "cat", "кош": "cat"}
_KIND_RU = {"fox": "лисёнком", "bunny": "зайкой", "bear": "мишкой", "cat": "котиком"}
_COLORS = {"рыж": "ginger", "сер": "gray", "графит": "graphite", "черн": "graphite", "терракот": "terracotta",
           "голуб": "sky", "син": "sky", "мят": "mint", "зелен": "mint", "сирен": "lilac", "фиолет": "lilac",
           "розов": "rose"}
_COLOR_RU = {"ginger": "рыжий", "gray": "серый", "graphite": "графитовый", "terracotta": "терракотовый",
             "sky": "голубой", "mint": "мятный", "lilac": "сиреневый", "rose": "розовый"}


def _stem(word: str, table: dict) -> str | None:
    """Самая длинная основа из таблицы, с которой начинается слово."""
    hits = [k for k in table if word.startswith(k)]
    return table[max(hits, key=len)] if hits else None


def _wardrobe(t: str) -> KaiAction | None:
    if re.search(r"\b(?:верни(?:сь)?\s+(?:как было|прежний вид|обычный вид)|стань\s+(?:как раньше|собой|обычным))", t):
        return KaiAction("wave", "Я снова прежний!", 1, {"reset": True})
    if re.search(r"\b(?:переоденься|смени\s+(?:образ|вид|наряд|одежду)|удиви\s+(?:меня\s+)?нарядом)\b", t):
        return KaiAction("wave", "Переодеваюсь!", 1, {"random": True})
    m = re.search(r"\b(?:надень|одень|нацепи|примерь)\s+(?:(?:свой|свои|свою|мне)\s+)?(?:костюм\w*\s+)?(\w+)", t)
    if m and (item := _stem(m.group(1), _ITEMS)):
        return KaiAction("wave", f"Надеваю {_ITEM_RU[item]}!", 1, {"wear": item})
    m = re.search(r"\b(?:сними|сбрось)\s+(?:(?:свой|свои|свою|с себя)\s+)?(?:костюм\w*\s+)?(\w+)", t)
    if m:
        if m.group(1) in ("все", "всё", "аксессуары", "наряд"):
            return KaiAction("wave", "Снимаю всё лишнее.", 1, {"remove": "all"})
        if item := _stem(m.group(1), _ITEMS):
            return KaiAction("wave", f"Снимаю {_ITEM_RU[item]}.", 1, {"remove": item})
    m = re.search(r"\b(?:стань|будь|превратись\s+в|перекрась(?:ся)?\s+в|покрась(?:ся)?\s+в)\s+(\w+)", t)
    if m:
        if kind := _stem(m.group(1), _KINDS):
            return KaiAction("wave", f"Стал {_KIND_RU[kind]}!", 1, {"kind": kind})
        if color := _stem(m.group(1), _COLORS):
            return KaiAction("wave", f"Теперь я {_COLOR_RU[color]}!", 1, {"color": color})
        item = _stem(m.group(1), _ITEMS)
        if item in _COSTUMES:                  # «стань акулёнком» — костюм целиком
            return KaiAction("wave", f"Надеваю {_ITEM_RU[item]}!", 1, {"wear": item})
    return None


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
    (r"\b(?:засыпай|поспи|усни|иди спать|ложись спать|спокойной ночи)\b", "bed",
     ("Спокойной ночи…", "Ухожу баиньки.")),
    (r"\b(?:проснись|просыпайся)\b", "wave", ("Я тут!", "Доброе утро!")),
    (r"\b(?:гордись|похвали меня|похвали)\b", "proud", ("Я тобой горжусь!", "Ты молодец!")),
    (r"\bвдохновись\b", "inspired", ("О, идея!", "Чувствую вдохновение!")),
    (r"\b(?:успокойся|расслабься)\b", "calm", ("Всё хорошо, я спокоен.", "Выдыхаем…")),
    (r"\b(?:испугайся|насторожись)\b", "cautious", ("Ой… что там?", "Я начеку.")),
]
_SIGN = re.compile(r"^(?:покажи|подними|держи|возьми|напиши|сделай)\s+(?:мне\s+)?(?:на\s+)?табличк\w*"
                   r"(?:\s+(?:с\s+)?(?:надписью|текстом|словами))?")
_FOCUS = re.compile(r"^(?:включи\s+|начни\s+|давай\s+)?(?:режим\s+)?(?:фокус\w*|помодоро|сосредоточ\w*)"
                    r"(?:\s+(?:на\s+)?(\d{1,3})\s*мин\w*)?[\s!.]*$")
_FOCUS_OFF = re.compile(r"^(?:выключи|останови|хватит|стоп|закончи)\s+(?:режим\s+)?(?:фокус\w*|помодоро)[\s!.]*$")
_SIGN_OFF = re.compile(r"^(?:убери|опусти|выброси|спрячь)\s+табличк\w*[\s!.]*$")
_ANY_GESTURE = re.compile(rf"{_VERB}\s+(?:какой[- ]нибудь\s+|любой\s+|свой\s+|какой[- ]то\s+)?жест")


# «Станцуй» — каждый раз другой танец.
PARTY_DANCES = ("dance", "disco", "bounce", "hiphop", "robot", "clapdance", "airguitar")


def _any_dance(anim: str) -> str:
    return random.choice(PARTY_DANCES) if anim == "dance" else anim


def parse(text: str) -> KaiAction | None:
    """Команда Каю или None, если это не ему (например, просьба отправить сообщение)."""
    original = _ADDRESS.sub("", text.strip())          # имена с заглавной берём из исходной фразы
    t = original.lower().replace("ё", "е")
    if _FOCUS_OFF.search(t):
        return KaiAction("wave", "Фокус выключен.", 1, focus=0)
    m = _FOCUS.search(t)
    if m:
        minutes = int(m.group(1)) if m.group(1) else 25
        return KaiAction("like", f"Фокус на {minutes} мин!", 1, focus=minutes)
    if _SIGN_OFF.search(t):
        return KaiAction("wave", "Убрал табличку.", 1, sign="")
    m = _SIGN.search(t)                                 # раньше «напиши»: это не сообщение, а табличка
    if m and original[m.end():].strip(" :,—-\"«»"):
        words = original[m.end():].strip(" :,—-\"«»")
        return KaiAction("wave", "Держу табличку!", 1, sign=words)
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

    if act := _wardrobe(t):
        return act
    if _ANY_GESTURE.search(t):
        anim, phrases = random.choice([(a, p) for _r, a, p in _GESTURES if a in ("heart", "like", "clap", "dance")])
        return KaiAction(_any_dance(anim), random.choice(phrases), 3 if anim in ("heart", "dance") else 2)
    for rx, anim, phrases in _GESTURES + _EMOTIONS:
        if re.search(rx, t):
            return KaiAction(_any_dance(anim), random.choice(phrases), 3 if anim in ("heart", "dance") else 2)
    return None
