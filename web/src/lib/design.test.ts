import { describe, expect, it } from 'vitest';
import ceilings from './design-ratchet.json';

// The design system's ratchet (Oct 30): raw font sizes, raw px radii and raw hex colours in .svelte files may only go
// down. Each file's count today is its ceiling (design-ratchet.json); a screen moved onto the tokens lowers its own.
// After lowering on purpose: UPDATE_RATCHET=1 npx vitest run src/lib/design.test.ts, then review the JSON's diff.
// ponytail: regex counts, not a CSS parser; a false hit only makes a ceiling one higher than it needs to be

type Count = { font: number; radius: number; hex: number };
const KEYS = ['font', 'radius', 'hex'] as const;
const SOURCES = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;

export function count(src: string): Count {
  const font = (src.match(/font(?:-size)?:[^;"'}\n]*?\d(?:\.\d+)?px/g) ?? []).length;
  const radius = (src.match(/border-radius:[^;"'}\n]+/g) ?? [])
    .filter((d) => /(^|[^\d.])[1-9][\d.]*px/.test(d.replace(/var\([^)]*\)/g, ''))).length;
  const hex = (src.match(/#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})(?![0-9a-zA-Z_-])/g) ?? []).length;
  return { font, radius, hex };
}

describe('design ratchet', () => {
  it('counts raw values the way the ratchet means', () => {
    expect(count('.a { font: 650 14px/1 var(--font-text); font-size: 12.5px; }')).toEqual({ font: 2, radius: 0, hex: 0 });
    expect(count('.a { font: 600 var(--fs-body)/1.3 var(--font-text); border-radius: var(--r-l); }')).toEqual({ font: 0, radius: 0, hex: 0 });
    expect(count('.a { border-radius: 12px; } .b { border-radius: 50%; } .c { border-radius: 0; } .d { border-radius: var(--r-s, 10px); }').radius).toBe(1);
    expect(count('color: #fff; background: #3B6BFF; id="#app"').hex).toBe(2);
  });

  it('no file has more raw font sizes, radii or colours than its ceiling', async () => {
    const now: Record<string, Count> = {};
    for (const [file, src] of Object.entries(SOURCES)) {
      const c = count(src);
      if (c.font || c.radius || c.hex) now[file.slice('/src/'.length)] = c;
    }
    if ((globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env.UPDATE_RATCHET) {
      const fs = await import('node:fs' as string);
      fs.writeFileSync(new URL('./design-ratchet.json', import.meta.url), JSON.stringify(Object.fromEntries(Object.entries(now).sort()), null, 1) + '\n');
      return;
    }
    const ceil = ceilings as Record<string, Count>;
    const over = Object.entries(now).flatMap(([f, c]) => KEYS.filter((k) => c[k] > (ceil[f]?.[k] ?? 0))
      .map((k) => `${f}: ${k} ${c[k]} > ${ceil[f]?.[k] ?? 0} (use the tokens in ui/tokens.css)`));
    expect(over).toEqual([]);
  });
});
