// The organizers' spreadsheet in the browser (Studio's guest list): a .csv, or an .xlsx read here with no library
// (an .xlsx is a zip of XML files: the zip's directory, the browser's own inflate, DOMParser). Only the first sheet and
// cell values (text, numbers, booleans); formulas come as their last saved value, never run.
// ponytail: no zip64 or encrypted workbooks (an organizer's list is far below 4 GB; Excel's password-protected file
// says "save as CSV"); a webview without DecompressionStream (iOS before 16.4) gets the same hint.

export const MAX_FILE = 5 * 1024 * 1024;

export class SheetError extends Error {}

/** CSV by RFC 4180: quotes, doubled quotes, newlines inside quotes; the separator guessed from the first line (; , or tab). */
export function parseCsv(text: string): string[][] {
  text = text.replace(/^﻿/, '');
  const first = text.slice(0, text.search(/\r?\n|$/));
  const sep = [';', '\t', ','].map((s) => [s, first.split(s).length] as const).sort((a, b) => b[1] - a[1])[0][0];
  const out: string[][] = [];
  let row: string[] = [], cell = '', quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"' && cell === '') quoted = true;
    else if (ch === sep) { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); out.push(row); row = []; cell = '';
    } else cell += ch;
  }
  if (cell !== '' || row.length) { row.push(cell); out.push(row); }
  return out.filter((r) => r.some((c) => c.trim()));
}

/** The zip's files by name, each inflated on demand (stored or deflated). */
function unzip(buf: ArrayBuffer): Map<string, () => Promise<Uint8Array>> {
  const v = new DataView(buf), b = new Uint8Array(buf);
  let end = -1;
  for (let i = b.length - 22; i >= Math.max(0, b.length - 22 - 65535); i--) if (v.getUint32(i, true) === 0x06054b50) { end = i; break; }
  if (end < 0) throw new SheetError('zip');
  const files = new Map<string, () => Promise<Uint8Array>>();
  const n = v.getUint16(end + 10, true);
  let p = v.getUint32(end + 16, true);
  const dec = new TextDecoder();
  for (let k = 0; k < n; k++) {
    if (p + 46 > b.length || v.getUint32(p, true) !== 0x02014b50) throw new SheetError('zip');
    const flags = v.getUint16(p + 8, true), method = v.getUint16(p + 10, true), size = v.getUint32(p + 20, true);
    const nameLen = v.getUint16(p + 28, true), extra = v.getUint16(p + 30, true), comment = v.getUint16(p + 32, true);
    const local = v.getUint32(p + 42, true);
    const name = dec.decode(b.subarray(p + 46, p + 46 + nameLen));
    p += 46 + nameLen + extra + comment;
    if (flags & 1) throw new SheetError('encrypted');
    files.set(name, async () => {
      const start = local + 30 + v.getUint16(local + 26, true) + v.getUint16(local + 28, true);
      const raw = b.subarray(start, start + size);
      if (method === 0) return raw;
      if (method !== 8 || typeof DecompressionStream === 'undefined') throw new SheetError('inflate');
      const stream = new Blob([raw]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    });
  }
  return files;
}

const text = async (files: Map<string, () => Promise<Uint8Array>>, name: string): Promise<string | null> => {
  const f = files.get(name);
  return f ? new TextDecoder().decode(await f()) : null;
};
// Excel's XML is regular enough for patterns (and they run in tests, where there is no DOMParser); a tag by its local
// name, with or without a namespace prefix
const tags = (src: string, tag: string): { attrs: string; body: string }[] =>
  [...src.matchAll(new RegExp(`<(?:[\\w.-]+:)?${tag}\\b([^>]*?)(?:/>|>([\\s\\S]*?)</(?:[\\w.-]+:)?${tag}>)`, 'g'))].map((m) => ({ attrs: m[1], body: m[2] ?? '' }));
const attr = (attrs: string, name: string): string | null => attrs.match(new RegExp(`(?:^|\\s)${name}="([^"]*)"`))?.[1] ?? null;
const unxml = (s: string): string => s.replace(/&(#x[0-9a-f]+|#[0-9]+|amp|lt|gt|quot|apos);/gi, (_, e: string) =>
  e[0] === '#' ? String.fromCodePoint(parseInt(e[1] === 'x' || e[1] === 'X' ? e.slice(2) : e.slice(1), e[1] === 'x' || e[1] === 'X' ? 16 : 10))
    : ({ amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" } as Record<string, string>)[e.toLowerCase()]);
const texts = (body: string): string => tags(body, 't').map((x) => unxml(x.body)).join('');
const col = (ref: string): number => { let n = 0; for (const ch of ref.replace(/[0-9]+$/, '')) n = n * 26 + ch.charCodeAt(0) - 64; return n - 1; };

/** The first sheet of an .xlsx as rows of text. */
export async function readXlsx(buf: ArrayBuffer): Promise<string[][]> {
  const files = unzip(buf);
  const book = await text(files, 'xl/workbook.xml');
  const rels = await text(files, 'xl/_rels/workbook.xml.rels');
  const first = book ? tags(book, 'sheet')[0] : undefined;
  const rid = first && (attr(first.attrs, 'r:id') ?? attr(first.attrs, 'id'));
  const rel = rels && rid ? tags(rels, 'Relationship').find((r) => attr(r.attrs, 'Id') === rid) : undefined;
  const target = rel && attr(rel.attrs, 'Target');
  const path = target ? (target.startsWith('/') ? target.slice(1) : 'xl/' + target) : 'xl/worksheets/sheet1.xml';
  const sheet = await text(files, path);
  if (sheet == null) throw new SheetError('sheet');
  const sst = await text(files, 'xl/sharedStrings.xml');
  const shared = sst ? tags(sst, 'si').map((si) => texts(si.body)) : [];
  const out: string[][] = [];
  for (const r of tags(sheet, 'row')) {
    const row: string[] = [];
    for (const c of tags(r.body, 'c')) {
      const ref = attr(c.attrs, 'r');
      const at = ref ? col(ref) : row.length;
      const type = attr(c.attrs, 't');
      const v = unxml(tags(c.body, 'v')[0]?.body ?? '');
      const val = type === 's' ? shared[Number(v)] ?? '' : type === 'inlineStr' ? texts(c.body) : type === 'b' ? (v === '1' ? '1' : '0') : v;
      if (at > 16384) continue; // past Excel's last column: a broken file
      while (row.length < at) row.push('');
      row[at] = val;
    }
    if (row.some((x) => x.trim())) out.push(row);
  }
  return out;
}

/** A picked file as rows: .xlsx read here, anything else as CSV text. */
export async function readSheet(file: File): Promise<string[][]> {
  if (file.size > MAX_FILE) throw new SheetError('big');
  const buf = await file.arrayBuffer();
  const b = new Uint8Array(buf, 0, Math.min(4, buf.byteLength));
  if (b[0] === 0x50 && b[1] === 0x4b) return readXlsx(buf); // "PK": a zip, so an .xlsx whatever its name
  if (b[0] === 0xd0 && b[1] === 0xcf) throw new SheetError('xls'); // the old binary .xls
  return parseCsv(new TextDecoder().decode(buf));
}

export const FIELDS = ['name', 'sid', 'adult', 'username', 'team'] as const;
export type Field = (typeof FIELDS)[number];
export type Columns = Record<Field, number | null>;

// header words in the three languages and as people type them (lowercase, no spaces; Cyrillic escaped: code stays ASCII)
const WORDS: Record<Field, string[]> = {
  name: ['\u0444\u0438\u043e', '\u0438\u043c\u044f', 'name', 'fullname', '\u0430\u0442\u044b', '\u0430\u0442\u044b\u0436\u04e9\u043d\u0456', '\u0442\u0435\u0433\u0456\u0430\u0442\u044b', '\u0444\u0430\u043c\u0438\u043b\u0438\u044f', '\u0443\u0447\u0430\u0441\u0442\u043d\u0438\u043a', '\u0441\u0442\u0443\u0434\u0435\u043d\u0442', 'student', 'guest', '\u0433\u043e\u0441\u0442\u044c'],
  sid: ['studentid', 'id', 'id\u0441\u0442\u0443\u0434\u0435\u043d\u0442\u0430', '\u0441\u0442\u0443\u0434\u0435\u043d\u0447\u0435\u0441\u043a\u0438\u0439', '\u0441\u0442\u0443\u0434\u0435\u043d\u0442id', '\u0441\u0442\u0443\u0434.id', '\u043d\u043e\u043c\u0435\u0440\u0441\u0442\u0443\u0434\u0435\u043d\u0442\u0430', 'student_id', 'barcode', '\u0430\u0439\u0434\u0438'],
  adult: ['18+', '18', 'adult', '\u0441\u043e\u0432\u0435\u0440\u0448\u0435\u043d\u043d\u043e\u043b\u0435\u0442\u043d\u0438\u0439', '\u0432\u043e\u0437\u0440\u0430\u0441\u0442', 'age', '\u043a\u04d9\u043c\u0435\u043b\u0435\u0442', '\u0436\u0430\u0441'],
  username: ['telegram', 'tg', 'username', '\u0442\u0435\u043b\u0435\u0433\u0440\u0430\u043c', '\u043d\u0438\u043a', 'nick', '\u044e\u0437\u0435\u0440\u043d\u0435\u0439\u043c', 'tg_username', '\u0442\u0435\u043b\u0435\u0433\u0440\u0430\u043c\u043c'],
  team: ['team', '\u043a\u043e\u043c\u0430\u043d\u0434\u0430', '\u0433\u0440\u0443\u043f\u043f\u0430', 'group', '\u0442\u043e\u043f', '\u043e\u0442\u0440\u044f\u0434', '\u0444\u0430\u043a\u0443\u043b\u044c\u0442\u0435\u0442'],
};

/** The header row's best guess: an exact word first, then a header that contains one; each column used once. */
export function guessColumns(header: string[]): Columns {
  const norm = header.map((h) => h.toLowerCase().replace(/[\s\-–—:№#]+/g, ''));
  const out = { name: null, sid: null, adult: null, username: null, team: null } as Columns;
  const used = new Set<number>();
  const pick = (f: Field, test: (h: string, w: string) => boolean) => {
    if (out[f] != null) return;
    const i = norm.findIndex((h, k) => !used.has(k) && h && WORDS[f].some((w) => test(h, w)));
    if (i >= 0) { out[f] = i; used.add(i); }
  };
  for (const f of FIELDS) pick(f, (h, w) => h === w);
  for (const f of ['username', 'sid', 'adult', 'team', 'name'] as Field[]) pick(f, (h, w) => w.length > 2 && h.includes(w));
  return out;
}

/** Whether the first row is a header: it names at least one column, and has no student ID in it. */
export const isHeader = (row: string[]): boolean =>
  Object.values(guessColumns(row)).some((x) => x != null) && !row.some((c) => /^[0-9]{2}([A-Za-z][0-9]{5,7}|[A-Za-z]{2}[0-9]{4,7})$/.test(c.trim()));

/** The rows the server takes: [name, student ID, 18+, username, team]. */
export const pickRows = (rows: string[][], cols: Columns): string[][] =>
  rows.map((r) => FIELDS.map((f) => (cols[f] == null ? '' : (r[cols[f]!] ?? '').trim())));
