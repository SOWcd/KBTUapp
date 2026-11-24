import type { CoverFormat } from './api/types';

// A phone photo shrunk before it leaves the phone: longest side 2000 px, JPEG. Seconds less on mobile
// internet and no EXIF (the GPS spot) on the wire; the server re-encodes it anyway (server/kbtu/media.py).
export async function shrink(file: Blob, side = 2000, quality = 0.88): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(file); // applies the EXIF rotation
    const k = Math.min(1, side / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    const g = c.getContext('2d')!;
    g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); // a transparent PNG (a logo) turns white in the JPEG, not black
    g.drawImage(bmp, 0, 0, c.width, c.height);
    bmp.close();
    return await new Promise<Blob>((done, fail) => c.toBlob((b) => (b ? done(b) : fail(new Error('toBlob'))), 'image/jpeg', quality));
  } catch {
    return file; // an old webview without createImageBitmap: the server copes with the original
  }
}

/** CSS object-position for a cover's focus (the point every frame keeps in view); '' = the middle. */
export const focusPos = (m: { focus?: [number, number] | null } | null | undefined): string =>
  m?.focus ? `${m.focus[0] * 100}% ${m.focus[1] * 100}%` : '';

type Framed = { focus?: [number, number] | null; formats?: Partial<Record<CoverFormat, object>> };
/** An event's cover as one format shows it: that format's own photo or its own crop over the one cover. */
export function coverFor<M extends Framed>(cover: M | null | undefined, fmt: CoverFormat): M | null {
  const own = cover?.formats?.[fmt];
  return cover ? (own ? { ...cover, ...own } : cover) : null;
}

const unit = (v: number) => Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000;
/** A photo dragged (dx, dy) screen px inside a frame it covers: its new focus. The photo follows the finger and stops at
 *  its edges; along the side that fits the frame exactly there is nowhere to go. */
export function panFocus(focus: [number, number] | null | undefined, dx: number, dy: number, photo: { w: number; h: number }, frame: { w: number; h: number }): [number, number] {
  const s = Math.max(frame.w / photo.w, frame.h / photo.h), ox = photo.w * s - frame.w, oy = photo.h * s - frame.h;
  const [x, y] = focus ?? [0.5, 0.5];
  return [unit(ox > 0.5 ? x - dx / ox : x), unit(oy > 0.5 ? y - dy / oy : y)];
}

/** Where a photo's subject most likely is, from an n x n RGBA thumbnail of the whole photo: the centre of its detail
 *  (edges weigh, flat sky and walls don't), held a little toward the middle. A flat picture: the middle.
 *  ponytail: edge energy, not faces; the Shape Detection API's FaceDetector where it exists is the upgrade. */
export function smartFocus(px: ArrayLike<number>, n = 32): [number, number] {
  const lum = (i: number) => px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114;
  let sum = 0, sx = 0, sy = 0;
  for (let y = 1; y < n - 1; y++) for (let x = 1; x < n - 1; x++) {
    const i = y * n + x, e = Math.abs(lum(i + 1) - lum(i - 1)) + Math.abs(lum(i + n) - lum(i - n));
    sum += e; sx += e * x; sy += e * y;
  }
  if (sum < n * n) return [0.5, 0.5]; // under one grey level a pixel: nothing to aim at
  const pull = (v: number) => unit(0.5 + (v / (n - 1) - 0.5) * 0.8);
  return [pull(sx / sum), pull(sy / sum)];
}

/** smartFocus of a photo by its address; the middle when it can't be read. */
export async function autoFocus(url: string): Promise<[number, number]> {
  const img = new Image();
  img.src = url;
  try {
    await img.decode();
    const cv = document.createElement('canvas');
    cv.width = cv.height = 32;
    const cx = cv.getContext('2d', { willReadFrequently: true })!;
    cx.drawImage(img, 0, 0, 32, 32); // the whole photo squeezed into the square: the answer is in shares of each side
    return smartFocus(cx.getImageData(0, 0, 32, 32).data);
  } catch { return [0.5, 0.5]; }
}
