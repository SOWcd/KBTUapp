// The generic error toast is counted against the screen on top; any other toast isn't.
import { expect, it, vi } from 'vitest';

vi.stubGlobal('document', { hidden: false, addEventListener: () => {}, documentElement: { dataset: {} } });
const count = vi.hoisted(() => vi.fn());
vi.mock('../stats', () => ({ count }));
vi.mock('../tg', () => ({ haptic: {}, tg: {} }));
vi.mock('./theme.svelte', () => ({ switching: () => null }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k }));
const { open, close, say, ui } = await import('./ui.svelte');

it('counts the error toast per screen', () => {
  ui.tab = 'forum';
  say('fine');
  expect(count).not.toHaveBeenCalled();
  say('common.error');
  expect(count).toHaveBeenLastCalledWith('err.tab.forum');
  const sheet = {} as never;
  const id = open(sheet, {}, 'sheet.event');
  expect(count).toHaveBeenLastCalledWith('sheet.event');
  say('common.error');
  expect(count).toHaveBeenLastCalledWith('err.sheet.event');
  close(id);
  say('common.error');
  expect(count).toHaveBeenLastCalledWith('err.tab.forum');
});
