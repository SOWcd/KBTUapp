// Team events' small decisions (server evteams.py), pure so the tests reach them.
import type { Key } from './i18n/index.svelte';

/** An invite link's Join by my sign-up: with a seat, join at once; none, sign up with the join; waiting for a seat
 *  (waitlist, a free event's hold) a team can't take me yet: say so and change nothing (toggleGoing would cancel the
 *  sign-up). A paid seat on hold: the join is kept until the receipt is in ('pay': join, then the payment sheet). */
export function inviteStep(status: string | null | undefined, paid = false): 'join' | 'signup' | 'noSeat' | 'pay' {
  return status === 'going' ? 'join' : status === 'hold' && paid ? 'pay' : status === 'waitlist' || status === 'hold' ? 'noSeat' : 'signup';
}

// a team's refusals, by the server's code and message; looked up before the generic "closed" and "full"
const ERR: Record<string, Key> = {
  'full/team_full': 'tm.full', 'conflict/name_taken': 'tm.nameTaken', 'bad_input/team_name': 'tm.nameBad', 'closed/not_going': 'tm.noSeat',
  'closed/locked': 'tm.locked', 'conflict/in_team': 'tm.inTeam', 'not_found/team_link': 'tm.dead',
  'forbidden/team_consent': 'tm.consentAgain', 'conflict/team_consent': 'tm.noConsentMove',
  'closed/pay_first': 'tm.payFirst', 'full/team_cap': 'tm.capFull', 'conflict/team_cap': 'ed.teamCapLow',
  'bad_input/team_seats': 'ed.teamSeats', 'conflict/team_paid': 'ed.teamPaid',
};
export const teamError = (code: string, message: string): Key | undefined => ERR[`${code}/${message}`];
