// "Write to the creator": opens the owner's Telegram DM with a one-line draft, so he sees at once that the message
// comes from the app (SPEC §4.11b; one button, a short draft, no version line).
import { openLink } from './tg';

export const OWNER = 'Sowers';
/** the app's open code (Profile's GitHub row, the end of People of the app) */
export const CODE = 'https://github.com/SOWcd/KBTUapp';

/** The same chat with a draft of the screen's own (e.g. DMP's list has me wrong, PLAN 95). */
export function writeSupport(draft: string): void {
  openLink(`https://t.me/${OWNER}?text=${encodeURIComponent(draft)}`);
}
