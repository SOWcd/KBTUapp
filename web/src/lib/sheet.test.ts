import { describe, expect, it } from 'vitest';
import { guessColumns, isHeader, parseCsv, pickRows, readXlsx, SheetError } from './sheet';

const deflate = async (raw: Uint8Array): Promise<Uint8Array> =>
  new Uint8Array(await new Response(new Blob([raw as BlobPart]).stream().pipeThrough(new CompressionStream('deflate-raw'))).arrayBuffer());

/** A minimal zip (what Excel writes, without the extras): each file deflated or stored. */
async function zip(files: Record<string, string>, store = false): Promise<ArrayBuffer> {
  const enc = new TextEncoder();
  const parts: Uint8Array[] = [], central: Uint8Array[] = [];
  let off = 0;
  for (const [name, body] of Object.entries(files)) {
    const n = enc.encode(name), raw = enc.encode(body), data = store ? raw : await deflate(raw);
    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true); local.setUint16(8, store ? 0 : 8, true);
    local.setUint32(18, data.length, true); local.setUint32(22, raw.length, true); local.setUint16(26, n.length, true);
    const dir = new DataView(new ArrayBuffer(46));
    dir.setUint32(0, 0x02014b50, true); dir.setUint16(10, store ? 0 : 8, true);
    dir.setUint32(20, data.length, true); dir.setUint32(24, raw.length, true); dir.setUint16(28, n.length, true); dir.setUint32(42, off, true);
    parts.push(new Uint8Array(local.buffer), n, data);
    central.push(new Uint8Array(dir.buffer), n);
    off += 30 + n.length + data.length;
  }
  const size = central.reduce((s, x) => s + x.length, 0);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true); end.setUint16(10, Object.keys(files).length, true); end.setUint32(12, size, true); end.setUint32(16, off, true);
  const all = [...parts, ...central, new Uint8Array(end.buffer)];
  const out = new Uint8Array(all.reduce((s, x) => s + x.length, 0));
  let p = 0;
  for (const x of all) { out.set(x, p); p += x.length; }
  return out.buffer;
}

const BOOK = {
  'xl/workbook.xml': '<workbook xmlns:r="r"><sheets><sheet name="Guests" sheetId="1" r:id="rId3"/></sheets></workbook>',
  'xl/_rels/workbook.xml.rels': '<Relationships><Relationship Id="rId3" Target="worksheets/guests.xml"/></Relationships>',
  'xl/sharedStrings.xml': '<sst><si><t>\u0424\u0418\u041e</t></si><si><t>Student ID</t></si><si><r><t>Jane </t></r><r><t>Testov &amp; Co</t></r></si></sst>',
  'xl/worksheets/guests.xml': '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="D1" t="inlineStr"><is><t>18+</t></is></c></row>'
    + '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2" t="str"><f>"24B"&amp;"030001"</f><v>24B030001</v></c><c r="C2" s="1"/><c r="D2" t="b"><v>1</v></c></row>'
    + '<row r="3"><c r="A3"><v>=1+1</v></c></row><row r="4"/></sheetData></worksheet>',
};

describe('sheet', () => {
  it('reads CSV with quotes, newlines in quotes and a guessed separator', () => {
    expect(parseCsv('﻿name;id\r\n"Testov; Jane";24B030001\n"Two\nLines";""""\n\n')).toEqual([['name', 'id'], ['Testov; Jane', '24B030001'], ['Two\nLines', '"']]);
    expect(parseCsv('a,b,c\n1,2,3')).toEqual([['a', 'b', 'c'], ['1', '2', '3']]);
    expect(parseCsv('a\tb\n1\t2')).toEqual([['a', 'b'], ['1', '2']]);
  });

  it('reads the first sheet of an xlsx: shared and inline strings, formulas as their value, gaps kept', async () => {
    const want = [['\u0424\u0418\u041e', 'Student ID', '', '18+'], ['Jane Testov & Co', '24B030001', '', '1'], ['=1+1']];
    expect(await readXlsx(await zip(BOOK))).toEqual(want);
    expect(await readXlsx(await zip(BOOK, true))).toEqual(want);
  });

  it('refuses what is not a workbook', async () => {
    await expect(readXlsx(new TextEncoder().encode('PK nothing').buffer)).rejects.toBeInstanceOf(SheetError);
    await expect(readXlsx(await zip({ 'a.txt': 'x' }))).rejects.toBeInstanceOf(SheetError);
  });

  it('guesses the columns from the header in three languages', () => {
    expect(guessColumns(['\u0424\u0418\u041e', 'Student ID', '18+', 'Telegram', '\u041a\u043e\u043c\u0430\u043d\u0434\u0430']))
      .toEqual({ name: 0, sid: 1, adult: 2, username: 3, team: 4 });
    expect(guessColumns(['Team', 'Full name', 'Telegram username', 'Adult?'])).toEqual({ name: 1, sid: null, adult: 3, username: 2, team: 0 });
    expect(guessColumns(['\u0410\u0442\u044b-\u0436\u04e9\u043d\u0456', 'x'])).toMatchObject({ name: 0, sid: null });
    expect(isHeader(['Name', 'ID'])).toBe(true);
    expect(isHeader(['Jane Testov', '24B030001'])).toBe(false);
    expect(isHeader(['Jane Testov', 'x'])).toBe(false);
  });

  it('picks the server rows in its order', () => {
    expect(pickRows([['24B030001', ' Jane ', '@jt']], { name: 1, sid: 0, adult: null, username: 2, team: null }))
      .toEqual([['Jane', '24B030001', '', '@jt', '']]);
  });
});
