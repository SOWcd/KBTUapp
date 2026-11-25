// The event page's "Links and documents" group: the addresses its description carries (a form, the rules on a site),
// each once, its host in sight. An event has no link list of its own: the organizers type them into the description.
import { linked } from './social';

export interface EventLink { url: string; host: string; rest: string }

const MAX = 6; // a description that is mostly links still gives a short group

/** `skip`: addresses the page already shows in a row of their own (the meeting, the sign-up outside, the chat) */
export function eventLinks(description: string | null | undefined, skip: (string | null | undefined)[] = []): EventLink[] {
  const shown = new Set(skip.filter((s): s is string => !!s).map(key));
  const out: EventLink[] = [];
  for (const p of linked(description ?? '')) {
    if (!p.url || out.length >= MAX) continue;
    let u: URL;
    try { u = new URL(p.url); } catch { continue; }
    if (u.protocol !== 'https:' && u.protocol !== 'http:') continue;
    if (u.username || u.password) continue; // user:pass@host hides the real host
    const k = key(p.url);
    if (shown.has(k)) continue;
    shown.add(k);
    out.push({ url: p.url, host: u.hostname.replace(/^www\./, ''), rest: path(u) }); // the page cuts it to one line
  }
  return out;
}

// the same address however typed: no scheme, www or trailing slash, the host in lower case
function key(url: string): string {
  return url.replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/+$/, '').replace(/^[^/?#]+/, (h) => h.toLowerCase());
}

function path(u: URL): string {
  const s = (u.pathname === '/' ? '' : u.pathname) + u.search;
  try { return decodeURI(s); } catch { return s; }
}
