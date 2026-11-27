// The applicant's own calls (server logic/ako.py): no account and no Telegram. The secret in /ako/<secret> is the
// credential, sent as X-Ako (never in an API path or query: no log or Referer carries it). Only the /ako screen's chunk
// imports this; the team's calls are in client.ts (api.ako*).
import { ApiErr } from './errors';
import type { AkoStart, AkoView, AkoFile, AkoDoc, ApiError, Id } from './types';

const code = (d: Record<string, unknown> | null) => (d?.error ?? 'unavailable') as ApiError['error'];

async function call<T>(method: string, path: string, token: string | null, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch('/api' + path, {
      method,
      headers: { ...(token ? { 'X-Ako': token } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      referrerPolicy: 'no-referrer',
    });
  } catch {
    throw new ApiErr('unavailable', 'network');
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null) as Record<string, unknown> | null;
  if (!r.ok) throw new ApiErr(code(data), (data?.message as string) || undefined, data ?? {});
  return data as T;
}

/** A page (photo or PDF) of a document, with its progress (0..1): a 10 MB scan on a phone's network takes a while. */
function upload(token: string, doc: AkoDoc, file: Blob, progress?: (done: number) => void): Promise<AkoFile> {
  return new Promise((ok, fail) => {
    const x = new XMLHttpRequest();
    x.open('POST', `/api/ako/a/files?doc=${doc}`);
    x.setRequestHeader('X-Ako', token);
    x.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    x.upload.onprogress = (e) => { if (e.lengthComputable) progress?.(e.loaded / e.total); };
    x.onload = () => {
      let data: Record<string, unknown> | null = null;
      try { data = JSON.parse(x.responseText); } catch { /* not JSON */ }
      if (x.status >= 200 && x.status < 300) ok(data as unknown as AkoFile);
      else fail(new ApiErr(code(data), (data?.message as string) || undefined, data ?? {}));
    };
    x.onerror = () => fail(new ApiErr('unavailable', 'network'));
    x.send(file);
  });
}

export const ako = {
  /** the website's start link: the org and its open programs; nothing is made */
  start: (slug: string): Promise<AkoStart> => call('GET', `/ako/o/${encodeURIComponent(slug)}`, null),
  /** the first real step from the start link: a draft with the program picked, and its secret (shown once, here) */
  begin: (slug: string, program: string, lang: string): Promise<{ token: string }> => call('POST', `/ako/o/${encodeURIComponent(slug)}`, null, { program, lang }),
  view: (token: string): Promise<AkoView> => call('GET', '/ako/a', token),
  /** program, name, phone, email, language; consent: true once the notice is agreed to (before any document) */
  patch: (token: string, x: Partial<{ program: string; name: string; phone: string; email: string; lang: string; consent: true }>): Promise<void> => call('PATCH', '/ako/a', token, x),
  upload,
  /** a page taken back (a blurry photo): replacing, never reading */
  dropFile: (token: string, id: Id): Promise<void> => call('DELETE', `/ako/a/files/${id}`, token),
  /** an interview time picked or moved; null gives it back (both closed inside the last hours: conflict 'closed') */
  book: (token: string, slot: Id | null): Promise<AkoView> => call('POST', '/ako/a/slot', token, { slot }),
  /** sent with what there is; bad_input 'ako_incomplete' names what is missing ({ missing }), 'ako_slot_needed' a time */
  submit: (token: string): Promise<AkoView> => call('POST', '/ako/a/submit', token),
  /** the interview as a calendar file (Teams link, alarms a day and an hour before) */
  ics: async (token: string): Promise<Blob> => {
    const r = await fetch('/api/ako/a/ics', { headers: { 'X-Ako': token }, referrerPolicy: 'no-referrer' });
    if (!r.ok) throw new ApiErr('not_found');
    return r.blob();
  },
};
