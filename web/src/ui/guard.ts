// Text typed and not sent asks before a hand closes the view it's in (a pull lost a club's application): Sheet and Pane.
import { close, type Overlay } from '../lib/state/ui.svelte';
import { sheets } from '../lib/state/sheets';
import { t } from '../lib/i18n/index.svelte';

/** Listen to `focusin` on the view; `typed()` when a close comes in, `ask()` instead of closing then. */
export function unsent(get: () => Overlay) {
  // each text field's value when first focused: a changed one is unsent text (a sent draft is cleared, so it doesn't ask);
  // a search field never counts
  const was = new Map<HTMLInputElement | HTMLTextAreaElement, string>();
  return {
    focusin(e: FocusEvent) {
      const el = e.target;
      const text = el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && /^(text|url|email|tel|number|)$/.test(el.getAttribute('type') ?? '') && el.enterKeyHint !== 'search');
      if (text && !was.has(el)) was.set(el, el.value);
    },
    typed: () => !!get().byUser && [...was].some(([el, v]) => el.isConnected && el.value.trim() !== v.trim()),
    async ask() {
      if (await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('common.cancel'), danger: true })) close(get().id);
    },
  };
}
