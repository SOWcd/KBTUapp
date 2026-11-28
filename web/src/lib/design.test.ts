import { describe, expect, it } from 'vitest';
import ceilings from './design-ratchet.json';

// The design system's ratchet (Oct 30): raw font sizes, raw px radii and raw hex colours in .svelte files may only go
// down, and so may color-mix() (iOS before 16.2 drops the whole declaration: Telegram still runs there). Each file's
// count today is its ceiling (design-ratchet.json); a screen moved onto the tokens lowers its own.
// After lowering on purpose: UPDATE_RATCHET=1 npx vitest run src/lib/design.test.ts, then review the JSON's diff.
// Two more since Nov 3: `weight`, font weights off the scale 450 / 500 (--fw-row's) / 600 /
// 700 / 800; `legacy`, uses of base.css's old classes (.set-row / .set-group / .set-cap / .set-foot, .field, .switch,
// .seg) that ui/Row, Group, Field and Segmented replace: both may only go down as the screens move.
// Outside ui/, backdrop-filter declarations and raw rgba()/hsla() colours may only go down too.
// ponytail: regex counts, not a CSS parser; a false hit only makes a ceiling one higher than it needs to be

type Count = { font: number; radius: number; hex: number; mix: number; weight: number; legacy: number; backdrop: number; rawColor: number };
const KEYS = ['font', 'radius', 'hex', 'mix', 'weight', 'legacy', 'backdrop', 'rawColor'] as const;
const SCALE = new Set(['450', '500', '600', '700', '800']);
const SOURCES = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

export function count(src: string, file = ''): Count {
  const font = (src.match(/font(?:-size)?:[^;"'}\n]*?\d(?:\.\d+)?px/g) ?? []).length;
  const radius = (src.match(/border-radius:[^;"'}\n]+/g) ?? [])
    .filter((d) => /(^|[^\d.])[1-9][\d.]*px/.test(d.replace(/var\([^)]*\)/g, ''))).length;
  const hex = (src.match(/#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])/g) ?? []).length;
  const mix = (src.match(/color-mix\(/g) ?? []).length;
  const weight = [...src.matchAll(/font(?:-weight)?:\s*(\d{3})\b/g)].filter((m) => !SCALE.has(m[1])).length;
  const legacy = (src.match(/(?<![\w-])set-(?:row|group|cap|foot)(?![\w-])/g) ?? []).length
    + [...src.matchAll(/class="([^"]*)"/g)].filter((m) => /(?<![\w-])(?:field|switch|seg)(?![\w-])/.test(m[1])).length;
  const backdrop = file.startsWith('ui/') ? 0 : (src.match(/(?<![\w-])(?:-webkit-)?backdrop-filter\s*:|\bstyle:(?:-webkit-)?backdrop-filter(?:\|important)?\s*=/gi) ?? []).length;
  const rawColor = file.startsWith('ui/') ? 0 : (src.match(/(?<![\w-])(?:(?:rgba|hsla)\(|(?:rgb|hsl)\([^)]*\/)/gi) ?? []).length;
  return { font, radius, hex, mix, weight, legacy, backdrop, rawColor };
}

describe('design ratchet', () => {
  it('counts raw values the way the ratchet means', () => {
    expect(count('.a { font: 650 14px/1 var(--font-text); font-size: 12.5px; }')).toEqual({ font: 2, radius: 0, hex: 0, mix: 0, weight: 1, legacy: 0, backdrop: 0, rawColor: 0 });
    expect(count('.a { font: 600 var(--fs-body)/1.3 var(--font-text); border-radius: var(--r-l); }')).toEqual({ font: 0, radius: 0, hex: 0, mix: 0, weight: 0, legacy: 0, backdrop: 0, rawColor: 0 });
    expect(count('<div class="set-group"><button class="set-row x">a</button></div><label class="switch">').legacy).toBe(3);
    expect(count('<p class="field-x">').legacy + count('font-weight: 500; font: 620 13px/1 x').weight).toBe(1);
    expect(count('background: color-mix(in srgb, var(--danger) 16%, transparent)').mix).toBe(1);
    expect(count('.a { border-radius: 12px; } .b { border-radius: 50%; } .c { border-radius: 0; } .d { border-radius: var(--r-s, 10px); }').radius).toBe(1);
    expect(count('color: #fff; background: #3B6BFF; id="#app"').hex).toBe(2);
  });

  it('counts local glass and raw rgba()/hsla() colours only outside ui/', () => {
    const src = '.a { backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); color: rgba(0, 0, 0, .5); background: HSLA(0, 0%, 0%, .5); font-size: 13px; }';
    expect(count(src, 'screens/Example.svelte')).toMatchObject({ backdrop: 2, rawColor: 2, font: 1 });
    expect(count(src, 'ui/glass/Example.svelte')).toMatchObject({ backdrop: 0, rawColor: 0, font: 1 });
    expect(count(src, 'screens/ui/Example.svelte')).toMatchObject({ backdrop: 2, rawColor: 2 });
    const directives = '<div style:backdrop-filter="blur(8px)" style:-webkit-backdrop-filter|important={blur}>';
    expect(count(directives, 'screens/Example.svelte').backdrop).toBe(2);
    expect(count(directives, 'ui/Example.svelte').backdrop).toBe(0);
    expect(count('transition: backdrop-filter 1s; --backdrop-filter: none; color: var(--ink);')).toMatchObject({ backdrop: 0, rawColor: 0 });
    // the slash syntax is the same see-through colour; an opaque rgb() is not
    expect(count('background: rgb(0 0 0 / .5); color: hsl(0 0% 0% / 50%); border-color: rgb(0, 0, 0);', 'screens/Example.svelte').rawColor).toBe(2);
  });

  it('no file has more design violations than its ceiling', async () => {
    const now: Record<string, Count> = {};
    for (const [file, src] of Object.entries(SOURCES)) {
      const f = file.slice('/src/'.length), c = count(src, f);
      if (KEYS.some((k) => c[k])) now[f] = c;
    }
    if ((globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.UPDATE_RATCHET) {
      const fs = await import('node:fs' as string);
      fs.writeFileSync(new URL('./design-ratchet.json', import.meta.url), JSON.stringify(Object.fromEntries(Object.entries(now).sort()), null, 1) + '\n');
      return;
    }
    const ceil = ceilings as Record<string, Partial<Count>>;
    const over = Object.entries(now).flatMap(([f, c]) => KEYS.filter((k) => c[k] > (ceil[f]?.[k] ?? 0))
      .map((k) => `${f}: ${k} ${c[k]} > ${ceil[f]?.[k] ?? 0} (use the tokens in ui/tokens.css and the ui/ components)`));
    expect(over).toEqual([]);
  });
});
