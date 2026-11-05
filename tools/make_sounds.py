"""Звуки Кая синтезируются кодом, без чужих записей: python tools/make_sounds.py → assets/sounds/*.wav."""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "assets" / "sounds"


def save(name: str, samples: list[float]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    peak = max(abs(s) for s in samples) or 1.0
    with wave.open(str(OUT / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s / peak * 0.3 * 32767)) for s in samples))  # тихо


def meow() -> list[float]:
    """Короткое «мяу»: тон поднимается и опадает, с обертонами и лёгким вибрато."""
    n, out, phase = int(RATE * 0.5), [], 0.0
    for i in range(n):
        t = i / n
        freq = 520 + 300 * math.sin(math.pi * min(1.0, t * 1.4)) + 8 * math.sin(2 * math.pi * 6 * i / RATE)
        phase += 2 * math.pi * freq / RATE
        env = min(1.0, t / 0.08) * (1 - t) ** 1.5
        out.append(env * (math.sin(phase) + 0.45 * math.sin(2 * phase) + 0.2 * math.sin(3 * phase)))
    return out


def purr() -> list[float]:
    """Мурчание: мягкий низкий шум, пульсирующий ~26 раз в секунду, на вдохе и выдохе."""
    rnd, n, out, smooth = random.Random(7), int(RATE * 1.6), [], 0.0
    for i in range(n):
        t = i / RATE
        smooth += (rnd.uniform(-1, 1) - smooth) * 0.05            # убираем верха — остаётся урчание
        pulse = 0.5 + 0.5 * math.sin(2 * math.pi * 26 * t)
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


if __name__ == "__main__":
    for name, fn in (("meow", meow), ("purr", purr), ("munch", munch)):
        save(name, fn())
    print("звуки сохранены в", OUT)
