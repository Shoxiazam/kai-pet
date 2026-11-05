/* Кай — персональный ИИ-питомец. Чистый JS без зависимостей: браузер (window.Kai) и Node (require). */
(function (root) {
'use strict';

// ── Палитра: единственное место, где заданы цвета. В браузере их можно переопределить CSS-переменными --kai-*.
const PALETTE = {
  main:   '#A7A2A0', // мягкий тёплый серый: шерсть
  cream:  '#F5EFE6', // кремовый: мордочка, грудка, кончик хвоста
  ink:    '#3B3330', // тёмный графит: контуры и глаза
  accent: '#F2A65A', // янтарный: кончики ушей, сияние
  blush:  '#F6A9A0', // розовый: щёки, ушки, носик, язычок
  spark:  '#D97757', // терракотовый лучистый знак на груди
};
// ── Гардероб: цвета шерсти, виды (ушки и хвост) и аксессуары. Мимика, позы и жесты у всех видов общие.
const PALETTES = {
  gray: PALETTE,
  ginger: { ...PALETTE, main: '#E39B5F', accent: '#F7CF7A' },
  graphite: { ...PALETTE, main: '#6E6765', cream: '#EDE6DC', ink: '#231D1B', blush: '#E99A9A' },
  terracotta: { ...PALETTE, main: '#D97757', ink: '#3D2B1F', blush: '#F4B393', spark: '#B5523A' },
  sky: { ...PALETTE, main: '#A3BBDA', ink: '#2F3442', accent: '#F2C14E', blush: '#F2A7B5' },
  mint: { ...PALETTE, main: '#98CFB9', ink: '#26352F', accent: '#F2C14E' },
  lilac: { ...PALETTE, main: '#BBA8D8', ink: '#2E2738', accent: '#F2C14E', blush: '#F2A7C0' },
  rose: { ...PALETTE, main: '#EDB4C3', ink: '#3B2A31', accent: '#F2C14E', blush: '#F28CA0', spark: '#C8553D' },
};
const COLOR_NAMES = { gray: 'Серый', ginger: 'Рыжий', graphite: 'Графитовый', terracotta: 'Терракотовый',
  sky: 'Голубой', mint: 'Мятный', lilac: 'Сиреневый', rose: 'Розовый' };
const KINDS = { cat: 'Котик', fox: 'Лисёнок', bunny: 'Зайка', bear: 'Мишка' };
// slot: на голове одна вещь, очки и шарф — к чему угодно
const ACCESSORIES = { scarf: { ru: 'Шарфик', slot: 'neck' }, hat: { ru: 'Шапочка', slot: 'head' },
  glasses: { ru: 'Очки', slot: 'face' }, headphones: { ru: 'Наушники', slot: 'head' }, crown: { ru: 'Корона', slot: 'head' } };
const LOOK = { kind: 'cat', color: 'gray', acc: [] };   // текущий образ; svg(..., { look }) может переопределить
const lookId = l => {
  const x = { ...LOOK, ...l };
  return `${x.kind}-${x.color}-${[...(x.acc || [])].sort().join('+') || 'none'}`;
};

const SIZE = 256;      // единый холст для всех кадров
const OUT = 5;         // толщина контура
const TAU = Math.PI * 2;

const col = k => `var(--kai-${k},${PALETTE[k]})`;
const f = n => Math.round(n * 100) / 100;
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const smooth = u => u * u * (3 - 2 * u);
const bump = (t, a, b) => (t > a && t < b ? Math.sin(Math.PI * (t - a) / (b - a)) : 0);

// ── Скелет: все параметры позы. Числа смешиваются линейно, строки переключаются на середине.
const BASE = {
  y: 0, sx: 1, sy: 1, rot: 0, facing: 1,      // тело: подъём, сжатие, наклон, разворот (-1 = зеркально)
  tilt: 0, look: [0, 0],                     // наклон головы, взгляд [-1..1, -1..1]
  earL: 0, earR: 0,                          // уши: + опущены наружу, − насторожены
  tail: 0, curl: 0.5,                        // хвост: + поднят, завиток 0..1
  eyeL: 'open', eyeR: 'open',                // open | happy | closed | squeeze
  openL: 1, openR: 1, eyeScale: 1, sparkle: 0,
  browL: 0, browR: 0, browLY: 0, browRY: 0,  // брови: + внутренний край вниз (хмурится), − вверх (беспокойство)
  mouth: 'smile', mouthOpen: 0,              // smile | grin | o | tongue | flat | frown | wavy | pout
  blush: 0.5, spark: 0.5, sparkRot: 0,      // румянец, яркость и поворот лучистого мотива
  armL: 6, armR: 6, step: 0,                 // лапки: 0 вниз, + наружу/вверх, − к груди; шаг −1..1
  heart: 0, thumbL: 0, thumbR: 0,            // жесты: сердечко в лапках, большой палец вверх (0 — нет)
};

const PAIRS = { eyes: ['eyeL', 'eyeR'], open: ['openL', 'openR'], brow: ['browL', 'browR'],
  browY: ['browLY', 'browRY'], ears: ['earL', 'earR'], arms: ['armL', 'armR'] };
function expand(o = {}) {
  const p = { ...o };
  for (const k in PAIRS) if (k in p) {
    const [a, b] = PAIRS[k];
    if (!(a in p)) p[a] = p[k];
    if (!(b in p)) p[b] = p[k];
    delete p[k];
  }
  return p;
}

function blend(a, b, k) {
  const o = {};
  for (const key in a) {
    const va = a[key], vb = key in b ? b[key] : va;
    o[key] = typeof va === 'number' ? va + (vb - va) * k
      : Array.isArray(va) ? va.map((x, i) => x + (vb[i] - x) * k)
      : (k < 0.5 ? va : vb);
  }
  return o;
}

// ── Состояния: поза + подсказка для поведения (в кадры текст не попадает).
const STATES = {
  neutral:    { ru: 'Нейтральный', say: 'Привет! Я тут.', pose: {} },
  curious:    { ru: 'Любопытство', say: 'Ого, а это что такое?',
    pose: { tilt: 10, look: [0.6, -0.3], earL: -14, earR: 14, eyeScale: 1.08, browL: -8, browLY: -5, mouth: 'o', mouthOpen: 0.15, tail: 12, curl: 0.8 } },
  excited:    { ru: 'Воодушевление', say: 'Вот это да, давай попробуем!',
    pose: { y: -6, sy: 1.05, sx: 0.97, ears: -16, eyeScale: 1.12, sparkle: 1, browY: -4, mouth: 'grin', mouthOpen: 1, arms: 120, blush: 0.6, spark: 0.9, tail: 24 } },
  playful:    { ru: 'Игривость', say: 'Спорим, я догадаюсь первым?',
    pose: { tilt: -12, rot: -3, eyeR: 'happy', earL: -10, earR: 32, mouth: 'tongue', armL: 75, tail: 26, curl: 1, blush: 0.55, look: [0.3, 0] } },
  focused:    { ru: 'Сосредоточенность', say: 'Так, секунду, разбираюсь.',
    pose: { open: 0.6, look: [0, 0.55], brow: 12, browY: 4, mouth: 'flat', ears: -8, arms: -38, tail: -5, curl: 0.3, blush: 0.15 } },
  calm:       { ru: 'Спокойствие', say: 'Всё спокойно, я рядом.',
    pose: { eyes: 'closed', ears: 8, tail: -4, curl: 0.9, blush: 0.35, sy: 0.98, sx: 1.01 } },
  caring:     { ru: 'Забота', say: 'Как ты сейчас? Можешь рассказать, если хочется.',
    pose: { tilt: -8, open: 0.9, brow: -10, ears: 10, arms: -24, blush: 0.6, spark: 0.75 } },
  sleepy:     { ru: 'Сонливость', say: 'Ммм… я немножко задремал.',
    pose: { tilt: 14, open: 0.3, brow: -4, browY: 3, mouth: 'o', mouthOpen: 0.6, ears: 26, sy: 0.96, sx: 1.02, tail: -10, curl: 0.9, blush: 0.25, spark: 0.3 } },
  tired:      { ru: 'Усталость', say: 'Длинный был день, да?',
    pose: { y: 3, sy: 0.92, sx: 1.05, open: 0.5, look: [0, 0.45], brow: -12, browY: 3, mouth: 'wavy', ears: 44, arms: -4, tail: -16, curl: 0.3, blush: 0, spark: 0.15 } },
  grumpy:     { ru: 'Лёгкое ворчание', say: 'Хм. Ну ладно, ладно, сделаем.',
    pose: { open: 0.58, look: [-0.55, 0], brow: 16, browY: 3, mouth: 'pout', ears: 24, sx: 1.03, arms: -60, tail: -8, curl: 0.2, blush: 0.45 } },
  cautious:   { ru: 'Осторожность', say: 'Погоди, давай сначала проверим.',
    pose: { y: 4, sy: 0.95, rot: -3, look: [0.75, 0], eyeScale: 1.06, brow: -9, browY: -2, mouth: 'flat', ears: -14, arms: -50, tail: -26, curl: 0.2 } },
  proud:      { ru: 'Гордость за прогресс', say: 'Смотри, как далеко ты продвинулся!',
    pose: { y: -4, sy: 1.04, look: [0, -0.25], eyes: 'happy', mouth: 'grin', mouthOpen: 0.7, ears: -10, arms: 38, blush: 0.5, spark: 1, tail: 28, curl: 0.8 } },
  confused:   { ru: 'Растерянность', say: 'Кажется, я не совсем понял. Пояснишь?',
    pose: { tilt: 16, look: [0.35, -0.5], openR: 0.72, browL: -14, browLY: -5, browR: 10, mouth: 'wavy', earL: -6, earR: 40, armL: 140, tail: 0 } },
  surprised:  { ru: 'Удивление', say: 'Ох! Неожиданно.',
    pose: { y: -8, sy: 1.07, sx: 0.96, eyeScale: 1.22, open: 1.12, browY: -8, brow: -4, mouth: 'o', mouthOpen: 1, ears: -22, arms: 75, tail: 30, curl: 0.2, spark: 0.85 } },
  inspired:   { ru: 'Вдохновение', say: 'Слушай, есть идея!',
    pose: { y: -4, look: [0.25, -0.8], sparkle: 1, eyeScale: 1.1, browY: -4, mouth: 'grin', mouthOpen: 0.6, ears: -16, armL: 150, armR: 12, spark: 1, sparkRot: 22.5, blush: 0.45, tail: 20 } },
  supportive: { ru: 'Тихая поддержка', say: 'Я тут. Можно и просто помолчать вместе.',
    pose: { tilt: 5, eyes: 'happy', ears: 14, arms: -18, blush: 0.5, spark: 0.65, sy: 0.99, tail: 6, curl: 0.8 } },
};

const LOOKS = { center: [0, 0], left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] };

// Ключевые кадры: [[t, частичная поза], ...]; первый и последний ключ совпадают → бесшовный цикл.
function keyed(keys) {
  return (p, t) => {
    let i = 0;
    while (i < keys.length - 2 && t >= keys[i + 1][0]) i++;
    const [t0, a] = keys[i], [t1, b] = keys[i + 1];
    return blend({ ...p, ...expand(a) }, { ...p, ...expand(b) }, smooth(clamp((t - t0) / (t1 - t0))));
  };
}

function blink(p, t, a, b) { const k = bump(t, a, b); p.openL *= 1 - k; p.openR *= 1 - k; }

// Бег в каноне «движется влево, хвост сзади справа»; вправо — то же, отражённое.
function run(facing) {
  return (p, t) => {
    const s = Math.sin(TAU * t);
    Object.assign(p, { facing, rot: -9, look: [-1, 0.1], step: s, armL: 35 * s, armR: -35 * s,
      tail: -14 + 8 * Math.sin(2 * TAU * t), curl: 0.15, mouth: 'grin', mouthOpen: 0.4 });
    p.y -= 9 * Math.abs(s);
    p.sy *= 1 + 0.05 * (Math.abs(s) - 0.5);
    p.earL += 20 + 5 * s; p.earR += 20 - 5 * s;
    return p;
  };
}

// ── Анимации: имя → кадры, fps, состояние по умолчанию, функция (поза, t∈[0,1)) → поза.
const ANIMS = {
  idle: { ru: 'Спокойное ожидание', frames: 48, fps: 24, state: 'neutral', fn: (p, t) => {
    const b = Math.sin(TAU * t);
    p.sy *= 1 + 0.02 * b; p.sx *= 1 - 0.012 * b;
    p.tail += 5 * Math.sin(TAU * t); p.earR += 5 * bump(t, 0.3, 0.4);
    blink(p, t, 0.72, 0.8);
    return p;
  } },
  runLeft:  { ru: 'Бег влево',  frames: 12, fps: 20, state: 'neutral', fn: run(1) },
  runRight: { ru: 'Бег вправо', frames: 12, fps: 20, state: 'neutral', fn: run(-1) },
  wave: { ru: 'Приветственный взмах', frames: 24, fps: 24, state: 'neutral', fn: (p, t) => {
    const w = Math.sin(2 * TAU * t);
    Object.assign(p, { eyeL: 'happy', eyeR: 'happy', mouth: 'grin', mouthOpen: 0.6, armL: 125 + 20 * w,
      tail: 18 + 10 * w, blush: Math.max(p.blush, 0.55) });
    p.tilt += 6 + 3 * w; p.earL -= 8; p.earR -= 8 + 6 * w;
    return p;
  } },
  jump: { ru: 'Прыжок', frames: 30, fps: 30, state: 'neutral', fn: keyed([
    [0, {}],
    [0.16, { sy: 0.84, sx: 1.1, ears: 10, arms: -10, open: 0.8 }],
    [0.28, { y: -28, sy: 1.1, sx: 0.94, ears: -18, arms: 120, mouth: 'grin', mouthOpen: 0.8 }],
    [0.42, { y: -40, sy: 1.02, eyes: 'happy', ears: -10, arms: 140, mouth: 'grin', mouthOpen: 1, tail: 25 }],
    [0.58, { y: -22, sy: 1.06, sx: 0.96, ears: -14, arms: 100, mouth: 'grin', mouthOpen: 0.6 }],
    [0.68, { y: 0, sy: 0.86, sx: 1.12, ears: 16, arms: 20 }],
    [0.82, { sy: 1.03, sx: 0.98 }],
    [1, {}],
  ]) },
  fail: { ru: 'Реакция на неудачу', frames: 36, fps: 24, state: 'neutral', fn: keyed([
    [0, {}],
    [0.12, { eyeScale: 1.15, ears: -12, sy: 1.03, mouth: 'o', mouthOpen: 0.5, browY: -4 }],
    [0.25, { eyes: 'squeeze', sy: 0.92, sx: 1.05, ears: 45, mouth: 'wavy', tilt: -7, brow: -10 }],
    [0.35, { eyes: 'squeeze', sy: 0.93, sx: 1.05, ears: 45, mouth: 'wavy', tilt: 7, brow: -10 }],
    [0.45, { eyes: 'squeeze', sy: 0.93, sx: 1.05, ears: 42, mouth: 'wavy', tilt: -4, brow: -10 }],
    [0.62, { open: 0.6, look: [0, 0.5], ears: 40, brow: -14, mouth: 'frown', sy: 0.95, spark: 0.2, tail: -20 }],
    [0.85, { open: 0.9, ears: 14, brow: -6, mouth: 'flat', spark: 0.4 }],
    [1, {}],
  ]) },
  waiting: { ru: 'Ожидание ответа', frames: 48, fps: 24, state: 'neutral', fn: (p, t) => {
    const s = Math.sin(TAU * t);
    p.tilt += 7 * s; p.look = [0.15 * s, -0.1]; p.browLY -= 3; p.browRY -= 3;
    p.earL += -6 + 6 * s; p.earR += -6 - 6 * s;
    p.tail += 10 + 10 * Math.sin(2 * TAU * t);
    blink(p, t, 0.45, 0.53);
    return p;
  } },
  working: { ru: 'Сосредоточенная работа', frames: 24, fps: 24, state: 'focused', fn: (p, t) => {
    const s = Math.sin(2 * TAU * t);
    p.armL = -38 + 10 * s; p.armR = -38 - 10 * s;
    p.look = [0.3 * Math.sin(TAU * t), 0.55];
    p.y += 1.2 * Math.abs(s); p.tail += 4 * Math.sin(TAU * t);
    return p;
  } },
  checking: { ru: 'Проверка результата', frames: 48, fps: 24, state: 'neutral', fn: keyed([
    [0, { look: [-0.7, 0.3], open: 0.82, brow: 6, mouth: 'flat', armR: -55, tilt: -4 }],
    [0.3, { look: [0.7, 0.3], open: 0.82, brow: 6, mouth: 'flat', armR: -55, tilt: 4 }],
    [0.5, { look: [0, 0], open: 1.05, browY: -3, armR: -55, ears: -8 }],
    [0.64, { eyes: 'happy', mouth: 'grin', mouthOpen: 0.5, y: 3, sy: 0.97, ears: -8, tail: 20 }],
    [0.76, { eyes: 'happy', mouth: 'grin', mouthOpen: 0.5, y: -2, sy: 1.02, tail: 10 }],
    [0.9, { look: [-0.5, 0.2], open: 0.85, brow: 4, mouth: 'flat', armR: -45 }],
    [1, { look: [-0.7, 0.3], open: 0.82, brow: 6, mouth: 'flat', armR: -55, tilt: -4 }],
  ]) },
  heart: { ru: 'Сердечко', frames: 24, fps: 24, state: 'neutral', fn: (p, t) => {
    const s = Math.sin(2 * TAU * t);
    Object.assign(p, { eyeL: 'happy', eyeR: 'happy', mouth: 'smile', armL: -65, armR: -65, heart: 1 + 0.12 * s,
      blush: 0.85, tail: 15 + 8 * Math.sin(TAU * t) });
    p.tilt += 4 * Math.sin(TAU * t); p.y -= 1.5 * Math.abs(s);
    return p;
  } },
  like: { ru: 'Лайк', frames: 24, fps: 24, state: 'neutral', fn: (p, t) => {
    const s = Math.sin(TAU * t);
    Object.assign(p, { eyeR: 'happy', mouth: 'grin', mouthOpen: 0.5, armL: 100 + 6 * s, thumbL: 1, blush: 0.6, tail: 20 });
    p.tilt -= 6; p.y -= 1.5 * (1 + s);
    return p;
  } },
  bye: { ru: 'Прощание', frames: 24, fps: 24, state: 'neutral', fn: (p, t) => {
    const w = Math.sin(2 * TAU * t);
    Object.assign(p, { eyeL: 'happy', eyeR: 'happy', mouth: 'smile', browL: -6, browR: -6, armL: 130 + 25 * w,
      tail: 8 + 6 * w, blush: 0.5 });
    p.tilt -= 6 + 2 * w; p.earL += 10; p.earR += 10;
    return p;
  } },
  dance: { ru: 'Танец', frames: 32, fps: 16, state: 'neutral', fn: (p, t) => {
    const s = Math.sin(TAU * t), c = Math.sin(2 * TAU * t);
    Object.assign(p, { eyeL: 'happy', eyeR: 'happy', mouth: 'grin', mouthOpen: 0.7, armL: 90 + 45 * s, armR: 90 - 45 * s,
      step: c, tail: 20 + 15 * c, blush: 0.6, spark: 0.9 });
    p.rot += 7 * s; p.tilt -= 6 * s; p.y -= 6 * Math.abs(c); p.earL += 8 * s; p.earR -= 8 * s;
    return p;
  } },
  hug: { ru: 'Обнимашки', frames: 30, fps: 20, state: 'neutral', fn: keyed([
    [0, {}],
    [0.25, { arms: 115, open: 1.08, sparkle: 1, mouth: 'grin', mouthOpen: 0.6, ears: -10 }],
    [0.5, { arms: -62, eyes: 'happy', blush: 1, sy: 0.95, sx: 1.04, heart: 0.7, tilt: 5 }],
    [0.8, { arms: -62, eyes: 'happy', blush: 1, sy: 0.96, sx: 1.03, heart: 0.8, tilt: -5 }],
    [1, {}],
  ]) },
  bow: { ru: 'Поклон', frames: 30, fps: 20, state: 'neutral', fn: keyed([
    [0, {}],
    [0.3, { y: 8, sy: 0.88, sx: 1.06, eyes: 'closed', ears: 22, arms: -40, look: [0, 0.8], tail: -10 }],
    [0.65, { y: 8, sy: 0.88, sx: 1.06, eyes: 'closed', ears: 22, arms: -40, look: [0, 0.8], tail: -10 }],
    [1, {}],
  ]) },
  clap: { ru: 'Аплодисменты', frames: 16, fps: 16, state: 'neutral', fn: (p, t) => {
    const c = Math.sin(2 * TAU * t);
    Object.assign(p, { eyeL: 'happy', eyeR: 'happy', mouth: 'grin', mouthOpen: 0.8, armL: -48 + 22 * c, armR: -48 + 22 * c,
      blush: 0.6 });
    p.y -= 2 * Math.abs(c); p.tail += 10 * c;
    return p;
  } },
  lookAround: { ru: 'Взгляд по сторонам', frames: 40, fps: 20, state: 'neutral', fn: keyed([
    [0, {}], [0.1, {}],
    [0.2, { look: LOOKS.left, tilt: -4 }], [0.3, { look: LOOKS.left, tilt: -4 }],
    [0.4, { look: LOOKS.up, ears: -8 }], [0.5, { look: LOOKS.up, ears: -8 }],
    [0.6, { look: LOOKS.right, tilt: 4 }], [0.7, { look: LOOKS.right, tilt: 4 }],
    [0.8, { look: LOOKS.down }], [0.9, { look: LOOKS.down }],
    [1, {}],
  ]) },
};

// ── Рендер. Каждая часть скелета — отдельный слой <g id="…">.
const BODY = 'M128,102 C170,102 198,132 198,170 C198,206 168,226 128,226 C88,226 58,206 58,170 C58,132 86,102 128,102 Z';
const EAR = 'M-23,8 C-23,-10 -10,-30 0,-41 Q4,-45 8,-41 C18,-29 24,-10 23,8 Z'; // кошачье ухо: широкое основание, короткий кончик
const EAR_IN = 'M-12,6 C-12,-6 -5,-20 2,-29 C9,-19 13,-6 12,6 Z';
// Ушки по видам: контур, внутренняя часть, наклон наружу, янтарный кончик (cx, cy, r) или null.
const EARS = {
  cat: { out: EAR, in: EAR_IN, angle: 14, tip: [4, -42, 11] },
  fox: { out: 'M-20,8 C-21,-18 -9,-44 3,-56 Q9,-62 14,-55 C22,-35 22,-12 20,8 Z',
    in: 'M-10,6 C-10,-12 -4,-30 3,-41 C9,-29 11,-12 10,6 Z', inner: 'cream', angle: 14, tip: [7, -56, 15] },
  bunny: { out: 'M-11,8 C-17,-26 -13,-60 0,-66 C13,-60 17,-26 11,8 Z',
    in: 'M-5,4 C-9,-22 -7,-48 0,-54 C7,-48 9,-22 5,4 Z', angle: 6, tip: [0, -66, 9] },
  bear: { out: 'M-17,-6 A17,17 0 1 1 17,-6 A17,17 0 1 1 -17,-6 Z',
    in: 'M-9,-6 A9,9 0 1 1 9,-6 A9,9 0 1 1 -9,-6 Z', angle: 22, tip: null },
};
const ACC_COLOR = { scarf: '#E05A47', hat: '#5B8DEF', crown: '#F2C14E', phones: '#5B6474', cups: '#E05A47' };

const star = (x, y, r) => `M${f(x)},${f(y - r)} Q${f(x)},${f(y)} ${f(x + r)},${f(y)} Q${f(x)},${f(y)} ${f(x)},${f(y + r)} ` +
  `Q${f(x)},${f(y)} ${f(x - r)},${f(y)} Q${f(x)},${f(y)} ${f(x)},${f(y - r)}Z`;

function eye(cx, cy, style, open, s, sparkle, dir, ink, cream) {
  const st = `fill:none;stroke:${ink};stroke-width:4.5;stroke-linecap:round;stroke-linejoin:round`;
  if (style === 'happy') return `<path d="M${f(cx - 10 * s)},${f(cy + 4)} Q${f(cx)},${f(cy - 10 * s)} ${f(cx + 10 * s)},${f(cy + 4)}" style="${st}"/>`;
  if (style === 'squeeze') return `<path d="M${f(cx - 7 * dir)},${f(cy - 7)} L${f(cx + 6 * dir)},${f(cy)} L${f(cx - 7 * dir)},${f(cy + 7)}" style="${st}"/>`;
  if (style === 'closed' || open < 0.15) return `<path d="M${f(cx - 10 * s)},${f(cy)} Q${f(cx)},${f(cy + 7 * s)} ${f(cx + 10 * s)},${f(cy)}" style="${st}"/>`;
  const rx = 12.5 * s, ry = 15 * s * Math.max(1, open), o = Math.min(1, open); // крупные круглые глаза — милее
  const lid = cy - ry + 2 * ry * (1 - o); // верхнее веко срезает глаз
  let shape;
  if (o > 0.995) shape = `<ellipse cx="${f(cx)}" cy="${f(cy)}" rx="${f(rx)}" ry="${f(ry)}"/>`;
  else {
    const w = rx * Math.sqrt(Math.max(0, 1 - ((lid - cy) / ry) ** 2));
    shape = `<path d="M${f(cx - w)},${f(lid)} A${f(rx)},${f(ry)} 0 ${o > 0.5 ? 1 : 0} 0 ${f(cx + w)},${f(lid)} Z"/>`;
  }
  const hy = Math.max(cy - 5 * s, lid + 5);
  let hl = '';
  if (hy < cy + ry - 5) hl += sparkle > 0.5 ? `<path d="${star(cx + 3 * s, hy, 7.5 * s)}"/>` : `<circle cx="${f(cx + 4 * s)}" cy="${f(hy)}" r="${f(4.6 * s)}"/>`;
  if (o > 0.45) hl += `<circle cx="${f(cx - 4 * s)}" cy="${f(cy + 6.5 * s)}" r="${f(2.2 * s)}"/>`;
  return `<g style="fill:${ink};stroke:${ink};stroke-width:2;stroke-linejoin:round">${shape}</g><g style="fill:${cream}">${hl}</g>`;
}

function mouth(type, open, ink, blush) {
  const x = 128, y = 163;
  const st = `fill:none;stroke:${ink};stroke-width:3.5;stroke-linecap:round;stroke-linejoin:round`;
  const nose = `<path d="M${x - 5},${y - 5} Q${x},${y - 7.5} ${x + 5},${y - 5} Q${x + 2},${y + 0.5} ${x},${y + 0.5} Q${x - 2},${y + 0.5} ${x - 5},${y - 5}Z" style="fill:${blush};stroke:${ink};stroke-width:2;stroke-linejoin:round"/>`;
  const w = `M${x - 9},${y + 1} Q${x - 4.5},${y + 7} ${x},${y + 1.5} Q${x + 4.5},${y + 7} ${x + 9},${y + 1}`;
  const line = d => `<path d="${d}" style="${st}"/>`;
  let m;
  switch (type) {
    case 'grin': {
      const h = 7 + 9 * open;
      m = `<path d="M${x - 10},${y + 2} Q${x},${f(y + 2 + 1.6 * h)} ${x + 10},${y + 2} Z" style="fill:${ink};stroke:${ink};stroke-width:2;stroke-linejoin:round"/>` +
        (h > 11 ? `<ellipse cx="${x}" cy="${f(y + 2 + 0.58 * h)}" rx="5" ry="${f(0.18 * h)}" style="fill:${blush}"/>` : '');
      break;
    }
    case 'o': { const ry = 3 + 4 * open; m = `<ellipse cx="${x}" cy="${f(y + 4 + ry)}" rx="${f(3.5 + 2.5 * open)}" ry="${f(ry)}" style="fill:${ink}"/>`; break; }
    case 'tongue': m = `<ellipse cx="${x + 4}" cy="${y + 8}" rx="4.5" ry="5" style="fill:${blush};stroke:${ink};stroke-width:2.5"/>` + line(w); break;
    case 'flat': m = line(`M${x - 6},${y + 5} L${x + 6},${y + 5}`); break;
    case 'frown': m = line(`M${x - 8},${y + 9} Q${x},${y + 3} ${x + 8},${y + 9}`); break;
    case 'wavy': m = line(`M${x - 10},${y + 6} Q${x - 5},${y + 2} ${x},${y + 6} Q${x + 5},${y + 10} ${x + 10},${y + 6}`); break;
    case 'pout': m = line(`M${x - 5},${y + 8} Q${x},${y + 4} ${x + 5},${y + 8}`); break;
    default: m = line(w);
  }
  return nose + m;
}

function svg(pose, opt = {}) {
  const p = { ...BASE, ...expand(pose) };
  const id = opt.id || 'kai', size = opt.size || SIZE;
  const look = { ...LOOK, ...(opt.look || {}) };
  const kind = KINDS[look.kind] ? look.kind : 'cat', wear = new Set(look.acc || []);
  const pal = PALETTES[look.color] || PALETTE;
  const col = k => `var(--kai-${k},${pal[k]})`;   // цвет образа; CSS-переменные --kai-* по-прежнему важнее
  const ink = col('ink'), main = col('main'), cream = col('cream'), acc = col('accent'), blush = col('blush');
  const outline = w => `fill:none;stroke:${ink};stroke-width:${w};stroke-linecap:round;stroke-linejoin:round`;
  const fillOut = c => `fill:${c};stroke:${ink};stroke-width:${OUT};stroke-linejoin:round`;
  const [lx, ly] = p.look;
  const tilt = `rotate(${f(p.tilt)} 128 160)`;

  const E = EARS[kind];
  const ear = side => {
    const a = side * (E.angle + (side < 0 ? p.earL : p.earR));
    const tip = E.tip ? `<circle cx="${E.tip[0]}" cy="${E.tip[1]}" r="${E.tip[2]}" clip-path="url(#${id}-ear)" style="fill:${acc}"/>` : '';
    return `<g id="ear-${side < 0 ? 'l' : 'r'}" transform="translate(${side < 0 ? 92 : 164} 120) rotate(${f(a)})${side < 0 ? ' scale(-1 1)' : ''}">` +
      `<path d="${E.out}" style="fill:${main}"/><path d="${E.in}" style="fill:${E.inner === 'cream' ? cream : blush}"/>${tip}` +
      `<path d="${E.out}" style="${outline(OUT)}"/></g>`;
  };

  const c = p.curl, tx = 40 - 18 * c, ty = -60 - 4 * c;
  const tailD = `M0,0 C24,6 54,${f(-20 - 14 * c)} ${f(tx)},${f(ty)}`;
  const tailBody = {
    cat: `<path d="${tailD}" style="${outline(15 + 2 * OUT)}"/><path d="${tailD}" style="fill:none;stroke:${main};stroke-width:15;stroke-linecap:round"/>` +
      `<path d="${tailD}" style="fill:none;stroke:${ink};stroke-width:15;stroke-dasharray:7 10;stroke-dashoffset:-14;opacity:.28"/>` + // полоски
      `<circle cx="${f(tx)}" cy="${f(ty)}" r="7.5" style="fill:${cream}"/>`,
    fox: `<path d="${tailD}" style="${outline(24 + 2 * OUT)}"/><path d="${tailD}" style="fill:none;stroke:${main};stroke-width:24;stroke-linecap:round"/>` +
      `<circle cx="${f(tx)}" cy="${f(ty)}" r="12" style="fill:${cream}"/>`,                 // пушистый хвост со светлым кончиком
    bunny: `<circle cx="16" cy="-8" r="15" style="${fillOut(cream)}"/>`,                     // хвостик-помпон
    bear: `<circle cx="14" cy="-6" r="11" style="${fillOut(main)}"/>`,                       // короткий круглый хвостик
  }[kind];
  const tail = `<g id="tail" transform="translate(180 208) rotate(${f(-p.tail)})">${tailBody}</g>`;

  const body = `<g id="body"><path d="${BODY}" style="${fillOut(main)}"/>` +
    `<ellipse cx="98" cy="126" rx="17" ry="8" transform="rotate(-32 98 126)" style="fill:${cream};opacity:.35"/>` +
    `<ellipse cx="128" cy="205" rx="34" ry="17" style="fill:${cream}"/></g>`;

  const sp = p.spark, L = 8 * (0.6 + 0.5 * sp);
  let rays = '';
  for (let i = 0; i < 8; i++) rays += `<path d="M0,-3 L0,${f(-3 - (i % 2 ? 0.55 * L : L))}" transform="rotate(${i * 45})"/>`;
  const spark = `<g id="spark" transform="translate(128 205) rotate(${f(p.sparkRot)})">` +
    `<circle r="${f(10 + 6 * sp)}" style="fill:${acc};opacity:${f(0.3 * sp)}"/>` +
    `<g style="fill:none;stroke:${col('spark')};stroke-width:3;stroke-linecap:round">${rays}</g><circle r="2.2" style="fill:${col('spark')}"/></g>`;

  const s = p.step;
  const feet = `<g id="feet" style="${fillOut(main)}">` +
    `<ellipse cx="${f(102 - 6 * s)}" cy="${f(226 - 10 * Math.max(0, s))}" rx="17" ry="9.5"/>` +
    `<ellipse cx="${f(154 + 6 * s)}" cy="${f(226 - 10 * Math.max(0, -s))}" rx="17" ry="9.5"/></g>`;

  const arm = side => {
    const d = 'M0,0 L0,26', a = side < 0 ? p.armL : -p.armR, th = side < 0 ? p.thumbL : p.thumbR;
    // большой палец всегда смотрит вверх: поворот лапки отменяется у её кончика
    const tg = `<g transform="translate(0 26) rotate(${f(-a)}) scale(${f(th)})">`, td = 'M0,-2 L0,-17';
    const thumbOut = th > 0.05 ? `${tg}<path d="${td}" style="${outline(15)}"/></g>` : '';
    const thumbIn = th > 0.05 ? `${tg}<path d="${td}" style="fill:none;stroke:${main};stroke-width:9;stroke-linecap:round"/></g>` : '';
    return `<g id="arm-${side < 0 ? 'l' : 'r'}" transform="translate(${side < 0 ? 76 : 180} 180) rotate(${f(a)})">` +
      `${thumbOut}<path d="${d}" style="${outline(16 + 2 * OUT)}"/><path d="${d}" style="fill:none;stroke:${main};stroke-width:16;stroke-linecap:round"/>` +
      `${thumbIn}<circle r="13.6" style="fill:${main}"/></g>`; // круг прячет контур у плеча — лапка «вырастает» из тела
  };
  const heart = p.heart > 0.05 ? `<g id="prop-heart" transform="translate(128 201) scale(${f(1.55 * p.heart)})">` +
    `<path d="M0,9 C-14,0 -12,-12 0,-5 C12,-12 14,0 0,9 Z" style="fill:${col('spark')};stroke:${ink};stroke-width:2.5;stroke-linejoin:round"/>` +
    `<ellipse cx="-4.5" cy="-3" rx="2.2" ry="1.6" style="fill:${cream};opacity:.7"/></g>` : '';

  const es = p.eyeScale;
  const browY = (o, dy) => f(151 - 24 * es * Math.max(1, o) + dy);
  const brows = `<g id="brows" style="${outline(4)}">` +
    `<path d="M-7,1.5 Q0,-1.5 7,1.5" transform="translate(99 ${browY(p.openL, p.browLY)}) rotate(${f(p.browL)})"/>` +
    `<path d="M-7,1.5 Q0,-1.5 7,1.5" transform="translate(157 ${browY(p.openR, p.browRY)}) rotate(${f(-p.browR)})"/></g>`;

  const stripes = kind === 'cat' ? `<g id="stripes" style="fill:none;stroke:${ink};stroke-width:4;stroke-linecap:round;opacity:.3">` +
    `<path d="M117,108 L120,119"/><path d="M128,106 L128,120"/><path d="M139,108 L136,119"/></g>` : '';
  const whiskers = kind === 'bear' ? '' : `<g id="whiskers" style="fill:none;stroke:${ink};stroke-width:2.2;stroke-linecap:round;opacity:.8">` +
    `<path d="M107,167 L80,161"/><path d="M107,172 L79,172"/><path d="M107,177 L81,184"/>` +
    `<path d="M149,167 L176,161"/><path d="M149,172 L177,172"/><path d="M149,177 L175,184"/></g>`;
  const glasses = wear.has('glasses') ? `<g id="acc-glasses" style="fill:${cream};fill-opacity:.18;stroke:${ink};stroke-width:3.5">` +
    `<circle cx="99" cy="151" r="18"/><circle cx="157" cy="151" r="18"/>` +
    `<path d="M117,149 Q128,142 139,149" style="fill:none"/></g>` : '';

  const face = `<g id="face" transform="${tilt} translate(${f(lx * 7)} ${f(ly * 5)})">` + stripes +
    `<g id="muzzle" style="fill:${cream}"><ellipse cx="120" cy="170" rx="11" ry="8.5"/><ellipse cx="136" cy="170" rx="11" ry="8.5"/></g>` +
    `<g id="cheeks" style="fill:${blush};opacity:${f(p.blush)}"><ellipse cx="86" cy="170" rx="9" ry="5.5"/><ellipse cx="170" cy="170" rx="9" ry="5.5"/></g>` +
    whiskers +
    `<g id="eyes" transform="translate(${f(lx * 3)} ${f(ly * 3)})">` +
    eye(99, 151, p.eyeL, p.openL, es, p.sparkle, 1, ink, cream) + eye(157, 151, p.eyeR, p.openR, es, p.sparkle, -1, ink, cream) + glasses + '</g>' +
    brows + `<g id="mouth">${mouth(p.mouth, p.mouthOpen, ink, blush)}</g></g>`;

  // Аксессуары: шарф — на шее под лапками, головные — поверх головы и наклоняются вместе с ней.
  const scarf = wear.has('scarf') ? `<g id="acc-scarf" style="fill:${ACC_COLOR.scarf};stroke:${ink};stroke-width:4;stroke-linejoin:round">` +
    `<path d="M160,192 L172,228 L186,223 L178,188 Z"/><path d="M68,178 Q128,197 188,178 L190,188 Q128,207 66,188 Z"/>` +
    `<path d="M80,185 Q128,201 176,185" style="fill:none;stroke:${cream};stroke-width:2.5;opacity:.7"/></g>` : '';
  let head = '';
  if (wear.has('hat')) head = `<g id="acc-hat" style="stroke:${ink};stroke-width:4;stroke-linejoin:round">` +
    `<path d="M90,124 Q92,82 128,80 Q164,82 166,124 Z" style="fill:${ACC_COLOR.hat}"/>` +
    `<path d="M86,118 Q128,108 170,118 L170,129 Q128,119 86,129 Z" style="fill:${cream}"/>` +
    `<circle cx="128" cy="77" r="9" style="fill:${cream}"/></g>`;
  else if (wear.has('crown')) head = `<g id="acc-crown" style="stroke:${ink};stroke-width:4;stroke-linejoin:round">` +
    `<path d="M106,112 L106,92 L117,102 L128,86 L139,102 L150,92 L150,112 Z" style="fill:${ACC_COLOR.crown}"/>` +
    `<circle cx="128" cy="104" r="3" style="fill:${blush};stroke-width:1.5"/></g>`;
  else if (wear.has('headphones')) head = `<g id="acc-headphones">` +
    `<path d="M70,150 C66,96 98,78 128,78 C158,78 190,96 186,150" style="${outline(11)}"/>` +
    `<path d="M70,150 C66,96 98,78 128,78 C158,78 190,96 186,150" style="fill:none;stroke:${ACC_COLOR.phones};stroke-width:5;stroke-linecap:round"/>` +
    `<g style="fill:${ACC_COLOR.cups};stroke:${ink};stroke-width:4"><ellipse cx="66" cy="156" rx="11" ry="18"/><ellipse cx="190" cy="156" rx="11" ry="18"/></g></g>`;
  const hat = head ? `<g id="acc-head" transform="${tilt}">${head}</g>` : '';

  const flip = p.facing < 0 ? 'translate(256 0) scale(-1 1) ' : '';
  const T = `${flip}translate(0 ${f(p.y)}) rotate(${f(p.rot)} 128 228) translate(128 228) scale(${f(p.sx)} ${f(p.sy)}) translate(-128 -228)`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${SIZE} ${SIZE}" width="${size}" height="${size}">` +
    `<defs><clipPath id="${id}-ear"><path d="${E.out}"/></clipPath></defs>` +
    `<g id="kai" transform="${T}">${tail}<g id="ears" transform="${tilt}">${ear(-1)}${ear(1)}</g>${body}${spark}${scarf}${feet}${arm(-1)}${arm(1)}${heart}${face}${hat}</g></svg>`;
}

// ── Публичный API
const statePose = name => {
  if (!STATES[name]) throw new Error(`Kai: нет состояния "${name}"`);
  return { ...BASE, ...expand(STATES[name].pose) };
};
function pose(state, anim = 'idle', t = 0) {
  const A = ANIMS[anim];
  if (!A) throw new Error(`Kai: нет анимации "${anim}"`);
  return A.fn(statePose(state || A.state), ((t % 1) + 1) % 1);
}
const frame = (state, anim, t, opt) => svg(pose(state, anim, t), opt);
const frames = (anim, state, opt) => Array.from({ length: ANIMS[anim].frames }, (_, i) => frame(state, anim, i / ANIMS[anim].frames, opt));

// Живой питомец в DOM-элементе: kai.set({ state: 'curious', anim: 'waiting' }) — состояние плавно перетекает.
let uid = 0;
function mount(el, opts = {}) {
  const id = `kai${++uid}`, blendMs = opts.blendMs ?? 300;
  let state = opts.state || ANIMS[opts.anim || 'idle'].state, anim = opts.anim || 'idle';
  let from = statePose(state), to = from, t0 = 0, start = performance.now(), last = '', raf;
  const tick = now => {
    const k = clamp((now - t0) / blendMs), A = ANIMS[anim];
    const i = Math.floor((now - start) / 1000 * A.fps) % A.frames;
    const key = `${anim}:${i}:${k}`;
    if (key !== last) { last = key; el.innerHTML = svg(A.fn(blend(from, to, smooth(k)), i / A.frames), { id, size: opts.size }); }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return {
    set({ state: s, anim: a } = {}) {
      if (a && a !== anim) { anim = a; start = performance.now(); }
      if (s && s !== state) { from = blend(from, to, smooth(clamp((performance.now() - t0) / blendMs))); to = statePose(s); state = s; t0 = performance.now(); }
    },
    get state() { return state; }, get anim() { return anim; },
    stop() { cancelAnimationFrame(raf); },
  };
}

const Kai = { PALETTE, PALETTES, COLOR_NAMES, KINDS, ACCESSORIES, LOOK, lookId, SIZE, BASE, STATES, ANIMS, LOOKS, expand, blend, pose, svg, frame, frames, mount };
if (typeof module !== 'undefined' && module.exports) module.exports = Kai; else root.Kai = Kai;
})(this);
