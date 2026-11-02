import { describe, expect, it } from 'vitest';
import { check, priceIn, titleWithoutClub } from './eventCheck';

const ok = { title: 'Open Mic', description: 'Stand-up and music, come with friends.', paid: false, price: null, tba: false, place: 'Atrium',
  startTs: 2000, now: 1000, live: false, cover: true, seats: null };

describe('event check', () => {
  it('reads a price from the text', () => {
    expect(priceIn('\u0421\u0442\u043e\u0438\u043c\u043e\u0441\u0442\u044c 7 500 \u20b8 \u0441 \u0447\u0435\u043b\u043e\u0432\u0435\u043a\u0430')).toBe(7500);
    expect(priceIn('\u0432\u0437\u043d\u043e\u0441 7500\u0442\u0433')).toBe(7500);
    expect(priceIn('ticket 12.000 tenge')).toBe(12000);
    expect(priceIn('room 412, 2025 year')).toBeNull();
  });
  it('a clean event has nothing to say', () => expect(check(ok)).toEqual([]));
  it('the trip marked free while the text asks 7500', () => {
    expect(check({ ...ok, description: 'Trip to Shymbulak, 7500 \u20b8 for the bus' })[0]).toEqual({ id: 'priceText', n: 7500 });
    expect(check({ ...ok, description: 'Trip, 7500 tg', paid: true, price: 5000 })[0]).toEqual({ id: 'priceDiff', n: 7500 });
    expect(check({ ...ok, description: 'Trip to the mountains, 7500 tg', paid: true, price: 7500 })).toEqual([]);
  });
  it('gaps', () => {
    const ids = check({ ...ok, title: 'x'.repeat(60), description: '', tba: true, startTs: 500, cover: false }).map((f) => f.id);
    expect(ids).toEqual(['past', 'noPlace', 'noCover', 'noAbout', 'longTitle']);
    expect(check({ ...ok, description: 'Only 30 seats, sign up early' }).map((f) => f.id)).toEqual(['seatsText']);
  });
  it('takes the club out of the title', () => {
    const club = ['Big City Lights', 'BCL', 'BC'];
    expect(titleWithoutClub('TSS by BCL', club)).toBe('TSS');
    expect(titleWithoutClub('BCL | The Secret of Sin', club)).toBe('The Secret of Sin');
    expect(titleWithoutClub('Open Mic x KBTU', [])).toBe('Open Mic');
    expect(titleWithoutClub('BCLub night', club)).toBeNull();
    expect(titleWithoutClub('BCL', club)).toBeNull();
    expect(titleWithoutClub('Fox KBTU', [])).toBeNull();                        // no separator: a word, not "x KBTU"
    expect(titleWithoutClub('Big City Lights \u2014 Halloween', club)).toBe('Halloween');
    expect(check({ ...ok, title: 'TSS by BCL', club })).toEqual([{ id: 'clubInTitle', clean: 'TSS' }]);
  });
});
