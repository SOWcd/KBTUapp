import { describe, expect, it } from 'vitest';
import type { BracketMatch, EventBracket } from './api/types';
import { editableMatch, lockedMatches, scoreNumber } from './bracket';

describe('bracket scoring', () => {
  it('locks both feed paths through byes, and unlocks them when the downstream score is cleared', () => {
    const opening: BracketMatch = {
      id: 1, stage: 'upper', round: 1, slot: 1, home: 10, away: 11, home_score: 1, away_score: 0,
      played_at: 1, winner: 10, status: 'played', next_win: 4, next_lose: 2,
    };
    const bye: BracketMatch = { ...opening, id: 2, stage: 'lower', away: null, winner: 11, home: 11,
      status: 'bye', home_score: null, away_score: null, played_at: null, next_win: 3, next_lose: null };
    const lower: BracketMatch = { ...opening, id: 3, stage: 'lower', round: 2, next_win: 4, next_lose: null };
    const final: BracketMatch = { ...lower, id: 4, stage: 'final', round: 1, status: 'pending',
      away: null, home_score: null, away_score: null, winner: null, played_at: null, next_win: null };
    const board: EventBracket = { upper: [{ round: 1, matches: [opening] }],
      lower: [{ round: 1, matches: [bye] }, { round: 2, matches: [lower] }],
      final: [{ round: 1, matches: [final] }], teams: [], winner: null };
    expect(lockedMatches(board)).toEqual(new Set([opening.id, bye.id]));
    expect(editableMatch(lower, lockedMatches(board))).toBe(true);
    expect(editableMatch(final, lockedMatches(board))).toBe(false);
    board.lower[1].matches[0] = { ...lower, status: 'ready', home_score: null, away_score: null, winner: null, played_at: null };
    expect(lockedMatches(board).size).toBe(0);
    expect(editableMatch(bye, lockedMatches(board))).toBe(false);
    board.final[0].matches[0] = { ...final, status: 'played', home_score: 1, away_score: 0 };
    expect(lockedMatches(board)).toContain(lower.id);
    expect(lockedMatches(board)).toContain(opening.id);
  });

  it('accepts zero and exactly representable scores, and rejects empty, fractional or rounded input', () => {
    expect(scoreNumber('0')).toBe(0);
    expect(scoreNumber('9007199254740991')).toBe(Number.MAX_SAFE_INTEGER);
    for (const text of ['', ' ', '-1', '1.5', '1e2', '9007199254740992']) expect(scoreNumber(text)).toBeNull();
  });
});
