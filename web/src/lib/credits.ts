// The people of the app (server logic/credits.py): my own answer to "name me next to what I gave?". The feature's own
// consent: a yes sends the version of the text the sheet showed and the latest answer the app saw (the server refuses a
// yes on top of anything newer); said again any time (the bot's link, Settings' switch).
import { api, ApiErr, type CreditItem, type Lang } from './api';
import { data, creditsAnswer } from './state/data.svelte';
import { session } from './state/session.svelte';
import { say } from './state/ui.svelte';
import { t, i18n } from './i18n/index.svelte';
import { haptic } from './tg';

/** a line in the viewer's language (ours: all three are always written) */
export const lineOf = (i: CreditItem): string => i.text[i18n.lang as Lang] || i.text.ru;

/** My answer; true once the server kept it. A yes shows only then (never before it is saved). A no hides me here at
 *  once: my name and face leave the list in the same frame, each of my lines a nameless row. Kept, refused or failed,
 *  the list is then read again and that read alone is shown (a yes from a sheet an answer has overtaken: `conflict`). */
export async function answerCredits(show: boolean): Promise<boolean> {
  const c = data.credits, me = session.me?.id;
  if (!c?.mine) return false;
  const { rev } = c.mine;
  void creditsAnswer(true);
  if (!show) {
    c.mine.consent = false;
    c.people = c.people.flatMap((p) => (p.person?.id === me ? p.items.map((i) => ({ person: null, items: [i] })) : [p]));
    if (c.idea?.person?.id === me) c.idea = { person: null, items: [] };
  }
  let err: unknown = null;
  try { await api.creditsConsent(show, c.version, rev); } catch (e) { err = e; }
  if (!err && data.credits?.mine) data.credits.mine.consent = show; // what I just said, known without the list (the read may fail)
  await creditsAnswer(false);
  if (!err) { haptic.ok(); return true; }
  haptic.error();
  if (!(err instanceof ApiErr && err.code === 'conflict')) say(t('common.error'), 'warning_3d');
  return false;
}
