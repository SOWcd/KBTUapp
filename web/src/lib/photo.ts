import type { CoverFormat } from './api/types';

// A phone photo shrunk before it leaves the phone: longest side 2000 px, JPEG. Seconds less on mobile
// internet and no EXIF (the GPS spot) on the wire; the server re-encodes it anyway (server/kbtu/media.py).
export async function shrink(file: Blob, side = 2000, quality = 0.88): Promise<Blob> {
  try {
    const bmp = await createImageBitmap(file); // applies the EXIF rotation
    try { return await drawJpeg(bmp, bmp.width, bmp.height, side, quality); }
    finally { bmp.close(); }
  } catch {
    return file; // an old webview without createImageBitmap: the server copes with the original
  }
}

/** The Gallery always sends a fresh JPEG. Older webviews can decode via a local image URL. */
export async function galleryJpeg(file: Blob, url: string): Promise<Blob> {
  let jpeg = await shrink(file);
  if (jpeg === file) {
    const img = new Image();
    await new Promise<void>((done, fail) => { img.onload = () => done(); img.onerror = fail; img.src = url; });
    jpeg = await drawJpeg(img, img.naturalWidth, img.naturalHeight, 2000, 0.88);
  }
  return cleanCanvasJpeg(jpeg);
}

// The browser can add its own metadata, such as an ICC profile. Drop APP segments and comments from the canvas header.
async function cleanCanvasJpeg(jpeg: Blob): Promise<Blob> {
  const bytes = new Uint8Array(await jpeg.arrayBuffer());
  const parts: Blob[] = [];
  let start = 0, i = 2;
  if (bytes[0] === 0xff && bytes[1] === 0xd8) {
    while (i + 3 < bytes.length && bytes[i] === 0xff) {
      const offset = i++;
      while (bytes[i] === 0xff) i++;
      const marker = bytes[i++];
      const length = bytes[i] * 256 + bytes[i + 1];
      const end = i + length;
      if (length < 2 || end > bytes.length) break;
      if (marker === 0xda) return parts.length ? new Blob([...parts, jpeg.slice(start)], { type: 'image/jpeg' }) : jpeg;
      if ((marker >= 0xe0 && marker <= 0xef) || marker === 0xfe) {
        parts.push(jpeg.slice(start, offset));
        start = end;
      }
      i = end;
    }
  }
  throw new Error('JPEG header');
}

function drawJpeg(source: CanvasImageSource, width: number, height: number, side: number, quality: number): Promise<Blob> {
  const k = Math.min(1, side / Math.max(width, height));
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(width * k)); c.height = Math.max(1, Math.round(height * k));
  const g = c.getContext('2d')!;
  g.fillStyle = '#fff'; g.fillRect(0, 0, c.width, c.height); // a transparent PNG turns white in the JPEG
  g.drawImage(source, 0, 0, c.width, c.height);
  return new Promise<Blob>((done, fail) => c.toBlob((b) => (b?.type === 'image/jpeg' ? done(b) : fail(new Error('JPEG encode'))), 'image/jpeg', quality));
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
 *  (edges weigh, flat sky and walls don't). A flat picture: the middle.
 *  ponytail: edge energy, not faces; the Shape Detection API's FaceDetector where it exists is the upgrade. */
export function smartFocus(px: ArrayLike<number>, n = 32): [number, number] {
  const lum = (i: number) => px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114;
  let sum = 0, sx = 0, sy = 0;
  for (let y = 1; y < n - 1; y++) for (let x = 1; x < n - 1; x++) {
    const i = y * n + x, e = Math.abs(lum(i + 1) - lum(i - 1)) + Math.abs(lum(i + n) - lum(i - n));
    sum += e; sx += e * x; sy += e * y;
  }
  if (sum < n * n) return [0.5, 0.5]; // under one grey level a pixel: nothing to aim at
  return [unit(sx / sum / (n - 1)), unit(sy / sum / (n - 1))];
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
