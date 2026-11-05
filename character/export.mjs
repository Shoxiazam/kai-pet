// Экспорт PNG-кадров в assets/ через headless Edge/Chrome (DevTools Protocol), без npm: node character/export.mjs
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync, rmSync, mkdtempSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const Kai = createRequire(import.meta.url)('./kai.js');
// Образ из гардероба: KAI_LOOK='{"kind":"fox","color":"ginger","acc":["scarf"]}', кадры — в KAI_OUT.
// Так питомец сам готовит кадры нового образа; без переменных — обычный экспорт с превью.
const LOOK = process.env.KAI_LOOK ? JSON.parse(process.env.KAI_LOOK) : null;
const OUT = process.env.KAI_OUT || join(here, '..', 'assets');
const DOCS = join(here, '..', 'docs');
const BROWSERS = [process.env.KAI_BROWSER,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'];
const exe = BROWSERS.find(p => p && existsSync(p));
if (!exe) throw new Error('Не найден Edge/Chrome. Укажите путь в KAI_BROWSER.');

const port = 9300 + Math.floor(Math.random() * 600), profile = mkdtempSync(join(tmpdir(), 'kai-'));  // два экспорта не мешают друг другу
const browser = spawn(exe, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  '--no-first-run', '--disable-gpu', 'about:blank'], { stdio: 'ignore' });

async function targetWs() {
  for (let i = 0; i < 50; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
      const page = list.find(t => t.type === 'page');
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error('Браузер не ответил по DevTools');
}

try {
  const ws = new WebSocket(await targetWs());
  await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });
  let n = 0; const pending = new Map();
  ws.onmessage = e => { const m = JSON.parse(e.data); pending.get(m.id)?.(m); pending.delete(m.id); };
  const send = (method, params = {}) => new Promise(r => { pending.set(++n, r); ws.send(JSON.stringify({ id: n, method, params })); });
  const ev = async expr => {
    const r = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
    if (r.error || r.result.exceptionDetails) throw new Error(JSON.stringify(r.error || r.result.exceptionDetails));
    return r.result.result.value;
  };

  await send('Page.navigate', { url: pathToFileURL(join(here, 'export.html')).href });
  for (let i = 0; i < 50 && (await ev('typeof grid').catch(() => '')) !== 'function'; i++) await new Promise(r => setTimeout(r, 100));
  if (LOOK) await ev(`Object.assign(Kai.LOOK, ${JSON.stringify(LOOK)}), true`);

  for (const d of ['frames', 'states', 'moods', 'look']) rmSync(join(OUT, d), { recursive: true, force: true });
  const save = async (rel, expr) => {
    const file = join(OUT, rel);
    mkdirSync(dirname(file), { recursive: true });
    writeFileSync(file, Buffer.from(await ev(expr), 'base64'));
  };
  const pad = i => String(i).padStart(3, '0');
  const saveDoc = async (name, expr) => { mkdirSync(DOCS, { recursive: true }); writeFileSync(join(DOCS, name), Buffer.from(await ev(expr), 'base64')); };

  for (const a in Kai.ANIMS) {
    const { frames } = Kai.ANIMS[a];
    for (let i = 0; i < frames; i++) await save(`frames/${a}/${a}_${pad(i)}.png`, `grid([Kai.frame(null, ${JSON.stringify(a)}, ${i / frames})], 1)`);
  }
  const states = Object.keys(Kai.STATES).filter(s => s !== 'neutral');
  for (const s of states) await save(`states/${s}.png`, `grid([Kai.frame(${JSON.stringify(s)}, 'idle', 0)], 1)`);
  // Живые эмоции для питомца: дыхание и моргание поверх каждого состояния, 24 кадра на 12 к/с.
  for (const s of states) for (let i = 0; i < 24; i++)
    await save(`moods/${s}/${s}_${pad(i)}.png`, `grid([Kai.frame(${JSON.stringify(s)}, 'idle', ${i / 24})], 1)`);
  for (const d in Kai.LOOKS) await save(`look/${d}.png`, `grid([Kai.svg({ look: Kai.LOOKS.${d} })], 1)`);
  if (!LOOK) {
    const statesGrid = `${JSON.stringify(states)}.map(s => Kai.frame(s, 'idle', 0))`;
    await saveDoc('states_grid.png', `grid(${statesGrid}, 5)`);
    await saveDoc('look_grid.png', `grid(Object.values(Kai.LOOKS).map(l => Kai.svg({ look: l })), 5)`);
    await saveDoc('anims_grid.png', `grid(Object.keys(Kai.ANIMS).map(a => Kai.frame(null, a, 0.3)), 5)`);
    // Гардероб: все виды во всех цветах и все аксессуары
    await saveDoc('wardrobe_kinds_colors.png', `grid(Object.keys(Kai.KINDS).flatMap(k => Object.keys(Kai.PALETTES).map(c =>
      Kai.svg({}, { look: { kind: k, color: c, acc: [] } }))), 8)`);
    await saveDoc('wardrobe_accessories.png', `grid([['scarf'], ['hat'], ['glasses'], ['headphones'], ['crown'],
      ['hat', 'scarf', 'glasses'], ['crown', 'scarf'], ['headphones', 'glasses']].map((a, i) =>
      Kai.svg({}, { look: { kind: Object.keys(Kai.KINDS)[i % 4], color: Object.keys(Kai.PALETTES)[i], acc: a } })), 4)`);
  }

  ws.close();
  console.log('PNG сохранены в', OUT);
} finally {
  browser.once('exit', () => { try { rmSync(profile, { recursive: true, force: true, maxRetries: 10 }); } catch {} });
  browser.kill();
}
