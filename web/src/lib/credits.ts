// The people of the app (server logic/credits.py): my own answer to "name me next to what I gave?". The feature's own
// consent: a yes sends the version of the text the sheet showed; said again any time (the bot's link, Settings' switch).
import { api, type CreditItem, type Lang } from './api';
import { data } from './state/data.svelte';
import { say } from './state/ui.svelte';
import { t, i18n } from './i18n/index.svelte';
import { haptic } from './tg';

/** a line in the viewer's language (ours: all three are always written) */
export const lineOf = (i: CreditItem): string => i.text[i18n.lang as Lang] || i.text.ru;

/** my answer: shown at once, back if the server says no; true once it is kept */
export async function answerCredits(show: boolean): Promise<boolean> {
  const c = data.credits;
  if (!c?.mine) return false;
  const was = c.mine.consent;
  c.mine.consent = show;
  try { data.credits = await api.creditsConsent(show, c.version); haptic.ok(); return true; }
  catch { if (data.credits?.mine) data.credits.mine.consent = was; haptic.error(); say(t('common.error'), 'warning_3d'); return false; }
}
