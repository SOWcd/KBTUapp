// A forum post's text rules as you type (ChannelCompose, ChannelReply): the server's own (server logic/fchannel.py
// _clean, LINKY, _long_number), mirrored. The server still decides; this only says it at the spot before Publish.
// Python's \w, \d and \b are Unicode, JavaScript's ASCII: here \p{L}\p{N} stand in, and "(?:^|[^...])" for a leading \b
// (no lookbehind: old iOS). The cases both sides must agree on: server/tests/fchannel_rules.json.
export type Rule = 'link' | 'mention' | 'phone' | 'signature';

const W = '\\p{L}\\p{N}_', B = `(?:^|[^${W}])`, E = `(?![${W}])`;
const CYR_TLD = 'рф|рус|онлайн|сайт|орг|ком|москва|қаз|бел|укр|срб|дети';
const LINK = new RegExp(`${B}[a-z][a-z0-9+.-]*://|${B}www\\.|${B}[\\p{L}\\p{N}][${W}-]*(?:\\.[\\p{L}\\p{N}][${W}-]*)*\\.(?:[a-z]{2,}|${CYR_TLD})${E}`, 'iu');
const MENTION = new RegExp(`@[${W}]{3,}`, 'u');
const PHONE = new RegExp(`\\+\\p{Nd}[\\p{Nd}\\s().-]{7,}\\p{Nd}|${B}[78][\\s(.-]*\\p{Nd}{3}[\\s).-]*\\p{Nd}{3}[\\s.-]*\\p{Nd}{2}[\\s.-]*\\p{Nd}{2}${E}`, 'u');
const DIGITS = /\p{Nd}(?:[\s-]?\p{Nd}){9,}/gu;
const SUM = /^[1-9]\p{Nd}{0,2}(?:\s\p{Nd}{3})*\s\p{Nd}00$/u;
const MONEY = /^\s*(?:\u20b8|\u0442\u0433|\u0442\u0435\u043d\u0433|tg(?![\p{L}\p{N}_])|kzt(?![\p{L}\p{N}_]))/iu; // tenge right after it
const SIGNED = /^[\p{Pd}−─━➖ー]/u;
const HIDDEN = /[\p{Cf}\p{Co}\p{Cn}͏ᅟᅠㅤﾠ\u{e0100}-\u{e01ef}]/gu; // the server's invisible ones (_visible)

// a run of ten digits or more, unless a price: one round sum or a range of two, each under ten digits, 12 in all, tenge after it
const longNumber = (s: string) => [...s.matchAll(DIGITS)].some((m) => {
  const parts = m[0].split('-');
  return !(parts.length <= 2 && m[0].replace(/\D/g, '').length <= 12 && parts.every((x) => SUM.test(x) && x.replace(/\D/g, '').length < 10) && MONEY.test(s.slice(m.index + m[0].length)));
});
// the line breaks Python's splitlines() knows (the server's _clean joins the lines on them)
const LINES = /\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/;

/** The first rule the words break, or null. */
export function broken(raw: string): Rule | null {
  const s = raw.replace(/‍/g, '').replace(HIDDEN, '').trim();
  const seen = s.normalize('NFKC').replace(/[。｡．]/g, '.');
  if (LINK.test(seen)) return 'link';
  if (MENTION.test(seen)) return 'mention';
  if (PHONE.test(seen) || longNumber(seen)) return 'phone';
  const lines = s.split(LINES).map((l) => l.trimEnd());
  const last = lines.length > 1 ? lines[lines.length - 1].normalize('NFKC').trimStart() : '';
  return last && SIGNED.test(last) ? 'signature' : null;
}
