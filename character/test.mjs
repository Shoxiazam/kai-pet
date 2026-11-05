// Самопроверка: node kai/test.mjs
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const Kai = createRequire(import.meta.url)('./kai.js');

const REQUIRED_STATES = ['curious', 'excited', 'playful', 'focused', 'calm', 'caring', 'sleepy', 'tired', 'grumpy',
  'cautious', 'proud', 'confused', 'surprised', 'inspired', 'supportive'];
const REQUIRED_ANIMS = ['idle', 'runLeft', 'runRight', 'wave', 'jump', 'fail', 'waiting', 'working', 'checking', 'lookAround'];
for (const s of REQUIRED_STATES) assert.ok(Kai.STATES[s], `нет состояния ${s}`);
for (const a of REQUIRED_ANIMS) assert.ok(Kai.ANIMS[a], `нет анимации ${a}`);

// Бесшовность: поза в t=0 совпадает с позой в t→1.
const close = (a, b) => JSON.stringify(a, (k, v) => typeof v === 'number' ? Math.round(v * 1e4) / 1e4 + 0 : v)
  === JSON.stringify(b, (k, v) => typeof v === 'number' ? Math.round(v * 1e4) / 1e4 + 0 : v);
for (const a in Kai.ANIMS) {
  const p0 = Kai.ANIMS[a].fn({ ...Kai.BASE, ...Kai.expand(Kai.STATES[Kai.ANIMS[a].state].pose) }, 0);
  const p1 = Kai.ANIMS[a].fn({ ...Kai.BASE, ...Kai.expand(Kai.STATES[Kai.ANIMS[a].state].pose) }, 1 - 1e-9);
  assert.ok(close(p0, p1), `шов в анимации ${a}`);
}

// Кадры: без текста, без NaN, с отдельными слоями скелета.
for (const st in Kai.STATES) for (const a in Kai.ANIMS) for (const svg of Kai.frames(a, st)) {
  assert.ok(!/<text|NaN|undefined/.test(svg), `${st}/${a}: мусор в SVG`);
}
const one = Kai.frame('neutral', 'idle', 0);
for (const id of ['body', 'ear-l', 'ear-r', 'tail', 'eyes', 'mouth', 'spark']) assert.ok(one.includes(`id="${id}"`), `нет слоя ${id}`);
for (const c of Object.values(Kai.PALETTE)) assert.ok(one.includes(c), `цвет ${c} не используется`);
console.log('ok:', Object.keys(Kai.STATES).length, 'состояний,', Object.keys(Kai.ANIMS).length, 'анимаций');
