import type { BracketMatch, EventBracket, Id } from './api/types';

export const stages = ['upper', 'lower', 'final'] as const;

// The API lists feeder rounds before their destinations. Walk back once so even a bye between
// an old result and a later played match locks the old result (server evbracket._check_dependents).
export function lockedMatches(board: EventBracket): Set<Id> {
  const locked = new Set<Id>(), playedOrLocked = new Set<Id>();
  const matches = stages.flatMap((stage) => board[stage].flatMap((round) => round.matches));
  for (const match of matches.reverse()) {
    if ((match.next_win !== null && playedOrLocked.has(match.next_win)) ||
        (match.next_lose !== null && playedOrLocked.has(match.next_lose))) locked.add(match.id);
    if (locked.has(match.id) || match.status === 'played') playedOrLocked.add(match.id);
  }
  return locked;
}

export function scoreNumber(text: string): number | null {
  const n = Number(text);
  return /^\d+$/.test(text) && Number.isSafeInteger(n) ? n : null;
}

export function editableMatch(match: BracketMatch, locked: Set<Id>): boolean {
  return (match.status === 'ready' || match.status === 'played') && !locked.has(match.id);
}
