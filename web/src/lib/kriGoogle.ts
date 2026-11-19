// The assistant's own yes to Google's Gemini answering first (server assistant.GOOGLE_YES; the policy names Google, but
// those who agreed before it did never said yes to it, and nobody is asked to accept the policy again). Asked by one
// quiet card on the assistant's empty opening, given or taken back in Settings → Privacy. me.kriGoogle absent: Google
// isn't open to me (no key, ASSIST_LEAD=off, an earlier policy), so neither the card nor the row shows.
import { api } from './api';
import { session } from './state/session.svelte';
import { say } from './state/ui.svelte';
import { t } from './i18n/index.svelte';
import { haptic } from './tg';

const LATER = 30 * 86400e3; // "Not now": the card rests this long on this phone (not a "no": nothing is sent)
const key = () => `kri.g.later.${session.me?.id}`;

/** "Not now" was tapped in the last 30 days here; storage blocked: as if it was (never nag) */
export function resting(): boolean {
  try { return Date.now() - Number(localStorage.getItem(key()) || 0) < LATER; } catch { return true; }
}

export function rest(): void {
  try { localStorage.setItem(key(), String(Date.now())); } catch { /* blocked: this opening only */ }
}

// the calls one at a time (review: an "on" answered after a later "off" left the switch on with no yes kept): the
// latest tap wins, and once they are all through the switch shows what the server last said
let saved: boolean | null = null, want = false, line: Promise<void> | null = null;

/** the yes given (on) or taken back: shown at once; true if it is what the server keeps after every tap went through */
export async function setKriGoogle(on: boolean): Promise<boolean> {
  const me = session.me;
  if (me?.kriGoogle == null) return false;
  if (!line) saved = me.kriGoogle; // nothing on its way: what shows is what is kept
  me.kriGoogle = want = on;
  line ??= (async () => {
    try { while (want !== saved) saved = (await api.kriGoogle(want)).yes; }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { line = null; me.kriGoogle = saved!; }
  })();
  await line;
  if (me.kriGoogle === on) haptic.ok();
  return me.kriGoogle === on;
}
