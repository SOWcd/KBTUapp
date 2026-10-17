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
