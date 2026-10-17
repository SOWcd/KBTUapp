// Kazakhstan phone numbers as people read them, "+7 701 234 56 78" (owner, Oct 11: the editor showed "77012345678"),
// from whatever is typed, pasted or autofilled: iOS gives "8 (701) 234-56-78", the server keeps "+77012345678".

/** The formatted number; the field's own "+7" and a trunk 8 never count as digits of the number. */
export function fmtPhone(v: string): string {
  let d = v.trim().replace(/^\+7/, '').replace(/\D/g, '');
  if (d.length > 10) d = d.slice(-10);   // 8 or 7 in front of the ten digits
  else if (d[0] === '8') d = d.slice(1); // a number itself never starts with 8: the trunk prefix, typed first
  if (!d) return '';
  return '+7 ' + [d.slice(0, 3), d.slice(3, 6), d.slice(6, 8), d.slice(8, 10)].filter(Boolean).join(' ');
}
