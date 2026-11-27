// The Google Play closed test's offer (AndroidTestSheet): on entry at most twice in all, the second time 3 days after
// the first and only if its button wasn't tapped; Profile's row (AppCard) stays until the installed app reports itself
// (tg.inPlayApp -> /api/me's androidApp). Kept on this phone; storage blocked: never shown, never a nag.
import { openLink } from './tg';
import { count } from './stats';
import { i18n } from './i18n/index.svelte';
import { PLAY_PAGE } from './feedback';

const AGAIN_AFTER = 3 * 86400_000;

/** Whether the sheet comes up on this launch ('first', 'again' or null), marking it shown. */
export function offerDue(now = Date.now()): 'first' | 'again' | null {
  try {
    const was = localStorage.getItem('andr.asked');
    // '1': shown before its time was kept (until Nov 27); its 3 days count from now
    if (!was || was === '1') { localStorage.setItem('andr.asked', String(now)); return was ? null : 'first'; }
    if (localStorage.getItem('andr.went') || localStorage.getItem('andr.again') || now - Number(was) < AGAIN_AFTER) return null;
    localStorage.setItem('andr.again', '1');
    return 'again';
  } catch { return null; }
}

/** The steps' page in the phone's own browser, where the Google account lives; the sheet won't come back.
 *  (Profile's row does the same inline, AppCard.svelte: this module stays off the start's path.) */
export function openPlayPage(from: 'andr.go' | 'andr.rowgo'): void {
  count(from);
  try { localStorage.setItem('andr.went', '1'); } catch { /* the sheet may come once more: fine */ }
  openLink(PLAY_PAGE + i18n.lang, true);
}
