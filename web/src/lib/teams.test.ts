import { expect, it } from 'vitest';
import { inviteStep, teamError } from './teams';

it("an invite's Join never cancels a sign-up waiting for a seat", () => {
  expect(inviteStep('going')).toBe('join');
  expect(inviteStep('waitlist')).toBe('noSeat');
  expect(inviteStep('hold')).toBe('noSeat');
  for (const s of [undefined, null, 'cancelled']) expect(inviteStep(s)).toBe('signup');
});

it("a team's refusal says its own words, not the event's", () => {
  expect(teamError('full', 'team_full')).toBe('tm.full');
  expect(teamError('closed', 'not_going')).toBe('tm.noSeat');
  expect(teamError('closed', 'locked')).toBe('tm.locked');
  expect(teamError('not_found', 'team_link')).toBe('tm.dead');
  expect(teamError('full', 'full')).toBeUndefined();
  expect(teamError('bad_input', 'name')).toBeUndefined(); // a club's name, not a team's
});
