"""Большой набор стикеров «Кай и друзья» (~100): наряды, друзья, пары, мемы и таблички.

python tools/make_sticker_pack.py → stickers/pack/*.webm и pack.json (тот же формат — его грузит sticker_bot.py).
Telegram: в одном наборе до 120 стикеров; создаётся первыми 50, остальные добавляются по одному (бот делает сам).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_stickers as ms  # noqa: E402
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFontMetricsF, QGuiApplication, QImage, QPainter, QPainterPath, QPen  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "stickers" / "pack"

# --- наряды ---
L = {
    "kai": {"kind": "cat", "color": "gray", "acc": []},
    "hoodie": {"kind": "cat", "color": "gray", "acc": ["hoodie", "headphones"]},
    "cool": {"kind": "cat", "color": "graphite", "acc": ["tuxedo", "sunglasses"]},
    "pajama": {"kind": "cat", "color": "ginger", "acc": ["pajama"]},
    "rain": {"kind": "cat", "color": "sky", "acc": ["raincoat", "umbrella"]},
    "shark": {"kind": "cat", "color": "gray", "acc": ["shark"]},
    "king": {"kind": "cat", "color": "gray", "acc": ["crown", "cape"]},
    "nerd": {"kind": "cat", "color": "mint", "acc": ["glasses", "sweater"]},
    "winter": {"kind": "cat", "color": "terracotta", "acc": ["hat", "scarf"]},
    "dino": {"kind": "cat", "color": "gray", "acc": ["dino"]},
    "mira": {"kind": "fox", "color": "ginger", "acc": ["bow"]},
    "tosha": {"kind": "bear", "color": "terracotta", "acc": ["glasses"]},
    "bunya": {"kind": "bunny", "color": "rose", "acc": ["flowers"]},
}


def S(name, anim, emoji, look="kai", top="", sign="", friend=None, fanim=None):
    """Один стикер: движение, эмодзи, наряд; top — подпись-мем сверху, sign — текст на табличке,
    friend — второй герой слева (наряд из L), fanim — его движение."""
    return {"name": name, "anim": anim, "emoji": emoji, "look": look, "top": top, "sign": sign,
            "friend": friend, "fanim": fanim}


PACK = [
    # Кай: основные эмоции
    S("hello", "wave", "👋"), S("love", "heart", "❤️"), S("like", "like", "👍"), S("yay", "jump", "🎉"),
    S("laugh", "laugh", "😂"), S("think", "think", "🤔"), S("shy", "shy", "😊"), S("spin", "spin", "🌀"),
    S("clap", "clap", "👏"), S("hug", "hug", "🤗"), S("bow", "bow", "🙇"), S("sad", "fail", "😢"),
    S("sleep", "bed", "😴"), S("yum", "eat", "🍪"), S("dance", "dance", "💃"), S("disco", "disco", "🕺"),
    S("guitar", "airguitar", "🎸"), S("bye", "bye", "🖐"), S("purr", "purr", "😌"), S("stretch", "stretch", "🙆"),
    S("yawn", "yawn", "🥱"), S("wash", "wash", "🧼"), S("tail", "chasetail", "🌪"), S("look", "lookAround", "👀"),
    S("robot", "robot", "🤖"), S("waltz", "waltz", "💫"), S("headbang", "headbang", "🤘"), S("hiphop", "hiphop", "😎"),
    S("grumpy", "mood:grumpy", "😤"), S("surprised", "mood:surprised", "😮"), S("proud", "mood:proud", "😌"),
    S("confused", "mood:confused", "😵"), S("inspired", "mood:inspired", "💡"), S("tired", "mood:tired", "😩"),
    # наряды
    S("hoodie_groove", "groove", "🎧", "hoodie"), S("hoodie_bounce", "bounce", "🎶", "hoodie"),
    S("cool_like", "like", "😎", "cool"), S("cool_bow", "bow", "🎩", "cool"),
    S("pajama_yawn", "yawn", "🥱", "pajama"), S("pajama_bed", "bed", "🌙", "pajama"),
    S("rain_sad", "sadsway", "🌧", "rain"), S("rain_wave", "wave", "☔", "rain"),
    S("shark_spin", "spin", "🦈", "shark"), S("shark_jump", "jump", "🌊", "shark"),
    S("king_proud", "mood:proud", "👑", "king"), S("king_disco", "disco", "🥳", "king"),
    S("nerd_think", "think", "🤓", "nerd"), S("nerd_working", "working", "💻", "nerd"),
    S("winter_wave", "wave", "❄️", "winter"), S("winter_hug", "hug", "☃️", "winter"),
    S("dino_bounce", "bounce", "🦖", "dino"), S("dino_laugh", "laugh", "🦕", "dino"),
    # друзья поодиночке
    S("mira_wave", "wave", "🦊", "mira"), S("mira_laugh", "laugh", "😆", "mira"), S("mira_disco", "disco", "💃", "mira"),
    S("mira_grumpy", "mood:grumpy", "😒", "mira"),
    S("tosha_think", "think", "🧐", "tosha"), S("tosha_hug", "hug", "🐻", "tosha"), S("tosha_bow", "bow", "🙏", "tosha"),
    S("bunya_heart", "heart", "💖", "bunya"), S("bunya_jump", "jump", "🐰", "bunya"), S("bunya_shy", "shy", "🥰", "bunya"),
    # пары: Кай и друг
    S("duo_mira_hold", "holdL", "🤝", friend="mira", fanim="holdR"),
    S("duo_tosha_hold", "holdL", "🫶", friend="tosha", fanim="holdR"),
    S("duo_bunya_hold", "holdL", "💞", friend="bunya", fanim="holdR"),
    S("duo_mira_high", "highL", "🙌", friend="mira", fanim="highR"),
    S("duo_tosha_high", "highL", "✋", friend="tosha", fanim="highR"),
    S("duo_bunya_hug", "hug", "🤗", friend="bunya", fanim="hug"),
    S("duo_mira_disco", "disco", "🪩", friend="mira", fanim="disco"),
    S("duo_tosha_laugh", "laugh", "🤣", friend="tosha", fanim="laugh"),
    S("duo_bunya_clap", "clapdance", "👯", friend="bunya", fanim="clapdance"),
    S("duo_mira_fight", "mood:grumpy", "😠", friend="mira", fanim="mood:grumpy"),
    # мемы: подпись сверху
    S("meme_base", "like", "💯", "cool", top="Это база"),
    S("meme_cringe", "shy", "😬", top="Кринж"),
    S("meme_house", "bed", "🏠", "pajama", top="Я в домике"),
    S("meme_meh", "think", "😐", top="Ну такое…"),
    S("meme_friday", "disco", "🍻", "king", top="Пятница!!!"),
    S("meme_monday", "sadsway", "😫", "rain", top="Понедельник"),
    S("meme_works", "mood:cautious", "⚠️", "nerd", top="Не трогай, работает"),
    S("meme_code", "dance", "🐛", "hoodie", top="Код заработал"),
    S("meme_relatable", "like", "👌", "mira", top="Жиза"),
    S("meme_lol", "laugh", "🤣", top="Ору"),
    S("meme_no", "mood:grumpy", "🙅", top="Нет."),
    S("meme_yes", "jump", "🙋", top="Да!"),
    S("meme_wait", "checking", "⏳", "nerd", top="Секундочку…"),
    S("meme_watch", "lookAround", "🕵", top="Я всё вижу"),
    S("meme_vacation", "sadsway", "🏖", "rain", top="Хочу в отпуск"),
    S("meme_party", "bounce", "🎊", "king", top="Король вечеринки"),
    S("meme_shark", "spin", "🦈", "shark", top="Кот-акула"),
    S("meme_coffee", "eat", "☕", "pajama", top="Сначала кофе"),
    S("meme_brain", "mood:confused", "🤯", top="Мозг всё"),
    S("meme_gg", "clap", "🏆", "tosha", top="Красавчик!"),
    # таблички
    S("sign_hi", "sign", "🙋", sign="Привет!"), S("sign_thanks", "sign", "🙏", sign="Спасибо!"),
    S("sign_ok", "sign", "👌", sign="Ок"), S("sign_bye", "sign", "👋", "mira", sign="Пока!"),
    S("sign_love", "sign", "😍", "bunya", sign="Люблю"), S("sign_miss", "sign", "🥺", sign="Скучаю"),
    S("sign_bday", "sign", "🎂", "king", sign="С ДР!"), S("sign_dnd", "sign", "⛔", "nerd", sign="Не беспокоить"),
    S("sign_lunch", "sign", "🍽", "tosha", sign="Ушёл обедать"), S("sign_busy", "sign", "📵", "hoodie", sign="Я занят"),
    S("sign_morning", "sign", "☀️", "pajama", sign="Доброе утро"), S("sign_night", "sign", "🌙", "pajama", sign="Спокойной ночи"),
    S("sign_later", "sign", "🕐", sign="Позже"), S("sign_online", "sign", "📱", sign="На связи"),
]


def caption(img: QImage, text: str) -> QImage:
    """Подпись-мем сверху: белые буквы с тёмной обводкой, в две строки, если длинная."""
    img = img.convertToFormat(QImage.Format_ARGB32)
    font = ms.sign_font()
    font.setBold(True)
    size = 64
    while size > 30:
        font.setPixelSize(size)
        fm = QFontMetricsF(font)
        if fm.horizontalAdvance(text) <= ms.SIZE - 40:
            lines = [text]
            break
        words = text.split()
        if len(words) > 1:                   # две строки поровну по ширине, а не по числу слов
            cut = min(range(1, len(words)), key=lambda i: max(fm.horizontalAdvance(" ".join(words[:i])),
                                                              fm.horizontalAdvance(" ".join(words[i:]))))
            lines = [" ".join(words[:cut]), " ".join(words[cut:])]
        else:
            lines = [text]
        if all(fm.horizontalAdvance(x) <= ms.SIZE - 40 for x in lines):
            break
        size -= 4
    fm = QFontMetricsF(font)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    y = 16 + fm.ascent()
    for line in lines:
        path.addText(QPointF((ms.SIZE - fm.horizontalAdvance(line)) / 2, y), font, line)
        y += fm.height() * 0.95
    p.setPen(QPen(QColor("#2B2420"), max(6, size / 8), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    p.drawPath(path)
    p.end()
    return img


def shrink(frames: list[QImage]) -> list[QImage]:
    """Под подписью-мемом Кай чуть меньше и ниже, чтобы слова не легли на уши."""
    out = []
    for f in frames:
        img = QImage(ms.SIZE, ms.SIZE, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        k = 0.82
        p.drawImage(QRectF(ms.SIZE * (1 - k) / 2, ms.SIZE * (1 - k), ms.SIZE * k, ms.SIZE * k), f)
        p.end()
        out.append(img)
    return out


def build(entries: list[dict], out: Path) -> list[dict]:
    QGuiApplication.instance() or QGuiApplication(sys.argv)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.webm"):
        old.unlink()
    tool, r = ms.ffmpeg(), ms.Renderer()
    pack = []
    try:
        for e in entries:
            frames, fps = r.frames(e["anim"], L[e["look"]])
            if e["friend"]:
                mate, fps2 = r.frames(e["fanim"], L[e["friend"]])
                n = min(len(frames), len(mate))
                frames, fps = ms.duo(frames[:n], mate[:n]), min(fps, fps2)
            if e["sign"]:
                frames = [ms.sign(f, e["sign"]) for f in frames]
            if e["top"]:
                frames = [caption(f, e["top"]) for f in shrink(frames)]
            size = ms.encode(frames, fps, out / f"{e['name']}.webm", tool)
            pack.append({"file": f"{e['name']}.webm", "emoji": e["emoji"]})
            print(f"{len(pack):3d} {e['name']}: {size // 1024} КБ", flush=True)
    finally:
        r.close()
    (out / "pack.json").write_text(json.dumps({"title": "Кай и друзья", "stickers": pack}, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return pack


if __name__ == "__main__":
    assert len(PACK) <= 120, "в наборе Telegram не больше 120 стикеров"
    assert len({e["name"] for e in PACK}) == len(PACK)
    print(f"готово: {len(build(PACK, OUT))} стикеров в {OUT}")
