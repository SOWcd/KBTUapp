// Adds one UI string to ru.ts, kk.ts and en.ts at the same spot, so the three files keep one key order (a vitest,
// src/lib/i18n/i18n.test.ts, checks it): after --after, else after the last key that shares the longest prefix
// with the new one (look.frame.x goes after the last look.frame.*, else after the last look.*).
// usage: node tools/i18n.mjs add <key> --ru "..." --kk "..." --en "..." [--after <key>]   (from web/)
// Plain strings only; a plural ({ one, few, many, other }) is added by hand.
import { readFileSync, writeFileSync } from 'node:fs';

const dir = new URL('../src/lib/i18n/', import.meta.url);
const LANGS = ['ru', 'kk', 'en'];
const fail = (msg) => { console.error(`i18n: ${msg}`); process.exit(1); };

const [cmd, key, ...rest] = process.argv.slice(2);
if (cmd !== 'add' || !key || key.startsWith('--')) fail('usage: node tools/i18n.mjs add <key> --ru "..." --kk "..." --en "..." [--after <key>]');
if (!/^[\w-]+(\.[\w-]+)+$/.test(key)) fail(`"${key}" is not a key like area.name`);
// the map's places live in spots.ts for kk and en (see its header): add those by hand
if (key.startsWith('route.spot.')) fail('route.spot.* keys go in ru.ts and spots.ts: add them by hand');
const opt = {};
for (let i = 0; i < rest.length; i += 2) {
  const name = rest[i]?.replace(/^--/, '');
  if (!rest[i]?.startsWith('--') || !['ru', 'kk', 'en', 'after'].includes(name) || rest[i + 1] === undefined) fail(`bad argument ${rest[i]}`);
  opt[name] = rest[i + 1];
}
for (const l of LANGS) if (!opt[l]?.trim()) fail(`--${l} is missing`);

// one entry per line, as the files are written: "  'key': ..." or '  "key": ...'
const files = LANGS.map((l) => {
  const lines = readFileSync(new URL(`${l}.ts`, dir), 'utf8').split('\n');
  const at = new Map();
  lines.forEach((s, i) => { const m = /^ {2}(['"])([^'"]+)\1:/.exec(s); if (m) at.set(m[2], i); });
  return { l, lines, at };
});
for (const f of files) if (f.at.has(key)) fail(`${key} already exists in ${f.l}.ts`);

let after = opt.after;
if (!after) {
  const ru = [...files[0].at.keys()].filter((k) => !k.startsWith('route.spot.'));
  for (let p = key.lastIndexOf('.'); p > 0 && !after; p = key.lastIndexOf('.', p - 1)) {
    after = ru.findLast((k) => k.startsWith(key.slice(0, p + 1)));
  }
  if (!after) fail(`no key starts with ${key.split('.')[0]}.: say where with --after <key>`);
}
for (const f of files) if (!f.at.has(after)) fail(`${after} is not in ${f.l}.ts`);

for (const f of files) {
  let i = f.at.get(after);
  while (!f.lines[i].trimEnd().endsWith(',') && i < f.lines.length - 1) i++; // an entry spread over lines
  f.lines.splice(i + 1, 0, `  '${key}': ${JSON.stringify(opt[f.l])},`);
}
for (const f of files) writeFileSync(new URL(`${f.l}.ts`, dir), f.lines.join('\n'));
console.log(`i18n: added ${key} after ${after} in ru, kk, en`);
