// Gemini's yes (lib/kriGoogle.ts): taps in a row go one at a time, the latest wins, and the switch ends on what the
// server last said, whatever order the answers would have come in.
import { expect, it, vi } from 'vitest';

const sent: boolean[] = [], answers: (() => void)[] = [];
let fail = false;
vi.mock('./api', () => ({ api: { kriGoogle: (on: boolean) => { sent.push(on); return new Promise((ok, no) => answers.push(() => (fail ? no(new Error('x')) : ok({ yes: on })))); } } }));
vi.mock('./state/session.svelte', () => ({ session: { me: { id: 1, kriGoogle: false } } }));
vi.mock('./state/ui.svelte', () => ({ say: () => {} }));
vi.mock('./i18n/index.svelte', () => ({ t: (k: string) => k }));
vi.mock('./tg', () => ({ haptic: { ok: () => {}, error: () => {} } }));
import { setKriGoogle } from './kriGoogle';
import { session } from './state/session.svelte';

const me = session.me as unknown as { kriGoogle: boolean };
const next = async () => { await Promise.resolve(); answers.shift()!(); await new Promise((r) => setTimeout(r)); };

it('on then off: off goes after on is through, the switch ends off', async () => {
  const a = setKriGoogle(true), b = setKriGoogle(false);
  expect(me.kriGoogle).toBe(false);            // the latest tap shows at once
  expect(sent).toEqual([true]);                // one call at a time
  await next(); expect(sent).toEqual([true, false]);
  await next();
  expect(await a).toBe(false); expect(await b).toBe(true); expect(me.kriGoogle).toBe(false);
});

it('on, off, on while the first is on its way: nothing more to send once on is kept', async () => {
  sent.length = 0;
  const a = setKriGoogle(true); void setKriGoogle(false); const c = setKriGoogle(true);
  await next();
  expect(sent).toEqual([true]); expect(await a).toBe(true); expect(await c).toBe(true); expect(me.kriGoogle).toBe(true);
});

it('a failed call: the switch shows what the server last said', async () => {
  sent.length = 0; fail = true;
  const a = setKriGoogle(false);
  expect(me.kriGoogle).toBe(false);
  await next();
  expect(await a).toBe(false); expect(me.kriGoogle).toBe(true);
});
