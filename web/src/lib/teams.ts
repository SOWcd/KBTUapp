// Team events' small decisions (server evteams.py), pure so the tests reach them.
import type { Key } from './i18n/index.svelte';

/** An invite link's Join by my sign-up: with a seat, join at once; none, sign up with the join; waiting for a seat
 *  (waitlist, hold) a team can't take me yet: say so and change nothing (toggleGoing would cancel the sign-up) */
export function inviteStep(status: string | null | undefined): 'join' | 'signup' | 'noSeat' {
  return status === 'going' ? 'join' : status === 'waitlist' || status === 'hold' ? 'noSeat' : 'signup';
}

// a team's refusals, by the server's code and message; looked up before the generic "closed" and "full"
const ERR: Record<string, Key> = {
  'full/team_full': 'tm.full', 'conflict/name_taken': 'tm.nameTaken', 'bad_input/team_name': 'tm.nameBad', 'closed/not_going': 'tm.noSeat',
  'closed/locked': 'tm.locked', 'conflict/in_team': 'tm.inTeam', 'not_found/team_link': 'tm.dead',
  'forbidden/team_consent': 'tm.consentAgain', 'conflict/team_consent': 'tm.noConsentMove',
};
export const teamError = (code: string, message: string): Key | undefined => ERR[`${code}/${message}`];
