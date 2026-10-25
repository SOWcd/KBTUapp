// A club's link → which network it is, for the icon and the label on the club sheet.
export type SocialKind = 'instagram' | 'tiktok' | 'youtube' | 'telegram' | 'github' | 'web';

const KNOWN: [RegExp, SocialKind, string][] = [
  [/(^|\.)instagram\.com$/, 'instagram', 'Instagram'],
  [/(^|\.)tiktok\.com$/, 'tiktok', 'TikTok'],
  [/(^|\.)(youtube\.com|youtu\.be)$/, 'youtube', 'YouTube'],
  [/^(t\.me|telegram\.me)$/, 'telegram', 'Telegram'],
  [/(^|\.)github\.com$/, 'github', 'GitHub'],
];

export function social(url: string): { kind: SocialKind; label: string } {
  let host = '';
  try { host = new URL(url).hostname.replace(/^www\./, ''); } catch { /* not a URL: shown as a site */ }
  const hit = KNOWN.find(([re]) => re.test(host));
  return hit ? { kind: hit[1], label: hit[2] } : { kind: 'web', label: host || url };
}

/** The server's rule for a saved link. */
export const LINK = /^https:\/\/[A-Za-z0-9.-]+\.[a-z]{2,}(\/\S*)?$/;

// The club's editor: pick a network and type the username, or paste a
// whole link, https:// optional. Saved as full links, as before.
export const NETS = [
  { kind: 'telegram', label: 'Telegram', base: 't.me/' },
  { kind: 'instagram', label: 'Instagram', base: 'instagram.com/' },
  { kind: 'tiktok', label: 'TikTok', base: 'tiktok.com/@' },
  { kind: 'youtube', label: 'YouTube', base: 'youtube.com/@' },
] as const;
export type LinkDraft = { kind: (typeof NETS)[number]['kind'] | 'web'; v: string };

const HANDLE = /^@?([A-Za-z0-9_.-]{1,64})$/;
/** A username in a network's row (not a pasted address). */
export const isHandle = (d: LinkDraft) => d.kind !== 'web' && HANDLE.test(d.v.trim());

/** What the club typed → the link saved; null while it isn't one. */
export function linkUrl(d: LinkDraft): string | null {
  const v = d.v.trim();
  const net = NETS.find((n) => n.kind === d.kind);
  const h = net && HANDLE.exec(v);
  if (h) return `https://${net.base}${h[1]}`;
  const u = /^https?:\/\//i.test(v) ? v.replace(/^http:/i, 'https:') : `https://${v}`;
  return v && LINK.test(u) ? u : null;
}

/** A saved link → its row: a network's username when the link is just that, else the address without https://. */
export function linkDraft(url: string): LinkDraft {
  const net = NETS.find((n) => n.kind === social(url).kind);
  const m = net && /^https:\/\/[^/]+\/@?([A-Za-z0-9_.-]{1,64})\/?$/.exec(url);
  return m ? { kind: net.kind, v: m[1] } : { kind: 'web', v: url.replace(/^https:\/\//, '') };
}
