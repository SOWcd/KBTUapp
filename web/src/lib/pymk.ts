// People you may know on the Friends page (server logic/pymk.py). Add and the x move the card first (the speed rule):
// these say what the page becomes, so the screen and its test share one rule. The offer to turn it on, put off for
// SNOOZE days on this phone only (a convenience: the switch itself lives in Settings and on the server).
import type { FriendRow, Friends, Suggestion, Ts } from './api';

const KEY = 'kb-pymk-later', SNOOZE = 30 * 86400;

/** The card gone (dismissed, or added and so waiting for an answer); the next one moves up. */
export const without = (f: Friends, id: number): Friends => ({ ...f, suggest: f.suggest?.filter((s) => s.person.id !== id) ?? f.suggest });

/** Added: off the strip and into "Waiting for an answer", as any request I sent. */
export const asked = (f: Friends, s: Suggestion, at: Ts): Friends => {
  const row: FriendRow = { person: s.person, fullName: s.person.name, course: s.course, school: s.school, at };
  return { ...without(f, s.person.id), outgoing: [row, ...f.outgoing.filter((x) => x.person.id !== s.person.id)] };
};

/** Put back where it was when the server said no (only if it isn't there already: a later refresh may have it). */
export const restored = (f: Friends, s: Suggestion, at: number): Friends =>
  !f.suggest || f.suggest.some((x) => x.person.id === s.person.id) ? f
    : { ...f, suggest: [...f.suggest.slice(0, at), s, ...f.suggest.slice(at)], outgoing: f.outgoing.filter((x) => x.person.id !== s.person.id) };

/** Offer the switch now? Not while "Not now" holds. */
export const offerDue = (now: Ts): boolean => { try { return now - (Number(localStorage.getItem(KEY)) || 0) > SNOOZE; } catch { return true; } };
export const offerLater = (now: Ts): void => { try { localStorage.setItem(KEY, String(now)); } catch { /* blocked: asked again next time */ } };
