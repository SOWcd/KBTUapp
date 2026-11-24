import type { TextEntity } from './api/types';

type Kind = TextEntity[0];
type Mark = { kind: Kind; start: number; end: number; url?: string };
type Part = string | { mark: Mark; children: Part[]; text: string };

const order: Record<Kind, number> = {
  blockquote: 0, pre: 1, spoiler: 2, text_link: 3, url: 3,
  bold: 4, italic: 5, underline: 6, strike: 7, code: 8,
};

function link(raw: string, bare: boolean): string | undefined {
  const url = bare && !raw.includes('://') ? `https://${raw}` : raw;
  if (!/^https?:\/\//i.test(url)) return;
  try { return new URL(url).href; } catch { return undefined; }
}

/** Split at Telegram's UTF-16 boundaries, keeping common wrappers open across adjacent slices. */
export function richParts(text: string, entities: TextEntity[]): Part[] {
  const marks: Mark[] = [];
  for (const [kind, start, length, target] of entities) {
    const end = start + length;
    if (!Number.isInteger(start) || !Number.isInteger(length) || start < 0 || end > text.length || length <= 0) continue;
    if (kind === 'url' || kind === 'text_link') {
      const url = link(target ?? (kind === 'url' ? text.slice(start, end) : ''), kind === 'url');
      if (url) marks.push({ kind, start, end, url });
    } else if (Object.prototype.hasOwnProperty.call(order, kind)) {
      marks.push({ kind, start, end });
    }
  }
  if (!marks.length) return [text];
  marks.sort((a, b) => order[a.kind] - order[b.kind] || a.start - b.start || b.end - a.end);
  const points = [...new Set([0, text.length, ...marks.flatMap(({ start, end }) => [start, end])])].sort((a, b) => a - b);
  const parts: Part[] = [];
  const stack: Exclude<Part, string>[] = [];
  const children = () => stack.length ? stack[stack.length - 1].children : parts;
  // ponytail: scan the marks at each boundary on short posts; sweep sorted start/end events if larger posts warrant it.
  for (let i = 1; i < points.length; i++) {
    const start = points[i - 1], end = points[i];
    const active = marks.filter((m) => m.start <= start && m.end >= end);
    const firstLink = active.find((m) => m.url);
    const wrappers = active.filter((m) => !m.url || m === firstLink);
    let common = 0;
    while (common < wrappers.length && stack[common]?.mark === wrappers[common]) common++;
    stack.length = common;
    for (const mark of wrappers.slice(common)) {
      const part = { mark, children: [], text: '' };
      children().push(part);
      stack.push(part);
    }
    const slice = text.slice(start, end);
    children().push(slice);
    for (const part of stack) if (part.mark.kind === 'spoiler') part.text += slice;
  }
  return parts;
}
