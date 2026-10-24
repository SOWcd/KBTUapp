import { describe, it, expect } from 'vitest';
import { liftRush } from './route';

describe('liftRush', () => {
  it('weekday breaks between classes only', () => {
    expect(liftRush(new Date(2026, 9, 21, 10, 50))).toBe(true);  // Wednesday 10:50
    expect(liftRush(new Date(2026, 9, 21, 11, 2))).toBe(true);
    expect(liftRush(new Date(2026, 9, 21, 11, 20))).toBe(false);
    expect(liftRush(new Date(2026, 9, 21, 22, 50))).toBe(false); // night
    expect(liftRush(new Date(2026, 9, 24, 18, 50))).toBe(false); // Saturday evening (the owner's screenshot)
    expect(liftRush(new Date(2026, 9, 25, 10, 50))).toBe(false); // Sunday
  });
});
