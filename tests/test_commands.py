"""Команды Каю: разбор фраз без модели."""
import pytest

from kai_pet.commands import parse


@pytest.mark.parametrize("text, anim, say", [
    ("Передай Антону привет", "wave", "Антон, привет!"),
    ("Кай, передай привет Олегу от меня", "wave", "Олег, привет!"),
    ("передай маме и папе привет", "wave", "Мама и папа, привет!"),
    ("Передай Маше привет", "wave", "Маша, привет!"),
    ("Передай Оле привет", "wave", "Оля, привет!"),
    ("Передай Андрею привет", "wave", "Андрей, привет!"),
    ("Передай Марии привет", "wave", "Мария, привет!"),
    ("передай всем привет", "wave", "Всем привет!"),
    ("Поздоровайся с Антоном", "wave", "Антон, привет!"),
    ("Попрощайся с Машей", "bye", "Пока, Маша!"),
    ("попрощайся с Андреем", "bye", "Пока, Андрей!"),
])
def test_greetings_and_goodbyes(text, anim, say):
    act = parse(text)
    assert act and act.anim == anim and act.say == say


@pytest.mark.parametrize("text, anim", [
    ("попрощайся", "bye"), ("пока", "bye"), ("поздоровайся", "wave"),
    ("покажи сердечко", "heart"), ("Кай, сделай сердечко", "heart"), ("люблю тебя", "heart"),
    ("покажи лайк", "like"), ("покажи класс", "like"), ("покажи большой палец", "like"),
    ("прыгни", "jump"), ("обними меня", "hug"),
    ("поклонись", "bow"), ("похлопай", "clap"), ("помаши", "wave"), ("подмигни", "playful"),
    ("удивись", "surprised"), ("обрадуйся", "excited"), ("поворчи", "grumpy"), ("иди спать", "bed"),
    ("похвали меня", "proud"), ("задумайся", "confused"), ("успокойся", "calm"),
])
def test_gestures_and_emotions(text, anim):
    act = parse(text)
    assert act and act.anim == anim and act.say


def test_any_gesture_picks_a_real_one():
    from kai_pet.commands import PARTY_DANCES
    for _ in range(20):
        assert parse("покажи какой-нибудь жест").anim in ("heart", "like", "clap", *PARTY_DANCES)


def test_dance_command_varies():
    from kai_pet.commands import PARTY_DANCES
    seen = {parse("станцуй").anim for _ in range(60)} | {parse("покажи танец").anim for _ in range(60)}
    assert seen <= set(PARTY_DANCES) and len(seen) >= 4                  # каждый раз другой танец


@pytest.mark.parametrize("text", [
    "Напиши Антону привет",                        # это сообщение в мессенджер — не Каю
    "передай Антону привет в телеграм",
    "отправь маме сердечко",
    "открой YouTube",
    "покажи файлы в загрузках",
    "сколько времени",
    "найди класс в коде",
    "покажи расписание класса",                    # жест должен стоять сразу после «покажи» и в конце
    "покажи мне класс в расписании",
    "поставь лайк под видео",                      # лайк под видео — задача ассистента
    "покажи сердце презентации",
    "",
])
def test_agent_tasks_are_not_taken(text):
    assert parse(text) is None


@pytest.mark.parametrize("text, look", [
    ("Кай, надень шарф", {"wear": "scarf"}),
    ("надень очки", {"wear": "glasses"}),
    ("сними всё", {"remove": "all"}),
    ("стань рыжим", {"color": "ginger"}),
    ("стань лисёнком", {"kind": "fox"}),
    ("превратись в зайчика", {"kind": "bunny"}),
    ("переоденься", {"random": True}),
    ("верни как было", {"reset": True}),
])
def test_wardrobe_commands(text, look):
    act = parse(text)
    assert act and act.look == look and act.say


@pytest.mark.parametrize("text", ["сними скриншот", "стань на паузу", "будь внимательнее"])
def test_wardrobe_does_not_take_other_tasks(text):
    assert parse(text) is None


def test_new_gestures_do_not_steal_tasks():
    from kai_pet import commands
    assert commands.parse("подумай").anim == "think"
    assert commands.parse("посмейся").anim == "laugh"
    assert commands.parse("покружись").anim == "spin"
    assert commands.parse("дай пять").anim == "high"
    assert commands.parse("подумай, как ответить на письмо") is None      # это работа ассистента
    assert commands.parse("долго думай над задачей") is None
    assert commands.parse("рассмеши меня анекдотом") is None
