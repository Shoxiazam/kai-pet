"""Звуки Кая и друзей синтезируются кодом, без чужих записей: python tools/make_sounds.py → assets/sounds/.

У каждого друга свой голос (assets/sounds/friends/<кто>/): та же речь облачками, но другой высоты и тембра.
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "assets" / "sounds"


def save(name: str, samples: list[float], folder: Path = OUT) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    peak = max(abs(s) for s in samples) or 1.0
    with wave.open(str(folder / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s / peak * 0.3 * 32767)) for s in samples))  # тихо


def meow(pitch: float = 1.0, length: float = 0.5, bright: float = 0.45) -> list[float]:
    """Короткое «мяу»: тон поднимается и опадает, с обертонами и лёгким вибрато."""
    n, out, phase = int(RATE * length), [], 0.0
    for i in range(n):
        t = i / n
        freq = pitch * (520 + 300 * math.sin(math.pi * min(1.0, t * 1.4))) + 8 * math.sin(2 * math.pi * 6 * i / RATE)
        phase += 2 * math.pi * freq / RATE
        env = min(1.0, t / 0.08) * (1 - t) ** 1.5
        out.append(env * (math.sin(phase) + bright * math.sin(2 * phase) + 0.2 * math.sin(3 * phase)))
    return out


def purr(rate: float = 26, soft: float = 0.05) -> list[float]:
    """Мурчание: мягкий низкий шум, пульсирующий ~26 раз в секунду, на вдохе и выдохе."""
    rnd, n, out, smooth = random.Random(7), int(RATE * 1.6), [], 0.0
    for i in range(n):
        t = i / RATE
        smooth += (rnd.uniform(-1, 1) - smooth) * soft            # убираем верха — остаётся урчание
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * rate * t)
        breath = math.sin(math.pi * (t % 0.8) / 0.8) * (1.0 if t % 1.6 < 0.8 else 0.7)
        out.append(smooth * pulse * breath)
    return out


def munch() -> list[float]:
    """Хруст печеньки: три коротких хрумка."""
    rnd, n, out = random.Random(3), int(RATE * 0.6), []
    for i in range(n):
        t = i / RATE
        k = t % 0.2
        out.append(rnd.uniform(-1, 1) * math.exp(-k * 45) if t < 0.58 else 0.0)
    return out


def chirp(syllables: int, seed: int, pitch: float = 1.0, speed: float = 1.0) -> list[float]:
    """«Мяу-голос»: короткие мурлыкающие слоги разной высоты — Кай «говорит» облачком, как в играх."""
    rnd, out, phase = random.Random(seed), [], 0.0
    for _ in range(syllables):
        n = int(RATE * rnd.uniform(0.06, 0.1) / speed)
        start, end = pitch * rnd.uniform(560, 900), pitch * rnd.uniform(520, 980)
        for i in range(n):
            t = i / n
            phase += 2 * math.pi * (start + (end - start) * t) / RATE
            env = math.sin(math.pi * t) ** 1.5
            out.append(env * (math.sin(phase) + 0.35 * math.sin(2 * phase)))
        out.extend([0.0] * int(RATE * rnd.uniform(0.025, 0.05)))      # пауза между слогами
    return out


def rustle() -> list[float]:
    """Шорох одежды в шкафу: мягкие волны шума, то громче, то тише."""
    rnd, n, out, smooth = random.Random(5), int(RATE * 1.4), [], 0.0
    for i in range(n):
        t = i / RATE
        smooth += (rnd.uniform(-1, 1) - smooth) * 0.35
        swell = max(0.0, math.sin(2 * math.pi * 2.2 * t)) ** 2 * (0.6 + 0.4 * math.sin(2 * math.pi * 0.7 * t))
        out.append(smooth * swell * min(1.0, (1.4 - t) * 4))
    return out


def door() -> list[float]:
    """Дверца шкафа: короткий деревянный стук с низким призвуком."""
    rnd, n, out = random.Random(9), int(RATE * 0.25), []
    for i in range(n):
        t = i / RATE
        out.append(math.exp(-t * 30) * (0.7 * math.sin(2 * math.pi * 180 * t) + 0.3 * rnd.uniform(-1, 1)))
    return out


# Голоса друзей: (высота, длина «мяу», яркость, частота мурчания, мягкость мурчания, скорость речи).
VOICES = {
    "mira": (1.3, 0.38, 0.75, 30, 0.07, 1.25),     # лисичка: выше, звонче, тараторит
    "tosha": (0.62, 0.65, 0.25, 17, 0.03, 0.8),    # мишка: низкий, басовитое урчание, говорит не спеша
    "bunya": (1.55, 0.3, 0.6, 34, 0.09, 1.35),     # зайка: самая высокая, пискливая
}


def set_of(pitch=1.0, length=0.5, bright=0.45, rate=26, soft=0.05, speed=1.0) -> dict:
    return {"meow": meow(pitch, length, bright), "purr": purr(rate, soft), "munch": munch(),
            "chirp1": chirp(3, 11, pitch, speed), "chirp2": chirp(5, 23, pitch, speed), "chirp3": chirp(7, 37, pitch, speed)}


if __name__ == "__main__":
    for name, samples in {**set_of(), "rustle": rustle(), "door": door()}.items():
        save(name, samples)
    for who, voice in VOICES.items():
        for name, samples in set_of(*voice).items():
            save(name, samples, OUT / "friends" / who)
    print("звуки сохранены в", OUT)
