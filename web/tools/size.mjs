// What a phone downloads for the first screen, gzipped: index.html's entry chunk, the chunks it imports eagerly and
// their CSS (from Vite's dist/.vite/manifest.json; dynamic imports are lazy and left out), and all JS for reference.
// Checked against size-budget.json: the first screen may grow by 3% or 5 KB, whichever is larger. CI's web job runs it
// after the build and writes the table to the job summary.
//   node tools/size.mjs            check (npm run size)
//   node tools/size.mjs --update   write the current numbers as the budget (npm run size:update), for deliberate growth
import { appendFileSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

const dist = new URL('../dist/', import.meta.url), budgetFile = new URL('../size-budget.json', import.meta.url);
const gz = (file) => gzipSync(readFileSync(new URL(file, dist)), { level: 9 }).length;

const manifest = JSON.parse(readFileSync(new URL('.vite/manifest.json', dist), 'utf8'));
const files = new Set(), seen = new Set();
(function walk(key) {
  if (seen.has(key)) return;
  seen.add(key);
  const m = manifest[key];
  files.add(m.file);
  for (const c of m.css ?? []) files.add(c);
  for (const i of m.imports ?? []) walk(i);
})('index.html');

const now = {
  firstScreen: [...files].reduce((n, f) => n + gz(f), 0),
  allJs: readdirSync(new URL('assets/', dist)).filter((f) => f.endsWith('.js')).reduce((n, f) => n + gz(`assets/${f}`), 0),
};

if (process.argv.includes('--update')) {
  writeFileSync(budgetFile, JSON.stringify(now, null, 2) + '\n');
  console.log(`size-budget.json: first screen ${now.firstScreen} B, all JS ${now.allJs} B (gzipped)`);
  process.exit(0);
}

const base = JSON.parse(readFileSync(budgetFile, 'utf8'));
const limit = base.firstScreen + Math.max(base.firstScreen * 0.03, 5 * 1024);
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
const change = (a, b) => `${b >= a ? '+' : '−'}${kb(Math.abs(b - a))} (${b >= a ? '+' : ''}${(((b - a) / a) * 100).toFixed(1)}%)`;
const over = now.firstScreen > limit;
const table = [
  '| gzipped | budget | this build | change |', '| --- | ---: | ---: | ---: |',
  `| first screen (${files.size} files) | ${kb(base.firstScreen)} | ${kb(now.firstScreen)} | ${change(base.firstScreen, now.firstScreen)} |`,
  `| all JS | ${kb(base.allJs)} | ${kb(now.allJs)} | ${change(base.allJs, now.allJs)} |`,
  '',
  over ? `**The first screen is over its budget (${kb(limit)}).** If that is deliberate: \`cd web && npm run build && npm run size:update\`, and commit size-budget.json.`
    : `First screen within its budget (${kb(limit)}: +3% or +5 KB).`,
].join('\n');
console.log(table);
if (process.env.GITHUB_STEP_SUMMARY) appendFileSync(process.env.GITHUB_STEP_SUMMARY, `### Bundle size\n\n${table}\n`);
process.exit(over ? 1 : 0);
