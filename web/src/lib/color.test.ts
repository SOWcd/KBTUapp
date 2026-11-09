import { describe, expect, it } from 'vitest';
import { fromHsl, logoGradient, luminance, shade } from './color';

describe('color', () => {
  it('turns hue, saturation and lightness into hex', () => {
    expect(fromHsl(0, 1, 0.5)).toBe('#ff0000');
    expect(fromHsl(1 / 3, 1, 0.5)).toBe('#00ff00');
    expect(fromHsl(2 / 3, 1, 0.25)).toBe('#000080');
  });
  it('shades like the server', () => expect(shade('#3B6BFF')).toBe('#2c50bf'));
});

describe('logoGradient', () => {
  const fill = (...parts: [number, [number, number, number]][]) => parts.flatMap(([n, c]) => Array.from({ length: n }, () => [...c, 255])).flat();
  const WHITE: [number, number, number] = [255, 255, 255], BLACK: [number, number, number] = [0, 0, 0];
  const stops = (g: string | null) => g!.match(/#[0-9a-f]{6}/g)!;

  it('has nothing to say about a black, white or grey logo', () => {
    expect(logoGradient(fill([1024, WHITE]))).toBeNull();
    expect(logoGradient(fill([500, BLACK], [524, [128, 128, 128]]))).toBeNull();
  });
  it('mixes the two main colours, not the ground', () => {
    const [a, b] = stops(logoGradient(fill([700, WHITE], [200, [220, 30, 30]], [124, [30, 60, 220]])));
    expect(parseInt(a.slice(1, 3), 16)).toBeGreaterThan(parseInt(a.slice(5), 16)); // red first, the heavier one
    expect(parseInt(b.slice(5), 16)).toBeGreaterThan(parseInt(b.slice(1, 3), 16)); // then blue
  });
  it('keeps white text readable on a yellow logo', () => {
    for (const c of stops(logoGradient(fill([1024, [255, 225, 40]])))) expect(1.05 / (luminance(c) + 0.05)).toBeGreaterThanOrEqual(4.5);
  });
});
