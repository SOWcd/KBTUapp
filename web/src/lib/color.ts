/** Sheet tint from the poster colour: the same hue, a quarter darker (the server's logic.shade). */
export function shade(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const c = (s: number) => Math.round(((n >> s) & 255) * 0.75).toString(16).padStart(2, '0');
  return '#' + c(16) + c(8) + c(0);
}

/** A picture read from a 32×32 copy of a square `part` of it around the focus. Null when it won't load or is from another origin. */
export async function sample(url: string, part = 1, [fx, fy]: [number, number] = [0.5, 0.5]): Promise<Uint8ClampedArray | null> {
  const img = new Image();
  img.src = url;
  try { await img.decode(); } catch { return null; }
  const w = img.naturalWidth, h = img.naturalHeight, side = Math.min(w, h) * part;
  const sx = Math.min(Math.max(fx * w - side / 2, 0), w - side), sy = Math.min(Math.max(fy * h - side / 2, 0), h - side);
  const cv = document.createElement('canvas');
  cv.width = cv.height = 32;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  if (!cx || !side) return null;
  cx.drawImage(img, sx, sy, side, side, 0, 0, 32, 32);
  try { return cx.getImageData(0, 0, 32, 32).data; } catch { return null; } // a photo from another origin
}

/** 24 hue bins, heaviest first; a pixel weighs its saturation, more so in the middle lightness; greys, black and white
 *  don't count. hue: the bin's mean, sat: its saturation evened out */
function hueBins(px: ArrayLike<number>) {
  const bins = Array.from({ length: 24 }, () => ({ w: 0, x: 0, y: 0, s: 0 }));
  for (let i = 0; i < px.length; i += 4) {
    const [hu, s, l] = hsl(px[i], px[i + 1], px[i + 2]);
    if (s < 0.2 || l < 0.12 || l > 0.92) continue;
    const wt = s * (1 - Math.abs(l - 0.5)), b = bins[Math.floor(hu * 24) % 24];
    b.w += wt; b.x += Math.cos(hu * 2 * Math.PI) * wt; b.y += Math.sin(hu * 2 * Math.PI) * wt; b.s += s * wt;
  }
  return bins.map((b) => ({ w: b.w, hue: (Math.atan2(b.y, b.x) / (2 * Math.PI) + 1) % 1, sat: Math.min(0.85, Math.max(0.55, b.s / b.w)) })).sort((a, b) => b.w - a.w);
}

/** A cover's own colour (SPEC §4.8b): the most vivid hue around the photo's focus, its lightness evened out so the tint
 *  reads in both themes. Null for a photo with hardly any colour (the dots stay). */
export async function coverColor(m: { url: string; focus?: [number, number] | null }): Promise<string | null> {
  const px = await sample(m.url, 0.6, m.focus ?? undefined);
  if (!px) return null;
  const best = hueBins(px)[0];
  return best.w < 8 ? null : fromHsl(best.hue, best.sat, 0.56);
}

/** WCAG relative luminance of '#rrggbb' */
export function luminance(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const c = (s: number) => { const v = ((n >> s) & 255) / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * c(16) + 0.7152 * c(8) + 0.0722 * c(0);
}

/** the hue, as light as white text still reads on it (4.5:1): yellow goes much darker than blue */
function deep(h: number, s: number): string {
  let l = 0.42, c: string;
  do { c = fromHsl(h, s, l); l -= 0.02; } while (luminance(c) > 0.18);
  return c;
}

/** A club's card from its logo's pixels: a gradient of its two main colours (one colour: that hue, turned a little and
 *  darker). Null when the logo is black, white or grey. */
export function logoGradient(px: ArrayLike<number>): string | null {
  const [a, ...rest] = hueBins(px);
  if (a.w < 8) return null;
  const apart = (h: number) => { const d = Math.abs(h - a.hue); return Math.min(d, 1 - d) > 0.1; };
  const b = rest.find((x) => x.w > a.w * 0.15 && apart(x.hue));
  return `linear-gradient(135deg,${deep(a.hue, a.sat)},${b ? deep(b.hue, b.sat) : shade(deep((a.hue + 0.05) % 1, a.sat))})`;
}

function hsl(r: number, g: number, b: number): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  if (!d) return [0, 0, l];
  const h = max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h / 6, d / (1 - Math.abs(2 * l - 1)), l];
}

export function fromHsl(h: number, s: number, l: number): string {
  const a = s * Math.min(l, 1 - l);
  const f = (n: number) => { const k = (n + h * 12) % 12; return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))).toString(16).padStart(2, '0'); };
  return '#' + f(0) + f(8) + f(4);
}
