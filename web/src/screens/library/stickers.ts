// The room's sticker sheet, drawn here (the app's font, the QR encoder the app has) as A4 pages at 150 dpi, six
// stickers a page with cut lines; the server only puts the pages together as a PDF into the bot's chat
// (server library.stickers). A sticker: the room, the table's label in big, its QR (the bare code, scannable only in the
// app), how to use it, the seats.
import qrcode from 'qrcode-generator';
import { t } from '../../lib/i18n/index.svelte';

const W = 1240, H = 1754, COLS = 2, ROWS = 3, MARGIN = 50;
const FONT = '"Inter Variable", system-ui, sans-serif';
const INK = '#111318', SOFT = '#6B7280', CUT = '#C9CDD4', ACCENT = '#3B6BFF';

export type StickerTable = { label: string; seats: number; code: string };

export async function stickerPages(room: string, tables: StickerTable[]): Promise<string[]> {
  await Promise.all(['400', '700', '800'].map((w) => document.fonts?.load(`${w} 40px ${FONT}`).catch(() => [])));
  const per = COLS * ROWS, pages: string[] = [];
  for (let p = 0; p < tables.length; p += per) {
    const canvas = document.createElement('canvas');
    canvas.width = W; canvas.height = H;
    const g = canvas.getContext('2d')!;
    g.fillStyle = '#FFFFFF'; g.fillRect(0, 0, W, H);
    const cw = (W - 2 * MARGIN) / COLS, ch = (H - 2 * MARGIN) / ROWS;
    tables.slice(p, p + per).forEach((tb, i) => sticker(g, MARGIN + (i % COLS) * cw, MARGIN + Math.floor(i / COLS) * ch, cw, ch, room, tb));
    pages.push(canvas.toDataURL('image/jpeg', 0.9));
  }
  return pages;
}

function sticker(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, room: string, tb: StickerTable) {
  g.save();
  g.setLineDash([10, 10]); g.strokeStyle = CUT; g.lineWidth = 2; g.strokeRect(x, y, w, h); g.setLineDash([]);
  const cx = x + w / 2;
  g.textAlign = 'center'; g.textBaseline = 'alphabetic';
  g.fillStyle = ACCENT; g.font = `800 26px ${FONT}`; g.fillText(fit(g, `KBTU App · ${room}`, w - 60), cx, y + 56);
  g.fillStyle = INK; g.font = `800 64px ${FONT}`; g.fillText(fit(g, t('lib.sticker.table', { table: tb.label }), w - 60), cx, y + 130);
  // the QR, its quiet zone kept: crisp whole-pixel modules
  const q = qrcode(0, 'M');
  q.addData(tb.code, 'Alphanumeric'); q.make();
  const n = q.getModuleCount(), cell = Math.floor(Math.min(w - 120, h - 300) / (n + 4)), size = cell * n;
  const qx = Math.round(cx - size / 2), qy = Math.round(y + 160 + 2 * cell);
  g.fillStyle = INK;
  for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) g.fillRect(qx + c * cell, qy + r * cell, cell, cell);
  const below = qy + size + 2 * cell + 40;
  g.fillStyle = INK; g.font = `700 26px ${FONT}`; g.fillText(fit(g, t('lib.sticker.how'), w - 60), cx, below);
  g.fillStyle = SOFT; g.font = `400 22px ${FONT}`; g.fillText(fit(g, t('lib.sticker.seats', { n: tb.seats }), w - 60), cx, below + 36);
  g.restore();
}

/** the text, cut with an ellipsis to the width (a long room name never runs past the cut line) */
function fit(g: CanvasRenderingContext2D, s: string, most: number): string {
  if (g.measureText(s).width <= most) return s;
  while (s.length > 1 && g.measureText(s + '…').width > most) s = s.slice(0, -1);
  return s + '…';
}
