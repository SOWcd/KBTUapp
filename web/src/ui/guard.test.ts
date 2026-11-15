import { expect, it, vi } from 'vitest';

vi.mock('../lib/state/ui.svelte', () => ({ close: vi.fn() }));
vi.mock('../lib/state/sheets', () => ({ sheets: {} }));
vi.mock('../lib/i18n/index.svelte', () => ({ t: (k: string) => k }));
import { unsent } from './guard';

it('guards words typed during a lazy load, but treats ordinary prefills as the baseline', () => {
  class Textarea {
    value = 'typed before mount';
    isConnected = true;
    constructor(public transferred: boolean) {}
    hasAttribute(name: string) { return name === 'data-unsent' && this.transferred; }
  }
  vi.stubGlobal('HTMLTextAreaElement', Textarea);
  vi.stubGlobal('HTMLInputElement', class {});
  try {
    for (const transferred of [false, true]) {
      const field = new Textarea(transferred);
      const overlay = { byUser: false };
      const guard = unsent(() => overlay as never);
      guard.focusin({ target: field } as unknown as FocusEvent);
      expect(guard.typed()).toBe(false);
      overlay.byUser = true;
      expect(guard.typed()).toBe(transferred);
      field.value = '';
      expect(guard.typed()).toBe(!transferred);
      field.isConnected = false;
      expect(guard.typed()).toBe(false);
    }
  } finally { vi.unstubAllGlobals(); }
});
