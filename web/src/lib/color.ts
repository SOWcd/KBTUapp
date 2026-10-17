/** Sheet tint from the poster colour: the same hue, a quarter darker (the server's logic.shade). */
export function shade(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  const c = (s: number) => Math.round(((n >> s) & 255) * 0.75).toString(16).padStart(2, '0');
  return '#' + c(16) + c(8) + c(0);
}

/** A cover's own colour (SPEC §4.8b): the most vivid hue around the photo's focus, read from a 32×32 copy, its
 *  lightness evened out so the tint reads in both themes. Null for a photo with hardly any colour (the dots stay). */
export async function coverColor(m: { url: string; focus?: [number, number] | null }): Promise<string | null> {
  const img = new Image();
  img.src = m.url;
  try { await img.decode(); } catch { return null; }
  const w = img.naturalWidth, h = img.naturalHeight, side = Math.min(w, h) * 0.6;
  const [fx, fy] = m.focus ?? [0.5, 0.5];
  const sx = Math.min(Math.max(fx * w - side / 2, 0), w - side), sy = Math.min(Math.max(fy * h - side / 2, 0), h - side);
  const cv = document.createElement('canvas');
  cv.width = cv.height = 32;
  const cx = cv.getContext('2d', { willReadFrequently: true });
  if (!cx || !side) return null;
  cx.drawImage(img, sx, sy, side, side, 0, 0, 32, 32);
  let px: Uint8ClampedArray;
  try { px = cx.getImageData(0, 0, 32, 32).data; } catch { return null; } // a photo from another origin
  // 24 hue bins; a pixel weighs its saturation, more so in the middle lightness; the heaviest bin's mean hue wins
  const bins = Array.from({ length: 24 }, () => ({ w: 0, x: 0, y: 0, s: 0 }));
  for (let i = 0; i < px.length; i += 4) {
    const [hu, s, l] = hsl(px[i], px[i + 1], px[i + 2]);
    if (s < 0.2 || l < 0.12 || l > 0.92) continue;
    const wt = s * (1 - Math.abs(l - 0.5)), b = bins[Math.floor(hu * 24) % 24];
    b.w += wt; b.x += Math.cos(hu * 2 * Math.PI) * wt; b.y += Math.sin(hu * 2 * Math.PI) * wt; b.s += s * wt;
  }
  const best = bins.reduce((a, b) => (b.w > a.w ? b : a));
  if (best.w < 8) return null;
  const hue = (Math.atan2(best.y, best.x) / (2 * Math.PI) + 1) % 1;
  return fromHsl(hue, Math.min(0.85, Math.max(0.55, best.s / best.w)), 0.56);
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
