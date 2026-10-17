// Every translation asks for the same holes as the Russian source ({name}, {n}…): a hole only one language has would
// show up as raw braces for the people reading it.
import { expect, it } from 'vitest';
import ru from './ru';
import kk from './kk';
import en from './en';

const holes = (v: unknown): string => [...new Set(JSON.stringify(v).match(/\{[a-zA-Z]+\}/g) ?? [])].sort().join(',');

it('keeps the same holes in ru, kk and en', () => {
  const bad: string[] = [];
  for (const [k, v] of Object.entries(ru)) for (const [name, d] of [['kk', kk], ['en', en]] as const) {
    if (holes(v) !== holes((d as Record<string, unknown>)[k])) bad.push(`${name} ${k}`);
  }
  expect(bad).toEqual([]);
});
