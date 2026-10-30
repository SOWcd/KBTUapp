import { describe, expect, it } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// The design system's ratchet (Oct 30): raw font sizes, raw px radii and raw hex colours in .svelte files may only go
// down. Each file's count today is its ceiling (design-ratchet.json); a screen moved onto the tokens lowers its own.
// After lowering on purpose: UPDATE_RATCHET=1 npx vitest run src/lib/design.test.ts, then review the JSON's diff.
// ponytail: regex counts, not a CSS parser; a false hit only makes a ceiling one higher than it needs to be

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CEILINGS = path.join(SRC, 'lib', 'design-ratchet.json');
type Count = { font: number; radius: number; hex: number };

export function count(src: string): Count {
  const font = (src.match(/font(?:-size)?:[^;"'}\n]*?\d(?:\.\d+)?px/g) ?? []).length;
  const radius = (src.match(/border-radius:[^;"'}\n]+/g) ?? [])
    .filter((d) => /(^|[^\d.])[1-9][\d.]*px/.test(d.replace(/var\([^)]*\)/g, ''))).length;
  const hex = (src.match(/#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])/g) ?? []).length;
  return { font, radius, hex };
}

function svelteFiles(dir: string): string[] {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? svelteFiles(p) : e.name.endsWith('.svelte') ? [p] : [];
  });
}

describe('design ratchet', () => {
  it('counts raw values the way the ratchet means', () => {
    expect(count('.a { font: 650 14px/1 var(--font-text); font-size: 12.5px; }')).toEqual({ font: 2, radius: 0, hex: 0 });
    expect(count('.a { font: 600 var(--fs-body)/1.3 var(--font-text); border-radius: var(--r-l); }')).toEqual({ font: 0, radius: 0, hex: 0 });
    expect(count('.a { border-radius: 12px; } .b { border-radius: 50%; } .c { border-radius: 0; } .d { border-radius: var(--r-s, 10px); }').radius).toBe(1);
    expect(count('color: #fff; background: #3B6BFF; id="#app"').hex).toBe(2);
  });

  it('no file has more raw font sizes, radii or colours than its ceiling', () => {
    const now: Record<string, Count> = {};
    for (const f of svelteFiles(SRC)) {
      const c = count(fs.readFileSync(f, 'utf8'));
      if (c.font || c.radius || c.hex) now[path.relative(SRC, f).split(path.sep).join('/')] = c;
    }
    if (process.env.UPDATE_RATCHET) {
      fs.writeFileSync(CEILINGS, JSON.stringify(Object.fromEntries(Object.entries(now).sort()), null, 1) + '\n');
      return;
    }
    const ceil: Record<string, Count> = JSON.parse(fs.readFileSync(CEILINGS, 'utf8'));
    const over = Object.entries(now).flatMap(([f, c]) => (['font', 'radius', 'hex'] as const)
      .filter((k) => c[k] > (ceil[f]?.[k] ?? 0)).map((k) => `${f}: ${k} ${c[k]} > ${ceil[f]?.[k] ?? 0} (use the tokens in ui/tokens.css)`));
    expect(over).toEqual([]);
  });
});
