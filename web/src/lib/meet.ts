// An online event's meeting link (server core.online_url decides; this is the same rule again on the phone).

/** Telegram's own hosts open inside Telegram as deep links: never a meeting link */
const TG_HOST = /(^|\.)(t\.me|telegram\.me|telegram\.dog)$/i;

/** What the editor takes as typed: https, a plain host, never Telegram's own (any other host: shown on the page) */
export const ONLINE_LINK = /^https:\/\/(?!(?:[a-z0-9-]+\.)*(?:t\.me|telegram\.me|telegram\.dog)(?:[/?#]|$))(?:[a-z0-9-]+\.)+[a-z][a-z0-9-]*[a-z0-9](?:[/?#][\x21-\x7e]*)?$/i;

/** The host the event page shows under "Online", '' when the link may not be opened (then no tap) */
export function meetHost(url: string | null | undefined): string {
  if (!url) return '';
  try {
    const x = new URL(url);
    return x.protocol === 'https:' && !x.username && !x.password && !x.port && !TG_HOST.test(x.hostname) ? x.hostname : '';
  } catch { return ''; }
}

/** A link the fill found, against the form: 'fill' it in, 'ask' (a different link or a place already set, "Add more"
 *  lists it for a tap like any field the new text says otherwise), or 'keep' (the same one, or nothing found) */
export function linkFill(found: string | undefined, adding: boolean, f: { online: boolean; onlineUrl: string; place: string; tba: boolean }): 'fill' | 'ask' | 'keep' {
  if (!found) return 'keep';
  const had = f.online ? f.onlineUrl.trim() : f.tba ? '' : f.place.trim();
  if (!adding || !had) return 'fill';
  return f.online && had === found ? 'keep' : 'ask';
}
