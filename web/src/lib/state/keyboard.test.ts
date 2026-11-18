// iOS's keyboard is guessed at the tap (its report comes late): the guess, the real height taking over, no report at all.
import { beforeEach, expect, it, vi } from 'vitest';

vi.useFakeTimers();
const on: Record<string, (() => void)[]> = {};
const listen = (k: string, f: () => void) => (on[k] ??= []).push(f);
const fire = (k: string) => on[k]?.forEach((f) => f());
const vv = { height: 812, width: 375, offsetTop: 0, addEventListener: (k: string, f: () => void) => listen(`vv:${k}`, f) };
const field = { matches: () => true, closest: () => null, parentElement: null };
const doc = { activeElement: null as unknown, documentElement: { style: { setProperty: () => {} } }, body: {} };
const store: Record<string, string> = {};
vi.stubGlobal('document', doc);
vi.stubGlobal('localStorage', { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => (store[k] = v) });
vi.stubGlobal('window', { visualViewport: vv, setTimeout, addEventListener: listen });
for (const [k, v] of Object.entries({ innerHeight: 812, innerWidth: 375, scrollY: 0, addEventListener: listen, scrollTo: () => {}, getComputedStyle: () => ({ overflowY: 'visible' }) }))
  vi.stubGlobal(k, v);
vi.mock('../tg', () => ({ onIos: true }));
const { keyboard } = await import('./keyboard.svelte');

async function tap() { fire('pointerdown'); doc.activeElement = field; fire('focusin'); await Promise.resolve(); }
async function blur() { doc.activeElement = null; fire('focusout'); await Promise.resolve(); vv.height = 812; fire('vv:resize'); }
beforeEach(() => blur());

it('rises at the tap, then the real height takes over', async () => {
  await tap();
  expect(keyboard.h).toBe(336); // the first-run guess for a 375 pt phone
  vv.height = 812 - 200; fire('vv:resize'); // a part of the rise: never pulls the guess down
  expect(keyboard.h).toBe(336);
  vv.height = 812 - 301; fire('vv:resize');
  vi.advanceTimersByTime(500);
  expect(keyboard.h).toBe(301);
  await blur();
  expect(keyboard.h).toBe(0);
  await tap();
  expect(keyboard.h).toBe(301); // remembered
});

it('no report ever comes: the guess holds while the field has the focus', async () => {
  await tap();
  vi.advanceTimersByTime(5000);
  expect(keyboard.h).toBe(301); // a field too high beats a field under the keyboard
  await blur();
  expect(keyboard.h).toBe(0);
});
