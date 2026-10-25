// "Write to the creator": opens the owner's Telegram DM with a one-line draft, so he sees at once that the message
// comes from the app (SPEC §4.11b; owner, Oct 5: one button, a short draft, no version line).
import { t } from './i18n/index.svelte';
import { openLink } from './tg';

export const OWNER = 'Sowers';

export function writeOwner(): void {
  writeSupport(t('fb.draft'));
}

/** The same chat with a draft of the screen's own (e.g. DMP's list has me wrong, PLAN 95). */
export function writeSupport(draft: string): void {
  openLink(`https://t.me/${OWNER}?text=${encodeURIComponent(draft)}`);
}
