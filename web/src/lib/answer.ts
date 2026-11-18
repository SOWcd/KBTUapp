// An assistant's answer as the server writes it (logic/assistant.py): the answer in the first line, a fact a line (some
// led by one emoji), the source last, alone in brackets. Split for drawing (screens/assistant): the emoji apart, so a
// wrapped line hangs beside it; the source apart, a caption without its brackets. Nothing else is touched.
export type AnswerLine = { e: string; t: string };

// one leading emoji with its tail (a keycap, a flag, a joined family, a skin tone), then the words
let LEAD: RegExp | null = null;
try {
  LEAD = new RegExp('^((?:[0-9#*]\\uFE0F?\\u20E3|\\p{Regional_Indicator}{2}|\\p{Extended_Pictographic})(?:[\\uFE0F\\u200D]|\\p{Emoji_Modifier}|\\p{Extended_Pictographic})*)\\s*(\\S.*)$', 'u');
} catch { /* an engine without Unicode properties: the line stays whole */ }

/** the whole line is one bracketed group: "(Handbook (2026), p. 3)" yes; "(a) and (b)" or "see (p. 3)" no */
function bracketed(s: string): boolean {
  if (!s.startsWith('(') || !s.endsWith(')')) return false;
  let depth = 0;
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '(') depth++;
    else if (s[i] === ')' && --depth === 0 && i < s.length - 1) return false;
  }
  return depth === 0;
}

export function answer(text: string): { lines: AnswerLine[]; source: string } {
  const rows = text.split('\n').map((r) => r.trim()).filter(Boolean);
  // an answer of one line is the answer, whatever its brackets
  const source = rows.length > 1 && bracketed(rows[rows.length - 1]) ? rows.pop()!.slice(1, -1).trim() : '';
  return { source, lines: rows.map((r) => { const m = LEAD?.exec(r); return m ? { e: m[1], t: m[2] } : { e: '', t: r }; }) };
}
