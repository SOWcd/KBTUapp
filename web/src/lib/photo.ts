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
