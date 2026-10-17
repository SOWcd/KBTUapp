import { describe, expect, it } from 'vitest';
import { fromHsl, shade } from './color';

describe('color', () => {
  it('turns hue, saturation and lightness into hex', () => {
    expect(fromHsl(0, 1, 0.5)).toBe('#ff0000');
    expect(fromHsl(1 / 3, 1, 0.5)).toBe('#00ff00');
    expect(fromHsl(2 / 3, 1, 0.25)).toBe('#000080');
  });
  it('shades like the server', () => expect(shade('#3B6BFF')).toBe('#2c50bf'));
});
